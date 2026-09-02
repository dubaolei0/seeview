"""Audit/sync image links from 高考拆题 Markdown into master_database patches.

The Markdown files are the human-editable source. master_database.jsonl is the
structured query index, with user edits layered through patches.jsonl. This
script compares image links in each Markdown "## 题目" block against the
corresponding original-question record content.

Default mode is read-only and writes an audit report. Use --write-patches to
append high-confidence content patches for original questions only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
OBSIDIAN_RE = re.compile(r"!\[\[([^\]]+)\]\]")
HTML_IMG_RE = re.compile(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"'][^>]*>", re.I)
QUESTION_BLOCK_RE = re.compile(
    r"^##\s*题目\s*(.*?)\n(?=^##\s+|\Z)",
    re.M | re.S,
)


@dataclass
class ImageRef:
    raw: str
    normalized: str
    embed: str
    kind: str


@dataclass
class Detail:
    category: str
    source_file: str
    md_path: str | None
    original_id: str | None
    missing_question_images: list[str]
    missing_other_images: list[str]
    notes: list[str]


def iter_markdown_image_targets(text: str) -> list[tuple[str, str]]:
    """Return (kind, raw target) pairs for Markdown, Obsidian, and HTML images."""
    refs: list[tuple[str, str]] = []

    refs.extend(("obsidian", m.group(1)) for m in OBSIDIAN_RE.finditer(text))
    refs.extend(("html", m.group(1)) for m in HTML_IMG_RE.finditer(text))

    pos = 0
    while True:
        start = text.find("![", pos)
        if start < 0:
            break
        if text.startswith("![[", start):
            pos = start + 3
            continue
        label_end = text.find("](", start + 2)
        if label_end < 0:
            pos = start + 2
            continue
        target_start = label_end + 2
        if target_start < len(text) and text[target_start] == "<":
            close = text.find(">)", target_start)
            if close < 0:
                pos = target_start
                continue
            refs.append(("markdown", text[target_start + 1 : close]))
            pos = close + 2
            continue

        depth = 0
        i = target_start
        while i < len(text):
            ch = text[i]
            if ch == "\\":
                i += 2
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                if depth == 0:
                    refs.append(("markdown", text[target_start:i]))
                    break
                depth -= 1
            i += 1
        pos = i + 1

    return refs


def normalize_target(raw: str) -> tuple[str | None, str | None]:
    """Return (comparison key, Obsidian embed target) for a local image ref."""
    value = raw.strip().strip("\"'")
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1].strip()
    if "|" in value and not value.lower().startswith(("http://", "https://")):
        value = value.split("|", 1)[0].strip()
    value = unquote(value)
    if value.lower().startswith(("http://", "https://")):
        return None, None
    if value.lower().startswith("file:///"):
        value = urlparse(value).path
    value = value.replace("\\", "/").split("#", 1)[0].split("?", 1)[0].strip()
    if not value:
        return None, None

    path = PurePosixPath(value)
    if path.suffix.lower() not in IMAGE_EXTS:
        return None, None

    parts = list(path.parts)
    asset_rel: str
    if "assets" in parts:
        asset_rel = "/".join(parts[parts.index("assets") + 1 :])
    elif len(parts) > 1 and not value.startswith(("../", "./", "/")):
        # Obsidian links can legitimately keep subdirectories under assets,
        # e.g. ![[拆题/整理版/2024年北京/2024BJ-8-1.png]].
        asset_rel = "/".join(parts)
    else:
        asset_rel = path.name
    if not asset_rel:
        return None, None
    key = asset_rel.lower()
    return key, asset_rel


def extract_image_refs(text: str) -> list[ImageRef]:
    refs: list[ImageRef] = []
    seen: set[str] = set()
    for kind, raw in iter_markdown_image_targets(text):
        normalized, embed = normalize_target(raw)
        if not normalized or not embed or normalized in seen:
            continue
        seen.add(normalized)
        refs.append(ImageRef(raw=raw, normalized=normalized, embed=embed, kind=kind))
    return refs


def extract_question_block(text: str) -> str:
    match = QUESTION_BLOCK_RE.search(text)
    return match.group(1).strip() if match else ""


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_effective_database(db_path: Path, patch_path: Path) -> list[dict]:
    records = load_jsonl(db_path)
    by_id = {row.get("id"): row for row in records}
    for patch in load_jsonl(patch_path):
        target = by_id.get(patch.get("target_id"))
        if not target:
            continue
        for key, value in (patch.get("fields") or {}).items():
            target[key] = value
    return records


def canonical_source_text(name: str) -> str:
    stem = Path(name).stem
    stem = stem.replace("全国二卷", "新高考Ⅱ卷")
    stem = stem.replace("全国2卷", "新高考Ⅱ卷")
    stem = stem.replace("全国Ⅰ卷", "新高考Ⅰ卷")
    stem = stem.replace("全国I卷", "新高考Ⅰ卷")
    stem = stem.replace("全国Ⅱ卷", "新高考Ⅱ卷")
    stem = stem.replace("全国II卷", "新高考Ⅱ卷")
    stem = stem.replace("新高考 Ⅰ 卷", "新高考Ⅰ卷")
    stem = stem.replace("新高考 Ⅱ 卷", "新高考Ⅱ卷")
    stem = stem.replace("新高考Ⅰ", "新高考Ⅰ卷")
    stem = stem.replace("新高考Ⅱ", "新高考Ⅱ卷")
    stem = stem.replace("（文科）", "（文）")
    stem = stem.replace("（理科）", "（理）")
    stem = stem.replace("(文)", "（文）")
    stem = stem.replace("(理)", "（理）")
    stem = re.sub(r"拆解训练.*$", "拆解训练", stem)
    stem = re.sub(r"\s+", "", stem)
    return stem


def source_signature(name: str) -> str | None:
    """Build a loose signature such as 2024|全国甲卷（文）:12|全国甲卷（理）:11."""
    text = canonical_source_text(name)
    year_match = re.search(r"(20\d{2})年", text)
    if not year_match:
        return None
    year = year_match.group(1)

    pairs: set[tuple[str, str]] = set()
    base_exam: str | None = None
    full_pattern = re.compile(r"20\d{2}年(.+?卷(?:（[文理]）)?)第(\d+)题")
    for match in full_pattern.finditer(text):
        exam, no = match.groups()
        pairs.add((exam, no))
        if base_exam is None:
            base_exam = re.sub(r"（[文理]）$", "", exam)

    if base_exam:
        for variant, no in re.findall(r"（([文理])）第(\d+)题", text):
            pairs.add((f"{base_exam}（{variant}）", no))

    if not pairs:
        return None
    return year + "|" + "|".join(f"{exam}:{no}" for exam, no in sorted(pairs))


def index_markdown(root: Path) -> tuple[dict[str, list[Path]], dict[str, list[Path]]]:
    by_name: dict[str, list[Path]] = defaultdict(list)
    by_signature: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(root.rglob("*.md")):
        if "assets" in path.parts:
            continue
        by_name[path.name].append(path)
        signature = source_signature(path.name)
        if signature:
            by_signature[signature].append(path)
    return by_name, by_signature


def find_markdown_paths(
    source_file: str,
    by_name: dict[str, list[Path]],
    by_signature: dict[str, list[Path]],
) -> tuple[list[Path], str]:
    exact = by_name.get(source_file)
    if exact:
        return exact, "exact_filename"
    signature = source_signature(source_file)
    if signature and by_signature.get(signature):
        return by_signature[signature], f"source_signature:{signature}"
    return [], "not_found"


def make_patch(record: dict, missing: list[ImageRef], by: str, reason: str) -> dict:
    current = (record.get("content") or "").rstrip()
    additions = "\n".join(f"![[{ref.embed}]]" for ref in missing)
    fields = {"content": f"{current}\n\n{additions}" if current else additions}
    return {
        "target_id": record["id"],
        "fields": fields,
        "by": by,
        "at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "reason": reason,
    }


def write_report(path: Path, details: list[Detail], patch_count: int) -> None:
    counts: dict[str, int] = defaultdict(int)
    for item in details:
        counts[item.category] += 1

    lines = [
        "# 高考拆题 md → 题库图链同步审计",
        "",
        "这份报告只关注 md 题目区图片是否同步进 `master_database.jsonl` 的原题 `content`。",
        "默认不改主库；可确认后用脚本生成 `patches.jsonl` 补丁。",
        "",
        "## 汇总",
    ]
    for category in sorted(counts):
        lines.append(f"- {category}: {counts[category]}")
    lines.append(f"- 本次写入补丁: {patch_count}")

    auto_items = [d for d in details if d.category == "AUTO_PATCH_CANDIDATE"]
    manual_items = [d for d in details if d.category == "MANUAL_REVIEW"]
    missing_md_items = [d for d in details if d.category in {"MD_NOT_FOUND", "NO_ORIGINAL_RECORD"}]

    lines += ["", "## 可自动同步候选"]
    if not auto_items:
        lines.append("")
        lines.append("暂无。")
    for item in auto_items:
        lines += [
            "",
            f"### {item.source_file}",
            f"- 原题记录: `{item.original_id}`",
            f"- md: `{item.md_path}`",
            "- 题目区缺失图片:",
        ]
        for image in item.missing_question_images:
            lines.append(f"  - `![[{image}]]`")
        for note in item.notes:
            lines.append(f"- 备注: {note}")

    lines += ["", "## 需要人工看"]
    if not manual_items:
        lines.append("")
        lines.append("暂无。")
    for item in manual_items:
        lines += [
            "",
            f"### {item.source_file}",
            f"- 原题记录: `{item.original_id or '无'}`",
            f"- md: `{item.md_path or '无'}`",
        ]
        if item.missing_other_images:
            lines.append("- 非题目区/无法自动定位图片:")
            for image in item.missing_other_images:
                lines.append(f"  - `![[{image}]]`")
        for note in item.notes:
            lines.append(f"- 备注: {note}")

    lines += ["", "## 映射异常"]
    if not missing_md_items:
        lines.append("")
        lines.append("暂无。")
    for item in missing_md_items:
        lines += [
            "",
            f"### {item.source_file}",
            f"- 类别: `{item.category}`",
            f"- 原题记录: `{item.original_id or '无'}`",
            f"- md: `{item.md_path or '无'}`",
        ]
        for note in item.notes:
            lines.append(f"- 备注: {note}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_details(path: Path, details: list[Detail]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in details:
            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit/sync Gaokao db image links from Markdown.")
    parser.add_argument("--md-root", type=Path, default=Path(r"Z:\_共享文件夹\knowledge\高考拆题"))
    parser.add_argument("--db", type=Path, default=Path(r"Z:\_共享文件夹\knowledge\高考题目\题库\master_database.jsonl"))
    parser.add_argument("--patches", type=Path, default=Path(r"Z:\_共享文件夹\knowledge\高考题目\题库\patches.jsonl"))
    parser.add_argument("--report", type=Path, default=Path(r"Z:\_共享文件夹\records\gaokao-image-sync\gaokao-db-image-sync-audit.md"))
    parser.add_argument("--details", type=Path, default=Path(r"Z:\_共享文件夹\records\gaokao-image-sync\gaokao-db-image-sync-audit.jsonl"))
    parser.add_argument("--write-patches", action="store_true", help="Append high-confidence content patches.")
    parser.add_argument("--by", default="哈斯", help="Name written to patches.jsonl when --write-patches is used.")
    parser.add_argument(
        "--reason",
        default="同步高考拆题 Markdown 题目区图片到题库原题 content",
        help="Patch reason when --write-patches is used.",
    )
    args = parser.parse_args()

    md_by_name, md_by_signature = index_markdown(args.md_root)
    records = load_effective_database(args.db, args.patches)
    by_source: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        source_file = record.get("source_file")
        if source_file:
            by_source[source_file].append(record)

    details: list[Detail] = []
    patches: list[dict] = []

    for source_file, group in sorted(by_source.items()):
        originals = [row for row in group if row.get("type") == "original"]
        original = originals[0] if originals else None
        md_paths, match_method = find_markdown_paths(source_file, md_by_name, md_by_signature)
        notes: list[str] = []

        if not original:
            details.append(
                Detail("NO_ORIGINAL_RECORD", source_file, str(md_paths[0]) if md_paths else None, None, [], [], [])
            )
            continue
        if len(originals) > 1:
            notes.append(f"同一 source_file 有 {len(originals)} 条 original 记录，只审计第一条")
        if not md_paths:
            details.append(Detail("MD_NOT_FOUND", source_file, None, original.get("id"), [], [], []))
            continue
        if len(md_paths) > 1:
            notes.append(f"同名 md 有 {len(md_paths)} 份，只审计第一份")
        if match_method != "exact_filename":
            notes.append(f"md 通过 {match_method} 匹配，source_file 与文件名不完全一致")

        md_path = md_paths[0]
        text = md_path.read_text(encoding="utf-8")
        question_block = extract_question_block(text)
        question_refs = extract_image_refs(question_block)
        doc_refs = extract_image_refs(text)
        db_refs = extract_image_refs("\n".join(str(row.get("content") or "") for row in group))
        original_refs = extract_image_refs(str(original.get("content") or ""))

        original_keys = {ref.normalized for ref in original_refs}
        db_keys = {ref.normalized for ref in db_refs}
        missing_question = [ref for ref in question_refs if ref.normalized not in original_keys]
        question_keys = {ref.normalized for ref in question_refs}
        missing_other = [
            ref for ref in doc_refs if ref.normalized not in db_keys and ref.normalized not in question_keys
        ]

        if missing_question:
            details.append(
                Detail(
                    "AUTO_PATCH_CANDIDATE",
                    source_file,
                    str(md_path),
                    original.get("id"),
                    [ref.embed for ref in missing_question],
                    [],
                    notes.copy(),
                )
            )
            patches.append(make_patch(original, missing_question, args.by, args.reason))

        if missing_other:
            details.append(
                Detail(
                    "MANUAL_REVIEW",
                    source_file,
                    str(md_path),
                    original.get("id"),
                    [],
                    [ref.embed for ref in missing_other],
                    notes.copy(),
                )
            )

    patch_count = 0
    if args.write_patches and patches:
        args.patches.parent.mkdir(parents=True, exist_ok=True)
        with args.patches.open("a", encoding="utf-8") as f:
            for patch in patches:
                f.write(json.dumps(patch, ensure_ascii=False) + "\n")
                patch_count += 1

    write_report(args.report, details, patch_count)
    write_details(args.details, details)
    print(f"details: {args.details}")
    print(f"report: {args.report}")
    print(f"auto candidates: {sum(1 for d in details if d.category == 'AUTO_PATCH_CANDIDATE')}")
    print(f"manual review: {sum(1 for d in details if d.category == 'MANUAL_REVIEW')}")
    print(f"patches written: {patch_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
