#!/usr/bin/env python3
"""Read-only Zoho Mail helper for the Inbox Lens skill."""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import html
import json
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = SKILL_DIR / ".env"
DEFAULT_SCOPES = "ZohoMail.accounts.READ,ZohoMail.folders.READ,ZohoMail.messages.READ"
DEFAULT_ACCOUNTS_BASE = "https://accounts.zoho.com"
DEFAULT_MAIL_BASE = "https://mail.zoho.com/api"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SECRET_KEYS = {"access_token", "refresh_token", "client_secret"}


class ZohoError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.skip_depth += 1
        elif tag in {"br", "p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.skip_depth:
            self.skip_depth -= 1
        elif tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        raw = html.unescape("".join(self.parts))
        lines = []
        for line in raw.splitlines():
            collapsed = re.sub(r"[ \t\r\f\v]+", " ", line).strip()
            if collapsed:
                lines.append(collapsed)
        return "\n".join(lines).strip()


def parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def load_config(env_path: Path) -> dict[str, str]:
    config = parse_dotenv(env_path)
    for key in [
        "ZOHO_CLIENT_ID",
        "ZOHO_CLIENT_SECRET",
        "ZOHO_ACCOUNTS_BASE_URL",
        "ZOHO_MAIL_BASE_URL",
        "ZOHO_ACCOUNT_ID",
        "ZOHO_TOKEN_FILE",
    ]:
        if key in os.environ:
            config[key] = os.environ[key]
    config.setdefault("ZOHO_ACCOUNTS_BASE_URL", DEFAULT_ACCOUNTS_BASE)
    config.setdefault("ZOHO_MAIL_BASE_URL", DEFAULT_MAIL_BASE)
    config.setdefault("ZOHO_TOKEN_FILE", ".zoho_tokens.json")
    config["_ENV_PATH"] = str(env_path)
    return config


def normalize_base_url(raw: str, default: str, ensure_api: bool = False) -> str:
    value = (raw or default).strip().rstrip("/")
    if ensure_api and not urllib.parse.urlparse(value).path.rstrip("/").endswith("/api"):
        value = value + "/api"
    return value


def token_path(config: dict[str, str]) -> Path:
    raw = config.get("ZOHO_TOKEN_FILE") or ".zoho_tokens.json"
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = SKILL_DIR / path
    return path


def required_missing(config: dict[str, str], include_token: bool = False) -> list[str]:
    keys = ["ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_ACCOUNTS_BASE_URL", "ZOHO_MAIL_BASE_URL"]
    if include_token and not load_tokens(token_path(config), required=False).get("refresh_token"):
        keys.append("refresh_token in token file")
    return [key for key in keys if not config.get(key)]


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: ("<redacted>" if key in SECRET_KEYS else redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def safe_error_body(body: str) -> str:
    try:
        parsed = json.loads(body)
        return json.dumps(redact(parsed), ensure_ascii=False)
    except json.JSONDecodeError:
        redacted = re.sub(r"(access_token|refresh_token|client_secret)=([^&\\s]+)", r"\1=<redacted>", body)
        return redacted[:500]


def http_json(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    form: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    if params:
        query = urllib.parse.urlencode(params)
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{query}"
    data = None
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "inbox-lens/1.0",
    }
    if headers:
        request_headers.update(headers)
    if form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ZohoError(f"HTTP {exc.code}: {safe_error_body(body)}", status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise ZohoError(f"Network error: {exc.reason}") from exc
    if not text.strip():
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ZohoError(f"Expected JSON response from Zoho, got: {text[:300]}") from exc


def load_tokens(path: Path, *, required: bool = True) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise ZohoError(f"Token file not found: {path}. Run exchange-code first.")
        return {}
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            os.chmod(path, 0o600)
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ZohoError(f"Token file is not valid JSON: {path}") from exc


def save_tokens(path: Path, tokens: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(tokens, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, path)
    os.chmod(path, 0o600)


def token_endpoint(config: dict[str, str]) -> str:
    base = normalize_base_url(config.get("ZOHO_ACCOUNTS_BASE_URL", ""), DEFAULT_ACCOUNTS_BASE)
    return f"{base}/oauth/v2/token"


def token_request(config: dict[str, str], form: dict[str, Any]) -> dict[str, Any]:
    missing = required_missing(config)
    if missing:
        raise ZohoError("Missing required configuration: " + ", ".join(missing))
    response = http_json("POST", token_endpoint(config), form=form)
    if "error" in response:
        details = response.get("error_description") or response.get("error")
        raise ZohoError(f"Zoho token error: {details}")
    if "access_token" not in response:
        raise ZohoError("Zoho token response did not include an access token.")
    return response


def merge_token_response(existing: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    now = int(time.time())
    expires_in = int(response.get("expires_in") or 3600)
    merged = dict(existing)
    merged.update(
        {
            "access_token": response["access_token"],
            "api_domain": response.get("api_domain", existing.get("api_domain")),
            "token_type": response.get("token_type", existing.get("token_type", "Bearer")),
            "expires_in": expires_in,
            "expires_at": now + max(expires_in - 60, 60),
            "updated_at": now,
        }
    )
    if response.get("refresh_token"):
        merged["refresh_token"] = response["refresh_token"]
    if response.get("scope"):
        merged["scope"] = response["scope"]
    return merged


def exchange_code(config: dict[str, str], code: str) -> dict[str, Any]:
    form = {
        "client_id": config["ZOHO_CLIENT_ID"],
        "client_secret": config["ZOHO_CLIENT_SECRET"],
        "grant_type": "authorization_code",
        "code": code,
    }
    response = token_request(config, form)
    if "refresh_token" not in response:
        raise ZohoError("Zoho did not return a refresh token. Generate a Self Client authorization code, not a client-credentials token.")
    tokens = merge_token_response({}, response)
    save_tokens(token_path(config), tokens)
    return tokens


def refresh_access_token(config: dict[str, str]) -> dict[str, Any]:
    path = token_path(config)
    existing = load_tokens(path)
    refresh_token = existing.get("refresh_token")
    if not refresh_token:
        raise ZohoError(f"Token file has no refresh token: {path}. Run exchange-code again.")
    form = {
        "client_id": config["ZOHO_CLIENT_ID"],
        "client_secret": config["ZOHO_CLIENT_SECRET"],
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    response = token_request(config, form)
    tokens = merge_token_response(existing, response)
    save_tokens(path, tokens)
    return tokens


def access_token(config: dict[str, str]) -> str:
    tokens = load_tokens(token_path(config))
    if tokens.get("access_token") and int(tokens.get("expires_at") or 0) > int(time.time()):
        return str(tokens["access_token"])
    return str(refresh_access_token(config)["access_token"])


def mail_base(config: dict[str, str]) -> str:
    return normalize_base_url(config.get("ZOHO_MAIL_BASE_URL", ""), DEFAULT_MAIL_BASE, ensure_api=True)


def mail_get(config: dict[str, str], path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    def request_with_current_token() -> dict[str, Any]:
        return http_json(
            "GET",
            f"{mail_base(config)}{path}",
            params=params,
            headers={"Authorization": f"Zoho-oauthtoken {access_token(config)}"},
        )

    try:
        return request_with_current_token()
    except ZohoError as exc:
        if exc.status != 401:
            raise
    refresh_access_token(config)
    return request_with_current_token()


def extract_records(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data", response)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ["messages", "emails", "accounts", "folders", "results"]:
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [data]
    return []


def first_value(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return ""


def normalize_people(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(filter(None, [normalize_people(item) for item in value]))
    if isinstance(value, dict):
        name = first_value(value, "name", "displayName", "personal")
        address = first_value(value, "address", "email", "emailAddress", "mailId")
        if name and address:
            return f"{name} <{address}>"
        return str(name or address or "")
    return str(value or "")


def clean_body(content: str) -> str:
    if "<" not in content or ">" not in content:
        return html.unescape(content).strip()
    parser = HTMLTextExtractor()
    parser.feed(content)
    return parser.text()


def body_from_content_response(response: dict[str, Any]) -> str:
    data = response.get("data", response)
    if isinstance(data, dict):
        content = first_value(data, "content", "body", "messageContent")
        return clean_body(str(content or ""))
    return ""


def account_id(config: dict[str, str]) -> str:
    configured = config.get("ZOHO_ACCOUNT_ID", "").strip()
    if configured:
        return configured
    records = extract_records(mail_get(config, "/accounts"))
    ids = [str(first_value(record, "accountId", "accountID", "id")).strip() for record in records]
    ids = [item for item in ids if item]
    if len(ids) == 1:
        return ids[0]
    if not ids:
        raise ZohoError("No accountId found. Run accounts and set ZOHO_ACCOUNT_ID in .env.")
    raise ZohoError("Multiple accounts found. Run accounts and set ZOHO_ACCOUNT_ID in .env.")


def zoho_date(date_value: dt.date) -> str:
    return f"{date_value.day:02d}-{MONTHS[date_value.month - 1]}-{date_value.year}"


def search_value(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ZohoError("--from must not be empty")
    if re.search(r"\s|::|\"", stripped):
        escaped = stripped.replace('"', '\\"')
        return f'"{escaped}"'
    return stripped


def build_search_key(sender: str, days: int) -> str:
    if days < 1:
        raise ZohoError("--days must be at least 1")
    from_date = dt.date.today() - dt.timedelta(days=days)
    return f"sender:{search_value(sender)}::fromDate:{zoho_date(from_date)}"


def message_ids(message: dict[str, Any]) -> tuple[str, str]:
    folder_id = str(first_value(message, "folderId", "folderID", "fid", "folder_id")).strip()
    message_id = str(first_value(message, "messageId", "messageID", "id", "message_id")).strip()
    return folder_id, message_id


def read_message(config: dict[str, str], folder_id: str, message_id: str) -> dict[str, Any]:
    acct = account_id(config)
    response = mail_get(config, f"/accounts/{acct}/folders/{folder_id}/messages/{message_id}/content")
    return {
        "accountId": acct,
        "folderId": folder_id,
        "messageId": message_id,
        "body_text": body_from_content_response(response),
    }


def search_messages(config: dict[str, str], sender: str, days: int, limit: int) -> dict[str, Any]:
    acct = account_id(config)
    search_key = build_search_key(sender, days)
    response = mail_get(
        config,
        f"/accounts/{acct}/messages/search",
        params={"searchKey": search_key, "start": 1, "limit": limit, "includeto": "true"},
    )
    messages = extract_records(response)
    results = []
    for message in messages:
        folder_id, message_id = message_ids(message)
        item = {
            "accountId": acct,
            "folderId": folder_id,
            "messageId": message_id,
            "subject": first_value(message, "subject", "summary"),
            "from": normalize_people(first_value(message, "fromAddress", "sender", "from")),
            "to": normalize_people(first_value(message, "toAddress", "to")),
            "date": first_value(message, "receivedTime", "sentDateInGMT", "receivedDate", "date"),
            "body_text": "",
        }
        if folder_id and message_id:
            try:
                item["body_text"] = read_message(config, folder_id, message_id)["body_text"]
            except ZohoError as exc:
                item["body_error"] = str(exc)
        else:
            item["body_error"] = "Search result did not include folderId and messageId."
        results.append(item)
    return {"accountId": acct, "searchKey": search_key, "count": len(results), "messages": results}


def markdown_messages(payload: dict[str, Any], title: str) -> str:
    lines = [f"# {title}", ""]
    if payload.get("searchKey"):
        lines.extend([f"Search key: `{payload['searchKey']}`", ""])
    messages = payload.get("messages")
    if not isinstance(messages, list):
        messages = [payload]
    if not messages:
        lines.append("No messages found.")
        return "\n".join(lines)
    for index, message in enumerate(messages, start=1):
        subject = message.get("subject") or "(no subject)"
        lines.extend([f"## {index}. {subject}", ""])
        for label, key in [
            ("From", "from"),
            ("To", "to"),
            ("Date", "date"),
            ("Account ID", "accountId"),
            ("Folder ID", "folderId"),
            ("Message ID", "messageId"),
        ]:
            value = message.get(key)
            if value:
                lines.append(f"{label}: {value}")
        if message.get("body_error"):
            lines.extend(["", f"Body error: {message['body_error']}"])
        else:
            body = message.get("body_text") or ""
            lines.extend(["", "Body:", "", body if body else "(empty body)"])
        lines.append("")
    return "\n".join(lines).rstrip()


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def command_check_config(args: argparse.Namespace) -> int:
    config = load_config(Path(args.env).expanduser())
    path = token_path(config)
    missing = required_missing(config)
    token_info = load_tokens(path, required=False)
    print("Zoho Mail configuration")
    print(f"Env file: {config['_ENV_PATH']} ({'found' if Path(config['_ENV_PATH']).exists() else 'missing'})")
    print(f"Accounts base URL: {normalize_base_url(config.get('ZOHO_ACCOUNTS_BASE_URL', ''), DEFAULT_ACCOUNTS_BASE)}")
    print(f"Mail base URL: {mail_base(config)}")
    print(f"Account ID: {'set' if config.get('ZOHO_ACCOUNT_ID') else 'not set'}")
    print(f"Client ID: {'set' if config.get('ZOHO_CLIENT_ID') else 'missing'}")
    print(f"Client secret: {'set' if config.get('ZOHO_CLIENT_SECRET') else 'missing'}")
    print(f"Token file: {path} ({'found' if path.exists() else 'missing'})")
    print(f"Refresh token: {'set' if token_info.get('refresh_token') else 'missing'}")
    print(f"Required scopes: {DEFAULT_SCOPES}")
    if missing:
        print("Missing required configuration: " + ", ".join(missing), file=sys.stderr)
        return 1
    return 0


def command_exchange_code(args: argparse.Namespace) -> int:
    config = load_config(Path(args.env).expanduser())
    code = args.code
    if not code:
        if not sys.stdin.isatty() or not sys.stderr.isatty():
            raise ZohoError(
                "For your security, run exchange-code in an interactive local terminal. "
                "It will not accept an authorization code from redirected input."
            )
        code = getpass.getpass("Paste the fresh Zoho authorization code here (hidden): ").strip()
    if not code:
        raise ZohoError("Authorization code must not be empty.")
    exchange_code(config, code)
    print(f"Stored Zoho OAuth tokens in {token_path(config)}")
    print("Refresh token: stored")
    print("Access token: stored")
    return 0


def command_refresh(args: argparse.Namespace) -> int:
    config = load_config(Path(args.env).expanduser())
    refresh_access_token(config)
    print(f"Refreshed Zoho access token in {token_path(config)}")
    return 0


def command_accounts(args: argparse.Namespace) -> int:
    config = load_config(Path(args.env).expanduser())
    payload = mail_get(config, "/accounts")
    records = extract_records(payload)
    if args.format == "json":
        print_json({"accounts": records})
        return 0
    if not records:
        print("No accounts found.")
        return 0
    print("# Zoho Mail Accounts\n")
    for record in records:
        acct = first_value(record, "accountId", "accountID", "id")
        email = first_value(record, "primaryEmailAddress", "emailAddress", "email")
        name = first_value(record, "displayName", "accountName", "name")
        print(f"- accountId: {acct} | email: {email or '-'} | name: {name or '-'}")
    return 0


def command_search(args: argparse.Namespace) -> int:
    search_key = build_search_key(args.sender, args.days)
    if args.dry_run:
        config = load_config(Path(args.env).expanduser())
        acct = config.get("ZOHO_ACCOUNT_ID") or "<accountId>"
        url = f"{mail_base(config)}/accounts/{acct}/messages/search"
        params = {"searchKey": search_key, "start": 1, "limit": args.limit, "includeto": "true"}
        print("Dry run only; no credentials or network used.")
        print(f"Search key: {search_key}")
        print(f"Request URL: {url}?{urllib.parse.urlencode(params)}")
        return 0
    config = load_config(Path(args.env).expanduser())
    payload = search_messages(config, args.sender, args.days, args.limit)
    if args.format == "json":
        print_json(payload)
    else:
        print(markdown_messages(payload, "Zoho Mail Search Results"))
    return 0


def command_read(args: argparse.Namespace) -> int:
    config = load_config(Path(args.env).expanduser())
    payload = read_message(config, args.folder_id, args.message_id)
    if args.format == "json":
        print_json(payload)
    else:
        print(markdown_messages(payload, "Zoho Mail Message"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Zoho Mail CLI for Codex.")
    parser.add_argument("--env", default=str(DEFAULT_ENV_PATH), help="Path to .env file. Defaults to the skill-local .env.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check-config", help="Validate local configuration without printing secrets.")
    check.set_defaults(func=command_check_config)

    exchange = subparsers.add_parser("exchange-code", help="Privately prompt for and exchange a Zoho Self Client authorization code.")
    exchange.add_argument("--code", help="Authorization code; avoid this option because command-line history can expose it.")
    exchange.set_defaults(func=command_exchange_code)

    refresh = subparsers.add_parser("refresh", help="Refresh the stored access token.")
    refresh.set_defaults(func=command_refresh)

    accounts = subparsers.add_parser("accounts", help="List Zoho Mail accounts for the authenticated user.")
    accounts.add_argument("--format", choices=["markdown", "json"], default="markdown")
    accounts.set_defaults(func=command_accounts)

    search = subparsers.add_parser("search", help="Search messages by sender and recent date range, then fetch body text.")
    search.add_argument("--from", dest="sender", required=True, help="Sender name, username, domain, or email address.")
    search.add_argument("--days", type=int, required=True, help="Search messages from this many days ago through today.")
    search.add_argument("--limit", type=int, default=10, help="Maximum messages to return, 1-200.")
    search.add_argument("--format", choices=["markdown", "json"], default="markdown")
    search.add_argument("--dry-run", action="store_true", help="Print generated search request without credentials or network.")
    search.set_defaults(func=command_search)

    read = subparsers.add_parser("read", help="Read a single message body by folder ID and message ID.")
    read.add_argument("--folder-id", required=True)
    read.add_argument("--message-id", required=True)
    read.add_argument("--format", choices=["markdown", "json"], default="markdown")
    read.set_defaults(func=command_read)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "limit", 1) < 1 or getattr(args, "limit", 1) > 200:
        parser.error("--limit must be between 1 and 200")
    try:
        return int(args.func(args))
    except ZohoError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
