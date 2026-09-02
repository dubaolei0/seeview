#!/usr/bin/env python
"""Generate candidate reports and exe-ready handout input Markdown files.

v2: Supports multi-tier question sources (original / molecular / atomic / textbook)
    based on lesson_type and example_plan configuration.

Default mode is review-only: it writes a candidate report and does not create
handout input files. Add --generate after reviewing candidates.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure UTF-8 output on Windows console
sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
DEFAULT_TOPICS = SCRIPT_DIR / "topics_derivative.json"
DEFAULT_REPORT = SCRIPT_DIR / "候选题报告_导数.md"
DEFAULT_OUTPUT = ROOT / "自动生成讲义工作区" / "哈斯工作区" / "讲义生成工具" / "输入"
DEFAULT_TEXTBOOK_INDEX = ROOT / "knowledge" / "教材题目索引" / "选必第二册_导数题目索引.jsonl"

GLOBAL_EXCLUDE = [
    "正四棱锥",
    "棱锥",
    "球",
    "三棱锥",
    "四棱锥",
    "椭圆",
    "双曲线",
    "抛物线",
    "圆锥曲线",
    "空间向量",
    "立体几何",
]

SOURCE_TYPE_LABELS = {
    "original": "原题",
    "molecular": "分子题",
    "atomic": "原子题",
    "textbook": "教材题",
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    score: int
    record: dict[str, Any]
    reasons: list[str]
    source_type: str = "original"
    plan_source: str = "original"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_master_records(root: Path) -> list[dict[str, Any]]:
    return load_jsonl(root / "knowledge" / "高考题目" / "题库" / "master_database.jsonl")


def load_textbook_records(index_path: Path | None) -> list[dict[str, Any]]:
    """Load textbook question index. Returns empty list if file missing."""
    if index_path is None or not index_path.exists():
        return []
    return load_jsonl(index_path)


# ---------------------------------------------------------------------------
# Config normalization (v1 backward compatibility)
# ---------------------------------------------------------------------------


def normalize_topic_config(topic: dict[str, Any]) -> dict[str, Any]:
    """Normalize a topic config entry to v2 format while keeping v1 compatible."""
    result = dict(topic)

    # lesson_type: prefer explicit field, fall back to old 'type' field
    if "lesson_type" not in result:
        result["lesson_type"] = result.get("type", "考法分支课")

    # example_plan: if missing, synthesize from old example_count
    if "example_plan" not in result:
        count = int(result.get("example_count", 3))
        result["example_plan"] = [{"source": "original", "count": count}]

    return result


# ---------------------------------------------------------------------------
# Source type helpers
# ---------------------------------------------------------------------------


def record_source_type(record: dict[str, Any]) -> str:
    """Determine the source type of a database record."""
    # Textbook records carry a source_type field from the index
    st = record.get("source_type", "")
    if st in {"textbook_example", "textbook_exercise", "textbook"}:
        return "textbook"

    depth = record.get("depth_level")
    rtype = record.get("type", "")
    if depth == 0 or rtype == "original":
        return "original"
    if depth == 1 or rtype == "molecular":
        return "molecular"
    if depth == 2 or rtype == "atomic":
        return "atomic"
    return "original"


def matches_source_type(record: dict[str, Any], source_type: str) -> bool:
    return record_source_type(record) == source_type


# ---------------------------------------------------------------------------
# Text normalization and identifiers
# ---------------------------------------------------------------------------


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(normalize_text(v) for v in value)
    if isinstance(value, dict):
        return " ".join(normalize_text(v) for v in value.values())
    return str(value)


def record_text_for_matching(record: dict[str, Any]) -> str:
    """Extract all textual fields for keyword matching."""
    return normalize_text(
        [
            record.get("content"),
            record.get("analysis"),
            record.get("logic_chain"),
            record.get("knowledge_chapter"),
            record.get("knowledge_points"),
            record.get("solve_strategies"),
            record.get("source_file"),
            record.get("scaffold_purpose"),
        ]
    )


def question_identifier(record: dict[str, Any]) -> str:
    exam = str(record.get("source_exam", "")).replace("年", "")
    year = record.get("source_year", "")
    number = record.get("source_question_no", "")
    return f"{year}{exam}_第{number}题"


def source_label(record: dict[str, Any]) -> str:
    return f"{record.get('source_year')}年{record.get('source_exam')}第{record.get('source_question_no')}题"


def textbook_label(record: dict[str, Any]) -> str:
    """Label for textbook questions."""
    book = record.get("book", "")
    section = record.get("section", "")
    title = record.get("title", "")
    return f"{book} {section} {title}".strip()


def display_source_label(candidate: Candidate) -> str:
    """Format display label with source type prefix."""
    type_label = SOURCE_TYPE_LABELS.get(candidate.source_type, "")
    if candidate.source_type == "textbook":
        detail = textbook_label(candidate.record)
    else:
        detail = source_label(candidate.record)
    return f"{type_label}｜{detail}"


def source_key(record: dict[str, Any]) -> str:
    text = source_label(record)
    return normalize_source_key(text)


def normalize_source_key(text: str) -> str:
    replacements = {
        "年": "",
        "第": "",
        "题": "",
        "卷": "",
        "（": "",
        "）": "",
        "(": "",
        ")": "",
        "科": "",
        "Ⅰ": "I",
        "Ⅱ": "II",
        "Ⅲ": "III",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return re.sub(r"\s+", "", text)


def dedupe_key(record: dict[str, Any], source_type: str) -> str:
    """Generate deduplication key based on source type."""
    if source_type == "textbook":
        return record.get("id", "")
    if source_type in ("molecular", "atomic"):
        # Use record id to avoid removing different sub-questions of the same parent
        return record.get("id", "")
    # original: dedup by source
    return f"{record.get('source_year')}|{record.get('source_exam')}|{record.get('source_question_no')}"


def occupied_identifiers(root: Path) -> set[str]:
    path = root / "records" / "选题记录表.md"
    if not path.exists():
        return set()
    occupied: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if "|" not in line or "已放弃" in line or "完整题目标识" in line:
            continue
        for token in re.findall(r"`([^`]+)`", line):
            occupied.add(token)
    return occupied


# ---------------------------------------------------------------------------
# Scoring logic (v2: source-type aware)
# ---------------------------------------------------------------------------


def score_record(
    topic: dict[str, Any],
    record: dict[str, Any],
    occupied: set[str],
    source_type: str,
) -> Candidate | None:
    """Score a record for a given topic and source type. Returns None if filtered out."""

    # --- Hard filter: source type match ---
    if not matches_source_type(record, source_type):
        return None

    # --- Hard filter: occupied check (only for original questions) ---
    if source_type == "original":
        identifier = question_identifier(record)
        if identifier in occupied:
            return None

    # --- Hard filter: exclude keywords ---
    text = record_text_for_matching(record)
    for word in [*GLOBAL_EXCLUDE, *topic.get("exclude", [])]:
        if word and word in text:
            return None

    # --- Scoring ---
    score = 0
    reasons: list[str] = []

    # Common: knowledge chapter & points match
    chapter = normalize_text(record.get("knowledge_chapter"))
    points = normalize_text(record.get("knowledge_points"))
    if "导数" in chapter:
        score += 8
        reasons.append("knowledge_chapter 包含导数")
    if "导数" in points:
        score += 5
        reasons.append("knowledge_points 包含导数")

    # Common: include keywords
    for word in topic.get("include", []):
        if word and word in text:
            score += 3
            reasons.append(f"命中关键词：{word}")

    # --- Source-type specific scoring ---
    if source_type == "original":
        # Preferred sources (high weight for original questions)
        preferred_sources = [normalize_source_key(item) for item in topic.get("preferred_sources", [])]
        record_sk = source_key(record)
        if any(item and item in record_sk for item in preferred_sources):
            score += 18
            reasons.append("命中章节分析推荐题源")

        # Content length preference
        content_len = len(normalize_text(record.get("content")))
        if content_len <= 180:
            score += 2
            reasons.append("题干较短，适合微课例题")
        elif content_len > 500:
            score -= 3

        # Question format bonus
        if record.get("question_format") in {"single_choice", "fill_in_blank"}:
            score += 1
            reasons.append("小题题型，便于讲解")

    elif source_type == "molecular":
        # Molecular: emphasize knowledge_points precision and scaffold_purpose
        kp_list = record.get("knowledge_points") or []
        for word in topic.get("include", []):
            if word and any(word in kp for kp in kp_list):
                score += 4
                reasons.append(f"knowledge_points 精确命中：{word}")
                break  # Only count once for this bonus

        scaffold = normalize_text(record.get("scaffold_purpose"))
        for word in topic.get("include", []):
            if word and word in scaffold:
                score += 3
                reasons.append(f"scaffold_purpose 命中：{word}")
                break

        # Format bonus for molecular
        if record.get("question_format") in {"single_choice", "fill_in_blank", "short_answer"}:
            score += 2
            reasons.append("适合单考法微课的题型")

        # Cognitive action bonus
        if record.get("cognitive_action") in {"apply_direct", "apply_transform"}:
            score += 2
            reasons.append(f"认知动作适合考法课：{record.get('cognitive_action')}")

        # Preferred sources still help but with lower weight
        preferred_sources = [normalize_source_key(item) for item in topic.get("preferred_sources", [])]
        record_sk = source_key(record)
        if any(item and item in record_sk for item in preferred_sources):
            score += 8
            reasons.append("命中推荐题源（分子题）")

    elif source_type == "atomic":
        # Atomic: precise knowledge_points match is king
        kp_list = record.get("knowledge_points") or []
        for word in topic.get("include", []):
            if word and any(word in kp for kp in kp_list):
                score += 6
                reasons.append(f"knowledge_points 精确命中：{word}")
                break

        # Prefer recall/apply_direct cognitive actions
        if record.get("cognitive_action") in {"recall", "apply_direct"}:
            score += 3
            reasons.append(f"认知动作适合基础微课：{record.get('cognitive_action')}")

        # Prefer short content for atomic
        content_len = len(normalize_text(record.get("content")))
        if content_len <= 120:
            score += 3
            reasons.append("题干极短，适合原子微课")
        elif content_len <= 200:
            score += 1

        # Format bonus
        if record.get("question_format") in {"single_choice", "fill_in_blank"}:
            score += 2
            reasons.append("选填题型，适合原子微课")

    elif source_type == "textbook":
        # Textbook: precise matching via preferred_textbook_ids or section/knowledge_points
        preferred_tb_ids = topic.get("preferred_textbook_ids", [])
        if record.get("id") in preferred_tb_ids:
            score += 20
            reasons.append("命中指定教材题 ID")

        # Section match
        section = record.get("section", "")
        for word in topic.get("include", []):
            if word and word in section:
                score += 4
                reasons.append(f"教材章节命中：{word}")
                break

        # Knowledge points match
        kp_list = record.get("knowledge_points") or []
        for word in topic.get("include", []):
            if word and any(word in kp for kp in kp_list):
                score += 5
                reasons.append(f"教材知识点命中：{word}")
                break

        # Prefer textbook examples over exercises
        if record.get("source_type") == "textbook_example":
            score += 3
            reasons.append("教材例题，优先于练习")

    # --- Minimum threshold ---
    # Use lower threshold for molecular/atomic (they have fewer bonus channels)
    min_threshold = 10 if source_type == "original" else 6
    if source_type == "textbook":
        min_threshold = 5

    if score < min_threshold:
        return None

    return Candidate(
        score=score,
        record=record,
        reasons=reasons,
        source_type=source_type,
        plan_source=source_type,
    )


# ---------------------------------------------------------------------------
# Candidate finding (v2: per-source slot)
# ---------------------------------------------------------------------------


def find_candidates_for_source(
    topic: dict[str, Any],
    records: list[dict[str, Any]],
    occupied: set[str],
    source_type: str,
    needed_count: int,
) -> list[Candidate]:
    """Find top candidates for a single source type within a topic."""
    candidates: list[Candidate] = []
    seen_keys: set[str] = set()

    for record in records:
        scored = score_record(topic, record, occupied, source_type)
        if scored is None:
            continue
        dk = dedupe_key(record, source_type)
        if dk in seen_keys:
            continue
        seen_keys.add(dk)
        candidates.append(scored)

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[: max(10, needed_count * 3)]


def find_candidates(
    topics: list[dict[str, Any]],
    master_records: list[dict[str, Any]],
    textbook_records: list[dict[str, Any]],
    occupied: set[str],
) -> dict[str, dict[str, list[Candidate]]]:
    """Find candidates for all topics, organized by topic_id -> source_type -> candidates."""
    result: dict[str, dict[str, list[Candidate]]] = {}

    for topic in topics:
        topic_id = topic["id"]
        result[topic_id] = {}

        for plan_item in topic["example_plan"]:
            src = plan_item["source"]
            count = plan_item["count"]

            if src == "textbook":
                records_pool = textbook_records
            else:
                records_pool = master_records

            candidates = find_candidates_for_source(topic, records_pool, occupied, src, count)
            result[topic_id][src] = candidates

    return result


# ---------------------------------------------------------------------------
# Output: formatting
# ---------------------------------------------------------------------------


def format_options(record: dict[str, Any]) -> str:
    options = record.get("options")
    if not options:
        return ""
    labels = ["A", "B", "C", "D", "E"]
    lines = ["", "**选项：**"]
    for label, option in zip(labels, options):
        lines.append(f"{label}. {option}")
    return "\n".join(lines)


def render_question(candidate: Candidate, index: int) -> str:
    record = candidate.record
    label = display_source_label(candidate)
    return (
        f"**例 {index}**（{label}）\n"
        f"{record.get('content', '').strip()}\n"
        f"{format_options(record)}"
    ).rstrip()


def safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\\\|?*\\r\\n]+', "_", name).strip(" .")


# ---------------------------------------------------------------------------
# Output: candidate report
# ---------------------------------------------------------------------------


def write_report(
    topics: list[dict[str, Any]],
    candidates_by_topic: dict[str, dict[str, list[Candidate]]],
    report_path: Path,
    warnings: list[str],
) -> None:
    lines: list[str] = [
        "# 导数微课候选题报告（v2）",
        "",
        "> 仅供人工确认。确认后再运行 `--generate` 生成讲义工具输入 md。",
        "",
    ]

    # Warnings section
    if warnings:
        lines.append("## ⚠️ 警告")
        lines.append("")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    for topic in topics:
        topic_id = topic["id"]
        plan = topic["example_plan"]
        lesson_type = topic["lesson_type"]

        lines.extend(
            [
                f"## {topic['title']}（{topic_id}）",
                "",
                f"- 知识点标题：{topic['knowledge_title']}",
                f"- 微课类型：{lesson_type}",
                f"- 选题计划：{json.dumps(plan, ensure_ascii=False)}",
                "",
            ]
        )

        topic_candidates = candidates_by_topic.get(topic_id, {})

        for plan_item in plan:
            src = plan_item["source"]
            count = plan_item["count"]
            src_label = SOURCE_TYPE_LABELS.get(src, src)
            candidates = topic_candidates.get(src, [])

            lines.append(f"### 候选题源：{src_label}（计划取 {count} 题）")
            lines.append("")

            if not candidates:
                lines.append(f"> ⚠️ 候选不足：计划 {count} 题，当前找到 0 题")
                lines.append("")
                continue

            if len(candidates) < count:
                lines.append(f"> ⚠️ 候选不足：计划 {count} 题，当前仅找到 {len(candidates)} 题")
                lines.append("")

            lines.append("| 排名 | 分数 | 题源层级 | 题源 | 题型 | 匹配理由 | 题干预览 |")
            lines.append("|---:|---:|---|---|---|---|---|")

            for idx, candidate in enumerate(candidates, start=1):
                record = candidate.record
                preview = normalize_text(record.get("content")).replace("|", "\\|")
                if len(preview) > 90:
                    preview = preview[:90] + "..."
                reasons = "；".join(candidate.reasons[:4]).replace("|", "\\|")

                if src == "textbook":
                    src_info = textbook_label(record)
                else:
                    src_info = source_label(record)
                src_info = src_info.replace("|", "\\|")

                lines.append(
                    f"| {idx} | {candidate.score} | {src_label} | {src_info} | "
                    f"{record.get('question_format', '')} | {reasons} | {preview} |"
                )

            lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Output: exe-ready Markdown files
# ---------------------------------------------------------------------------


def generate_markdown_files(
    topics: list[dict[str, Any]],
    candidates_by_topic: dict[str, dict[str, list[Candidate]]],
    output_dir: Path,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for topic in topics:
        topic_id = topic["id"]
        plan = topic["example_plan"]
        topic_candidates = candidates_by_topic.get(topic_id, {})

        # Assemble examples in plan order
        selected: list[Candidate] = []
        for plan_item in plan:
            src = plan_item["source"]
            count = plan_item["count"]
            pool = topic_candidates.get(src, [])
            selected.extend(pool[:count])

        if not selected:
            continue

        lines = [
            f"# {topic['title']}",
            "",
            f"## {topic['knowledge_title']}：",
            "",
        ]
        for idx, candidate in enumerate(selected, start=1):
            lines.append(render_question(candidate, idx))
            lines.append("")

        path = output_dir / f"{safe_filename(topic['title'])}.md"
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        written.append(path)

    return written


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate micro-lesson handout input Markdown (v2).")
    parser.add_argument("--root", type=Path, default=ROOT, help="Project root path.")
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS, help="Topics JSON file.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Candidate report output path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT, help="Handout input md output dir.")
    parser.add_argument("--generate", action="store_true", help="Write exe-ready md files using top candidates.")
    parser.add_argument("--textbook-index", type=Path, default=None, help="Path to textbook question index jsonl.")
    parser.add_argument(
        "--strict-textbook",
        action="store_true",
        help="Exit with error if textbook index is needed but missing.",
    )
    args = parser.parse_args()

    root = args.root
    warnings: list[str] = []

    # Load and normalize topics
    raw_topics = json.loads(args.topics.read_text(encoding="utf-8"))
    topics = [normalize_topic_config(t) for t in raw_topics]

    # Load master database
    master_records = load_master_records(root)
    print(f"已加载题库记录：{len(master_records)} 条")

    # Determine textbook index path
    tb_index_path = args.textbook_index or DEFAULT_TEXTBOOK_INDEX

    # Check if any topic needs textbook source
    needs_textbook = any(
        any(p["source"] == "textbook" for p in t["example_plan"])
        for t in topics
    )

    # Load textbook records
    textbook_records: list[dict[str, Any]] = []
    if needs_textbook:
        if tb_index_path.exists():
            textbook_records = load_textbook_records(tb_index_path)
            print(f"已加载教材题索引：{len(textbook_records)} 条")
        else:
            msg = f"textbook 题源未启用：未找到 {tb_index_path}"
            warnings.append(msg)
            print(f"⚠️ {msg}")
            if args.strict_textbook:
                print("错误：--strict-textbook 模式下教材索引缺失，退出。")
                return 1

    # Load occupied identifiers
    occupied = occupied_identifiers(root)

    # Find candidates
    candidates = find_candidates(topics, master_records, textbook_records, occupied)

    # Write report
    write_report(topics, candidates, args.report, warnings)
    print(f"候选题报告已生成：{args.report}")

    if args.generate:
        written = generate_markdown_files(topics, candidates, args.output_dir)
        print(f"已生成 {len(written)} 个讲义输入 md：{args.output_dir}")
        for path in written:
            print(f"  {path}")
    else:
        print("当前为审题模式；确认候选题后再加 --generate 生成 md。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
