"""
Act 和 Stage 之间的转场。
"""

from __future__ import annotations

from manim import FadeOut, FadeIn, Scene, VGroup

from ..theme import ACT_SOFT_TRANSITION, ACT_HARD_TRANSITION


def transition_none(scene: Scene, board):
    """无转场。保留原有内容，不做动画"""
    pass


def transition_soft(scene: Scene, board, run_time: float = ACT_SOFT_TRANSITION):
    """软转场：已有内容淡化为 0.35 透明度，继续保留作为背景"""
    board.dim_all(scene, opacity=0.35, run_time=run_time)


def transition_hard(scene: Scene, board, run_time: float = ACT_HARD_TRANSITION):
    """硬转场：清空所有内容 + 短暂空白"""
    board.fade_out_all(scene, run_time=run_time * 0.6)
    scene.wait(run_time * 0.4)


def cover_to_teach(
    scene: Scene, cover_mobs, header_region,
    anchor_region=None, figure_region=None, conditions_region=None,
    statement_inline=None,
    run_time: float = 1.2,
):
    """
    读题阶段 → 讲题阶段的关键转场：
    1. 题干内容淡出
    2. 顶栏浮现
    3. 锚点栏（布局 A）/ 条件栏+图栏（布局 D）/ 图栏（布局 C）浮现
    4. 内联题干（布局 B）浮现
    """
    # 同步播放淡出 + 顶栏构建
    scene.play(FadeOut(cover_mobs), run_time=run_time * 0.5)
    header_region.build()
    header_region.play_appearance(scene, run_time=run_time * 0.5)

    if anchor_region is not None:
        anchor_region.play_appearance(scene, run_time=run_time * 0.5)
    if conditions_region is not None:
        conditions_region.play_appearance(scene, run_time=run_time * 0.5)
    if figure_region is not None:
        figure_region.play_appearance(scene, run_time=run_time * 0.5)

    # 布局 B：题干缩小显示在顶栏下方
    if statement_inline is not None:
        scene.play(FadeIn(statement_inline), run_time=run_time * 0.4)


def teach_to_summary(
    scene: Scene, board_region,
    anchor_region=None, figure_region=None, conditions_region=None,
    statement_inline=None,
    run_time: float = 1.0,
):
    """
    讲题 → 升华：清空推导主区 + 淡出锚点栏 / 条件栏 / 图栏 / 内联题干（顶栏保留）
    """
    board_region.fade_out_all(scene, run_time=run_time * 0.6)
    extras = []
    if anchor_region is not None and anchor_region.content:
        extras.append(FadeOut(anchor_region.content))
    if conditions_region is not None and conditions_region.content:
        extras.append(FadeOut(conditions_region.content))
    if figure_region is not None and figure_region.content and len(figure_region.content) > 0:
        # content 非空才淡出：dismiss_at_act 已把题干图清空成空 content，
        # 但若 dismiss 后又 reveal 了新元素（题干图换分步图），content 重新非空，仍需在此收尾淡出。
        extras.append(FadeOut(figure_region.content))
    if statement_inline is not None:
        extras.append(FadeOut(statement_inline))
    if extras:
        scene.play(*extras, run_time=run_time * 0.4)
