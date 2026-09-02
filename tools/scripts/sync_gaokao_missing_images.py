"""Restore high-confidence missing image links from source split-question Markdown.

This script consumes records/gaokao-image-sync/gaokao-image-link-audit.jsonl,
which compares the original "按人分" Markdown tree with knowledge/高考拆题. It
only auto-inserts images that are missing from the structured Markdown and whose
source position is classified as the original question block. Other missing
images are reported for manual review because their correct target position may
be inside analysis or a sub-question.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path


FOCUS_CATEGORIES = {
    "TARGET_MISSING_REFS",
    "SOURCE_MORE_REFS_WITH_FILE_URL",
    "BROKEN_TARGET_REF",
}

IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}


@dataclass
class MissingImage:
    key: str
    category: str
    target_md: str
    source_md: str
    asset: str
    asset_rel: str
    raw: str
    source_line: int
    source_context: str
    action: str
    note: str
    replace_raw: str | None = None


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def ref_identity(ref: dict) -> str:
    return ref.get("matched_asset") or ref.get("normalized") or ref.get("raw") or ""


def target_ref_identities(item: dict) -> set[str]:
    return {ref_identity(ref).lower() for ref in item.get("target_refs") or []}


def source_ref_line(lines: list[str], ref: dict) -> int:
    candidates = [
        str(ref.get("raw") or "").split("|", 1)[0],
        str(ref.get("normalized") or "").split("|", 1)[0],
        str(ref.get("filename") or ""),
    ]
    candidates = [c for c in candidates if c]
    for idx, line in enumerate(lines):
        if any(c in line for c in candidates):
            return idx
    return -1


def classify_source_context(lines: list[str], idx: int) -> tuple[str, str]:
    if idx < 0:
        return "unknown", "未在源文档中定位到图片行"

    before = "\n".join(lines[max(0, idx - 30) : idx + 1])
    window = lines[max(0, idx - 30) : idx + 1]
    headings = [line.strip() for line in window if re.match(r"^\s*#{1,5}\s+", line)]
    bold_labels = [line.strip() for line in window if re.match(r"^\s*\*\*.*[：:】]", line)]
    nearest = headings[-1] if headings else ""

    sub_re = re.compile(r"分子题|原子题|第一题|第二题|第三题|第四题|第五题|第[一二三四五六七八九十]+关|题目\s*[一二三四五六七八九十\d]", re.I)
    analysis_re = re.compile(r"教研|解题|解析|最优|常规|秒杀|总结|方法|逻辑|Step\s*\d|步骤|快速|找点|手绘", re.I)
    original_heading_re = re.compile(r"原题|题目呈现|题目再现|原题呈现|原题再现|高考原题|原题文字版", re.I)
    question_line_re = re.compile(r"^\s*(?:\*\*)?\(?\d+\)?[．.、]|如图|已知|设|函数|在.*中", re.I)

    # A nearby explicit original-question heading is the strongest signal.
    if nearest and original_heading_re.search(nearest):
        return "original", f"最近标题/字段：{nearest}"

    # Some source files start directly with the stem and figure before any
    # heading. Treat only the very beginning as original, and only if no
    # analysis/sub-question marker has appeared.
    before_text = "\n".join(lines[: idx + 1])
    if idx < 18 and not analysis_re.search(before_text) and not sub_re.search(before_text):
        if any(question_line_re.search(line) for line in lines[max(0, idx - 8) : idx + 1]):
            return "original", "文档开头题干块"

    if sub_re.search(before):
        label = nearest or (bold_labels[-1] if bold_labels else "")
        return "subquestion", f"最近标题/字段：{label or '未识别'}"
    if analysis_re.search(before):
        label = nearest or (bold_labels[-1] if bold_labels else "")
        return "analysis", f"最近标题/字段：{label or '未识别'}"
    return "unknown", f"最近标题/字段：{nearest or (bold_labels[-1] if bold_labels else '未识别')}"


def markdown_ref(asset_rel: str) -> str:
    normalized = asset_rel.replace("\\", "/")
    return f"![图](<{normalized}>)"


def relative_asset_ref(target_md: Path, asset: Path) -> str:
    rel = asset.relative_to(target_md.parent) if False else None
    try:
        rel_path = asset.resolve().relative_to(target_md.parent.resolve())
        return rel_path.as_posix()
    except Exception:
        pass
    try:
        import os

        return Path(os.path.relpath(asset, target_md.parent)).as_posix()
    except Exception:
        return asset.as_posix()


def question_block_bounds(text: str) -> tuple[int, int] | None:
    match = re.search(r"^##\s*题目[^\n]*\n", text, re.M)
    if not match:
        return None
    start = match.end()
    end_match = re.search(r"^##\s+", text[start:], re.M)
    end = start + end_match.start() if end_match else len(text)
    return start, end


def insert_into_question_block(text: str, refs: list[str]) -> tuple[str, bool]:
    bounds = question_block_bounds(text)
    if not bounds:
        return text, False
    _, end = bounds
    insertion = "\n" + "\n".join(refs) + "\n"
    # Keep a blank line before the next ## section.
    insert_at = end
    while insert_at > 0 and text[insert_at - 1] in " \t":
        insert_at -= 1
    return text[:insert_at].rstrip() + "\n" + insertion + "\n" + text[end:].lstrip("\n"), True


def read_text_and_newline(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    newline = "\r\n" if b"\r\n" in data else "\n"
    return data.decode("utf-8"), newline


def write_text_preserving_newline(path: Path, text: str, newline: str) -> None:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if newline == "\r\n":
        normalized = normalized.replace("\n", "\r\n")
    path.write_bytes(normalized.encode("utf-8"))


def collect_missing(audit_items: list[dict]) -> list[MissingImage]:
    details: list[MissingImage] = []
    seen: set[tuple[str, str]] = set()
    for item in audit_items:
        if item.get("category") not in FOCUS_CATEGORIES:
            continue
        target_md = Path(item.get("target_md") or "")
        source_md = Path(item.get("source_md") or "")
        if not target_md.exists() or not source_md.exists():
            continue

        target_refs = item.get("target_refs") or []
        target_ids = target_ref_identities(item)
        broken_targets = [ref for ref in target_refs if not ref.get("matched_asset")]
        source_lines = source_md.read_text(encoding="utf-8", errors="ignore").splitlines()
        for ref in item.get("source_refs") or []:
            asset_raw = ref.get("matched_asset")
            if not asset_raw:
                continue
            asset = Path(asset_raw)
            if asset.suffix.lower() not in IMG_EXTS:
                continue
            if ref_identity(ref).lower() in target_ids:
                continue
            dedupe_key = (str(target_md).lower(), str(asset.resolve()).lower())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            idx = source_ref_line(source_lines, ref)
            context, note = classify_source_context(source_lines, idx)
            rel = relative_asset_ref(target_md, asset)
            replace_raw = None
            if item.get("category") == "BROKEN_TARGET_REF" and context == "original" and broken_targets:
                action = "replace_broken_question"
                replace_raw = broken_targets[0].get("raw") or broken_targets[0].get("normalized")
            else:
                action = "auto_insert_question" if context == "original" else "manual_review"
            details.append(
                MissingImage(
                    key=item.get("key") or target_md.stem,
                    category=item.get("category") or "",
                    target_md=str(target_md),
                    source_md=str(source_md),
                    asset=str(asset),
                    asset_rel=rel,
                    raw=ref.get("raw") or "",
                    source_line=idx + 1 if idx >= 0 else 0,
                    source_context=context,
                    action=action,
                    note=note,
                    replace_raw=replace_raw,
                )
            )
    return details


def apply_md_updates(details: list[MissingImage]) -> tuple[int, int]:
    by_target: dict[Path, list[MissingImage]] = {}
    for item in details:
        if item.action in {"auto_insert_question", "replace_broken_question"}:
            by_target.setdefault(Path(item.target_md), []).append(item)

    changed_files = 0
    inserted_refs = 0
    for target, items in sorted(by_target.items()):
        text, newline = read_text_and_newline(target)
        original_text = text
        existing = text
        refs = []
        for item in items:
            ref = markdown_ref(item.asset_rel)
            if item.action == "replace_broken_question" and item.replace_raw:
                raw = re.escape(item.replace_raw)
                patterns = [
                    rf"!\[[^\]]*\]\(<{raw}>\)",
                    rf"!\[[^\]]*\]\({raw}\)",
                ]
                replaced = False
                for pattern in patterns:
                    new_text, count = re.subn(pattern, ref, text)
                    if count:
                        text = new_text
                        replaced = True
                        break
                if replaced:
                    inserted_refs += 1
                    continue
                item.action = "manual_review"
                item.note = f"未能替换断链 raw={item.replace_raw}"
                continue
            if item.asset_rel in existing or ref in existing:
                item.action = "already_present"
                continue
            refs.append(ref)

        new_text = text
        if refs:
            new_text, ok = insert_into_question_block(text, refs)
            if not ok:
                for item in items:
                    if item.action == "auto_insert_question":
                        item.action = "manual_review"
                        item.note = "target 缺少 ## 题目 区块，未自动插入"
                continue
        if new_text != original_text:
            write_text_preserving_newline(target, new_text, newline)
            changed_files += 1
            inserted_refs += len(refs)

    return changed_files, inserted_refs


def write_reports(details: list[MissingImage], report: Path, jsonl: Path, changed_files: int, inserted_refs: int) -> None:
    counts = Counter(item.action for item in details)
    contexts = Counter(item.source_context for item in details)
    report.parent.mkdir(parents=True, exist_ok=True)
    jsonl.parent.mkdir(parents=True, exist_ok=True)

    with jsonl.open("w", encoding="utf-8") as f:
        for item in details:
            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")

    lines = [
        "# 高考拆题缺失图片同步报告",
        "",
        "只自动插入源文档原题区图片；解析区/拆解子题区图片保留为人工复核。",
        "",
        "## 汇总",
        f"- 改动 md 文件数：{changed_files}",
        f"- 插入/修复图片引用数：{inserted_refs}",
        "",
        "## 动作统计",
    ]
    for key, count in counts.most_common():
        lines.append(f"- `{key}`：{count}")
    lines.append("")
    lines.append("## 来源位置统计")
    for key, count in contexts.most_common():
        lines.append(f"- `{key}`：{count}")

    auto = [item for item in details if item.action in {"auto_insert_question", "replace_broken_question", "already_present"}]
    manual = [item for item in details if item.action == "manual_review"]

    lines += ["", "## 已自动处理/可自动处理"]
    if not auto:
        lines.append("")
        lines.append("暂无。")
    for item in auto:
        lines += [
            "",
            f"### {item.key}",
            f"- action：`{item.action}`",
            f"- target：`{item.target_md}`",
            f"- source line：`{item.source_line}`",
            f"- insert：`{markdown_ref(item.asset_rel)}`",
            f"- note：{item.note}",
        ]

    lines += ["", "## 人工复核"]
    if not manual:
        lines.append("")
        lines.append("暂无。")
    for item in manual:
        lines += [
            "",
            f"### {item.key}",
            f"- source_context：`{item.source_context}`",
            f"- target：`{item.target_md}`",
            f"- source：`{item.source_md}:{item.source_line}`",
            f"- image：`{markdown_ref(item.asset_rel)}`",
            f"- note：{item.note}",
        ]

    report.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore high-confidence missing Gaokao image links.")
    parser.add_argument("--audit", type=Path, default=Path(r"Z:\_共享文件夹\records\gaokao-image-sync\gaokao-image-link-audit.jsonl"))
    parser.add_argument("--report", type=Path, default=Path(r"Z:\_共享文件夹\records\gaokao-image-sync\gaokao-missing-image-sync.md"))
    parser.add_argument("--details", type=Path, default=Path(r"Z:\_共享文件夹\records\gaokao-image-sync\gaokao-missing-image-sync.jsonl"))
    parser.add_argument("--write-md", action="store_true", help="Actually insert high-confidence image links into Markdown.")
    args = parser.parse_args()

    audit_items = load_jsonl(args.audit)
    details = collect_missing(audit_items)
    changed_files = 0
    inserted_refs = 0
    if args.write_md:
        changed_files, inserted_refs = apply_md_updates(details)
    write_reports(details, args.report, args.details, changed_files, inserted_refs)

    print(f"details: {args.details}")
    print(f"report: {args.report}")
    print(f"actions: {dict(Counter(item.action for item in details))}")
    print(f"contexts: {dict(Counter(item.source_context for item in details))}")
    print(f"changed_files: {changed_files}")
    print(f"inserted_refs: {inserted_refs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
