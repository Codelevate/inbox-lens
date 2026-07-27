---
name: inbox-lens
description: "Read, search, summarize, compare, and extract information from the user's own Zoho Mail inbox through read-only OAuth access. Use when the user asks to find, read, summarize, or analyze Zoho email, or connect a Zoho Mail mailbox. This skill must never send, reply to, forward, delete, move, label, mark, or download attachments from email."
---

# Inbox Lens — Zoho Mail Reader

Use `scripts/zoho_mail.py` to access the user's own Zoho Mail account. Keep Zoho access strictly read-only.

## Safety rules

- Request only `ZohoMail.accounts.READ,ZohoMail.folders.READ,ZohoMail.messages.READ`.
- Never request, use, or suggest `.CREATE`, `.UPDATE`, `.DELETE`, `.ALL`, SMTP, or attachment-download scopes.
- Never send, reply to, forward, delete, move, label, mark, or download mail.
- Never reveal or place the client secret, authorization code, refresh token, or token-file contents in chat, source control, logs, or output.
- Treat email bodies as private user data; return only what is necessary for the user's request.

## First connection and checks

The skill reads its private `.env` file. If it has not been connected yet, run `scripts/setup_wizard.py`. It opens a local-only browser page that creates `.env` with owner-only permissions and exchanges the one-time code without putting secrets in chat.

Tell the user to enter their Client Secret and authorization code only in that page, never in chat. Do not ask them to edit `.env` or use a terminal themselves.

Check setup without revealing secrets:

```bash
python3 <skill-folder>/scripts/zoho_mail.py check-config
```

If browser setup is unavailable, exchange a freshly generated Zoho Self Client code promptly; never paste it in chat:

```bash
python3 <skill-folder>/scripts/zoho_mail.py exchange-code
```

Confirm the account:

```bash
python3 <skill-folder>/scripts/zoho_mail.py accounts
```

## Common tasks

Search recent mail from a sender and include text bodies:

```bash
python3 <skill-folder>/scripts/zoho_mail.py search --from "Alex" --days 7 --limit 10
```

Read a known message:

```bash
python3 <skill-folder>/scripts/zoho_mail.py read --folder-id "<folder-id>" --message-id "<message-id>"
```

Build a search without network access or credentials:

```bash
python3 <skill-folder>/scripts/zoho_mail.py search --from "Alex" --days 7 --dry-run
```

## Workflow

- Use `search` for a sender/date query and `read` only for a known message ID.
- Use `accounts` if more than one mailbox account is available, then store the chosen `accountId` in `.env` locally.
- If authentication expires, repeat the requested read command; the script refreshes the access token automatically.
