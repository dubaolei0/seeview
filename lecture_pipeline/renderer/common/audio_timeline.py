"""
音频时间线构建。

流程：
1. 对 doc 的所有 say 文本，按顺序调用 TTS，得到音频文件和时长
2. 以 INTRO_SILENCE 为起点，串联所有音频，段间加 BEAT_GAP 静音
3. 记录每一段的 (stage, act_idx, beat_idx, start_time, end_time)
4. 输出一个混合后的 wav 文件路径 + timeline 列表

本模块复用 src/tts_manager.py（不重写）。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# 让老代码可被 import（src/ 位置随部署而变，用自适应定位）
from .paths import find_project_root  # noqa: E402

_PROJECT_ROOT = find_project_root()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pydub import AudioSegment  # noqa: E402
from src.tts_manager import TTSManager  # noqa: E402

from ..schema import LectureDoc, Transition  # noqa: E402
from ..theme import (  # noqa: E402
    INTRO_SILENCE, BEAT_GAP, OUTRO_WAIT,
    COVER_TO_TEACH_RUN_TIME, TEACH_TO_SUMMARY_RUN_TIME,
    ACT_SOFT_TRANSITION, ACT_HARD_TRANSITION,
)


@dataclass
class AudioSegmentInfo:
    """一段音频的时间信息"""
    stage: str           # 'read' | 'teach' | 'summary'
    act_idx: int         # summary/read 为 -1
    beat_idx: int        # read 为 -1，其他为 beat 下标
    start_time: float    # 秒
    duration: float
    end_time: float = 0.0

    def __post_init__(self):
        self.end_time = self.start_time + self.duration


@dataclass
class AudioTimeline:
    mixed_path: Path
    total_duration: float
    segments: list[AudioSegmentInfo] = field(default_factory=list)

    def find(self, stage: str, act_idx: int = -1, beat_idx: int = -1) -> Optional[AudioSegmentInfo]:
        for s in self.segments:
            if s.stage == stage and s.act_idx == act_idx and s.beat_idx == beat_idx:
                return s
        return None


def build_audio_timeline(
    doc: LectureDoc,
    problem_id: str,
    cache_dir: Path,
    tts_provider: str | None = None,
    tts_voice: str | None = None,
    tts_retries: int = 2,
    tts_speech_rate: float | None = None,
) -> AudioTimeline:
    """
    为整个 doc 构建音频时间线。

    Args:
        doc: 已解析的 LectureDoc
        problem_id: 题目标识（用于输出文件名）
        cache_dir: 音频缓存目录
        tts_speech_rate: 可选语速倍率（0.5~2.0，1.0=默认）

    Returns:
        AudioTimeline 对象
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    tts = TTSManager(
        provider=tts_provider, voice=tts_voice,
        retry_count=tts_retries, speech_rate=tts_speech_rate,
    )
    print(f"[audio] TTS 配置：provider={tts.provider}, voice={tts.voice}, retries={tts.retry_count}"
          + (f", speech_rate={tts_speech_rate}" if tts_speech_rate else ""))

    # 1. 收集所有 say，按顺序生成音频
    segments_raw: list[dict] = []

    # 读题 say
    segments_raw.append({
        "text": doc.core.say,
        "stage": "read",
        "act_idx": -1,
        "beat_idx": -1,
    })

    # teach beats
    for ai, act in enumerate(doc.teach.acts):
        for bi, beat in enumerate(act.beats):
            segments_raw.append({
                "text": beat.say,
                "stage": "teach",
                "act_idx": ai,
                "beat_idx": bi,
            })

    # summary beats（summary 可省略）
    if doc.summary is not None:
        for bi, beat in enumerate(doc.summary.beats):
            segments_raw.append({
                "text": beat.say,
                "stage": "summary",
                "act_idx": -1,
                "beat_idx": bi,
            })

    # 2. 调 TTS（带 prev_text 上下文）
    prev_text = None
    audio_infos: list[dict] = []
    print(f"\n[audio] 生成 {len(segments_raw)} 段 TTS...")
    for i, seg in enumerate(segments_raw):
        try:
            audio_path, duration = tts.generate(
                seg["text"], mode="normal", prev_text=prev_text,
            )
        except Exception as e:
            loc = f"{seg['stage']}.{seg['act_idx']}.{seg['beat_idx']}"
            raise RuntimeError(
                f"TTS 生成失败：{loc}, provider={tts.provider}, voice={tts.voice}. "
                f"失败详情已记录到 media/cache/tts/failures.jsonl。错误：{e}"
            ) from e
        audio_infos.append({
            **seg,
            "audio_path": audio_path,
            "duration": duration,
        })
        prev_text = seg["text"]
        print(f"  [{i + 1}/{len(segments_raw)}] {seg['stage']}.{seg['act_idx']}.{seg['beat_idx']} "
              f"-> {duration:.2f}s")

    # 3. 计算每段之后的静音间隙（核心：转场位置用转场时长，普通位置用 BEAT_GAP）
    gaps = _compute_gaps(doc, audio_infos)

    # 4. 拼接音频，记录时间线
    mixed = AudioSegment.silent(duration=int(INTRO_SILENCE * 1000))
    current_time = INTRO_SILENCE
    segments: list[AudioSegmentInfo] = []

    for i, info in enumerate(audio_infos):
        audio = AudioSegment.from_file(info["audio_path"])
        actual_duration = len(audio) / 1000.0

        # 用实际音频时长而非 TTS 报告时长，避免缓存不一致导致偏移
        if abs(actual_duration - info["duration"]) > 0.1:
            print(f"  ⚠ duration mismatch [{info['stage']}.{info['act_idx']}.{info['beat_idx']}]: "
                  f"TTS报告={info['duration']:.2f}s, 实际文件={actual_duration:.2f}s")

        # 静音检测：TTS 可能失败返回空白音频，此处发出警告
        if audio.rms == 0 and actual_duration > 0.5:
            print(f"  ⚠ SILENT audio [{info['stage']}.{info['act_idx']}.{info['beat_idx']}]: "
                  f"{actual_duration:.1f}s 完全静音！TTS 可能失败。"
                  f" 文件: {info['audio_path']}")

        seg_info = AudioSegmentInfo(
            stage=info["stage"],
            act_idx=info["act_idx"],
            beat_idx=info["beat_idx"],
            start_time=current_time,
            duration=actual_duration,
        )
        segments.append(seg_info)

        mixed += audio
        current_time += actual_duration

        # 段间空隙（按转场类型动态调整）
        gap = gaps[i]
        mixed += AudioSegment.silent(duration=int(gap * 1000))
        current_time += gap

    # 末尾等待
    mixed += AudioSegment.silent(duration=int(OUTRO_WAIT * 1000))

    mixed_path = cache_dir / f"{problem_id}_mixed.wav"
    mixed.export(str(mixed_path), format="wav")
    total = len(mixed) / 1000.0
    print(f"[audio] 拼接完成，总时长 {total:.2f}s -> {mixed_path}")

    return AudioTimeline(
        mixed_path=mixed_path,
        total_duration=total,
        segments=segments,
    )


def _compute_gaps(doc: LectureDoc, audio_infos: list[dict]) -> list[float]:
    """
    计算每段音频之后的静音间隙。

    核心逻辑：视频在 stage 转场和 act 转场时会播放过渡动画，
    这些动画消耗的时间必须作为音频静音写入 WAV，否则视频时间线
    会逐步落后于音频时间线，导致声画错位。

    间隙 = max(视觉转场时长, BEAT_GAP)
    """
    n = len(audio_infos)
    gaps = [BEAT_GAP] * n  # 默认值
    if n == 0:
        return gaps

    # 最后一段没有后续间隙（OUTRO_WAIT 另外加）
    gaps[-1] = 0

    for i in range(n - 1):
        curr = audio_infos[i]
        nxt = audio_infos[i + 1]

        # ---- 读题 → 讲题 ----
        # 视频播放：cover_to_teach + 第一个 act 的转场
        if curr["stage"] == "read" and nxt["stage"] == "teach":
            # cover_to_teach 由 run_time 参数控制：
            #   FadeOut(run_time*0.5) + Header(run_time*0.5) 是基础
            #   layout A 或 C 会额外 +run_time*0.5（anchor/figure 出场）
            rt = COVER_TO_TEACH_RUN_TIME
            visual_time = rt  # base: FadeOut + Header = rt*0.5 + rt*0.5
            layout = doc.core.layout_branch
            # show_in_read：图已在读题阶段淡入并常驻，转场不再有“figure 出场”这段时间
            show_in_read = (
                doc.core.figure is not None
                and getattr(doc.core.figure, "show_in_read", False)
                and doc.core.figure.reveal_at_act is None
                and layout in ("C", "D")
            )
            if layout == "A":
                visual_time += rt * 0.5  # anchor 出场
            elif layout == "D" and doc.core.figure is not None:
                # 条件栏 + 图栏同时出场
                visual_time += rt * 0.5  # conditions 出场
                if doc.core.figure.reveal_at_act is None and not show_in_read:
                    visual_time += rt * 0.5  # figure 出场
            elif layout == "C" and doc.core.figure is not None:
                if doc.core.figure.reveal_at_act is None and not show_in_read:
                    visual_time += rt * 0.5  # figure 出场

            # 第一个 act 的转场也发生在 teach beats 开始之前
            first_act = doc.teach.acts[nxt["act_idx"]]
            if first_act.transition == Transition.SOFT:
                visual_time += ACT_SOFT_TRANSITION
            elif first_act.transition == Transition.HARD:
                visual_time += ACT_HARD_TRANSITION

            gaps[i] = max(visual_time, BEAT_GAP)
            continue

        # ---- 讲题 → 升华 ----
        if curr["stage"] == "teach" and nxt["stage"] == "summary":
            # teach_to_summary: board fadeout + optional figure/anchor fadeout
            rt = TEACH_TO_SUMMARY_RUN_TIME
            visual_time = rt  # 基础：board fadeout(rt*0.6) + extras(rt*0.4)
            gaps[i] = max(visual_time, BEAT_GAP)
            continue

        # ---- act 边界（同属 teach，但 act_idx 不同）----
        if (curr["stage"] == "teach" and nxt["stage"] == "teach"
                and curr["act_idx"] != nxt["act_idx"]):
            next_act = doc.teach.acts[nxt["act_idx"]]
            if next_act.transition == Transition.HARD:
                visual_time = ACT_HARD_TRANSITION
            elif next_act.transition == Transition.SOFT:
                visual_time = ACT_SOFT_TRANSITION
            else:
                visual_time = 0
            gaps[i] = max(visual_time, BEAT_GAP)
            continue

        # 同 act 内普通 beat 之间：默认 BEAT_GAP（已在初始化时设置）

    return gaps
