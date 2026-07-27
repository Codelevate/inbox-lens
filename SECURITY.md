# Security and privacy

Inbox Lens is designed for read-only access to one Zoho Mail account that you choose.

## What it stores

After you connect Zoho Mail, Inbox Lens stores two private files inside its own installed skill folder:

- `.env` contains the Zoho Client ID, Client Secret, and regional Zoho addresses.
- `.zoho_tokens.json` contains the OAuth refresh token used to keep the connection active.

Both files are excluded from Git and are set to owner-only permissions where the operating system supports it.

Never paste their contents into an AI chat, issue, screenshot, or shared document.

## What it sends over the network

Inbox Lens communicates only with Zoho’s OAuth and Mail API endpoints for the region you select. Its setup page runs only on your own computer at `127.0.0.1`.

Inbox Lens does not include telemetry, analytics, an MCP server, hooks, a browser extension, or a remote backend.

## Reporting a security issue

Do not post secrets or a live exploit publicly. Use GitHub’s private security reporting option for this repository when available. Otherwise, open a minimal issue that contains no credentials and asks for a private contact channel.

## Disconnecting

Revoke the Inbox Lens client in Zoho’s API Console, then delete `.env` and `.zoho_tokens.json` from the installed Inbox Lens folder.
