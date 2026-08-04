"""
Region 基类

每个 Region 负责：
- 知道自己在屏幕上的位置和尺寸
- 管理自己区域内的 Mobject 生命周期
- 接受 Block 对象，将其正确摆放、动画入场
- 处理区域内的滚动/清屏（如 BoardRegion）
"""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, Optional

from manim import VGroup, Scene

from ..theme import RegionBox


if TYPE_CHECKING:
    from manim import Mobject


class Region(ABC):
    """
    所有 Region 的基类。

    约定：Region 不拥有 Scene，但在被 Scene 调用时接收它以 play 动画。
    """

    def __init__(self, box: RegionBox, name: str = ""):
        self.box = box
        self.name = name or self.__class__.__name__
        # 区域内所有活跃的 Mobject 组
        self.content: VGroup = VGroup()

    @property
    def left(self) -> float:
        return self.box.x

    @property
    def right(self) -> float:
        return self.box.x + self.box.width

    @property
    def top(self) -> float:
        return self.box.y

    @property
    def bottom(self) -> float:
        return self.box.y - self.box.height

    @property
    def center_x(self) -> float:
        return self.box.x + self.box.width / 2

    @property
    def center_y(self) -> float:
        return self.box.y - self.box.height / 2

    def clear(self, scene: Optional[Scene] = None, run_time: float = 0.3) -> None:
        """清空区域内所有内容。若给 scene 则播 FadeOut 动画"""
        if not self.content:
            return
        if scene is not None:
            from manim import FadeOut
            scene.play(FadeOut(self.content), run_time=run_time)
        else:
            # 静默清除（初始化或非 play 场景）
            pass
        self.content = VGroup()

    def __repr__(self) -> str:
        return f"<{self.name} box={self.box} items={len(self.content)}>"
