"""
wow_formula · 顿悟公式

视觉（方向 B，简化版 - 只保留一层框）：
- 琥珀金描边（较粗）
- 半透明金底（米黄加深一度）
- 阴影（让徽章感不丢）
- 超大号金色公式 + 下方小字 caption
"""

from __future__ import annotations

from manim import VGroup, MathTex, Text, RoundedRectangle, DOWN

from ..theme import (
    FONT_SIZE_WOW, FONT_SIZE_WOW_CAPTION, INSIGHT_GOLD, TEXT_MUTED,
    FONT_SONG, FONT_WOW, CARD_INNER_PADDING, CARD_CORNER_RADIUS, CARD_BORDER_WIDTH,
    SHADOW_COLOR, SHADOW_OPACITY, SHADOW_OFFSET,
    color_hex_to_manim,
)
from ..schema import Show
from .text_mixin import create_mixed_tex


# 金色系自有色板
WOW_FILL = "#FDEFCF"        # 半透明金底（比普通 yellowbox 更亮）

# 顿悟卡内容的最大宽度（Manim 单位）。
# 推导：present_centered 之后整卡还会再 ×1.25，再加左右内边距≈1.04，
#       9.4 × 1.25 + 1.04×1.25 ≈ 13.05 < 屏宽 14.22，左右各留 ≈0.58 安全边。
# hero（formula/body）与 caption 各自独立按此限宽，互不牵连：
# 下面 caption 再长，也只缩 caption 自己，绝不连累上面的大金字。
WOW_MAX_WIDTH = 9.4

# minipage 换行宽度（cm）。标定：manim 宽 ≈ 0.706 × cm，故 9.4 / 0.706 ≈ 13.3cm。
# body(hero) 与 caption 都用这同一预算换行 → "宽度根据最大的来"，
# caption 不再被写死的窄 6.5cm 挤成小一团；仍是固定值，与对方无关。
WOW_MAX_WIDTH_CM = round(WOW_MAX_WIDTH / 0.706, 1)  # ≈ 13.3


def _fit_width(mob, max_width: float):
    """超宽时按比例缩小到 max_width；从不放大。每个元素独立调用，彼此互不影响。"""
    if max_width > 0 and mob.width > max_width:
        mob.scale(max_width / mob.width)
    return mob


def build_wow_formula(show: Show, tex_template=None) -> VGroup:
    formula_text = show.formula or ""
    body_text = show.body or ""
    caption_text = show.caption or ""

    # 1. 公式本体
    # 优先级：formula（纯 LaTeX，走 MathTex）→ body（可能含中文/$...$ 混排，走 mixed_tex）
    if formula_text:
        # formula 路径（纯 LaTeX）：MathTex 不会自动换行，超长靠 _fit_width 等比缩字
        formula_mob = MathTex(
            formula_text,
            tex_template=tex_template,
            font_size=FONT_SIZE_WOW,
            color=color_hex_to_manim(INSIGHT_GOLD),
        )
    elif body_text:
        # body 路径：用 minipage（Tex 而非 MathTex），让中文+混排都能渲染并自动换行
        formula_mob = create_mixed_tex(
            body_text,
            font_size=FONT_SIZE_WOW,
            color=color_hex_to_manim(INSIGHT_GOLD),
            tex_template=tex_template,
            max_width_cm=WOW_MAX_WIDTH_CM,
            font=FONT_WOW,            # wow 强调汉字用马善政毛笔
        )
    else:
        formula_mob = MathTex(
            "",
            tex_template=tex_template,
            font_size=FONT_SIZE_WOW,
            color=color_hex_to_manim(INSIGHT_GOLD),
        )

    # hero 独立限宽：只看 hero 自己的宽度，超了就缩它自己
    _fit_width(formula_mob, WOW_MAX_WIDTH)

    content_items = [formula_mob]
    if caption_text:
        if "$" in caption_text:
            # caption 含 LaTeX：走 mixed_tex（带宽度约束，避免过长）
            caption_mob = create_mixed_tex(
                caption_text,
                font_size=FONT_SIZE_WOW_CAPTION,
                color=color_hex_to_manim(TEXT_MUTED),
                tex_template=tex_template,
                max_width_cm=WOW_MAX_WIDTH_CM,
            )
        else:
            caption_mob = Text(
                caption_text,
                font=FONT_SONG,
                font_size=FONT_SIZE_WOW_CAPTION,
                color=color_hex_to_manim(TEXT_MUTED),
            )
        # caption 独立限宽：只看 caption 自己的宽度，缩它自己，绝不回头动 hero
        _fit_width(caption_mob, WOW_MAX_WIDTH)
        caption_mob.next_to(formula_mob, DOWN, buff=0.3)
        content_items.append(caption_mob)

    content = VGroup(*content_items)

    # 2. 金框（唯一一层）
    pad = CARD_INNER_PADDING * 1.3
    frame = RoundedRectangle(
        width=content.width + 2 * pad,
        height=content.height + 2 * pad,
        corner_radius=CARD_CORNER_RADIUS * 1.2,
        fill_color=color_hex_to_manim(WOW_FILL),
        fill_opacity=1.0,
        stroke_color=color_hex_to_manim(INSIGHT_GOLD),
        stroke_width=CARD_BORDER_WIDTH * 1.8,
    )
    frame.move_to(content.get_center())

    # 3. 阴影（偏移比常规卡片更大，强化"浮起"感）
    shadow = RoundedRectangle(
        width=frame.width,
        height=frame.height,
        corner_radius=CARD_CORNER_RADIUS * 1.2,
        fill_color=color_hex_to_manim(SHADOW_COLOR),
        fill_opacity=SHADOW_OPACITY * 1.5,
        stroke_width=0,
    )
    shadow.move_to([
        frame.get_center()[0] + SHADOW_OFFSET[0] * 1.5,
        frame.get_center()[1] + SHADOW_OFFSET[1] * 1.5,
        0,
    ])

    return VGroup(shadow, frame, content)
