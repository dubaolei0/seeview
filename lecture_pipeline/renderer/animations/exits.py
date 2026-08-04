"""
退场动画（MVP 简化版）。
"""

from __future__ import annotations

from manim import FadeOut, LEFT


def exit_animation(mob, kind: str = "fade_out"):
    if kind == "fade_out":
        return FadeOut(mob)
    if kind == "shift_out":
        return mob.animate.shift(LEFT * 5).fade(1)
    if kind == "shrink_to":
        return mob.animate.scale(0.2).shift(LEFT * 5).fade(1)
    return FadeOut(mob)
