"""
SummaryRegion · 升华主区

升华阶段替代 Board。主要呈现两种内容：
- 一串 takeaway 条目（垂直排列、依次浮现）
- 思维导图（多个 mindmap_node + 连线）

MVP 只做 takeaway 形式。思维导图 Phase 2。
"""

from __future__ import annotations

from manim import VGroup, Scene, FadeIn, DOWN, LEFT, UP

from ..theme import BOARD_BOX_A, BLOCK_SPACING, DEFAULT_RUN_TIME
from .base import Region


class SummaryRegion(Region):
    """
    升华主区。占据讲题主区 + 锚点区的位置（几乎全宽）。
    """

    def __init__(self):
        # 升华时内容居中，用更宽的框
        from ..theme import SCREEN_WIDTH, SCREEN_HEIGHT
        from ..theme import RegionBox
        wide_box = RegionBox(
            x=-SCREEN_WIDTH / 2 + 1.0,
            y=SCREEN_HEIGHT / 2 - 1.2,
            width=SCREEN_WIDTH - 2.0,
            height=SCREEN_HEIGHT - 2.0,
        )
        super().__init__(wide_box, name="Summary")
        self.items: list = []
        # 3D 模式锁帧
        self.fixed_frame_scene = None

    def _lock_to_frame(self, mob):
        if self.fixed_frame_scene is None:
            return
        try:
            self.fixed_frame_scene.add_fixed_in_frame_mobjects(mob)
        except Exception:
            pass

    def add_takeaway(self, mob, scene: Scene, run_time: float = DEFAULT_RUN_TIME):
        """
        依次添加 takeaway 并保持整体垂直居中。
        - 第一条：直接放屏幕中心淡入
        - 后续条：老条平移到新目标位置，新条从下方 FadeIn
        """
        from manim import FadeIn as _FadeIn

        if not self.items:
            self.items.append(mob)
            self.content.add(mob)
            mob.move_to([self.center_x, self.center_y, 0])
            self._lock_to_frame(mob)
            scene.play(_FadeIn(mob, shift=DOWN * 0.3), run_time=run_time)
            return

        # 多条：记录旧 items 的原始位置
        old_items = list(self.items)
        old_positions = [item.get_center().copy() for item in old_items]

        # 临时构建完整组排版，得到目标位置（arrange 会改子对象位置）
        temp_group = VGroup(*old_items, mob)
        temp_group.arrange(DOWN, buff=BLOCK_SPACING * 1.5, aligned_edge=LEFT)
        temp_group.move_to([self.center_x, self.center_y, 0])

        target_positions_old = [item.get_center().copy() for item in old_items]
        target_position_new = mob.get_center().copy()

        # 恢复旧 items 原位置 → 用 animate 平滑迁移到新位置
        for item, orig_pos in zip(old_items, old_positions):
            item.move_to(orig_pos)

        # 新 mob 先置于目标位置略下方，FadeIn 上移
        mob.move_to(target_position_new).shift(DOWN * 0.3)
        self._lock_to_frame(mob)

        anims = [
            item.animate.move_to(target_pos)
            for item, target_pos in zip(old_items, target_positions_old)
        ]
        anims.append(_FadeIn(mob, shift=UP * 0.3))

        scene.play(*anims, run_time=run_time)

        self.items.append(mob)
        self.content.add(mob)

    def fade_out_all(self, scene: Scene, run_time: float = 0.5):
        if not self.items:
            return
        from manim import FadeOut
        group = VGroup(*self.items)
        scene.play(FadeOut(group), run_time=run_time)
        self.content = VGroup()
        self.items = []
