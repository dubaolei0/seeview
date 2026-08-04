"""
takeaway · 升华心法条

视觉：楷体大号 + 可选序号前缀 + 箭头图标。
"""

from __future__ import annotations

from manim import VGroup, Text, LEFT

from ..theme import (
    FONT_SIZE_TAKEAWAY, MAIN_BLUE, TEXT_DARK, FONT_TAKEAWAY,
    SCREEN_WIDTH,
    color_hex_to_manim,
)
from ..schema import Show
from .text_mixin import create_mixed_tex


def build_takeaway(show: Show, tex_template=None) -> VGroup:
    body = show.body or ""
    number = show.number

    items: list = []

    # 序号/箭头前缀。三角用 \blacktriangleright（amssymb 保证有字形）；
    # 不再用 Unicode ▸ + 系统字体（思源宋体无该符号会出豆腐块）。
    if number is not None:
        prefix_src = f"{_num_cn(number)} " + r"$\blacktriangleright$"
    else:
        prefix_src = r"$\blacktriangleright$"

    prefix_mob = create_mixed_tex(
        prefix_src,
        font_size=FONT_SIZE_TAKEAWAY,
        color=color_hex_to_manim(MAIN_BLUE),
        tex_template=tex_template,
        font=FONT_TAKEAWAY,          # 序号文字与正文同字体（楷体），不再用宋体显得割裂
    )
    items.append(prefix_mob)

    # 正文：用 minipage 包裹，让长 takeaway 自动换行，不溢出屏幕
    # SummaryRegion 总宽 ≈ SCREEN_WIDTH - 2.0；前缀和 buff 占 ~2 单位
    max_width_cm = SCREEN_WIDTH - 4.0

    body_mob = create_mixed_tex(
        body,
        font_size=FONT_SIZE_TAKEAWAY,
        color=color_hex_to_manim(TEXT_DARK),
        tex_template=tex_template,
        font=FONT_TAKEAWAY,
        max_width_cm=max_width_cm,
    )
    items.append(body_mob)

    group = VGroup(*items)
    group.arrange_submobjects(buff=0.3)
    return group


_CN_NUMS = {1: "第一", 2: "第二", 3: "第三", 4: "第四", 5: "第五"}


def _num_cn(n: int) -> str:
    return _CN_NUMS.get(n, f"第 {n}")
