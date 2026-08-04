"""
读题阶段（开场）。

画面：大标题 + 大字号题干居中。
同步：和 core.say 的 TTS 对齐。
"""

from __future__ import annotations

from manim import Scene, Text, Write, FadeIn, VGroup

from ..theme import (
    FONT_SIZE_COVER_TITLE, FONT_SIZE_COVER_STATEMENT,
    FONT_DEFAULT, FONT_STATEMENT, MAIN_BLUE, TEXT_DARK, COVER_TITLE_Y,
    COVER_STATEMENT_BOX, SCREEN_WIDTH, SCREEN_HEIGHT,
    HEADER_RULE_X_LEFT, HEADER_RULE_X_RIGHT,
    color_hex_to_manim,
)
from ..schema import LectureDoc
from ..blocks.text_mixin import create_statement_tex_for_screen_width


def render_read_stage(scene: Scene, doc: LectureDoc, tex_template, audio_segment,
                      figure_region=None) -> VGroup:
    """
    渲染读题阶段。返回读题画面 VGroup（调用方负责淡出）。

    audio_segment 提供 start_time / duration，用于时序同步。
    figure_region 不为 None 时启用 show_in_read：题干和题图按当前图栏位置自适应分列
    （图在左则题干在右，图在右则题干在左）。题图摆在讲题时的最终图栏位置，
    转场后原位保留——所以返回的 VGroup 不含图，由调用方让图常驻。
    """
    show_in_read = figure_region is not None

    # 1. 大标题
    title = Text(
        doc.core.title,
        font=FONT_DEFAULT,
        weight="BOLD",
        font_size=FONT_SIZE_COVER_TITLE,
        color=color_hex_to_manim(MAIN_BLUE),
    )
    title.move_to([0, COVER_TITLE_Y, 0])

    # 2. 题干内容（按屏幕目标宽度换算为 LaTeX minipage 宽度，再自动换行）
    def _cover_statement(target_screen_w):
        return create_statement_tex_for_screen_width(
            doc.core.statement,
            target_screen_w,
            font_size=FONT_SIZE_COVER_STATEMENT,
            color=color_hex_to_manim(TEXT_DARK),
            tex_template=tex_template,
            font=FONT_STATEMENT,            # 题干用霞鹜文楷
        )

    if show_in_read:
        # 按图栏真实位置自适应：当前主题 C/D 图栏在左，旧逻辑会算出负宽度。
        statement_left, statement_right = _statement_slot_for_figure(figure_region)
        statement_width = statement_right - statement_left
        statement = _cover_statement(statement_width)
        max_allowed_width = statement_width
    else:
        # 无图读题阶段与讲解阶段 A/B 顶部题干共用同一版心宽度，避免开场题干显得偏窄偏小。
        statement_left, statement_right = HEADER_RULE_X_LEFT, HEADER_RULE_X_RIGHT
        statement_width = statement_right - statement_left
        statement = _cover_statement(statement_width)
        max_allowed_width = SCREEN_WIDTH - 1.0          # 居中题干两侧各留 0.5 缝

    # 宽度溢出保护：题干（尤其含 choices 整宽分列时）过宽则等比缩小，确保不出血
    if statement.width > max_allowed_width:
        scale_factor = max_allowed_width / statement.width
        statement.scale(scale_factor)
        print(f"[read] 题干过宽 ({statement.width / scale_factor:.2f} > {max_allowed_width:.2f})，"
              f"缩放到 {scale_factor:.2f}")

    # 高度溢出保护：题干过长时自动等比缩小，确保完整显示
    # 可用高度：从封面题干顶线（COVER_STATEMENT_BOX.y）到屏幕底部留 0.5 安全边距
    bottom_limit = -SCREEN_HEIGHT / 2 + 0.5
    top_limit = COVER_STATEMENT_BOX.y          # 题干顶部锚定线
    max_allowed_height = top_limit - bottom_limit  # 约 4.5 单位
    if statement.height > max_allowed_height:
        scale_factor = max_allowed_height / statement.height
        statement.scale(scale_factor)
        print(f"[read] 题干过高 ({statement.height / scale_factor:.2f} > {max_allowed_height:.2f})，"
              f"缩放到 {scale_factor:.2f}")

    # 定位（在缩放之后，确保用最终尺寸计算位置）
    if show_in_read:
        statement.move_to([(statement_left + statement_right) / 2, 0.2, 0])
    else:
        statement.move_to([
            (statement_left + statement_right) / 2,
            COVER_STATEMENT_BOX.y - statement.height / 2,
            0,
        ])

    # 3D 模式：把 cover 锁到屏幕坐标，避免相机角度让文字歪掉
    if hasattr(scene, "add_fixed_in_frame_mobjects"):
        try:
            scene.add_fixed_in_frame_mobjects(title, statement)
        except Exception:
            pass

    # 播出现动画
    scene.play(Write(title), run_time=1.0)
    scene.play(FadeIn(statement), run_time=1.0)

    # show_in_read：题图随题干一起淡入（在它的最终图栏位置）
    if show_in_read and figure_region.content is not None and len(figure_region.content) > 0:
        scene.play(FadeIn(figure_region.content), run_time=0.8)

    # 等待 TTS 播完：用 scene.renderer.time 精确计算剩余等待
    remaining = audio_segment.end_time - scene.renderer.time
    if remaining > 0.05:
        scene.wait(remaining)

    # 返回的 cover 只含会被淡出的文字；图（若有）不在内，留在屏上常驻
    return VGroup(title, statement)


def _statement_slot_for_figure(figure_region) -> tuple[float, float]:
    """计算 show_in_read 时题干可用的屏幕区间，单位为 Manim 坐标。"""
    cover_left = max(COVER_STATEMENT_BOX.x, -SCREEN_WIDTH / 2 + 0.5)
    cover_right = min(COVER_STATEMENT_BOX.x + COVER_STATEMENT_BOX.width, SCREEN_WIDTH / 2 - 0.5)
    cover_mid = (cover_left + cover_right) / 2

    box = figure_region.box
    gap = 0.5
    figure_left = box.x
    figure_right = box.x + box.width
    figure_mid = (figure_left + figure_right) / 2

    left_slot = (cover_left, min(figure_left - gap, cover_right))
    right_slot = (max(figure_right + gap, cover_left), cover_right)

    def width(slot: tuple[float, float]) -> float:
        return max(0.0, slot[1] - slot[0])

    preferred = right_slot if figure_mid <= cover_mid else left_slot
    fallback = left_slot if width(left_slot) > width(right_slot) else right_slot

    # 小于这个宽度时长题干必然不可读，改用更宽的一侧；再不行则退回封面整宽。
    min_readable_width = 2.5
    if width(preferred) >= min_readable_width:
        return preferred
    if width(fallback) >= min_readable_width:
        return fallback
    return cover_left, cover_right
