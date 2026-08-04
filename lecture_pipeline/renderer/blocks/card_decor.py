"""
卡片装饰工厂：给任意 content Mobject 加「阴影 + 圆角底 + 边框」三层视觉。

使用：
    card_bg = build_card_background(content, fill="#E8DDB5", border="#B45309")
    # 返回一个 VGroup，里面先是阴影、然后底板、再是内容
    # 调用方用 group.move_to(...) 定位即可
"""

from __future__ import annotations

from manim import VGroup, RoundedRectangle

from ..theme import (
    CARD_INNER_PADDING, CARD_CORNER_RADIUS, CARD_BORDER_WIDTH,
    SHADOW_COLOR, SHADOW_OPACITY, SHADOW_OFFSET, color_hex_to_manim,
)


def build_card_background(
    content,
    fill_color: str,
    border_color: str | None = None,
    padding: float = CARD_INNER_PADDING,
    corner_radius: float = CARD_CORNER_RADIUS,
    shadow: bool = True,
    border_width: float = CARD_BORDER_WIDTH,
) -> VGroup:
    """
    给一个 content Mobject 包装成「卡片」：阴影 + 圆角底（可选边框）。

    返回的 VGroup 结构：[shadow, bg, content]，按先后顺序绘制（shadow 最底层）。
    调用方 move_to() 整组即可，不需要关心内部元素位置。

    Args:
        content: 内容 Mobject（会被包进结果 VGroup）
        fill_color: 底色 hex
        border_color: 边框色 hex，None 表示无边框
        padding: 内边距
        corner_radius: 圆角半径
        shadow: 是否加阴影（半透明灰色偏移）
        border_width: 边框笔画宽度

    Returns:
        VGroup(shadow, bg, content)
    """
    w = content.width + 2 * padding
    h = content.height + 2 * padding

    # 底板
    bg = RoundedRectangle(
        width=w,
        height=h,
        corner_radius=corner_radius,
        fill_color=color_hex_to_manim(fill_color),
        fill_opacity=1.0,
        stroke_color=(
            color_hex_to_manim(border_color) if border_color else color_hex_to_manim(fill_color)
        ),
        stroke_width=border_width if border_color else 0,
    )
    bg.move_to(content.get_center())

    pieces = []

    # 阴影（放在底板下方偏右下，制造浮起感）
    if shadow:
        shadow_mob = RoundedRectangle(
            width=w,
            height=h,
            corner_radius=corner_radius,
            fill_color=color_hex_to_manim(SHADOW_COLOR),
            fill_opacity=SHADOW_OPACITY,
            stroke_width=0,
        )
        shadow_mob.move_to([
            bg.get_center()[0] + SHADOW_OFFSET[0],
            bg.get_center()[1] + SHADOW_OFFSET[1],
            0,
        ])
        pieces.append(shadow_mob)

    pieces.append(bg)
    pieces.append(content)

    return VGroup(*pieces)
