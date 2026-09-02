#!/usr/bin/env python
"""Append one usage line to records/log.md.

Usage:
    python tools/scripts/record_log.py <project_root> <name> <what>
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print("Usage: python tools/scripts/record_log.py <project_root> <name> <what>", file=sys.stderr)
        return 2

    base_dir = Path(argv[1])
    name = argv[2].strip()
    what = argv[3].strip()
    if not name or not what:
        print("Name and work summary cannot be empty.", file=sys.stderr)
        return 2

    log_file = base_dir / "records" / "log.md"
    line = f"{date.today().isoformat()} | {name} | {what}"
    existing = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
    if line not in existing.splitlines():
        if existing and not existing.endswith("\n"):
            existing += "\n"
        log_file.write_text(existing + line + "\n", encoding="utf-8")
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
