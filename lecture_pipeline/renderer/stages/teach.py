"""
讲题阶段主控。

职责：
- 遍历 doc.teach.acts
- 每个 act 开头根据 transition 做转场
- 每个 act 内遍历 beats，按音频时间线对齐播放动画
- beat 的 show 通过 blocks.build 构建 Mobject，交给 BoardRegion 摆位
- beat 的 recall 通过 emphasis_animation 强调已有 block
- 无 show 无 recall → 纯过渡 beat，只等音频播完
- knowledge_card / answer_box / wow_formula 走特殊演出（居中 + 归位 或 居中放大）
"""

from __future__ import annotations

from manim import Scene, Indicate

from ..schema import LectureDoc, Mode, BlockType, Transition
from ..blocks import build as build_block
from ..animations.entrance import entrance_name
from ..animations.emphasis import emphasis_animation
from ..animations.transitions import transition_none, transition_soft, transition_hard
from ..regions import BoardRegion
from ..common.audio_timeline import AudioTimeline
from ..theme import DEFAULT_REPLACE_TIME


# 走"居中展示 + 沉降归位"二生命周期的 block 类型
CENTERED_PRESENTATION_TYPES = {
    BlockType.KNOWLEDGE_CARD,
}

# 居中展示但不沉降（讲完 fade out 即可）的 block 类型
CENTERED_ONLY_TYPES = {
    BlockType.WOW_FORMULA,
}

# 居中对齐但仍进 board 列表（例如 answer_box）
CENTER_ALIGN_TYPES = {
    BlockType.ANSWER_BOX,
}


def render_teach_stage(
    scene: Scene,
    doc: LectureDoc,
    board: BoardRegion,
    tex_template,
    timeline: AudioTimeline,
    figure_region=None,
):
    """
    渲染讲题阶段。所有动画严格按 audio timeline 对齐。
    figure_region 若不为 None 且 figure.reveal_at_act 指定了 act_idx，
    则在到达该 act 开始前让 figure 淡入。
    """
    reveal_idx = None
    dismiss_idx = None
    if figure_region is not None and figure_region.figure is not None:
        reveal_idx = figure_region.figure.reveal_at_act
        dismiss_idx = figure_region.figure.dismiss_at_act

    for ai, act in enumerate(doc.teach.acts):
        # 1. Act 入场转场
        # 注意：音频时间线已在 act 边界处预留了足够的静音间隙
        # （见 audio_timeline._compute_gaps），所以这里不需要压缩转场时间
        if act.transition == Transition.NONE:
            transition_none(scene, board)
        elif act.transition == Transition.HARD:
            transition_hard(scene, board)
        else:
            transition_soft(scene, board)

        # 2. 如果到了延迟显示的 act，figure 淡入
        if reveal_idx is not None and ai == reveal_idx and figure_region is not None:
            figure_region.play_appearance(scene, run_time=0.8)

        # 2b. 如果到了 dismiss_at_act，figure 淡出
        if dismiss_idx is not None and ai == dismiss_idx and figure_region is not None:
            if figure_region.content and len(figure_region.content) > 0:
                from manim import FadeOut as _FadeOut
                scene.play(_FadeOut(figure_region.content), run_time=0.6)
                figure_region.content = type(figure_region.content)()
                # 标记已 dismiss，避免后续 transition 再次处理
                figure_region._dismissed = True

        # 3. 遍历 beats
        for bi, beat in enumerate(act.beats):
            seg = timeline.find("teach", ai, bi)
            if seg is None:
                continue

            # 同步到此 beat 的音频起点
            _sync_to(scene, seg.start_time)

            # 分支：figure 引用 / show / recall / 纯过渡
            if beat.show is not None and beat.show.type == BlockType.FIGURE:
                # 唤出题图里被引用的图元，不进推导主区、不调 build_block
                if figure_region is not None:
                    figure_region.reveal_element(
                        scene, beat.show.ref, beat.show.anim, run_time=0.8,
                    )
            elif beat.show is not None:
                mob = build_block(
                    beat.show,
                    tex_template=tex_template,
                    target_screen_width=board.left_flow_target_width(),
                )
                _present_block(scene, board, beat, mob, seg)
            elif beat.recall is not None:
                target = _resolve_recall_target(beat.recall, board)
                if target is not None:
                    anim = emphasis_animation(target, beat.recall.action)
                    scene.play(anim, run_time=1.0)
            # else: 纯过渡 beat，只等音频

            # 等待音频播完
            _sync_to(scene, seg.end_time)


def _present_block(scene: Scene, board: BoardRegion, beat, mob, seg):
    """
    根据 show.type 和 mode 决定呈现方式：
    - knowledge_card: 居中呈现 → 讲完 FadeOut（推导区 dim/恢复）
    - wow_formula:    居中呈现 → 讲完 FadeOut（戏剧性金句时刻）
    - answer_box:     居中对齐加入推导流（永久保留）
    - step (replace_prev=True): TransformMatchingTex 替换上一个 step
    - 其他:           左对齐加入推导流
    """
    show_type = beat.show.type
    mode = beat.mode or Mode.SPOTLIGHT

    if show_type in CENTERED_PRESENTATION_TYPES or show_type in CENTERED_ONLY_TYPES:
        # knowledge_card / wow_formula: 居中呈现 + 讲完消失
        total = seg.duration
        present_time = max(0.8, min(total * 0.25, 1.2))
        dismiss_time = max(0.5, min(total * 0.15, 0.8))

        # wow 放大倍率更夸张
        scale = 1.25 if show_type in CENTERED_ONLY_TYPES else 1.15

        token = board.present_centered(
            mob, scene,
            run_time=present_time,
            scale=scale,
        )

        # 让 mob 在屏幕中央停留大部分时间
        stay_until = seg.start_time + total - dismiss_time - 0.1
        _sync_to(scene, stay_until)

        board.dismiss_centered(token, scene, run_time=dismiss_time)

    elif show_type == BlockType.STEP and getattr(beat.show, "replace_prev", False):
        # step replace_prev：原地变形替换上一个 step
        board.replace_last_with_match(mob, scene, run_time=DEFAULT_REPLACE_TIME)

    elif show_type in CENTER_ALIGN_TYPES:
        # 居中对齐加入推导流
        anim_name = entrance_name(show_type, mode)
        board.add_block(mob, scene, animation=anim_name, align="center")

    else:
        # 默认：左对齐加入推导流
        anim_name = entrance_name(show_type, mode)
        board.add_block(mob, scene, animation=anim_name, align="left")


def _sync_to(scene: Scene, target_time: float):
    """把 scene 时间推进到 target_time（基于 scene.renderer.time）"""
    current = scene.renderer.time
    wait = target_time - current
    if wait > 0.05:
        scene.wait(wait)


def _resolve_recall_target(recall, board: BoardRegion):
    """从 recall.of 字段解析目标 Mobject"""
    of = recall.of
    if of == "prev":
        return board.last()
    if of.startswith("prev_"):
        try:
            n = int(of.split("_", 1)[1])
            return board.nth_from_last(n)
        except ValueError:
            return None
    return board.last()
