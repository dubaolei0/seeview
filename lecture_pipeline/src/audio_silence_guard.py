"""Detect and repair unexpectedly long silence inside one TTS clip.

Originally shadow-mode detection only; now also compresses over-long internal
silence in place. Deterministic TTS voices (e.g. Aliyun CosyVoice) reproduce
the same silence on every retry, so rejecting-and-retry is a dead end — we cap
each abnormal internal silence to a natural pause length and accept the clip.
"""

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
# Abnormal internal silences (>= DEFAULT_MIN_INTERNAL_SILENCE_MS) are capped to
# this length instead of rejecting the whole clip.
DEFAULT_SILENCE_CAP_MS = 800
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


def compress_internal_silences(
    audio_path: str | Path,
    text: str,
    *,
    cap_ms: int = DEFAULT_SILENCE_CAP_MS,
    silence_threshold_dbfs: int = DEFAULT_SILENCE_THRESHOLD_DBFS,
    edge_tolerance_ms: int = EDGE_TOLERANCE_MS,
) -> dict[str, Any]:
    """Cap each internal silence longer than ``cap_ms`` down to ``cap_ms``.

    Rewrites the file in place and returns a report describing the change.
    Clips whose ``text`` carries an explicit ``[pause:...]`` marker are returned
    untouched (``compressed=False``), and leading/trailing (edge) silence is
    always preserved so the TTS clip's natural intro/outro stays intact.
    """
    path = Path(audio_path)
    with path.open("rb") as handle:
        audio = AudioSegment.from_file(handle)
    duration_ms = len(audio)

    if EXPLICIT_PAUSE_RE.search(text or ""):
        return {
            "compressed": False,
            "reason": "explicit_pause",
            "duration_ms": duration_ms,
            "cap_ms": cap_ms,
        }

    frame_rate = audio.frame_rate
    channels = audio.channels

    detected = detect_silence(
        audio,
        min_silence_len=cap_ms,
        silence_thresh=silence_threshold_dbfs,
        seek_step=10,
    )
    # Only cap INTERNAL silences; leave leading/trailing silence intact.
    targets = [
        (start, end)
        for start, end in detected
        if start > edge_tolerance_ms
        and end < duration_ms - edge_tolerance_ms
        and (end - start) > cap_ms
    ]
    if not targets:
        return {
            "compressed": False,
            "reason": "no_long_internal_silence",
            "duration_ms": duration_ms,
            "cap_ms": cap_ms,
        }

    # Match the original's format so concatenation never resamples/downmixes.
    silence_chunk = AudioSegment.silent(duration=cap_ms, frame_rate=frame_rate)
    if silence_chunk.channels != channels:
        silence_chunk = silence_chunk.set_channels(channels)

    rebuilt = AudioSegment.silent(duration=0, frame_rate=frame_rate)
    if rebuilt.channels != channels:
        rebuilt = rebuilt.set_channels(channels)

    cursor = 0
    capped: list[dict[str, int]] = []
    for start, end in targets:
        if start > cursor:
            rebuilt += audio[cursor:start]
        rebuilt += silence_chunk
        capped.append({
            "start_ms": int(start),
            "end_ms": int(end),
            "original_ms": int(end - start),
            "capped_ms": int(cap_ms),
        })
        cursor = end
    if cursor < duration_ms:
        rebuilt += audio[cursor:]

    # Atomic write-back so a half-written file never replaces the original.
    temp_path = path.with_name(path.name + ".tmp")
    with temp_path.open("wb") as handle:
        rebuilt.export(handle, format="wav")
    temp_path.replace(path)

    return {
        "compressed": True,
        "reason": "capped",
        "cap_ms": cap_ms,
        "duration_ms": len(rebuilt),
        "original_duration_ms": duration_ms,
        "capped_silences": capped,
    }


def enforce_tts_silence_quality(
    audio_path: str | Path,
    text: str,
    *,
    cap_ms: int = DEFAULT_SILENCE_CAP_MS,
) -> dict[str, Any]:
    """Ensure no abnormal long internal silence; compress rather than reject.

    If the clip contains an unexpected long internal silence (>= the gate
    threshold), cap each over-long internal silence to ``cap_ms`` in place and
    return a report with ``compressed=True``. Explicit ``[pause:...]`` markers
    and edge silences are left untouched. The clip is never rejected for long
    silence, because deterministic TTS voices would reproduce the same silence
    on retry.
    """
    report = analyze_tts_silence(audio_path, text)
    if not report["would_compress"]:
        report["compressed"] = False
        return report
    compression = compress_internal_silences(audio_path, text, cap_ms=cap_ms)
    report["compressed"] = compression["compressed"]
    report["post_duration_ms"] = compression.get("duration_ms")
    report["capped_silences"] = compression.get("capped_silences", [])
    return report
