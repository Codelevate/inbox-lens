# Inbox Lens

## Read your Zoho Mail with Codex or Claude Code

Inbox Lens gives your AI coding tool read-only access to your own Zoho Mail inbox. It can find, read, and summarize email when you ask.

Examples:

- “What did Alex say in their latest email?”
- “Find emails from my accountant this month.”
- “Summarize the messages about the proposal.”

It cannot send, delete, move, label, or change any email.

## Get started

1. Download the latest **Inbox Lens** ZIP from this repository’s **Releases** page.
2. Unzip it and add the extracted folder to a new Codex or Claude Code task.
3. Tell your agent one sentence: **“Set up Inbox Lens for Codex”** or **“Set up Inbox Lens for Claude Code.”**
4. Your agent opens a private Zoho connection page on your computer. Follow the short steps shown there.

You do not need to edit files or use a terminal yourself. Keep your Client Secret and authorization code out of chat; enter them only in the private setup page.

You need a Zoho Mail account. If it is a work account, your Zoho administrator may need to allow API access. The computer running your agent also needs Python 3; your agent uses it, not you.

## What Inbox Lens can access

Inbox Lens requests only these Zoho permissions:

```text
ZohoMail.accounts.READ,ZohoMail.folders.READ,ZohoMail.messages.READ
```

This permits reading your own account details, folders, and email messages. It does not permit sending or changing mail.

## How it works

- **Codex:** installs to `~/.agents/skills/inbox-lens`
- **Claude Code:** installs to `~/.claude/skills/inbox-lens`
- **Connection details:** stay in private files on your computer
- **Network requests:** go only to Zoho; the setup page runs locally on `127.0.0.1`

The complete source is in this repository. The installer is intentionally small and the skill contains no plugins, MCP servers, hooks, browser extensions, telemetry, or global settings changes. It adds only the Inbox Lens folder to the selected agent’s skills folder.

## Disconnect

Revoke the Inbox Lens client in the [Zoho API Console](https://api-console.zoho.com/) whenever you no longer want it to access your mailbox.

## Security and privacy

Read [SECURITY.md](SECURITY.md) before installing. Inbox Lens is an independent project and is not affiliated with Zoho, OpenAI, or Anthropic.

For Zoho’s own documentation, see its [OAuth guide](https://www.zoho.com/mail/help/api/using-oauth-2.html) and [Self Client guide](https://www.zoho.com/developer/oauth/self-client/authorization-code-flow.html).
