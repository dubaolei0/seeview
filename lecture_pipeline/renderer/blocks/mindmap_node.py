"""
mindmap_node · 思维导图节点

MVP 简化实现：就是一个带圆角边框的小 block，手动定位由 SummaryRegion 决定。
真正的树状连线留到 Phase 2。
"""

from __future__ import annotations

from manim import VGroup, Text, RoundedRectangle

from ..theme import (
    FONT_SIZE_MINDMAP, MAIN_BLUE, BG_BLUE, TEXT_DARK,
    FONT_KAI, CARD_INNER_PADDING, color_hex_to_manim,
)
from ..schema import Show


def build_mindmap_node(show: Show, tex_template=None) -> VGroup:
    body = show.body or ""

    text_mob = Text(
        body,
        font=FONT_KAI,
        font_size=FONT_SIZE_MINDMAP,
        color=color_hex_to_manim(TEXT_DARK),
    )

    padding = CARD_INNER_PADDING
    bg = RoundedRectangle(
        width=text_mob.width + 2 * padding,
        height=text_mob.height + 2 * padding,
        corner_radius=0.15,
        fill_color=color_hex_to_manim(BG_BLUE),
        fill_opacity=1.0,
        stroke_color=color_hex_to_manim(MAIN_BLUE),
        stroke_width=2,
    )
    bg.move_to(text_mob.get_center())

    return VGroup(bg, text_mob)
