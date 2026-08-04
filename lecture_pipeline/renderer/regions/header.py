"""
HeaderRegion · 顶栏

讲题阶段和升华阶段常驻。结构：
  [标题文字]  ← mainblue 加粗无衬线
  ──────────  ← 0.8pt mainblue 细线
"""

from __future__ import annotations

from manim import Text, Line, VGroup, Write, Create, LEFT, RIGHT, DOWN, UP

from ..theme import (
    HEADER_BOX, MAIN_BLUE, FONT_SIZE_HEADER_TITLE, FONT_TITLE,
    HEADER_RULE_THICKNESS, color_hex_to_manim,
    HEADER_RULE_Y, HEADER_RULE_X_LEFT, HEADER_RULE_X_RIGHT,
)
from .base import Region


class HeaderRegion(Region):
    """
    顶栏。读题阶段隐藏，讲题/升华阶段常驻。
    """

    def __init__(self, title_text: str, tex_template=None):
        super().__init__(HEADER_BOX, name="Header")
        self.title_text = title_text
        self.tex_template = tex_template
        self._title_mob = None
        self._rule_mob = None

    def build(self) -> VGroup:
        """构建 Mobject（不 play）。返回 VGroup 方便整组控制"""
        if "$" in self.title_text:
            from ..blocks.text_mixin import create_mixed_tex
            title = create_mixed_tex(
                self.title_text,
                font_size=FONT_SIZE_HEADER_TITLE,
                color=color_hex_to_manim(MAIN_BLUE),
                tex_template=self.tex_template,
                font=FONT_TITLE,
            )
        else:
            title = Text(
                self.title_text,
                font=FONT_TITLE,
                # 不加粗，避免字体显得太粗
                font_size=FONT_SIZE_HEADER_TITLE,
                color=color_hex_to_manim(MAIN_BLUE),
            )
        # 左对齐放到顶栏左缘（留 0.5 单位边距）。整体下移（title 居顶栏上半）
        title.move_to([self.left + 0.5 + title.width / 2, self.top - 0.25, 0])

        # 细线从左到右贯穿（title 下方）。位置取自 theme 常量，与题干卡片上沿共用。
        rule = Line(
            start=[HEADER_RULE_X_LEFT, HEADER_RULE_Y, 0],
            end=[HEADER_RULE_X_RIGHT, HEADER_RULE_Y, 0],
            color=color_hex_to_manim(MAIN_BLUE),
            stroke_width=0.6,
        )

        self._title_mob = title
        self._rule_mob = rule
        self.content = VGroup(title, rule)
        return self.content

    def play_appearance(self, scene, run_time: float = 1.0):
        """读题阶段结束后，顶栏浮现的动画"""
        if self._title_mob is None:
            self.build()
        # 3D 模式锁帧
        if hasattr(scene, "add_fixed_in_frame_mobjects"):
            try:
                scene.add_fixed_in_frame_mobjects(self._title_mob, self._rule_mob)
            except Exception:
                pass
        from manim import Write, Create
        scene.play(
            Write(self._title_mob),
            Create(self._rule_mob),
            run_time=run_time,
        )
