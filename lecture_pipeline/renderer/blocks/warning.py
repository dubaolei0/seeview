"""
warning · 易错提示框

视觉：浅色底 + 深朱红粗边框 + 左上朱红圆角标签
"""

from __future__ import annotations

from manim import VGroup, Text, RoundedRectangle

from ..theme import (
    FONT_SIZE_WARNING, MAIN_PINK, EYE_WHITE, TEXT_DARK,
    BOARD_BOX_A, CARD_INNER_PADDING, CARD_CORNER_RADIUS, CARD_BORDER_WIDTH,
    FONT_SONG, color_hex_to_manim,
)
from ..schema import Show
from .text_mixin import create_mixed_tex, create_mixed_tex_for_screen_width


# warning 的自有底色：极浅红（比主背景更亮一点，有"提示感"）
WARN_FILL = "#FBEDED"


def build_warning(show: Show, tex_template=None, target_screen_width: float | None = None) -> VGroup:
    body = show.body or ""
    label_text = show.label or "注意"

    if target_screen_width is not None:
        content = create_mixed_tex_for_screen_width(
            body,
            target_screen_width,
            font_size=FONT_SIZE_WARNING,
            color=color_hex_to_manim(TEXT_DARK),
            tex_template=tex_template,
        )
    else:
        content = create_mixed_tex(
            body,
            font_size=FONT_SIZE_WARNING,
            color=color_hex_to_manim(TEXT_DARK),
            tex_template=tex_template,
            max_width_cm=BOARD_BOX_A.width * 0.85,
        )

    # 边框（实线，不用虚线）
    padding = CARD_INNER_PADDING
    border = RoundedRectangle(
        width=content.width + 2 * padding,
        height=content.height + 2 * padding,
        corner_radius=CARD_CORNER_RADIUS,
        stroke_color=color_hex_to_manim(MAIN_PINK),
        stroke_width=CARD_BORDER_WIDTH * 1.3,
        fill_color=color_hex_to_manim(WARN_FILL),
        fill_opacity=1.0,
    )
    border.move_to(content.get_center())

    # 左上角圆角标签
    label = Text(
        label_text,
        font=FONT_SONG,
        weight="BOLD",
        font_size=FONT_SIZE_WARNING - 4,
        color="#FFFFFF",
    )
    label_bg = RoundedRectangle(
        width=label.width + 0.35,
        height=label.height + 0.2,
        corner_radius=0.09,
        fill_color=color_hex_to_manim(MAIN_PINK),
        fill_opacity=1.0,
        stroke_width=0,
    )
    label_bg.move_to(label.get_center())
    label_group = VGroup(label_bg, label)
    # 定位到 border 左上角（略偏向外侧，给"从卡片出发的徽章"感）
    label_group.move_to([
        border.get_left()[0] + label_bg.width / 2 + 0.25,
        border.get_top()[1],
        0,
    ])

    return VGroup(border, content, label_group)
