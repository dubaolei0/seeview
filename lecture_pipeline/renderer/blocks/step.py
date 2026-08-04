"""
step · 推导一步

默认字体、黑色、Write 动画。
支持 emphasis 字段（在 body 中高亮若干片段，但 MVP 暂不实现精细高亮，
整条 step 统一样式即可，强调通过单独 emphasis block 或 Indicate 动画实现）。

特殊：show.replace_prev=True 时，body 应该是纯 LaTeX 公式（不含中文），
渲染器会用 MathTex 直接构造，由 board 用 TransformMatchingTex 替换上一个 step。
"""

from __future__ import annotations

from manim import MathTex

from ..theme import FONT_SIZE_STEP, TEXT_DARK, BOARD_BOX_A, color_hex_to_manim
from ..schema import Show
from .text_mixin import create_mixed_tex, create_mixed_tex_for_screen_width


def build_step(show: Show, tex_template=None, target_screen_width: float | None = None):
    """返回 step 对应的 Mobject"""
    body = show.body or ""

    # replace_prev 模式：body 必须是纯 LaTeX，用 MathTex 构造（让 TransformMatchingTex 能匹配）
    if show.replace_prev:
        # 去除最外层 $...$（如果有）
        formula = body.strip()
        if formula.startswith("$") and formula.endswith("$"):
            formula = formula[1:-1]
        try:
            return MathTex(
                formula,
                tex_template=tex_template,
                color=color_hex_to_manim(TEXT_DARK),
                font_size=FONT_SIZE_STEP,
            )
        except Exception as e:
            print(f"[build_step] replace_prev MathTex 失败，回退普通 step: {e}")

    # 普通模式：minipage 包裹，支持中英文混排
    if target_screen_width is not None:
        return create_mixed_tex_for_screen_width(
            body,
            target_screen_width,
            font_size=FONT_SIZE_STEP,
            color=color_hex_to_manim(TEXT_DARK),
            tex_template=tex_template,
        )

    max_width_cm = BOARD_BOX_A.width * 0.95
    return create_mixed_tex(
        body,
        font_size=FONT_SIZE_STEP,
        color=TEXT_DARK,
        tex_template=tex_template,
        max_width_cm=max_width_cm,
    )
