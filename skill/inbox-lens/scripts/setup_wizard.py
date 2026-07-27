#!/usr/bin/env python3
"""Run a local-only browser setup page for the Inbox Lens skill."""

from __future__ import annotations

import html
import os
import stat
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from zoho_mail import ZohoError, exchange_code, load_config


SKILL_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = SKILL_DIR / ".env"
REGIONS = {
    "US": ("United States", "https://accounts.zoho.com", "https://mail.zoho.com/api"),
    "EU": ("Europe", "https://accounts.zoho.eu", "https://mail.zoho.eu/api"),
    "IN": ("India", "https://accounts.zoho.in", "https://mail.zoho.in/api"),
    "AU": ("Australia", "https://accounts.zoho.com.au", "https://mail.zoho.com.au/api"),
    "JP": ("Japan", "https://accounts.zoho.jp", "https://mail.zoho.jp/api"),
    "CA": ("Canada", "https://accounts.zohocloud.ca", "https://mail.zohocloud.ca/api"),
    "CN": ("China", "https://accounts.zoho.com.cn", "https://mail.zoho.com.cn/api"),
    "AE": ("United Arab Emirates", "https://accounts.zoho.ae", "https://mail.zoho.ae/api"),
    "SA": ("Saudi Arabia", "https://accounts.zoho.sa", "https://mail.zoho.sa/api"),
}


def quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def save_env(client_id: str, client_secret: str, region: str) -> None:
    _, accounts_url, mail_url = REGIONS[region]
    ENV_PATH.write_text(
        "\n".join(
            [
                "# Created locally by Inbox Lens. Keep this file private.",
                f"ZOHO_CLIENT_ID={quoted(client_id)}",
                f"ZOHO_CLIENT_SECRET={quoted(client_secret)}",
                f"ZOHO_ACCOUNTS_BASE_URL={accounts_url}",
                f"ZOHO_MAIL_BASE_URL={mail_url}",
                "ZOHO_ACCOUNT_ID=",
                "ZOHO_TOKEN_FILE=.zoho_tokens.json",
                "",
            ]
        ),
        encoding="utf-8",
    )
    try:
        os.chmod(ENV_PATH, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def page(message: str = "") -> str:
    options = "".join(f'<option value="{code}">{name}</option>' for code, (name, _, _) in REGIONS.items())
    notice = f'<p class="notice">{html.escape(message)}</p>' if message else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Connect Inbox Lens</title>
<style>body{{font:17px/1.5 system-ui,sans-serif;max-width:700px;margin:42px auto;padding:0 20px;color:#18212b}}h1{{font-size:32px}}h2{{font-size:22px;margin:0 0 8px}}.card{{background:#f5f7f9;border-radius:14px;padding:24px;margin:20px 0}}label{{display:block;font-weight:650;margin-top:16px}}input,select{{box-sizing:border-box;width:100%;font:inherit;padding:10px;margin-top:5px;border:1px solid #aeb8c2;border-radius:7px}}button{{background:#0b6e4f;color:white;border:0;border-radius:8px;padding:12px 18px;font:inherit;font-weight:650;margin-top:22px}}.notice{{background:#fff3cd;padding:12px;border-radius:8px}}.small{{font-size:14px;color:#53606d}}code{{font-size:14px;overflow-wrap:anywhere}}</style></head>
<body><h1>Connect Inbox Lens to Zoho Mail</h1>
<p>Inbox Lens can read and summarize your email. It cannot send, delete, move, or change messages.</p>{notice}
<div class="card"><h2>1. Create a private Zoho connection</h2>
<ol><li>Open the <a href="https://api-console.zoho.com/" target="_blank" rel="noreferrer">Zoho API Console</a> and sign in to the same mailbox you want to use.</li>
<li>Select <strong>ADD CLIENT</strong> (or <strong>GET STARTED</strong>), choose <strong>Self Client</strong>, and create it. You do not need to enter a website or redirect address.</li>
<li>Open its <strong>Client Secret</strong> tab to find your Client ID and Client Secret.</li>
<li>Open <strong>Generate Code</strong>. Paste only the permissions below, create the code, and return here straight away. The code expires quickly.</li></ol>
<p><code>ZohoMail.accounts.READ,ZohoMail.folders.READ,ZohoMail.messages.READ</code></p>
<p class="small">Using a work or team mailbox? If Zoho does not let you create a client or use mail APIs, ask your Zoho administrator to allow these three read-only permissions.</p></div>
<div class="card"><h2>2. Enter the details privately here</h2>
<p class="small">These values go directly from this page to Inbox Lens on this computer. Do not paste them into your AI chat, a document, or a screenshot.</p>
<form method="post"><label>Your Zoho region <span class="small">(match the country domain in your Zoho Mail address)</span><select name="region">{options}</select></label>
<label>Client ID<input name="client_id" autocomplete="off" required></label>
<label>Client Secret<input type="password" name="client_secret" autocomplete="new-password" required></label>
<label>Fresh authorization code<input type="password" name="code" autocomplete="off" required></label>
<button>Connect my mailbox</button></form></div>
<p class="small">When this succeeds, close this page and return to your AI agent.</p></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return  # Never log form fields or URLs.

    def respond(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        self.respond(page())

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 20_000:
                raise ValueError("Please try again.")
            values = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
            region = values.get("region", [""])[0]
            client_id = values.get("client_id", [""])[0].strip()
            client_secret = values.get("client_secret", [""])[0].strip()
            code = values.get("code", [""])[0].strip()
            if region not in REGIONS or not client_id or not client_secret or not code:
                raise ValueError("Please complete every field.")
            save_env(client_id, client_secret, region)
            exchange_code(load_config(ENV_PATH), code)
        except (ValueError, ZohoError) as exc:
            self.respond(page(str(exc)))
            return
        self.respond("""<!doctype html><meta charset=\"utf-8\"><title>Inbox Lens connected</title>
<body style=\"font:18px/1.5 system-ui,sans-serif;max-width:620px;margin:50px auto;padding:0 20px\"><h1>✓ Inbox Lens is connected</h1><p>Your private connection was saved on this computer. Close this page and return to your AI agent.</p><p>Try: <em>“Use Inbox Lens to summarize my most recent email from [name].”</em></p></body>""")
        threading.Thread(target=self.server.shutdown, daemon=True).start()


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Open this private Inbox Lens setup page: {url}", flush=True)
    webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
