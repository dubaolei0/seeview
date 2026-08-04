"""
knowledge_card · 知识卡片

视觉：米黄底板（BG_YELLOW）+ 深蓝边框 + 阴影 + 楷体蓝色标题 + 宋体项目符号要点
"""

from __future__ import annotations

from manim import VGroup, Text, DOWN, LEFT

from ..theme import (
    FONT_SIZE_KNOWLEDGE_TITLE, FONT_SIZE_KNOWLEDGE_BODY,
    MAIN_BLUE, BG_YELLOW, TEXT_DARK, BOARD_BOX_A,
    CARD_INNER_PADDING, FONT_KAI, FONT_SONG, color_hex_to_manim,
)
from ..schema import Show
from .text_mixin import create_mixed_tex
from .card_decor import build_card_background


def build_knowledge_card(show: Show, tex_template=None) -> VGroup:
    """返回整张 knowledge_card 的 VGroup（阴影 + 底板 + 标题 + 正文/要点）"""
    title_text = show.title or ""
    body_text = show.body
    points = show.points or []

    # 内容列（先堆起来，不加背景）
    content_items: list = []

    if title_text:
        if "$" in title_text:
            # 含 LaTeX：走 mixed_tex（楷体中文 + 数学公式混排）
            title_mob = create_mixed_tex(
                title_text,
                font_size=FONT_SIZE_KNOWLEDGE_TITLE,
                color=color_hex_to_manim(MAIN_BLUE),
                tex_template=tex_template,
                font=FONT_KAI,
            )
        else:
            # 纯文本：保留 Text 路径，避免 mixed_tex 的字号偏差
            title_mob = Text(
                title_text,
                font=FONT_KAI,
                font_size=FONT_SIZE_KNOWLEDGE_TITLE,
                color=color_hex_to_manim(MAIN_BLUE),
            )
        content_items.append(title_mob)

    if body_text:
        body_mob = create_mixed_tex(
            body_text,
            font_size=FONT_SIZE_KNOWLEDGE_BODY,
            color=color_hex_to_manim(TEXT_DARK),
            tex_template=tex_template,
            max_width_cm=BOARD_BOX_A.width * 0.85,
        )
        content_items.append(body_mob)

    for pt in points:
        bullet = create_mixed_tex(
            f"• {pt}",
            font_size=FONT_SIZE_KNOWLEDGE_BODY,
            color=color_hex_to_manim(TEXT_DARK),
            tex_template=tex_template,
            max_width_cm=BOARD_BOX_A.width * 0.85,
        )
        content_items.append(bullet)

    if not content_items:
        return VGroup()

    content_group = VGroup(*content_items)
    content_group.arrange(DOWN, aligned_edge=LEFT, buff=0.3)

    return build_card_background(
        content_group,
        fill_color=BG_YELLOW,
        border_color=MAIN_BLUE,
        shadow=True,
    )
