from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydub import AudioSegment
from pydub.generators import Sine

from src.audio_silence_guard import (
    analyze_tts_silence,
    compress_internal_silences,
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

    @staticmethod
    def _len_ms(path: Path) -> int:
        with path.open("rb") as handle:
            return len(AudioSegment.from_file(handle))

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

    def test_quality_gate_compresses_long_internal_silence(self):
        with tempfile.TemporaryDirectory() as directory:
            tone = Sine(440).to_audio_segment(duration=700).apply_gain(-8)
            path = self._export(tone + AudioSegment.silent(2500) + tone, directory, "compress.wav")
            report = enforce_tts_silence_quality(path, "前半句，后半句。")
            self.assertTrue(report["compressed"])
            # 压缩后不再触发静音门
            after = analyze_tts_silence(path, "前半句，后半句。")
            self.assertFalse(after["would_compress"])

    def test_quality_gate_accepts_normal_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            tone = Sine(440).to_audio_segment(duration=1500).apply_gain(-8)
            path = self._export(tone, directory, "accept.wav")
            report = enforce_tts_silence_quality(path, "正常音频。")
            self.assertFalse(report["would_compress"])
            self.assertFalse(report["compressed"])

    def test_compress_caps_long_internal_pause(self):
        with tempfile.TemporaryDirectory() as directory:
            tone = Sine(440).to_audio_segment(duration=700).apply_gain(-8)
            path = self._export(tone + AudioSegment.silent(2500) + tone, directory, "cap.wav")
            before = self._len_ms(path)
            report = compress_internal_silences(path, "前半句，后半句。")
            self.assertTrue(report["compressed"])
            after = self._len_ms(path)
            self.assertLess(after, before)
            # 最长内部静音已被压到 cap 以下（用更低阈值复检）
            reanalyze = analyze_tts_silence(path, "前半句，后半句。", min_internal_silence_ms=500)
            self.assertLessEqual(reanalyze["longest_internal_silence_ms"], 850)

    def test_compress_preserves_edge_silence(self):
        with tempfile.TemporaryDirectory() as directory:
            tone = Sine(440).to_audio_segment(duration=700).apply_gain(-8)
            # 首尾长静音、中间无长内部静音：不应压缩
            path = self._export(
                AudioSegment.silent(2500) + tone + AudioSegment.silent(2500),
                directory, "edge.wav",
            )
            before = self._len_ms(path)
            report = compress_internal_silences(path, "一句话。")
            self.assertFalse(report["compressed"])
            self.assertEqual(self._len_ms(path), before)

    def test_compress_respects_explicit_pause(self):
        with tempfile.TemporaryDirectory() as directory:
            tone = Sine(440).to_audio_segment(duration=700).apply_gain(-8)
            path = self._export(tone + AudioSegment.silent(2500) + tone, directory, "pause.wav")
            before = self._len_ms(path)
            report = compress_internal_silences(path, "前半句[pause:2.5s]后半句。")
            self.assertFalse(report["compressed"])
            self.assertEqual(self._len_ms(path), before)

    @patch("src.tts_manager.time.sleep", return_value=None)
    def test_generated_audio_with_long_silence_is_compressed_and_cached(self, _sleep):
        with tempfile.TemporaryDirectory() as directory:
            tone = Sine(440).to_audio_segment(duration=700).apply_gain(-8)
            bad = self._export(tone + AudioSegment.silent(2500) + tone, directory, "bad.wav")
            driver = FakeDriver([bad])
            manager = self._manager(directory, driver, retries=1)

            path, duration = manager.generate("前半句，后半句。")

            self.assertEqual(driver.calls, 1)  # 压缩即接受，不再重试
            self.assertEqual(Path(path), bad)  # 就地压缩，路径不变
            self.assertLess(duration, 3.0)     # 3.9s -> ~2.2s
            self.assertEqual(Path(manager.cache_index["test-fingerprint"]["path"]), bad)
            self.assertTrue(any(manager.silence_quarantine_dir.iterdir()))  # 原始已隔离

    def test_bad_cache_is_compressed_in_place(self):
        with tempfile.TemporaryDirectory() as directory:
            tone = Sine(440).to_audio_segment(duration=700).apply_gain(-8)
            bad = self._export(tone + AudioSegment.silent(2500) + tone, directory, "bad-cache.wav")
            driver = FakeDriver([])  # 不应被调用
            manager = self._manager(directory, driver, retries=0)
            with bad.open("rb") as handle:
                bad_duration = len(AudioSegment.from_file(handle)) / 1000.0
            manager.cache_index["test-fingerprint"] = {
                "path": str(bad), "duration": bad_duration,
            }

            path, duration = manager.generate("缓存复检。")

            self.assertEqual(driver.calls, 0)  # 缓存命中并就地压缩，不重新生成
            self.assertEqual(Path(path), bad)
            self.assertLess(duration, bad_duration)
            self.assertEqual(manager.cache_index["test-fingerprint"]["duration"], duration)
            self.assertTrue(any(manager.silence_quarantine_dir.iterdir()))


if __name__ == "__main__":
    unittest.main()
