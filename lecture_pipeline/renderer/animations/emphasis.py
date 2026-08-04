"""
强调动画（recall 使用）。
"""

from __future__ import annotations

from manim import Indicate, Flash, FocusOn, Circle, Create, FadeOut

from ..schema import RecallAction


def emphasis_animation(mob, action: RecallAction = RecallAction.INDICATE):
    """
    为已存在的 Mobject 生成强调动画。
    """
    if action == RecallAction.INDICATE:
        return Indicate(mob)
    if action == RecallAction.CIRCLE:
        # 画一个圆圈包围 mob（Create + Fade）
        c = Circle(
            radius=max(mob.width, mob.height) * 0.6,
            color="#C8102E",
            stroke_width=3,
        )
        c.move_to(mob.get_center())
        return Create(c)  # 调用方可能想随后 FadeOut，此处只做 Create
    if action == RecallAction.FOCUS:
        return FocusOn(mob.get_center())
    if action == RecallAction.HIGHLIGHT:
        return Indicate(mob, scale_factor=1.15, color="#D4A017")
    if action == RecallAction.UNDERLINE:
        from manim import Underline
        line = Underline(mob, color="#C8102E")
        return Create(line)

    # 兜底
    return Indicate(mob)
