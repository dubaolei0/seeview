"""
AnchorRegion · 锚点栏

布局 A 中的右侧区域，显示题干的关键条件（keypoint 列表）。
讲题阶段和升华阶段常驻，内容不变。

视觉：
  ┌────────────────┐
  │  已知           │  ← 标签左对齐
  │  ─────         │
  │  条件 1         │
  │  条件 2         │
  │  ...           │
  └────────────────┘

实现策略：
- 背景板宽度 = ANCHOR_BOX.width（固定），不按内容自适应，避免被截或悬空
- card 居中对齐到 ANCHOR_BOX 中心
- 内部内容左对齐靠近推导主区一侧
"""

from __future__ import annotations

from manim import VGroup, Text, Line, FadeIn, RoundedRectangle, DOWN, RIGHT, LEFT

from ..theme import (
    ANCHOR_BOX, FONT_SONG, FONT_SIZE_KEYPOINT_LABEL, FONT_SIZE_KEYPOINT_ITEM,
    MAIN_BLUE, TEXT_MUTED, TEXT_DARK, BG_ANCHOR, RULE_GREY, BLOCK_SPACING,
    CARD_INNER_PADDING, CARD_CORNER_RADIUS,
    SHADOW_COLOR, SHADOW_OPACITY, SHADOW_OFFSET,
    color_hex_to_manim,
)
from ..blocks.text_mixin import create_mixed_tex
from .base import Region


class AnchorRegion(Region):
    """锚点栏。在布局 A / D 下使用。背景板宽度固定 = box.width"""

    def __init__(self, keypoints: list[str], tex_template=None, box: 'RegionBox | None' = None):
        super().__init__(box or ANCHOR_BOX, name="Anchor")
        self.keypoints = keypoints
        self.tex_template = tex_template

    def build(self) -> VGroup:
        """构建锚点栏：卡片宽度按内容自适应（不超过 box.width），避免短条件时卡片过宽。"""
        # 1. box.width 仅作为上限；超宽条目在此上限内换行/缩放
        box_max_w = self.box.width - 0.15
        padding = CARD_INNER_PADDING * 0.7
        content_cap = box_max_w - 2 * padding     # 条目宽度上限

        # "已知" 标签
        label = Text(
            "已知",
            font=FONT_SONG,
            font_size=FONT_SIZE_KEYPOINT_LABEL,
            color=color_hex_to_manim(TEXT_MUTED),
        )

        # 逐条 keypoint：自然渲染，超过上限才缩
        item_mobs: list = []
        for kp in self.keypoints:
            item = create_mixed_tex(
                kp,
                font_size=FONT_SIZE_KEYPOINT_ITEM,
                color=color_hex_to_manim(TEXT_DARK),
                tex_template=self.tex_template,
            )
            if item.width > content_cap:
                item.scale(content_cap / item.width)
            item_mobs.append(item)

        # 卡片宽度 = 内容自然宽（label / 各条目里最宽者）+ 内边距，再以 box 宽为上限
        natural_w = max([label.width] + [m.width for m in item_mobs]) if item_mobs else label.width
        card_width = min(box_max_w, natural_w + 2 * padding)
        content_w = card_width - 2 * padding

        # 细分割线（与内容同宽）
        rule = Line(
            start=[0, 0, 0],
            end=[content_w, 0, 0],
            color=color_hex_to_manim(RULE_GREY),
            stroke_width=0.5,
        )

        inner_group = VGroup(label, rule, *item_mobs)
        inner_group.arrange(DOWN, aligned_edge=LEFT, buff=BLOCK_SPACING * 0.45)

        # 2. 高度 = 内容自然高度 + padding
        card_height = inner_group.height + 2 * padding
        max_card_h = self.box.height - 0.3
        if card_height > max_card_h:
            scale = max_card_h / card_height
            inner_group.scale(scale)
            card_height = inner_group.height + 2 * padding

        # 3. 背景板
        bg = RoundedRectangle(
            width=card_width,
            height=card_height,
            corner_radius=CARD_CORNER_RADIUS,
            fill_color=color_hex_to_manim(BG_ANCHOR),
            fill_opacity=1.0,
            stroke_color=color_hex_to_manim(RULE_GREY),
            stroke_width=0.8,
        )

        # 4. 阴影
        shadow = RoundedRectangle(
            width=card_width,
            height=card_height,
            corner_radius=CARD_CORNER_RADIUS,
            fill_color=color_hex_to_manim(SHADOW_COLOR),
            fill_opacity=SHADOW_OPACITY,
            stroke_width=0,
        )
        shadow.shift([SHADOW_OFFSET[0], SHADOW_OFFSET[1], 0])

        # 5. 组装
        card = VGroup(shadow, bg, inner_group)

        # 6. 顶对齐到 ANCHOR_BOX
        top_y = self.box.y
        bg_center_y = top_y - card_height / 2 - 0.05
        card.move_to([self.center_x, bg_center_y, 0])

        # 7. inner_group 左对齐 + 顶对齐到 bg 内部
        inner_group.move_to([
            bg.get_left()[0] + padding + inner_group.width / 2,
            bg.get_top()[1] - padding - inner_group.height / 2,
            0,
        ])

        self.content = card
        return card

    def play_appearance(self, scene, run_time: float = 0.8):
        """从右侧淡入"""
        if not self.content:
            self.build()
        # 3D 锁帧
        if hasattr(scene, "add_fixed_in_frame_mobjects"):
            try:
                scene.add_fixed_in_frame_mobjects(self.content)
            except Exception:
                pass
        self.content.shift(RIGHT * 1.5)
        scene.play(
            self.content.animate.shift(LEFT * 1.5),
            FadeIn(self.content),
            run_time=run_time,
        )
