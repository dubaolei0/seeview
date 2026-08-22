"""
渲染器 v3 主入口

用法：
    py -m lecture_pipeline.renderer.render <yaml_path> [--quality low|medium|high]
    py -m lecture_pipeline.renderer.render <yaml_path> --validate-only
    py -m lecture_pipeline.renderer.render <yaml_path> --no-audio   # 调试模式，跳过 TTS

当前状态：MVP。实现了完整的三阶段流程 + 音频时间线同步。
暂未实现：FigureRegion（TikZ）、TransformMatchingTex、动点滑动。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from manim import Scene, ThreeDScene, config, FadeOut

from .schema import LectureDoc, validate
from .theme import (
    EYE_WHITE, INTRO_SILENCE, COVER_TO_TEACH_RUN_TIME, TEACH_TO_SUMMARY_RUN_TIME,
    TEXT_DARK,
)
from .common import get_chinese_template, build_audio_timeline
from .common.audio_timeline import AudioTimeline, AudioSegmentInfo
from .regions import HeaderRegion, AnchorRegion, ConditionsRegion, BoardRegion, FigureRegion, SummaryRegion
from .animations.transitions import cover_to_teach, teach_to_summary
from .stages.read import render_read_stage
from .stages.teach import render_teach_stage
from .stages.summary import render_summary_stage
from .schema import FigureType


# =====================================================================
# Manim 配置
# =====================================================================

# =====================================================================
# Manim 全局配置（仅背景色，quality 在 render_lecture 里设置）
# =====================================================================

config.background_color = EYE_WHITE


# =====================================================================
# 主场景类
# =====================================================================

def _is_3d_doc(doc: LectureDoc) -> bool:
    return (
        doc.core.figure is not None
        and doc.core.figure.type == FigureType.GEOMETRY3D
    )


def _ensure_vendored_texmf():
    """把引擎自带的 texmf 目录（renderer/common/texmf）前置到 TEXINPUTS，
    让 xelatex 优先用随引擎同步过来的宏包（如 multiple-choice.sty），
    成员本地缺这个包也无需联网下载。结尾留空项以保留系统默认搜索路径。

    注意：multiple-choice 依赖 bidi（biditools），bidi 几乎所有 TeX 发行版自带，未一并内置。
    """
    import os
    vendor = Path(__file__).parent / "common" / "texmf"
    if not vendor.exists():
        return
    old = os.environ.get("TEXINPUTS", "")
    parts = [str(vendor)]
    if old:
        parts.append(old)
    os.environ["TEXINPUTS"] = os.pathsep.join(parts) + os.pathsep


def _build_statement_banner(
    scene,
    *,
    content_left: float | None = None,
    content_right: float | None = None,
    font_size: int | None = None,
):
    """构建讲解阶段常驻题干：纯文本、无底框、左对齐、固定字号。

    - 上沿在顶栏细线下方留 STATEMENT_TOP_GAP；与下方"图栏+讲解区"整块同宽，左缘对齐图栏左缘。
    - 字号固定，不做自适应缩放；题干越长就在 minipage 内多换几行。
    - 返回 (题干 Mob, content_top)：content_top = 题干底沿再下留 STATEMENT_TO_CONTENT_GAP，
      即下方图栏/主区应起始的 y，随题干行数联动下移（越长，下面整体越往下让）。
    """
    from .blocks.text_mixin import create_statement_tex_for_screen_width
    from .theme import (
        color_hex_to_manim, FONT_SIZE_TEACH_STATEMENT, FONT_STATEMENT,
        HEADER_RULE_Y, FIGURE_BOX, BOARD_BOX_C,
        STATEMENT_TOP_GAP, STATEMENT_TO_CONTENT_GAP,
    )

    top_y = HEADER_RULE_Y - STATEMENT_TOP_GAP
    # 题干与下方"图栏 + 讲解区"整块同宽：左缘对齐图栏左缘，右缘对齐讲解区右缘。
    if content_left is None:
        content_left = FIGURE_BOX.x
    if content_right is None:
        content_right = BOARD_BOX_C.x + BOARD_BOX_C.width
    if font_size is None:
        font_size = FONT_SIZE_TEACH_STATEMENT
    max_text_w = content_right - content_left

    stmt_text = scene.doc.core.statement or ""
    text_mob = create_statement_tex_for_screen_width(
        stmt_text,
        max_text_w,
        font_size=font_size,
        color=color_hex_to_manim(TEXT_DARK),
        tex_template=scene.tex_template,
        font=FONT_STATEMENT,            # 题干用霞鹜文楷
    )

    # 左上角锚定：左缘对齐内容左缘（图栏左缘），上沿在 top_y。固定字号，不缩放、左对齐。
    text_mob.move_to([content_left + text_mob.width / 2, top_y - text_mob.height / 2, 0])

    content_top = (top_y - text_mob.height) - STATEMENT_TO_CONTENT_GAP
    return text_mob, content_top


def _run_lecture(self, fixed_frame: bool = False):
    """LectureScene2D 和 LectureScene3D 共享的主流程"""
    if self.doc is None:
        raise RuntimeError("LectureScene.doc 未注入")

    self.camera.background_color = EYE_WHITE

    # 3D 模式：设置默认相机角度
    if fixed_frame and self.doc.core.figure is not None:
        from manim import DEGREES
        fig = self.doc.core.figure
        # 默认 phi=70°（微俯）、theta=-90°（正面看）
        # —— 此组合下 +z 严格屏幕竖直，圆柱对称、不歪
        # focal_distance 拉大到接近正交，消除离轴竖直物体的透视倾斜（详见 theme 常量）
        from .theme import GEOMETRY3D_FOCAL_DISTANCE
        phi = (fig.camera_phi if fig.camera_phi is not None else 70) * DEGREES
        theta = (fig.camera_theta if fig.camera_theta is not None else -90) * DEGREES
        self.set_camera_orientation(
            phi=phi, theta=theta, focal_distance=GEOMETRY3D_FOCAL_DISTANCE
        )

    # 1. 读题阶段
    read_seg = self.timeline.find("read") if self.timeline else AudioSegmentInfo(
        stage="read", act_idx=-1, beat_idx=-1,
        start_time=INTRO_SILENCE, duration=3.0,
    )

    self.wait(INTRO_SILENCE)

    layout = self.doc.core.layout_branch

    # 题干是否在讲解阶段常驻为顶部卡片。这是渲染时的人工判断（--no-statement 关闭），
    # 不写进 yaml；默认 A/C/D 带着；B 作为无图全宽布局走独立字号。
    from .theme import (
        FIGURE_BOX as _FIG_C, FIGURE_BOX_D as _FIG_D,
        ANCHOR_BOX as _ANCHOR, CONDITIONS_BOX as _COND,
        BOARD_BOX_A as _BRD_A, BOARD_BOX_B as _BRD_B,
        BOARD_BOX_C as _BRD_C, BOARD_BOX_D as _BRD_D,
        HEADER_RULE_X_LEFT, HEADER_RULE_X_RIGHT,
        RegionBox, shift_box_top_to as _shift,
        compute_c_layout,
    )
    show_statement_in_teach = (
        layout in ("A", "C", "D")
        and not fixed_frame
        and not getattr(self, "hide_statement", False)
    )

    # 布局 C/D 的自定义覆盖：yaml 里 figure.board_ratio / figure_side 可调整步骤与图的宽度比和左右位置
    _custom_fig_box = None
    _custom_brd_box = None
    if layout in ("C", "D") and self.doc.core.figure is not None:
        fig_cfg = self.doc.core.figure
        _br = fig_cfg.board_ratio
        _fs = fig_cfg.figure_side
        if _br is not None or _fs is not None:
            _custom_fig_box, _custom_brd_box = compute_c_layout(
                board_ratio=_br if _br is not None else 0.60,
                figure_side=_fs if _fs is not None else "left",
            )

    # 先把题干卡片建出来并量好高度——下方图栏/条件栏/主区的顶部要随卡片底沿联动下移，
    # 卡片越长（或上沿越往下），下面的内容一起往下让。
    statement_inline = None
    content_top = None
    if show_statement_in_teach:
        if layout == "A":
            statement_inline, content_top = _build_statement_banner(
                self,
                content_left=HEADER_RULE_X_LEFT,
                content_right=HEADER_RULE_X_RIGHT,
            )
        elif layout in ("C", "D") and _custom_fig_box is not None:
            statement_inline, content_top = _build_statement_banner(
                self,
                content_left=min(_custom_fig_box.x, _custom_brd_box.x),
                content_right=max(
                    _custom_fig_box.x + _custom_fig_box.width,
                    _custom_brd_box.x + _custom_brd_box.width,
                ),
            )
        else:
            statement_inline, content_top = _build_statement_banner(self)
    elif layout == "B":
        statement_inline, content_top = _build_statement_banner(
            self,
            content_left=HEADER_RULE_X_LEFT,
            content_right=HEADER_RULE_X_RIGHT,
        )

    figure_box = (
        _custom_fig_box if _custom_fig_box is not None and layout == "C" else
        (_FIG_D if layout == "D" else _FIG_C)
    )
    anchor_box = _ANCHOR
    conditions_box = _COND
    board_box = (
        _custom_brd_box if _custom_brd_box is not None and layout == "C" else
        (
            _BRD_A if layout == "A" else (
                _BRD_B if layout == "B" else (
                    _BRD_D if layout == "D" else (
                        _BRD_C if layout == "C" else None
                    )
                )
            )
        )
    )
    if show_statement_in_teach:
        # 把各栏顶部下压到 content_top（= 卡片底沿下方一点，随卡片联动）。
        # A 压右侧已知栏；C 的图栏占满整列要随之下压；D 的图栏在左下方本就够低，只压条件栏与主区。
        if layout == "A":
            anchor_box = _shift(anchor_box, content_top)
        elif layout == "C":
            figure_box = _shift(figure_box, content_top)
        conditions_box = _shift(conditions_box, content_top)
        if board_box is not None:
            board_box = _shift(board_box, content_top)
    elif layout == "B" and content_top is not None:
        bottom = _BRD_B.y - _BRD_B.height
        board_box = RegionBox(
            _BRD_B.x,
            content_top,
            _BRD_B.width,
            max(content_top - bottom, 0.5),
        )

    # show_in_read：题图在读题封面就和题干一起出现（文左图右）。
    # 仅 2D 布局 C/D 支持；3D（fixed_frame）不做。需在读题前把图栏建好，让封面就能显示。
    show_in_read = (
        not fixed_frame
        and self.doc.core.figure is not None
        and getattr(self.doc.core.figure, "show_in_read", False)
        and self.doc.core.figure.reveal_at_act is None
        and layout in ("C", "D")
    )
    prebuilt_figure = None
    if show_in_read:
        prebuilt_figure = FigureRegion(
            self.doc.core.figure, box=figure_box,
            referenced_ids=self.doc.figure_referenced_ids(),
            tex_template=self.tex_template,
        )
        prebuilt_figure.build()

    cover_group = render_read_stage(
        self, self.doc, self.tex_template, read_seg,
        figure_region=prebuilt_figure,
    )
    if fixed_frame:
        # 把读题阶段的 mob 锁到屏幕
        try:
            self.add_fixed_in_frame_mobjects(*cover_group.submobjects)
        except Exception:
            pass

    # 2. 读题 → 讲题转场
    header = HeaderRegion(self.doc.core.title, tex_template=self.tex_template)

    anchor = None
    figure = None
    conditions = None
    defer_figure = False
    if layout == "A":
        anchor = AnchorRegion(
            self.doc.core.keypoint, tex_template=self.tex_template,
            box=anchor_box,
        )
        anchor.build()
    elif layout == "D" and self.doc.core.figure is not None:
        conditions = ConditionsRegion(
            self.doc.core.conditions, tex_template=self.tex_template,
            box=conditions_box,
        )
        conditions.build()
        # show_in_read 时图已在读题阶段建好并显示，直接复用，避免重建/重复淡入
        figure = prebuilt_figure or FigureRegion(
            self.doc.core.figure, box=figure_box,
            referenced_ids=self.doc.figure_referenced_ids(),
            tex_template=self.tex_template,
        )
        if prebuilt_figure is None:
            figure.build()
        defer_figure = self.doc.core.figure.reveal_at_act is not None
    elif layout == "C" and self.doc.core.figure is not None:
        figure = prebuilt_figure or FigureRegion(
            self.doc.core.figure, box=figure_box,
            referenced_ids=self.doc.figure_referenced_ids(),
            tex_template=self.tex_template,
        )
        if prebuilt_figure is None:
            figure.build()
        defer_figure = self.doc.core.figure.reveal_at_act is not None

    cover_to_teach(
        self, cover_group, header,
        anchor_region=anchor,
        # show_in_read 时图已在封面显示并常驻，转场不再重复淡入
        figure_region=None if (defer_figure or fixed_frame or show_in_read) else figure,
        conditions_region=conditions,
        statement_inline=statement_inline,
        run_time=COVER_TO_TEACH_RUN_TIME,
    )

    # 3D 模式：figure 是 3D 内容，单独 FadeIn（让它处于 3D 世界，不锁帧）
    if fixed_frame and figure is not None and not defer_figure:
        from manim import FadeIn as _FadeIn
        if figure.content and len(figure.content) > 0:
            self.play(_FadeIn(figure.content), run_time=0.6)

    # 3D 模式：可选启用 figure 自旋（绕物体自身中心，绕 z 轴）
    if fixed_frame and self.doc.core.figure is not None and self.doc.core.figure.camera_rotate:
        from .theme import GEOMETRY3D_SPIN_RATE
        if figure is not None and figure.content is not None and len(figure.content) > 0:
            spin_target = figure.content
            # 自旋轴：经过物体 (x, y) 中心、方向 +z 的直线（保持物体竖直）
            center = spin_target.get_center().copy()
            spin_pivot = [center[0], center[1], 0.0]

            def _spin(m, dt):
                m.rotate(
                    GEOMETRY3D_SPIN_RATE * dt,
                    axis=[0, 0, 1],
                    about_point=spin_pivot,
                )
            spin_target.add_updater(_spin)
            self._geometry3d_spin = (spin_target, _spin)

    # 3. 讲题阶段
    board = BoardRegion(layout_branch=layout, box=board_box)
    if fixed_frame:
        board.fixed_frame_scene = self
    self._fixed_frame_mode = fixed_frame
    self._figure_region_for_3d = figure if fixed_frame else None
    # 把 figure_region 传给 teach 阶段——无论 reveal_at_act 是否 None，
    # dismiss_at_act 也可能要在某 act 触发淡出
    render_teach_stage(
        self, self.doc, board,
        self.tex_template, self.timeline,
        figure_region=figure,
    )

    # 4. 讲题 → 升华转场（同时把讲解内容淡出清屏；无升华段时它就是收尾的淡出）
    teach_to_summary(
        self, board,
        anchor_region=anchor,
        figure_region=figure,
        conditions_region=conditions,
        statement_inline=statement_inline,
        run_time=TEACH_TO_SUMMARY_RUN_TIME,
    )

    # 5. 升华阶段（summary 可省略：套路/无升华价值的题没有这一段）
    if self.doc.summary is not None:
        summary = SummaryRegion()
        if fixed_frame:
            summary.fixed_frame_scene = self
        render_summary_stage(
            self, self.doc, summary,
            self.tex_template, self.timeline,
        )

    # 结尾等待
    from .theme import OUTRO_WAIT
    self.wait(OUTRO_WAIT)


class LectureScene2D(Scene):
    """2D 版本：layout A/B/C（schematic/plot/image）"""
    doc: LectureDoc = None
    tex_template = None
    timeline: AudioTimeline = None
    skip_audio: bool = False
    hide_statement: bool = False        # True = 讲解阶段不显示题干横幅（--no-statement）

    def construct(self):
        _run_lecture(self, fixed_frame=False)


class LectureScene3D(ThreeDScene):
    """3D 版本：layout C with geometry3d figure"""
    doc: LectureDoc = None
    tex_template = None
    timeline: AudioTimeline = None
    skip_audio: bool = False
    hide_statement: bool = False

    def construct(self):
        _run_lecture(self, fixed_frame=True)


# 兼容别名（被外部引用）
LectureScene = LectureScene2D


# =====================================================================
# 渲染流程
# =====================================================================

def render_lecture(
    yaml_path: Path,
    quality: str,
    skip_audio: bool = False,
    tts_provider: str | None = None,
    tts_voice: str | None = None,
    tts_retries: int = 2,
    tts_speech_rate: float | None = None,
    hide_statement: bool = False,
    media_dir: str | None = None,
    enable_caching: bool = False,
) -> Path:
    """
    主渲染流程。返回最终 mp4 路径。

    media_dir：manim media 输出根目录。并发渲染时各进程传不同 media_dir，
    避免 partial_movie_files / Tex 缓存在共享 media/ 下互相覆盖。默认 None 用 manim 默认 media/。
    enable_caching：默认 False 关闭 manim 动画缓存哈希。缓存的哈希计算会把场上全部
    mobject 反复 JSON 序列化（且 memoizer 集合只增不减），讲题视频 beat 多、LaTeX
    内容大时直接 MemoryError；本流水线每次渲染的 yaml/输出都不同，缓存收益趋近于零。
    """
    # 0. 让 xelatex 能找到随引擎自带的宏包（multiple-choice 等），免得成员本地 MiKTeX 还要联网下载
    _ensure_vendored_texmf()
    # 0b. 注册自带中文字体给 manim Text(Pango)，使标题等不依赖系统安装（与 xelatex 侧一致）
    from .font_config import register_vendored_fonts
    register_vendored_fonts()
    # 0c. 隔离 media 目录（并发渲染安全）
    if media_dir:
        config.media_dir = Path(media_dir)
    # 0d. 关闭动画缓存哈希（默认）：防止长视频渲染中途 MemoryError，见 render_lecture docstring
    config.disable_caching = not enable_caching

    # 1. 解析 schema
    doc = LectureDoc.from_yaml_file(yaml_path)
    print(f"✓ 解析成功：{doc.core.title}")
    print(f"  布局分支：{doc.core.layout_branch}")
    print(f"  Act 数：{len(doc.teach.acts)}")
    print(f"  总 beats：{doc.total_beats()}")

    # 2. 软约束警告
    warnings = validate(doc)
    if warnings:
        print(f"\n⚠ 软约束警告 {len(warnings)} 条：")
        for w in warnings[:5]:
            print(f"  - {w}")
        if len(warnings) > 5:
            print(f"  ... 还有 {len(warnings) - 5} 条")

    # 3. 生成音频时间线
    problem_id = yaml_path.stem
    cache_dir = Path(config.media_dir) / "cache"

    if skip_audio:
        print("\n[audio] 跳过 TTS（--no-audio 模式）")
        timeline = _build_dummy_timeline(doc)
        mixed_audio_path = None
    else:
        print("\n=== 生成音频时间线 ===")
        timeline = build_audio_timeline(
            doc,
            problem_id,
            cache_dir,
            tts_provider=tts_provider,
            tts_voice=tts_voice,
            tts_retries=tts_retries,
            tts_speech_rate=tts_speech_rate,
        )
        mixed_audio_path = timeline.mixed_path

    # 4. 配置 Manim 质量（显式设像素和帧率，确保覆盖默认）
    if quality == "low":
        config.pixel_height = 480
        config.pixel_width = 854
        config.frame_rate = 15
        config.quality = "low_quality"
    elif quality == "medium":
        config.pixel_height = 720
        config.pixel_width = 1280
        config.frame_rate = 30
        config.quality = "medium_quality"
    else:
        config.pixel_height = 1080
        config.pixel_width = 1920
        config.frame_rate = 60
        config.quality = "high_quality"

    # 5. 渲染
    print("\n=== 渲染视频 ===")
    tex_template = get_chinese_template()

    # 选场景类：含 geometry3d 用 3D；否则 2D
    is_3d = _is_3d_doc(doc)
    SceneCls = LectureScene3D if is_3d else LectureScene2D
    SceneCls.doc = doc
    SceneCls.tex_template = tex_template
    SceneCls.timeline = timeline
    SceneCls.skip_audio = skip_audio
    SceneCls.hide_statement = hide_statement
    print(f"  场景类型：{'3D (ThreeDScene)' if is_3d else '2D (Scene)'}")

    # 用 problem_id 命名输出文件，避免每次都叫 LectureScene2D.mp4 互相覆盖
    config.output_file = problem_id

    scene = SceneCls()
    scene.render()

    # 找到输出路径
    out_mp4 = _find_latest_output(problem_id)
    print(f"\n✓ 视频渲染完成：{out_mp4}")

    # 6. 合并音频
    if mixed_audio_path is not None and out_mp4 is not None:
        final_mp4 = _merge_audio(out_mp4, mixed_audio_path, problem_id)
        print(f"✓ 音画合并：{final_mp4}")
        return final_mp4

    return out_mp4


def _build_dummy_timeline(doc: LectureDoc) -> AudioTimeline:
    """不做 TTS 的模式：每段给固定假时长，仍计算正确的转场间隙"""
    from .common.audio_timeline import _compute_gaps, BEAT_GAP

    FIXED = 2.0
    # 先构造 audio_infos 列表供 _compute_gaps 使用
    audio_infos = [{"stage": "read", "act_idx": -1, "beat_idx": -1, "duration": FIXED * 2}]
    for ai, act in enumerate(doc.teach.acts):
        for bi in range(len(act.beats)):
            audio_infos.append({"stage": "teach", "act_idx": ai, "beat_idx": bi, "duration": FIXED})
    if doc.summary is not None:
        for bi in range(len(doc.summary.beats)):
            audio_infos.append({"stage": "summary", "act_idx": -1, "beat_idx": bi, "duration": FIXED})

    gaps = _compute_gaps(doc, audio_infos)

    segments = []
    current = INTRO_SILENCE
    for i, info in enumerate(audio_infos):
        segments.append(AudioSegmentInfo(
            info["stage"], info["act_idx"], info["beat_idx"],
            current, info["duration"],
        ))
        current += info["duration"] + gaps[i]

    return AudioTimeline(
        mixed_path=Path("_dummy.wav"),
        total_duration=current,
        segments=segments,
    )


def _find_latest_output(scene_name: str = "LectureScene2D") -> Path | None:
    """找到 manim 最近输出的 scene mp4（按修改时间排序，取最新）

    优先找 scene_name.mp4，兼容旧的 LectureScene2D.mp4 命名。
    """
    candidates = [scene_name, "LectureScene", "LectureScene2D", "LectureScene3D"]
    all_found: list[Path] = []
    videos_dir = Path(config.media_dir) / "videos"
    for name in candidates:
        all_found.extend(videos_dir.rglob(f"{name}.mp4"))
    if all_found:
        return max(all_found, key=lambda f: f.stat().st_mtime)
    return None


def _merge_audio(video_mp4: Path, audio_wav: Path, problem_id: str) -> Path:
    """用 ffmpeg 合并 mp4 和 wav。

    输入输出可能同名（当 config.output_file 已设为 problem_id 时），
    所以先写到临时文件再原地替换。
    """
    out_dir = video_mp4.parent
    out_path = out_dir / f"{problem_id}.mp4"
    # 用临时文件避免 ffmpeg 输入输出同路径报错
    tmp_path = out_dir / f"{problem_id}_tmp_merge.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_mp4),
        "-i", str(audio_wav),
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a:0",
        str(tmp_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        # 替换原文件
        tmp_path.replace(out_path)
        return out_path
    except Exception as e:
        print(f"[ffmpeg] 合并失败：{e}")
        return video_mp4


# =====================================================================
# 命令行入口
# =====================================================================

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="renderer_v3",
        description="渲染 v3 schema yaml 为视频",
    )
    parser.add_argument("yaml_file", help="输入的 v3 yaml 路径")
    parser.add_argument("--quality", choices=["low", "medium", "high"], default="medium")
    parser.add_argument(
        "--validate-only", action="store_true",
        help="只做 schema 校验，不渲染",
    )
    parser.add_argument(
        "--no-audio", action="store_true",
        help="跳过 TTS，用假时长渲染（调试用）",
    )
    parser.add_argument(
        "--tts-provider",
        choices=["auto", "aliyun", "doubao"],
        default="auto",
        help="TTS 平台。默认 auto：未指定音色时用豆包；zh_ 开头音色自动推断为豆包。",
    )
    parser.add_argument(
        "--tts-voice",
        default=None,
        help="本次渲染使用的音色短名或 ID。默认豆包 zh_male_jieshuoxiaoming_uranus_bigtts；例如 jieshuoxiaoming、liufei。",
    )
    parser.add_argument(
        "--tts-retries",
        type=int,
        default=2,
        help="TTS 失败后的同音色重试次数。默认 2。",
    )
    parser.add_argument(
        "--speech-rate",
        type=float,
        default=None,
        help="TTS 语速倍率（0.5~2.0，1.0=默认）。如 0.8 慢速、1.25 快速。",
    )
    parser.add_argument(
        "--no-statement", action="store_true",
        help="讲解阶段不显示题干横幅（默认 C/D 布局会在顶部常驻题干卡片）。",
    )
    parser.add_argument(
        "--media-dir",
        default=None,
        help="manim media 输出目录（并发渲染时隔离用，默认 media/）。",
    )
    parser.add_argument(
        "--enable-caching", action="store_true",
        help="启用 manim 动画缓存哈希（默认关闭）。长视频开缓存会把内存耗尽报 MemoryError，"
             "仅短视频反复重渲染同一 yaml 想省时间时才开。",
    )
    args = parser.parse_args(argv)

    yaml_path = Path(args.yaml_file).resolve()
    if not yaml_path.exists():
        print(f"[错误] 找不到 yaml：{yaml_path}")
        return 1

    if args.validate_only:
        try:
            doc = LectureDoc.from_yaml_file(yaml_path)
        except Exception as e:
            print(f"[错误] schema 解析失败：{e}")
            return 1
        print(f"✓ 解析成功：{doc.core.title}")
        print(f"  布局分支：{doc.core.layout_branch}")
        print(f"  Act 数：{len(doc.teach.acts)}")
        print(f"  总 beats：{doc.total_beats()}")
        warnings = validate(doc)
        if warnings:
            print(f"\n⚠ 软约束警告 {len(warnings)} 条：")
            for w in warnings:
                print(f"  - {w}")
        return 0

    try:
        render_lecture(
            yaml_path,
            args.quality,
            skip_audio=args.no_audio,
            tts_provider=args.tts_provider,
            tts_voice=args.tts_voice,
            tts_retries=args.tts_retries,
            tts_speech_rate=args.speech_rate,
            hide_statement=args.no_statement,
            media_dir=args.media_dir,
            enable_caching=args.enable_caching,
        )
        return 0
    except Exception as e:
        import traceback
        print(f"\n[错误] 渲染失败：{e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
