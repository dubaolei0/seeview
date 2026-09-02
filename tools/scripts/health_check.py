#!/usr/bin/env python
"""Generate a lightweight health report for the shared math workspace."""

from __future__ import annotations

import collections
import json
import re
import runpy
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _jsonl_count(path: Path) -> tuple[int, collections.Counter[str]]:
    total = 0
    counter: collections.Counter[str] = collections.Counter()
    if not path.exists():
        return total, counter
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            total += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                counter["parse_error"] += 1
                continue
            key = obj.get("type") or obj.get("status") or obj.get("question_type") or "unknown"
            counter[str(key)] += 1
    return total, counter


def _knowledge_network_stats(path: Path) -> dict[str, int | str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    books = data.get("books", [])
    chapters = 0
    sections = 0
    concepts = 0
    for book in books:
        book_chapters = book.get("chapters", [])
        chapters += len(book_chapters)
        for chapter in book_chapters:
            chapter_sections = chapter.get("sections", [])
            sections += len(chapter_sections)
            for section in chapter_sections:
                concepts += len(section.get("concepts", []))
    return {
        "books": len(books),
        "chapters": chapters,
        "sections": sections,
        "concepts": concepts,
        "description": data.get("description", ""),
    }


def _chapter_counter(paths: list[Path]) -> collections.Counter[str]:
    counter: collections.Counter[str] = collections.Counter()
    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                chapter = obj.get("knowledge_chapter") or obj.get("chapter")
                if chapter:
                    counter[str(chapter).strip()] += 1
    return counter


def _mcp_loaded_count() -> int | None:
    server = ROOT / "tools" / "mcp" / "math_questions_server.py"
    if not server.exists():
        return None
    try:
        ns = runpy.run_path(str(server), run_name="mcp_health_check")
        ns["_load_database"]()
        return len(ns["_questions"])
    except Exception:
        return None


def _skill_rows() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    skills_dir = ROOT / "skills"
    if not skills_dir.exists():
        return rows
    for item in sorted(skills_dir.iterdir(), key=lambda p: p.name):
        if not item.is_dir():
            continue
        has_upper = (item / "SKILL.md").exists()
        has_lower = (item / "skill.md").exists()
        if has_upper:
            status = "SKILL.md"
        elif has_lower:
            status = "skill.md"
        else:
            status = "missing"
        rows.append((item.name, status))
    return rows


def _expected_numbers_from_index(index_text: str) -> dict[str, int]:
    expected: dict[str, int] = {}
    for label, pattern in {
        "拆题份数": r"(\d+)\s*份结构化拆题",
        "master题量": r"master_database\.jsonl，(\d+)\s*条",
        "原题": r"原题(\d+)",
        "分子题": r"分子题(\d+)",
        "原子题": r"原子题(\d+)",
    }.items():
        match = re.search(pattern, index_text)
        if match:
            expected[label] = int(match.group(1))
    return expected


def build_report() -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: list[str] = [
        "# 知识库健康检查",
        "",
        f"> 自动生成时间：{now}",
        "",
    ]

    issues: list[str] = []

    network_path = ROOT / "knowledge" / "知识图谱" / "knowledge_network.json"
    network = _knowledge_network_stats(network_path)
    description = str(network["description"])
    if "71节" in description and network["sections"] == 72:
        issues.append("knowledge_network.json 的 description 写 71 节，实际统计为 72 节。")

    lines.extend(
        [
            "## 资产规模",
            "",
            f"- 知识图谱：{network['books']} 册、{network['chapters']} 章、{network['sections']} 节、{network['concepts']} 个概念标签",
        ]
    )

    split_dirs = [p for p in (ROOT / "knowledge" / "高考拆题").iterdir() if p.is_dir() and p.name != "assets"]
    split_docs = list((ROOT / "knowledge" / "高考拆题").rglob("*.md"))
    lines.append(f"- 高考拆题：{len(split_dirs)} 个试卷目录、{len(split_docs)} 份 Markdown")

    db_dir = ROOT / "knowledge" / "高考题目" / "题库"
    db_files = [
        "master_database.jsonl",
        "textbook_questions.jsonl",
        "contributions.jsonl",
        "patches.jsonl",
    ]
    lines.append("- 题库文件：")
    for name in db_files:
        total, counter = _jsonl_count(db_dir / name)
        detail = "，".join(f"{k}={v}" for k, v in sorted(counter.items())) or "空"
        lines.append(f"  - {name}：{total} 条（{detail}）")

    mcp_count = _mcp_loaded_count()
    if mcp_count is None:
        issues.append("MCP 健康检查未能加载题库服务。")
    else:
        lines.append(f"- MCP 实际加载题量：{mcp_count} 条")

    index_path = ROOT / "INDEX.md"
    if index_path.exists():
        index_text = index_path.read_text(encoding="utf-8")
        expected = _expected_numbers_from_index(index_text)
        if expected.get("拆题份数") and expected["拆题份数"] != len(split_docs):
            issues.append(f"INDEX.md 写高考拆题 {expected['拆题份数']} 份，实际 Markdown 为 {len(split_docs)} 份。")

    lines.extend(["", "## Skills", ""])
    for name, status in _skill_rows():
        marker = "OK" if status == "SKILL.md" else ("兼容" if status == "skill.md" else "缺入口")
        lines.append(f"- {name}：{marker}（{status}）")

    chapter_counter = _chapter_counter(
        [
            db_dir / "master_database.jsonl",
            db_dir / "textbook_questions.jsonl",
            db_dir / "contributions.jsonl",
        ]
    )
    singleton_count = sum(1 for _name, count in chapter_counter.items() if count == 1)
    lines.extend(
        [
            "",
            "## 标签治理观察",
            "",
            f"- 当前章节表述数：{len(chapter_counter)}",
            f"- 只出现 1 次的章节表述：{singleton_count}",
            "- 高频章节表述：",
        ]
    )
    for name, count in chapter_counter.most_common(12):
        lines.append(f"  - {name}：{count}")
    alias_file = ROOT / "knowledge" / "知识图谱" / "chapter_aliases.json"
    if singleton_count > 30 and alias_file.exists():
        issues.append("章节表述碎片化明显；chapter_aliases.json 已建立，建议继续扩充并在后续统计脚本中接入。")
    elif singleton_count > 30:
        issues.append("章节表述碎片化明显，建议维护 chapter_aliases.json 做标准章名映射。")

    lines.extend(["", "## 待处理提醒", ""])
    if issues:
        lines.extend(f"- {issue}" for issue in issues)
    else:
        lines.append("- 暂无明显结构性问题。")

    lines.extend(
        [
            "",
            "## 运行方式",
            "",
            "```powershell",
            "python tools/scripts/health_check.py",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else ROOT / "records" / "health-report.md"
    report = build_report()
    out.write_text(report, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
