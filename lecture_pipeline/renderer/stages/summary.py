"""
升华阶段主控。
"""

from __future__ import annotations

from manim import Scene

from ..schema import LectureDoc, Mode
from ..blocks import build as build_block
from ..regions import SummaryRegion
from ..common.audio_timeline import AudioTimeline


def render_summary_stage(
    scene: Scene,
    doc: LectureDoc,
    summary_region: SummaryRegion,
    tex_template,
    timeline: AudioTimeline,
):
    for bi, beat in enumerate(doc.summary.beats):
        seg = timeline.find("summary", -1, bi)
        if seg is None:
            continue

        _sync_to(scene, seg.start_time)

        if beat.show is not None:
            mob = build_block(beat.show, tex_template=tex_template)
            summary_region.add_takeaway(mob, scene, run_time=0.8)

        _sync_to(scene, seg.end_time)


def _sync_to(scene: Scene, target_time: float):
    current = scene.renderer.time
    wait = target_time - current
    if wait > 0.05:
        scene.wait(wait)
