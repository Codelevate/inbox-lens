#!/usr/bin/env python3
"""Install the Inbox Lens skill for Codex or Claude Code."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
SOURCE_SKILL = PACKAGE_DIR / "skill" / "inbox-lens"


def default_skills_dir(host: str) -> Path:
    if host == "claude":
        return Path.home() / ".claude" / "skills"
    return Path.home() / ".agents" / "skills"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the read-only Inbox Lens Zoho Mail skill.")
    parser.add_argument(
        "--host",
        choices=["codex", "claude"],
        required=True,
        help="AI coding tool that will use Inbox Lens: codex or claude",
    )
    parser.add_argument(
        "--skills-dir",
        type=Path,
        help="Override the normal skills directory for the chosen tool",
    )
    args = parser.parse_args()
    skills_dir = args.skills_dir or default_skills_dir(args.host)
    destination = skills_dir.expanduser().resolve() / "inbox-lens"

    if not (SOURCE_SKILL / "SKILL.md").is_file():
        print("Error: the package is incomplete (skill/inbox-lens/SKILL.md is missing).", file=sys.stderr)
        return 1
    if destination.exists():
        print(f"Inbox Lens is already installed at: {destination}")
        print("Keeping the existing installation to avoid overwriting its private credentials.")
        return 0

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE_SKILL, destination, ignore=shutil.ignore_patterns(".env", ".zoho_tokens.json", "__pycache__"))
    print(f"Installed Inbox Lens for {args.host} at: {destination}")
    print("Next, start the private browser setup page:")
    print(f"  python3 {destination / 'scripts' / 'setup_wizard.py'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
