"""Audit cached TTS clips referenced by lecture YAML files; never modifies audio."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from renderer.schema import LectureDoc
from src.audio_silence_guard import analyze_tts_silence
from src.tts_manager import TTSManager


def iter_yaml_files(inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in inputs:
        path = Path(raw)
        if path.is_dir():
            files.extend(sorted(path.glob("*.yaml")))
        elif path.suffix.lower() in {".yaml", ".yml"}:
            files.append(path)
    return files


def collect_segments(doc: LectureDoc) -> list[tuple[str, str]]:
    segments: list[tuple[str, str]] = [("read", doc.core.say)]
    for ai, act in enumerate(doc.teach.acts):
        for bi, beat in enumerate(act.beats):
            segments.append((f"teach.{ai}.{bi}", beat.say))
    if doc.summary is not None:
        for bi, beat in enumerate(doc.summary.beats):
            segments.append((f"summary.{bi}", beat.say))
    return segments


def cached_path(tts: TTSManager, text: str, prev_text: str | None) -> Path | None:
    cache_key = f"nofallback_v1_{tts.provider}_{tts.voice}_{text}_normal_{prev_text or ''}"
    fingerprint = tts.driver._get_fingerprint(cache_key, "normal")
    entry = tts.cache_index.get(fingerprint)
    if not entry:
        return None
    path = Path(entry["path"])
    return path if path.exists() else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="YAML files or directories")
    parser.add_argument("--provider", default="aliyun")
    parser.add_argument("--voice", default="longcheng_v3")
    parser.add_argument("--threshold-dbfs", type=int, default=-40)
    parser.add_argument("--min-silence-ms", type=int, default=2000)
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()

    tts = TTSManager(provider=args.provider, voice=args.voice, retry_count=0)
    results: list[dict] = []
    missing = 0
    for yaml_path in iter_yaml_files(args.inputs):
        doc = LectureDoc.from_yaml_file(yaml_path)
        prev_text = None
        for location, text in collect_segments(doc):
            path = cached_path(tts, text, prev_text)
            if path is None:
                missing += 1
                results.append({
                    "yaml": str(yaml_path), "location": location,
                    "text": text, "cache_missing": True,
                })
            else:
                report = analyze_tts_silence(
                    path, text,
                    silence_threshold_dbfs=args.threshold_dbfs,
                    min_internal_silence_ms=args.min_silence_ms,
                )
                results.append({
                    "yaml": str(yaml_path), "location": location,
                    "cache_missing": False, **report,
                })
            prev_text = text

    flagged = [item for item in results if item.get("would_compress")]
    print(f"YAML={len(iter_yaml_files(args.inputs))} SEGMENTS={len(results)} MISSING={missing} FLAGGED={len(flagged)}")
    for item in flagged:
        print(
            f"FLAG {Path(item['yaml']).name} {item['location']} "
            f"longest={item['longest_internal_silence_ms']/1000:.3f}s "
            f"text={item['text']}"
        )

    if args.json_path:
        output = Path(args.json_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
