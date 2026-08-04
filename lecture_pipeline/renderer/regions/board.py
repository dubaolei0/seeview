"""
BoardRegion · 推导主区（核心）

讲题阶段的主要工作区。负责：
- 接受 Block Mobject，按"板书式向下写"方式摆位
- 超出底部时自动滚动（最上面的 fade out，其余上移）
- 提供"居中呈现 + 结束消失"机制（knowledge_card / wow_formula 用）
- 提供"最近加入的 N 个 block"索引（给 recall 用）
- 提供 clear/dim（为 transition 服务）
"""

from __future__ import annotations

from typing import Optional

from manim import VGroup, Scene, FadeOut, Write, Create, FadeIn, GrowFromCenter, UP, LEFT

from ..theme import (
    BOARD_BOX_A, BOARD_BOX_B, BOARD_BOX_C, BOARD_BOX_D,
    BLOCK_SPACING, FAST_RUN_TIME, DEFAULT_RUN_TIME,
    BOARD_B_FLOW_WIDTH_RATIO,
)
from .base import Region


class BoardRegion(Region):
    """
    推导主区。讲题阶段核心。

    使用方法：
        board = BoardRegion(layout_branch='A')
        # 常规 block（step/answer_box/warning）
        board.add_block(mob, scene)
        # 居中呈现（knowledge_card/wow_formula）
        token = board.present_centered(mob, scene)
        ... 讲解期间 ...
        board.dismiss_centered(token, scene)
    """

    def __init__(self, layout_branch: str = "A", box=None):
        # box 显式传入则优先（题干横幅常驻时 render 会传"下压后"的框）；
        # 否则按布局选默认框：B 全宽、C/D 右侧、A 左侧。
        if box is None:
            if layout_branch == "B":
                box = BOARD_BOX_B
            elif layout_branch == "C":
                box = BOARD_BOX_C
            elif layout_branch == "D":
                box = BOARD_BOX_D
            else:
                box = BOARD_BOX_A
        super().__init__(box, name=f"Board-{layout_branch}")
        self.layout_branch = layout_branch

        # 当前光标位置（下一个 block 的上沿 y）
        self.cursor_y: float = self.top
        # 活跃推导内容（按插入顺序）
        self.items: list = []
        # 当前居中呈现的 mob（同时最多一个）
        self._centered_mob = None
        # 3D 模式下：scene 引用，用于 add_fixed_in_frame_mobjects
        self.fixed_frame_scene = None

    def left_flow_target_width(self) -> float | None:
        """左对齐板书流的目标屏幕宽度；None 表示沿用 block 默认宽度。"""
        if self.layout_branch == "B":
            return self.box.width * BOARD_B_FLOW_WIDTH_RATIO
        return None

    def _lock_to_frame(self, mob):
        """3D 模式下把 mob 锁定为屏幕坐标（不随相机旋转）"""
        if self.fixed_frame_scene is None:
            return
        try:
            self.fixed_frame_scene.add_fixed_in_frame_mobjects(mob)
        except Exception as e:
            print(f"[BoardRegion] add_fixed_in_frame_mobjects failed: {e}")

    # -----------------------------------------------------------------
    # 添加 block
    # -----------------------------------------------------------------

    def replace_last_with_match(
        self,
        new_mob,
        scene: Scene,
        run_time: float = DEFAULT_RUN_TIME,
        align: str = "left",
    ):
        """
        用 TransformMatchingTex 把上一个 block 替换成 new_mob。
        要求 self.last() 和 new_mob 都是 MathTex（或子类）。

        效果：相同的子串保留，新增 FadeIn，删除 FadeOut。比"删旧+加新"自然得多。
        """
        from manim import TransformMatchingTex, MathTex
        prev = self.last()
        if prev is None or not isinstance(prev, MathTex) or not isinstance(new_mob, MathTex):
            # 退路：当成普通 add_block
            return self.add_block(new_mob, scene, animation="write", run_time=run_time, align=align)

        # 把 new_mob 摆到 prev 的位置（保持相对 board 一致）
        new_mob.move_to(prev.get_center())

        # 3D 锁帧
        self._lock_to_frame(new_mob)

        scene.play(TransformMatchingTex(prev, new_mob), run_time=run_time)

        # 用 new_mob 顶替 prev 在 items / content 里的位置
        idx = self.items.index(prev)
        self.items[idx] = new_mob
        self.content.remove(prev)
        self.content.add(new_mob)

    def add_block(
        self,
        mob,
        scene: Scene,
        animation: str = "write",
        run_time: float = DEFAULT_RUN_TIME,
        align: str = "left",          # "left" / "center"
    ):
        """
        将一个已构建的 Mobject 加入板书区。

        Args:
            mob: 已经构建好的 Mobject（未摆位）
            scene: 当前 Scene 实例
            animation: 入场动画类型（write / fade_in / grow_from_center / create）
            run_time: 动画时长
            align: "left" 左对齐（默认，step/knowledge_card），
                   "center" 居中（answer_box/wow_formula 更合适）
        """
        # 1. 摆位
        padding_left = 0.25
        if align == "center":
            target_x = self.center_x
        else:
            target_x = self.left + padding_left + mob.width / 2
        mob.move_to([target_x, self.cursor_y - mob.height / 2, 0])

        # 2. 预判滚动：若新 mob 底部会低于区域底部，批量计算需要淘汰哪几条旧 mob
        # 合并成"一次动画"：淘汰 + 剩余上移 + 新 mob 入场，同一个 scene.play
        items_to_remove, scroll_distance = self._plan_scroll(mob)

        # 如果需要滚动，把 mob 的 y 位置上调到滚动后的正确位置
        if items_to_remove:
            # 新 cursor 位置 = 旧 cursor + 滚动距离
            new_cursor_y = self.cursor_y + scroll_distance
            # 新 mob 位置根据新 cursor
            if align == "center":
                target_x = self.center_x
            else:
                target_x = self.left + padding_left + mob.width / 2
            mob.move_to([target_x, new_cursor_y - mob.height / 2, 0])

        # 3. 合成动画列表
        from manim import VGroup as _VG
        anim_list = []

        if items_to_remove:
            # 移出的 mob 一起 FadeOut
            outgoing = _VG(*items_to_remove)
            anim_list.append(FadeOut(outgoing))

            # 剩下的 mob 一起上移
            remaining = [it for it in self.items if it not in items_to_remove]
            if remaining:
                anim_list.append(_VG(*remaining).animate.shift(UP * scroll_distance))

        # 新 mob 入场：3D 模式下先锁帧，再播动画
        self._lock_to_frame(mob)
        anim_list.append(self._make_entrance(mob, animation))

        scene.play(*anim_list, run_time=run_time)

        # 4. 更新状态
        if items_to_remove:
            # 从 items / content 中移除
            for it in items_to_remove:
                self.items.remove(it)
                self.content.remove(it)
            self.cursor_y += scroll_distance

        self.items.append(mob)
        self.content.add(mob)
        self.cursor_y -= (mob.height + BLOCK_SPACING)

    def _plan_scroll(self, new_mob):
        """
        预判：为了放下 new_mob，需要从 items 顶部淘汰几条？
        返回 (被淘汰的 mob 列表, 需要滚动的总距离)。
        不做任何动画，只做数学计算。
        """
        # new_mob 即将占用 cursor_y 到 cursor_y - new_mob.height 这段
        projected_bottom = self.cursor_y - new_mob.height
        # 已经够放
        if projected_bottom >= self.bottom or not self.items:
            return [], 0.0

        to_remove = []
        freed_height = 0.0
        for item in self.items:
            # 检查在当前状态下是否已经够放
            if projected_bottom + freed_height >= self.bottom:
                break
            to_remove.append(item)
            freed_height += item.height + BLOCK_SPACING

        return to_remove, freed_height

    def _make_entrance(self, mob, animation: str):
        anim_map = {
            "write": Write,
            "fade_in": FadeIn,
            "create": Create,
            "grow_from_center": GrowFromCenter,
        }
        Animation = anim_map.get(animation, Write)
        return Animation(mob)

    # -----------------------------------------------------------------
    # 滚动机制
    # -----------------------------------------------------------------

    def _scroll_one(self, scene: Scene):
        """
        移除最顶部的 item，其余上移腾出空间。
        """
        if not self.items:
            return

        top_item = self.items.pop(0)
        scroll_amount = top_item.height + BLOCK_SPACING

        remaining = VGroup(*self.items)
        if len(remaining) > 0:
            scene.play(
                FadeOut(top_item),
                remaining.animate.shift(UP * scroll_amount),
                run_time=FAST_RUN_TIME,
            )
        else:
            scene.play(FadeOut(top_item), run_time=FAST_RUN_TIME * 0.6)

        self.content.remove(top_item)
        self.cursor_y += scroll_amount

    # -----------------------------------------------------------------
    # 居中呈现（knowledge_card / wow_formula 用）
    # -----------------------------------------------------------------

    def present_centered(
        self,
        mob,
        scene: Scene,
        run_time: float = 1.0,
        scale: float = 1.15,
        dim_items: bool = True,
    ):
        """
        居中呈现一个 block（跨越 Board + Anchor 区域，居于屏幕中央偏上）。

        Args:
            mob: 要呈现的 Mobject
            scene: Scene
            run_time: 呈现动画时长
            scale: 相对原始尺寸的放大倍率
            dim_items: 是否把推导区已有内容 dim 到 0.25 透明度

        Returns:
            (mob, was_dimmed) 二元组，作为 token 传给 dismiss_centered
        """
        # 定位：屏幕中轴偏上
        target_x = 0.0
        target_y = 0.8
        mob.move_to([target_x, target_y, 0])
        mob.scale(scale)

        # 3D 锁帧
        self._lock_to_frame(mob)

        # dim 已有内容
        was_dimmed = False
        if dim_items and self.items:
            from manim import VGroup as _VG
            group = _VG(*self.items)
            scene.play(
                group.animate.set_opacity(0.25),
                GrowFromCenter(mob),
                run_time=run_time,
            )
            was_dimmed = True
        else:
            scene.play(GrowFromCenter(mob), run_time=run_time)

        self._centered_mob = mob
        return (mob, was_dimmed)

    def dismiss_centered(
        self,
        token,
        scene: Scene,
        run_time: float = 0.6,
    ):
        """
        居中呈现结束：mob FadeOut，推导区已有内容恢复 opacity 到 1.0。

        Args:
            token: present_centered 返回的二元组
            scene: Scene
            run_time: 消失动画时长
        """
        mob, was_dimmed = token
        from manim import VGroup as _VG

        animations = [FadeOut(mob)]
        if was_dimmed and self.items:
            animations.append(_VG(*self.items).animate.set_opacity(1.0))

        scene.play(*animations, run_time=run_time)

        if self._centered_mob is mob:
            self._centered_mob = None

    # -----------------------------------------------------------------
    # Transition 支持
    # -----------------------------------------------------------------

    def dim_all(self, scene: Scene, opacity: float = 0.3, run_time: float = 0.4):
        """软转场：已有内容淡化但保留在屏幕上"""
        if not self.items:
            return
        group = VGroup(*self.items)
        scene.play(group.animate.set_opacity(opacity), run_time=run_time)

    def fade_out_all(self, scene: Scene, run_time: float = 0.5):
        """硬转场：清空全部内容"""
        if not self.items:
            return
        group = VGroup(*self.items)
        scene.play(FadeOut(group), run_time=run_time)
        self.content = VGroup()
        self.items = []
        self.cursor_y = self.top

    # -----------------------------------------------------------------
    # 引用最近的 block（recall 支持）
    # -----------------------------------------------------------------

    def last(self) -> Optional:
        """返回最近一个加入的 block，没有则 None"""
        return self.items[-1] if self.items else None

    def nth_from_last(self, n: int = 1) -> Optional:
        """返回倒数第 n 个 block（n=1 即最近的）"""
        if n < 1 or n > len(self.items):
            return None
        return self.items[-n]
