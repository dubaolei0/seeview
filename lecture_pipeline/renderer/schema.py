"""
Schema 定义：v3 yaml 的数据类 + 解析器

对应文档：lecture_pipeline/docs/schema规范.md

核心类层次：
    LectureDoc                # 一道题的完整讲稿
    ├── Core                  # 题目元信息
    │   └── Figure            # 可选
    ├── Teach
    │   └── list[Act]
    │       └── list[Beat]
    │           ├── Show      # 可选，这一拍显示什么
    │           └── Recall    # 可选，强调已有
    └── Summary
        └── list[Beat]

使用方法：
    from lecture_pipeline.renderer.schema import LectureDoc
    doc = LectureDoc.from_yaml_file("path/to/lecture.yaml")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

import yaml


# =====================================================================
# 枚举
# =====================================================================

class Transition(str, Enum):
    """Act 入场转场类型"""
    NONE = "none"
    SOFT = "soft"
    HARD = "hard"


class Mode(str, Enum):
    """Beat 演出模式"""
    SPOTLIGHT = "spotlight"
    CONSTRUCT = "construct"
    TOUR = "tour"
    INSIGHT = "insight"


class BlockType(str, Enum):
    """Block 类型清单（见 schema 规范第四部分）"""
    # 自动生成，不由 beat 创建
    PROBLEM_STATEMENT = "problem_statement"
    KEYPOINT_ITEM = "keypoint_item"

    # 讲题主区
    STEP = "step"
    KNOWLEDGE_CARD = "knowledge_card"
    ANSWER_BOX = "answer_box"
    WOW_FORMULA = "wow_formula"
    WARNING = "warning"
    FIGURE = "figure"          # 引用并唤出题图里的某个元素（见 Show.ref / Show.anim）

    # 升华主区
    TAKEAWAY = "takeaway"
    MINDMAP_NODE = "mindmap_node"


class FigureType(str, Enum):
    """Figure 来源类型"""
    TIKZ = "tikz"
    IMAGE = "image"
    PLOT = "plot"
    SCHEMATIC = "schematic"    # 通用 2D 示意图：用 Manim 原生图元声明式描述
    GEOMETRY3D = "geometry3d"  # 通用 3D 几何：sphere/cylinder/cube/cone/plane/segment3d/dot3d/label3d


class RecallAction(str, Enum):
    """Recall 强调方式"""
    INDICATE = "indicate"
    CIRCLE = "circle"
    FOCUS = "focus"
    HIGHLIGHT = "highlight"
    UNDERLINE = "underline"


# =====================================================================
# 数据类
# =====================================================================

@dataclass
class Figure:
    """题干自带的图"""
    type: FigureType
    # tikz 模式
    source: Optional[str] = None
    # image 模式
    path: Optional[str] = None
    # plot / schematic / geometry3d 模式
    x_range: Optional[list[float]] = None
    y_range: Optional[list[float]] = None
    elements: Optional[list[dict]] = None
    # 出现时机：None = 读题→讲题转场时出现；int = 某个 act 开始前出现
    reveal_at_act: Optional[int] = None
    # 退场时机：None = 直到讲题阶段结束才在 teach→summary 转场淡出；
    #          int = 某个 act 开始前淡出（早退场）
    dismiss_at_act: Optional[int] = None
    # geometry3d 专用：相机角度（phi 仰角度，theta 方位角度）+ 是否环境慢转
    camera_phi: Optional[float] = None       # 默认 70 度
    camera_theta: Optional[float] = None     # 默认 -30 度
    camera_rotate: bool = False              # 启用慢转
    # geometry3d 专用：整组缩放到 max(width, height, depth) ≤ max_size；不填走默认
    max_size: Optional[float] = None
    # geometry3d 专用：缩放后的额外位移 [dx, dy, dz]
    shift: Optional[list[float]] = None
    # True = 题图在读题封面就和题干一起出现（文左图右），转场后原位留在图栏；
    #        False（默认）= 旧行为，图在 cover→teach 转场时才出现。仅 2D（C/D）支持。
    show_in_read: bool = False
    # 布局覆盖（仅 C/D 生效）
    board_ratio: Optional[float] = None     # 推导主区占可用宽度的比例（None=沿用 theme 默认 0.60）
    figure_side: Optional[str] = None       # "left" | "right"（None=沿用 theme 默认 "left"）
    show_numbers: Optional[bool] = None     # 坐标轴是否显示数字刻度（None=沿用默认 True）

    @classmethod
    def from_dict(cls, data: dict) -> "Figure":
        return cls(
            type=FigureType(data["type"]),
            source=data.get("source"),
            path=data.get("path"),
            x_range=data.get("x_range"),
            y_range=data.get("y_range"),
            elements=data.get("elements"),
            reveal_at_act=data.get("reveal_at_act"),
            dismiss_at_act=data.get("dismiss_at_act"),
            camera_phi=data.get("camera_phi"),
            camera_theta=data.get("camera_theta"),
            camera_rotate=data.get("camera_rotate", False),
            max_size=data.get("max_size"),
            shift=data.get("shift"),
            show_in_read=data.get("show_in_read", False),
            board_ratio=data.get("board_ratio"),
            figure_side=data.get("figure_side"),
            show_numbers=data.get("show_numbers"),
        )


@dataclass
class Core:
    """题目元信息。对应 schema 规范第一部分"""
    title: str                              # 顶栏文字
    statement: str                          # 题干（含 LaTeX）
    say: str                                # 读题 TTS
    keypoint: list[str] = field(default_factory=list)  # 可选锚点列表
    conditions: list[str] = field(default_factory=list)  # 可选已知条件列表（布局 D）
    figure: Optional[Figure] = None         # 可选图

    @property
    def layout_branch(self) -> str:
        """根据 keypoint / conditions / figure 自动判定布局分支。
        - conditions + figure：D（已知 + 图，右侧上下分区）
        - 仅 figure：C（图栏占右侧）
        - 仅 keypoint：A（锚点栏）
        - 都无：B（题干缩到顶栏下）
        """
        if self.figure is not None and self.conditions:
            return "D"
        if self.figure is not None:
            return "C"
        if self.keypoint:
            return "A"
        return "B"

    @classmethod
    def from_dict(cls, data: dict) -> "Core":
        return cls(
            title=data["title"],
            statement=data["statement"],
            say=data["say"],
            keypoint=data.get("keypoint") or [],
            conditions=data.get("conditions") or [],
            figure=Figure.from_dict(data["figure"]) if data.get("figure") else None,
        )


@dataclass
class Show:
    """Beat 中新登场的内容。字段 schema 随 type 变化"""
    type: BlockType
    # 通用字段（按 block type 选用）
    body: Optional[str] = None
    title: Optional[str] = None
    points: list[str] = field(default_factory=list)
    icon: Optional[str] = None
    emphasis: list[str] = field(default_factory=list)
    formula: Optional[str] = None
    caption: Optional[str] = None
    number: Optional[int] = None
    parent: Optional[str] = None
    level: int = 1
    label: Optional[str] = None            # warning 用
    replace_prev: bool = False             # step 专用：用 TransformMatchingTex 替换上一个 step
    ref: list[str] = field(default_factory=list)  # figure 专用：要唤出的图元 id（可单个或多个）
    anim: Optional[str] = None             # figure 专用：fadein(默认) / create / grow

    @classmethod
    def from_dict(cls, data: dict) -> "Show":
        # ref 接受字符串或列表，统一成列表
        raw_ref = data.get("ref")
        if raw_ref is None:
            ref = []
        elif isinstance(raw_ref, str):
            ref = [raw_ref]
        else:
            ref = list(raw_ref)
        return cls(
            type=BlockType(data["type"]),
            body=data.get("body"),
            title=data.get("title"),
            points=data.get("points") or [],
            icon=data.get("icon"),
            emphasis=data.get("emphasis") or [],
            formula=data.get("formula"),
            caption=data.get("caption"),
            number=data.get("number"),
            parent=data.get("parent"),
            level=data.get("level", 1),
            label=data.get("label"),
            replace_prev=data.get("replace_prev", False),
            ref=ref,
            anim=data.get("anim"),
        )


@dataclass
class Recall:
    """Beat 中强调已有内容（替代 show）"""
    of: str = "prev"                        # 被引用 block（默认上一个）
    action: RecallAction = RecallAction.INDICATE

    @classmethod
    def from_value(cls, value: Union[str, dict]) -> "Recall":
        """支持简写字符串 (如 "indicate") 或完整 dict"""
        if isinstance(value, str):
            return cls(action=RecallAction(value))
        return cls(
            of=value.get("of", "prev"),
            action=RecallAction(value.get("action", "indicate")),
        )


@dataclass
class Beat:
    """最小节拍单位"""
    say: str                                # 必填 TTS
    show: Optional[Show] = None             # 可选：新内容
    recall: Optional[Recall] = None         # 可选：强调已有（与 show 互斥）
    mode: Optional[Mode] = None             # 可选：默认由 stage 推断

    @classmethod
    def from_dict(cls, data: dict, default_mode: Mode = Mode.SPOTLIGHT) -> "Beat":
        show = Show.from_dict(data["show"]) if data.get("show") else None
        recall = Recall.from_value(data["recall"]) if data.get("recall") else None
        if show and recall:
            raise ValueError("show 和 recall 不能同时出现在一个 beat 里")
        mode_value = data.get("mode")
        mode = Mode(mode_value) if mode_value else None
        return cls(
            say=data["say"],
            show=show,
            recall=recall,
            mode=mode or default_mode,
        )


@dataclass
class Act:
    """讲题阶段内部的 act"""
    title: str
    beats: list[Beat] = field(default_factory=list)
    transition: Transition = Transition.SOFT
    figure: Optional[Figure] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Act":
        transition = Transition(data.get("transition", "soft"))
        beats = [Beat.from_dict(b, Mode.SPOTLIGHT) for b in data["beats"]]
        if not beats:
            raise ValueError(f"Act '{data.get('title')}' 的 beats 不能为空")
        figure = Figure.from_dict(data["figure"]) if data.get("figure") else None
        return cls(
            title=data["title"],
            beats=beats,
            transition=transition,
            figure=figure,
        )


@dataclass
class Teach:
    """讲题阶段"""
    acts: list[Act] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "Teach":
        acts = [Act.from_dict(a) for a in data["acts"]]
        if not acts:
            raise ValueError("teach.acts 不能为空")
        return cls(acts=acts)


@dataclass
class Summary:
    """升华阶段"""
    beats: list[Beat] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "Summary":
        beats = [Beat.from_dict(b, Mode.CONSTRUCT) for b in data["beats"]]
        if not beats:
            raise ValueError("summary.beats 不能为空")
        return cls(beats=beats)


@dataclass
class LectureDoc:
    """一道题的完整讲稿。顶层类"""
    core: Core
    teach: Teach
    summary: Optional[Summary] = None        # 可选：套路/无升华价值的题可整段省略升华

    @classmethod
    def from_dict(cls, data: dict) -> "LectureDoc":
        core = Core.from_dict(data["core"])
        teach = Teach.from_dict(data["teach"])
        # summary 可省略；若写了就必须合规（非空 beats，见 Summary.from_dict）
        summary = Summary.from_dict(data["summary"]) if data.get("summary") else None
        # 向后兼容：顶层 figure（旧格式）下沉到 core.figure
        if core.figure is None and data.get("figure"):
            core.figure = Figure.from_dict(data["figure"])
        # 把 act 级别的 figure 提升到 core.figure（仅当 core 没有自带图时）
        if core.figure is None:
            for act_idx, act in enumerate(teach.acts):
                if act.figure is not None:
                    fig = act.figure
                    if fig.reveal_at_act is None:
                        fig.reveal_at_act = act_idx
                    core.figure = fig
                    break
        return cls(core=core, teach=teach, summary=summary)

    @classmethod
    def from_yaml_file(cls, path: Union[str, Path]) -> "LectureDoc":
        path = Path(path)
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_yaml_string(cls, text: str) -> "LectureDoc":
        return cls.from_dict(yaml.safe_load(text))

    # ---------- 便捷查询 ----------

    def iter_beats(self) -> list[tuple[str, int, int, Beat]]:
        """
        遍历所有 beat，返回 (stage, act_idx, beat_idx, beat) 四元组。
        stage 取值 'teach' 或 'summary'；summary 时 act_idx = -1。
        """
        result = []
        for ai, act in enumerate(self.teach.acts):
            for bi, beat in enumerate(act.beats):
                result.append(("teach", ai, bi, beat))
        if self.summary is not None:
            for bi, beat in enumerate(self.summary.beats):
                result.append(("summary", -1, bi, beat))
        return result

    def total_beats(self) -> int:
        summary_n = len(self.summary.beats) if self.summary is not None else 0
        return sum(len(act.beats) for act in self.teach.acts) + summary_n

    def figure_referenced_ids(self) -> set:
        """收集所有 beat 里 show:{type:figure} 引用的图元 id。

        这些 id 对应的图元会在 FigureRegion 初始隐藏，到对应 beat 才被唤出；
        未被任何 beat 引用的图元沿用旧行为（figure 出现时整组显示）。
        """
        ids = set()
        for _s, _a, _b, beat in self.iter_beats():
            if beat.show is not None and beat.show.type == BlockType.FIGURE:
                ids.update(beat.show.ref)
        return ids


# =====================================================================
# 校验
# =====================================================================

def validate(doc: LectureDoc) -> list[str]:
    """
    软约束检查。返回警告字符串列表（空列表表示完全通过）。
    硬约束在 from_dict 时已经抛异常，此处只查软约束。
    """
    warnings = []

    wow_count = 0
    for stage, ai, bi, beat in doc.iter_beats():
        loc = f"{stage}.{ai}.{bi}" if stage == "teach" else f"summary.{bi}"

        # say 过长兜底（与动画 mode 解耦：step 恒为逐字写出，不再因 spotlight 长度报警）
        if len(beat.say) > 250:
            warnings.append(f"[{loc}] say 偏长 {len(beat.say)} 字，建议拆拍或精简")

        # say 不能有双引号
        if '"' in beat.say:
            warnings.append(f"[{loc}] say 内有双引号（会破坏 YAML/TTS）")

        # say 不能有 LaTeX 符号
        if "$" in beat.say:
            warnings.append(f"[{loc}] say 内有 $ 符号（应翻译为口语）")

        # 计数 wow_formula
        if beat.show and beat.show.type == BlockType.WOW_FORMULA:
            wow_count += 1

    if wow_count > 2:
        warnings.append(f"wow_formula 出现 {wow_count} 次，建议不超过 2 处")

    # 每个 act 的 beat 数
    for ai, act in enumerate(doc.teach.acts):
        if len(act.beats) > 15:
            warnings.append(f"[teach.{ai}] act '{act.title}' 有 {len(act.beats)} 个 beat，建议拆分")

    return warnings


# =====================================================================
# 自测
# =====================================================================

if __name__ == "__main__":
    import sys

    samples_dir = Path(__file__).parent.parent / "samples" / "yaml样例"
    if not samples_dir.exists():
        print(f"[WARN] 样例目录不存在：{samples_dir}")
        sys.exit(0)

    for yaml_file in sorted(samples_dir.glob("*.yaml")):
        print(f"\n=== {yaml_file.name} ===")
        try:
            doc = LectureDoc.from_yaml_file(yaml_file)
            print(f"✓ 解析成功")
            print(f"  title: {doc.core.title}")
            print(f"  layout: {doc.core.layout_branch}")
            print(f"  keypoint: {len(doc.core.keypoint)} 条")
            print(f"  acts: {len(doc.teach.acts)}")
            print(f"  total beats: {doc.total_beats()}")
            print(f"  summary beats: {len(doc.summary.beats) if doc.summary else 0}（无升华段）" if not doc.summary else f"  summary beats: {len(doc.summary.beats)}")

            warnings = validate(doc)
            if warnings:
                print(f"  ⚠ 软约束警告 {len(warnings)} 条：")
                for w in warnings[:5]:
                    print(f"    - {w}")
                if len(warnings) > 5:
                    print(f"    ... 还有 {len(warnings) - 5} 条")
            else:
                print(f"  ✓ 软约束全部通过")
        except Exception as e:
            print(f"✗ 解析失败：{e}")
