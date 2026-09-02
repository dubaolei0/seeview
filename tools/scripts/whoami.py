#!/usr/bin/env python
"""Cross-platform user identity lookup for the shared math workspace.

Usage:
    python tools/scripts/whoami.py <project_root>

Output matches whoami.sh:
    <name>
    UNKNOWN|<ip>
    UNKNOWN
"""

from __future__ import annotations

import ipaddress
import re
import socket
import subprocess
import sys
from pathlib import Path


def _read_mapping(mapping_file: Path) -> list[dict[str, str]]:
    if not mapping_file.exists():
        return []

    rows: list[dict[str, str]] = []
    for raw in mapping_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|") or "---" in line or "IP 地址" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        rows.append(
            {
                "ip": cells[0],
                "host": cells[1],
                "name": cells[2],
                "first_used": cells[3],
                "note": cells[4] if len(cells) > 4 else "",
            }
        )
    return rows


def _ipconfig_addresses() -> list[str]:
    try:
        result = subprocess.run(
            ["ipconfig"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=3,
        )
    except Exception:
        return []

    addresses: list[str] = []
    for match in re.finditer(r"(?:IPv4[^\r\n:]*|IPv4 Address[^\r\n:]*):\s*([0-9.]+)", result.stdout):
        addresses.append(match.group(1))
    return addresses


def _socket_addresses() -> list[str]:
    addresses: list[str] = []
    try:
        _host, _aliases, resolved = socket.gethostbyname_ex(socket.gethostname())
        addresses.extend(resolved)
    except Exception:
        pass
    return addresses


def _usable_ipv4(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if ip.version != 4 or ip.is_loopback or ip.is_link_local:
        return False
    return True


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _candidate_ips() -> list[str]:
    addresses = _dedupe(_ipconfig_addresses() + _socket_addresses())
    usable = [addr for addr in addresses if _usable_ipv4(addr)]

    def priority(addr: str) -> tuple[int, str]:
        if addr.startswith("192.168."):
            return (0, addr)
        if addr.startswith("10.") or addr.startswith("172."):
            return (1, addr)
        if addr.startswith("100."):
            return (2, addr)
        if addr.startswith("198.18."):
            return (3, addr)
        return (4, addr)

    return sorted(usable, key=priority)


def main(argv: list[str]) -> int:
    base_dir = Path(argv[1]) if len(argv) > 1 else Path(".")
    mapping_file = base_dir / "records" / "ip-mapping.md"
    rows = _read_mapping(mapping_file)
    hostname = socket.gethostname()
    ips = _candidate_ips()

    for ip in ips:
        for row in rows:
            if row["ip"] == ip and row["name"]:
                print(row["name"])
                return 0

    names_by_host = {
        row["name"]
        for row in rows
        if row["name"]
        and row["host"]
        and row["host"] != "(待补充)"
        and row["host"].lower() == hostname.lower()
    }
    if len(names_by_host) == 1:
        print(next(iter(names_by_host)))
        return 0

    if ips:
        print(f"UNKNOWN|{ips[0]}")
        return 1

    print("UNKNOWN")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
