"""Shadow-mode detection for unexpectedly long silence inside one TTS clip."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from pydub import AudioSegment
from pydub.silence import detect_silence


DEFAULT_SILENCE_THRESHOLD_DBFS = -40
DEFAULT_MIN_INTERNAL_SILENCE_MS = 2000
EDGE_TOLERANCE_MS = 120
EXPLICIT_PAUSE_RE = re.compile(r"\[pause:\d+(?:\.\d+)?(?:s|ms)\]")


class TTSLongInternalSilenceError(RuntimeError):
    """Raised when a TTS clip contains an unexpected long internal silence."""

    def __init__(self, report: dict[str, Any]):
        self.report = report
        longest = report["longest_internal_silence_ms"]
        super().__init__(f"TTS returned long internal silence: {longest}ms")


def analyze_tts_silence(
    audio_path: str | Path,
    text: str,
    *,
    silence_threshold_dbfs: int = DEFAULT_SILENCE_THRESHOLD_DBFS,
    min_internal_silence_ms: int = DEFAULT_MIN_INTERNAL_SILENCE_MS,
) -> dict[str, Any]:
    """Return a JSON-serializable report without changing the audio file."""
    path = Path(audio_path)
    with path.open("rb") as handle:
        audio = AudioSegment.from_file(handle)
    duration_ms = len(audio)
    explicit_pause = bool(EXPLICIT_PAUSE_RE.search(text))
    detected = detect_silence(
        audio,
        min_silence_len=min_internal_silence_ms,
        silence_thresh=silence_threshold_dbfs,
        seek_step=10,
    )

    internal_ranges: list[dict[str, int]] = []
    for start_ms, end_ms in detected:
        if start_ms <= EDGE_TOLERANCE_MS or end_ms >= duration_ms - EDGE_TOLERANCE_MS:
            continue
        internal_ranges.append({
            "start_ms": int(start_ms),
            "end_ms": int(end_ms),
            "duration_ms": int(end_ms - start_ms),
        })

    longest_ms = max((item["duration_ms"] for item in internal_ranges), default=0)
    return {
        "audio_path": str(path),
        "text": text,
        "silence_threshold_dbfs": silence_threshold_dbfs,
        "min_internal_silence_ms": min_internal_silence_ms,
        "explicit_pause": explicit_pause,
        "skipped_for_explicit_pause": explicit_pause,
        "internal_silences": [] if explicit_pause else internal_ranges,
        "longest_internal_silence_ms": 0 if explicit_pause else longest_ms,
        "would_compress": bool(internal_ranges) and not explicit_pause,
    }


def append_shadow_log(log_path: str | Path, report: dict[str, Any], **context: Any) -> None:
    """Append one detection event; failures here must never block rendering."""
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"timestamp": time.time(), "mode": "shadow", **context, **report}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def enforce_tts_silence_quality(audio_path: str | Path, text: str) -> dict[str, Any]:
    """Return the report for valid audio; reject unexpected long internal silence."""
    report = analyze_tts_silence(audio_path, text)
    if report["would_compress"]:
        raise TTSLongInternalSilenceError(report)
    return report
