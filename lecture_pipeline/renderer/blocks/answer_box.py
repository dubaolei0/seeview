"""
answer_box · 答案框

视觉：米黄底板 + 深蓝边框（略粗） + 阴影 + 加粗正文
"""

from __future__ import annotations

from manim import VGroup

from ..theme import (
    FONT_SIZE_ANSWER, BG_YELLOW, TEXT_DARK, BOARD_BOX_A,
    MAIN_BLUE, color_hex_to_manim,
)
from ..schema import Show
from .text_mixin import create_mixed_tex
from .card_decor import build_card_background


def build_answer_box(show: Show, tex_template=None) -> VGroup:
    body = show.body or ""

    content = create_mixed_tex(
        body,
        font_size=FONT_SIZE_ANSWER,
        color=color_hex_to_manim(TEXT_DARK),
        tex_template=tex_template,
        max_width_cm=BOARD_BOX_A.width * 0.85,
    )

    return build_card_background(
        content,
        fill_color=BG_YELLOW,
        border_color=MAIN_BLUE,
        shadow=True,
    )
