#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Audit image links between the structured Gaokao split-question markdown files
and the older source folder.

This script is read-only. It writes a Markdown report plus a JSONL detail file
under records/ by default.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import unquote


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
SKIP_DIRS = {".obsidian", ".claude", "output", "__pycache__"}


MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((.*)\)")
OBSIDIAN_IMAGE_RE = re.compile(r"!\[\[([^\]]+)\]\]")
HTML_IMAGE_RE = re.compile(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.I)
FILE_URL_RE = re.compile(r"^file:///", re.I)


@dataclass
class ImageRef:
    raw: str
    kind: str
    normalized: str
    filename: str
    exists_local: bool
    matched_asset: str | None
    match_method: str | None


@dataclass
class AuditItem:
    key: str
    target_md: str | None
    source_md: str | None
    target_refs: list[ImageRef]
    source_refs: list[ImageRef]
    category: str
    notes: list[str]


def configure_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            yield Path(dirpath) / filename


def normalize_ref(raw: str) -> str:
    ref = raw.strip().strip("<>").strip()
    if "|" in ref and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", ref):
        ref = ref.split("|", 1)[0]
    if "#" in ref:
        ref = ref.split("#", 1)[0]
    return unquote(ref)


def is_remote(ref: str) -> bool:
    if re.match(r"^[A-Za-z]:[\\/]", ref):
        return False
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", ref)) and not FILE_URL_RE.match(ref)


def extract_image_refs(text: str) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for match in MD_IMAGE_RE.finditer(text):
        refs.append(("markdown", match.group(1)))
    for match in OBSIDIAN_IMAGE_RE.finditer(text):
        refs.append(("obsidian", match.group(1)))
    for match in HTML_IMAGE_RE.finditer(text):
        refs.append(("html", match.group(1)))
    return refs


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_asset_indexes(assets_dir: Path):
    by_name: dict[str, list[Path]] = defaultdict(list)
    by_hash: dict[str, list[Path]] = defaultdict(list)
    asset_paths: list[Path] = []
    for path in iter_files(assets_dir):
        if path.suffix.lower() not in IMAGE_EXTS:
            continue
        asset_paths.append(path)
        by_name[path.name.lower()].append(path)
        try:
            by_hash[md5(path)].append(path)
        except Exception:
            pass
    return asset_paths, by_name, by_hash


def resolve_ref(md_path: Path, root: Path, assets_dir: Path, ref: str) -> list[Path]:
    if FILE_URL_RE.match(ref):
        return []
    raw_path = Path(ref)
    candidates: list[Path] = []
    if raw_path.is_absolute() or re.match(r"^[A-Za-z]:[\\/]", ref):
        candidates.append(Path(ref))
    else:
        candidates.append((md_path.parent / raw_path).resolve())
        candidates.append((root / raw_path).resolve())
        candidates.append((assets_dir / raw_path.name).resolve())
    return [path for path in candidates if path.exists()]


def find_asset_match(
    ref_path: Path | None,
    filename: str,
    by_name: dict[str, list[Path]],
    by_hash: dict[str, list[Path]],
    assets_dir: Path,
) -> tuple[Path | None, str | None]:
    name_hits = by_name.get(filename.lower(), []) if filename else []
    if len(name_hits) == 1:
        return name_hits[0], "asset_name_unique"
    if len(name_hits) > 1:
        return None, "asset_name_ambiguous"

    if ref_path is not None and ref_path.exists() and ref_path.suffix.lower() in IMAGE_EXTS:
        try:
            hash_hits = by_hash.get(md5(ref_path), [])
        except Exception:
            hash_hits = []
        if len(hash_hits) == 1:
            return hash_hits[0], "asset_hash_unique"
        if len(hash_hits) > 1:
            return None, "asset_hash_ambiguous"

    direct = assets_dir / filename
    if filename and direct.exists():
        return direct, "asset_direct"
    return None, None


def make_ref(
    md_path: Path,
    root: Path,
    assets_dir: Path,
    raw_kind: str,
    raw_ref: str,
    by_name: dict[str, list[Path]],
    by_hash: dict[str, list[Path]],
) -> ImageRef | None:
    ref = normalize_ref(raw_ref)
    if not ref or is_remote(ref):
        return None
    filename = Path(ref).name
    local_hits = resolve_ref(md_path, root, assets_dir, ref)
    local = local_hits[0] if local_hits else None
    matched, method = find_asset_match(local, filename, by_name, by_hash, assets_dir)
    return ImageRef(
        raw=raw_ref,
        kind=("file_url" if FILE_URL_RE.match(ref) else raw_kind),
        normalized=ref,
        filename=filename,
        exists_local=local is not None,
        matched_asset=str(matched) if matched else None,
        match_method=method,
    )


def normalize_key(path: Path) -> str:
    stem = path.stem
    stem = stem.replace("+", " ")
    stem = re.sub(r"拆解训练.*$", "拆解训练", stem)
    stem = stem.replace("全国二卷", "新高考Ⅱ卷")
    stem = stem.replace("全国2卷", "新高考Ⅱ卷")
    stem = stem.replace("全国Ⅰ卷", "新高考Ⅰ卷")
    stem = stem.replace("全国I卷", "新高考Ⅰ卷")
    stem = stem.replace("全国Ⅱ卷", "新高考Ⅱ卷")
    stem = stem.replace("全国II卷", "新高考Ⅱ卷")
    stem = stem.replace("新高考 Ⅱ 卷", "新高考Ⅱ卷")
    stem = stem.replace("新高考Ⅰ", "新高考Ⅰ卷")
    stem = stem.replace("新高考Ⅱ", "新高考Ⅱ卷")
    stem = stem.replace("（文科）", "（文）")
    stem = stem.replace("（理科）", "（理）")
    stem = stem.replace("(文)", "（文）")
    stem = stem.replace("(理)", "（理）")
    stem = re.sub(r"\s+", "", stem)
    return stem


def load_markdown_refs(root: Path, assets_dir: Path, by_name, by_hash) -> dict[str, tuple[Path, list[ImageRef]]]:
    result: dict[str, tuple[Path, list[ImageRef]]] = {}
    for md_path in iter_files(root):
        if md_path.suffix.lower() != ".md":
            continue
        try:
            text = md_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        refs: list[ImageRef] = []
        for kind, raw in extract_image_refs(text):
            item = make_ref(md_path, root, assets_dir, kind, raw, by_name, by_hash)
            if item is not None:
                refs.append(item)
        key = normalize_key(md_path)
        if key not in result:
            result[key] = (md_path, refs)
        else:
            # Keep the first but append a suffix-like note by using a synthetic key.
            result[f"{key}__DUP__{len(result)}"] = (md_path, refs)
    return result


def rel(path: str | Path | None, base: Path) -> str | None:
    if path is None:
        return None
    p = Path(path)
    try:
        return str(p.relative_to(base))
    except Exception:
        return str(p)


def categorize(target_refs: list[ImageRef], source_refs: list[ImageRef]) -> tuple[str, list[str]]:
    notes: list[str] = []
    target_broken = [r for r in target_refs if not r.exists_local and r.matched_asset is None]
    source_file_urls = [r for r in source_refs if r.kind == "file_url"]
    source_unmatched = [r for r in source_refs if r.kind != "file_url" and r.matched_asset is None]

    def identity(ref: ImageRef) -> str:
        return ref.matched_asset or ref.normalized

    target_ids = {identity(ref) for ref in target_refs}
    source_ids = {identity(ref) for ref in source_refs}

    if target_broken:
        notes.append(f"target has {len(target_broken)} broken image ref(s)")
    if source_file_urls:
        notes.append(f"source has {len(source_file_urls)} file:// temp image ref(s)")
    if source_unmatched:
        notes.append(f"source has {len(source_unmatched)} image ref(s) not matched in assets")

    if target_broken:
        return "BROKEN_TARGET_REF", notes
    if len(source_ids) > len(target_ids):
        if source_file_urls and not source_unmatched:
            return "SOURCE_MORE_REFS_WITH_FILE_URL", notes
        return "TARGET_MISSING_REFS", notes
    if len(target_ids) > len(source_ids):
        return "TARGET_EXTRA_REFS", notes
    if source_unmatched:
        return "SOURCE_IMAGE_NOT_IN_ASSETS", notes
    return "OK", notes


def write_report(items: list[AuditItem], report_path: Path, details_path: Path, target_root: Path, source_root: Path) -> None:
    counts = Counter(item.category for item in items)
    focus_categories = {
        "TARGET_MISSING_REFS",
        "BROKEN_TARGET_REF",
        "SOURCE_MORE_REFS_WITH_FILE_URL",
        "SOURCE_IMAGE_NOT_IN_ASSETS",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    details_path.parent.mkdir(parents=True, exist_ok=True)

    with details_path.open("w", encoding="utf-8") as f:
        for item in items:
            data = asdict(item)
            f.write(json.dumps(data, ensure_ascii=False) + "\n")

    lines: list[str] = []
    lines.append("# 高考拆题图链审计报告")
    lines.append("")
    lines.append(f"- 结构化目录：`{target_root}`")
    lines.append(f"- 源目录：`{source_root}`")
    lines.append(f"- 配对/扫描条目：{len(items)}")
    lines.append("")
    lines.append("## 分类统计")
    lines.append("")
    for category, count in counts.most_common():
        lines.append(f"- `{category}`：{count}")
    lines.append("")
    lines.append("> 这份 md 只展开图链缺失/断链候选；完整逐文档比对见 JSONL 明细。")
    lines.append("")

    focus = [i for i in items if i.category in focus_categories]
    lines.append("## 缺失/断链候选")
    lines.append("")
    for item in focus[:120]:
        lines.append(f"### {item.key}")
        lines.append("")
        lines.append(f"- 分类：`{item.category}`")
        if item.target_md:
            lines.append(f"- knowledge：`{rel(item.target_md, target_root)}`")
        if item.source_md:
            lines.append(f"- source：`{rel(item.source_md, source_root)}`")
        for note in item.notes:
            lines.append(f"- 备注：{note}")
        lines.append(f"- knowledge 图链数：{len(item.target_refs)}")
        for ref in item.target_refs:
            asset = rel(ref.matched_asset, target_root.parent) if ref.matched_asset else None
            lines.append(f"  - `{ref.normalized}` -> `{asset or '未匹配'}` ({ref.match_method or 'no_match'})")
        lines.append(f"- source 图链数：{len(item.source_refs)}")
        for ref in item.source_refs:
            asset = rel(ref.matched_asset, target_root.parent) if ref.matched_asset else None
            lines.append(f"  - `{ref.normalized}` -> `{asset or '未匹配'}` ({ref.kind}, {ref.match_method or 'no_match'})")
        lines.append("")
    if len(focus) > 120:
        lines.append(f"> 仅展示前 120 条，其余见 `{details_path}`。")
        lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Audit Gaokao split-question image links.")
    parser.add_argument("--target-root", default=r"Z:\_共享文件夹\knowledge\高考拆题")
    parser.add_argument("--source-root", default=r"Z:\01工作资料\04真题拆解（按人分）")
    parser.add_argument("--report", default=r"Z:\_共享文件夹\records\gaokao-image-sync\gaokao-image-link-audit.md")
    parser.add_argument("--details", default=r"Z:\_共享文件夹\records\gaokao-image-sync\gaokao-image-link-audit.jsonl")
    args = parser.parse_args()

    target_root = Path(args.target_root)
    source_root = Path(args.source_root)
    assets_dir = target_root / "assets"
    report_path = Path(args.report)
    details_path = Path(args.details)

    if not target_root.exists():
        raise FileNotFoundError(target_root)
    if not source_root.exists():
        raise FileNotFoundError(source_root)
    if not assets_dir.exists():
        raise FileNotFoundError(assets_dir)

    print("[1/4] indexing assets...")
    _, by_name, by_hash = build_asset_indexes(assets_dir)
    print(f"      asset names={len(by_name)}, hashes={len(by_hash)}")
    print("[2/4] reading target markdown...")
    target = load_markdown_refs(target_root, assets_dir, by_name, by_hash)
    print(f"      target md={len(target)}")
    print("[3/4] reading source markdown...")
    source = load_markdown_refs(source_root, assets_dir, by_name, by_hash)
    print(f"      source md={len(source)}")

    print("[4/4] comparing...")
    items: list[AuditItem] = []
    all_keys = sorted(set(target) | set(source))
    for key in all_keys:
        target_md, target_refs = target.get(key, (None, []))
        source_md, source_refs = source.get(key, (None, []))
        category, notes = categorize(target_refs, source_refs)
        if target_md is None:
            category = "SOURCE_ONLY_MD"
        elif source_md is None:
            category = "TARGET_ONLY_MD"
        items.append(
            AuditItem(
                key=key,
                target_md=str(target_md) if target_md else None,
                source_md=str(source_md) if source_md else None,
                target_refs=target_refs,
                source_refs=source_refs,
                category=category,
                notes=notes,
            )
        )

    write_report(items, report_path, details_path, target_root, source_root)
    counts = Counter(item.category for item in items)
    print("done")
    for category, count in counts.most_common():
        print(f"{category}: {count}")
    print(f"report: {report_path}")
    print(f"details: {details_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
