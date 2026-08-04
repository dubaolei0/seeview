from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydub import AudioSegment
from pydub.generators import Sine

from src.audio_silence_guard import (
    TTSLongInternalSilenceError,
    analyze_tts_silence,
    enforce_tts_silence_quality,
)
from src.tts_manager import TTSManager


class FakeDriver:
    def __init__(self, outputs: list[Path]):
        self.outputs = outputs
        self.calls = 0

    def _get_fingerprint(self, text: str, mode: str) -> str:
        return "test-fingerprint"

    def generate(self, text: str, mode: str, prev_text: str | None):
        path = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        with path.open("rb") as handle:
            duration = len(AudioSegment.from_file(handle)) / 1000.0
        return str(path), duration


class AudioSilenceGuardTests(unittest.TestCase):
    def _export(self, audio: AudioSegment, directory: str, name: str) -> Path:
        path = Path(directory) / name
        exported = audio.export(path, format="wav")
        exported.close()
        return path

    def _manager(self, directory: str, driver: FakeDriver, retries: int) -> TTSManager:
        manager = TTSManager.__new__(TTSManager)
        manager.provider = "fake"
        manager.voice = "fake-voice"
        manager.retry_count = retries
        manager.driver = driver
        root = Path(directory)
        manager.cache_index_path = root / "cache_index.json"
        manager.failure_log_path = root / "failures.jsonl"
        manager.silence_guard_log_path = root / "silence_guard.jsonl"
        manager.silence_quarantine_dir = root / "quarantine"
        manager.cache_index = {}
        return manager

    def test_detects_long_internal_silence(self):
        with tempfile.TemporaryDirectory() as directory:
            tone = Sine(440).to_audio_segment(duration=700).apply_gain(-8)
            path = self._export(tone + AudioSegment.silent(2500) + tone, directory, "internal.wav")
            report = analyze_tts_silence(path, "前半句，后半句。")
            self.assertTrue(report["would_compress"])
            self.assertGreaterEqual(report["longest_internal_silence_ms"], 2400)

    def test_ignores_edge_silence(self):
        with tempfile.TemporaryDirectory() as directory:
            tone = Sine(440).to_audio_segment(duration=700).apply_gain(-8)
            path = self._export(AudioSegment.silent(2500) + tone, directory, "edge.wav")
            report = analyze_tts_silence(path, "一句话。")
            self.assertFalse(report["would_compress"])

    def test_explicit_pause_is_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            tone = Sine(440).to_audio_segment(duration=700).apply_gain(-8)
            path = self._export(tone + AudioSegment.silent(2500) + tone, directory, "pause.wav")
            report = analyze_tts_silence(path, "前半句[pause:2.5s]后半句。")
            self.assertTrue(report["skipped_for_explicit_pause"])
            self.assertFalse(report["would_compress"])

    def test_quality_gate_rejects_long_internal_silence(self):
        with tempfile.TemporaryDirectory() as directory:
            tone = Sine(440).to_audio_segment(duration=700).apply_gain(-8)
            path = self._export(tone + AudioSegment.silent(2500) + tone, directory, "reject.wav")
            with self.assertRaises(TTSLongInternalSilenceError):
                enforce_tts_silence_quality(path, "前半句，后半句。")

    def test_quality_gate_accepts_normal_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            tone = Sine(440).to_audio_segment(duration=1500).apply_gain(-8)
            path = self._export(tone, directory, "accept.wav")
            report = enforce_tts_silence_quality(path, "正常音频。")
            self.assertFalse(report["would_compress"])

    @patch("src.tts_manager.time.sleep", return_value=None)
    def test_generated_bad_audio_is_retried_and_not_cached(self, _sleep):
        with tempfile.TemporaryDirectory() as directory:
            tone = Sine(440).to_audio_segment(duration=700).apply_gain(-8)
            bad = self._export(tone + AudioSegment.silent(2500) + tone, directory, "bad.wav")
            good = self._export(tone + AudioSegment.silent(500) + tone, directory, "good.wav")
            driver = FakeDriver([bad, good])
            manager = self._manager(directory, driver, retries=1)

            path, _duration = manager.generate("前半句，后半句。")

            self.assertEqual(driver.calls, 2)
            self.assertEqual(Path(path), good)
            self.assertEqual(Path(manager.cache_index["test-fingerprint"]["path"]), good)
            self.assertTrue(any(manager.silence_quarantine_dir.iterdir()))

    def test_bad_cache_is_invalidated_before_regeneration(self):
        with tempfile.TemporaryDirectory() as directory:
            tone = Sine(440).to_audio_segment(duration=700).apply_gain(-8)
            bad = self._export(tone + AudioSegment.silent(2500) + tone, directory, "bad-cache.wav")
            good = self._export(tone, directory, "regenerated.wav")
            driver = FakeDriver([good])
            manager = self._manager(directory, driver, retries=0)
            with bad.open("rb") as handle:
                bad_duration = len(AudioSegment.from_file(handle)) / 1000.0
            manager.cache_index["test-fingerprint"] = {
                "path": str(bad), "duration": bad_duration,
            }

            path, _duration = manager.generate("缓存复检。")

            self.assertEqual(driver.calls, 1)
            self.assertEqual(Path(path), good)
            self.assertEqual(Path(manager.cache_index["test-fingerprint"]["path"]), good)
            self.assertTrue(any(manager.silence_quarantine_dir.iterdir()))


if __name__ == "__main__":
    unittest.main()
