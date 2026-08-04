"""Check that LaTeX math environments do not contain bare CJK text.

Short CJK labels inside ``\text{...}`` are allowed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


MATH_ENV_RE = re.compile(
    r"\$\$(.*?)\$\$|\$(.*?)\$|\\\((.*?)\\\)|\\\[(.*?)\\\]",
    re.S,
)
CJK_RE = re.compile(r"[\u4e00-\u9fff，。；：！？、（）《》“”‘’]")


def strip_text_commands(expr: str) -> str:
    """Remove contents of simple \text{...} commands before checking."""
    out: list[str] = []
    i = 0
    marker = r"\text{"
    while i < len(expr):
        if expr.startswith(marker, i):
            depth = 1
            i += len(marker)
            while i < len(expr) and depth:
                if expr[i] == "\\":
                    i += 2
                    continue
                if expr[i] == "{":
                    depth += 1
                elif expr[i] == "}":
                    depth -= 1
                i += 1
            out.append(r"\text{}")
        else:
            out.append(expr[i])
            i += 1
    return "".join(out)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_math_env_cjk.py <yaml-path>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    text = path.read_text(encoding="utf-8")
    hits: list[tuple[int, str]] = []

    for match in MATH_ENV_RE.finditer(text):
        expr = next(group for group in match.groups() if group is not None)
        checked_expr = strip_text_commands(expr)
        if CJK_RE.search(checked_expr):
            line = text[: match.start()].count("\n") + 1
            preview = expr.replace("\n", r"\n")[:120]
            hits.append((line, preview))

    for line, preview in hits:
        print(f"{path}:{line}: math env contains bare CJK text/punctuation: {preview}")

    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
