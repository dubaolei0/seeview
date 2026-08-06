"""
FigureRegion · 几何图栏

布局 C 下使用（题干含图）。讲题阶段常驻。

MVP 只支持 type=image 和 type=plot。
TikZ 内嵌支持留到 Phase 2。
"""

from __future__ import annotations

from typing import Optional

from manim import VGroup, ImageMobject, FadeIn, RIGHT, LEFT

from ..theme import FIGURE_BOX, BLOCK_SPACING, RegionBox
from ..schema import Figure, FigureType
from .base import Region


class FigureRegion(Region):
    """几何图栏。静态显示题干图，讲题阶段不变。"""

    def __init__(self, figure: Figure, box: RegionBox = None, referenced_ids=None,
                 tex_template=None):
        super().__init__(box or FIGURE_BOX, name="Figure")
        self.figure = figure
        self.tex_template = tex_template
        # 被 beat 用 show:{type:figure, ref:...} 引用的图元 id —— 初始隐藏，到那拍才唤出
        self._referenced_ids = set(referenced_ids or ())
        self._mob_by_id: dict = {}      # id -> mobject
        self._revealed_ids: set = set()  # 已唤出的 id，防重复

    def build(self) -> VGroup:
        if self.figure.type == FigureType.IMAGE:
            return self._build_image()
        elif self.figure.type == FigureType.PLOT:
            return self._build_plot()
        elif self.figure.type == FigureType.SCHEMATIC:
            return self._build_schematic()
        elif self.figure.type == FigureType.GEOMETRY3D:
            return self._build_geometry3d()
        else:
            # TikZ 暂不支持
            return VGroup()

    def _build_image(self):
        """从 path 加载图片：位图（png/jpg…）用 ImageMobject，矢量（svg）用 SVGMobject。"""
        if not self.figure.path:
            return VGroup()
        from manim import Group
        try:
            path = str(self.figure.path)
            if path.lower().endswith(".svg"):
                from manim import SVGMobject
                img = SVGMobject(path)
            else:
                img = ImageMobject(path)
            # 按区域等比缩放：先适配宽，超高再适配高
            img.scale_to_fit_width(self.box.width * 0.9)
            if img.height > self.box.height * 0.9:
                img.scale_to_fit_height(self.box.height * 0.9)
            img.move_to([self.center_x, self.center_y, 0])
            # Group 同时兼容 ImageMobject（位图）和 SVGMobject（矢量）
            self.content = Group(img)
            return self.content
        except Exception as e:
            print(f"[FigureRegion] 图片加载失败：{e}")
            return VGroup()

    def _build_plot(self) -> VGroup:
        """使用老的 plot_manager 绘图"""
        # 延迟导入，避免无图题目加载 plot_manager 失败
        import sys

        from ..common.paths import find_project_root

        project_root = find_project_root()
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        try:
            from src.clipped_plot_manager import ClippedPlotManager
        except ImportError:
            print("[FigureRegion] ClippedPlotManager 不可用")
            return VGroup()

        f = self.figure
        plot_mgr = ClippedPlotManager(
            x_range=f.x_range or [-3, 3, 1],
            y_range=f.y_range or [-3, 3, 1],
            position=[self.center_x, self.center_y, 0],
            width=self.box.width * 0.9,
            height=self.box.height * 0.9,
        )

        axes = plot_mgr.create_axes(
            show_tips=True,
            show_numbers=(f.show_numbers if f.show_numbers is not None else True),
        )
        axis_labels = plot_mgr.create_axis_labels(axes)
        group = VGroup(axes, axis_labels)

        # 绘制 elements（函数 / 点 / 线）
        for elem in f.elements or []:
            t = elem.get("type")
            if t == "function":
                curve = axes.plot(
                    lambda x, expr=elem["expression"]: eval(
                        expr, {"__builtins__": {}},
                        {"x": x, "np": __import__("numpy")},
                    ),
                    color=elem.get("color", "BLUE"),
                )
                group.add(curve)
            elif t == "point":
                pt = plot_mgr.mark_point(
                    axes, elem["position"],
                    color=elem.get("color", "RED"),
                    label=elem.get("label", ""),
                    tex_template=self.tex_template,
                )
                group.add(pt)
            # 更多类型按需扩展

        self.content = group
        return group

    def play_appearance(self, scene, run_time: float = 1.0):
        """几何图栏浮现"""
        if not self.content or len(self.content) == 0:
            self.build()
        if not self.content or len(self.content) == 0:
            return
        scene.play(FadeIn(self.content), run_time=run_time)

    def _finalize_content(self, group):
        """把被 beat 引用的图元移出初始显示（保留引用，待 reveal_element 唤出）。

        所有图元都先加入 group（保证 geometry3d 的整组缩放/位移作用到它们），
        再把被引用的从初始显示里摘出来——它们已带上正确的世界坐标，唤出时原位浮现。
        """
        for eid in self._referenced_ids:
            mob = self._mob_by_id.get(eid)
            if mob is not None:
                try:
                    group.remove(mob)
                except Exception:
                    pass
        self.content = group
        return group

    def reveal_element(self, scene, refs, anim: str = None, run_time: float = 0.8):
        """按 id 唤出一个/多个图元，带入场动画：fadein(默认) / create(描边) / grow(生长)。"""
        from manim import FadeIn as _FadeIn, Create as _Create, GrowFromCenter as _Grow
        anim_map = {"fadein": _FadeIn, "create": _Create, "grow": _Grow}
        anim_cls = anim_map.get((anim or "fadein").lower(), _FadeIn)
        plays = []
        for rid in refs or []:
            if rid in self._revealed_ids:
                continue
            mob = self._mob_by_id.get(rid)
            if mob is None:
                print(f"[FigureRegion] reveal: 未找到图元 id={rid}")
                continue
            plays.append(anim_cls(mob))
            self.content.add(mob)
            self._revealed_ids.add(rid)
        if plays:
            scene.play(*plays, run_time=run_time)

    # ------------------------------------------------------------------
    # schematic：通用 2D 示意图
    # ------------------------------------------------------------------
    # 每个 element 是一个 dict，支持以下 type：
    #   rect       {x, y, width, height, color?, stroke_width?, fill_color?, fill_opacity?}
    #   circle     {x, y, radius, color?, stroke_width?, fill_color?, fill_opacity?}
    #   line       {x1, y1, x2, y2, color?, stroke_width?, dashed?}
    #   dot        {x, y, color?}
    #   label      {x, y, text, font_size?, color?}     # 支持 $...$
    #   arrow      {x1, y1, x2, y2, color?}
    #   arc        {x, y, radius, start_angle, end_angle, color?, stroke_width?}
    #              start_angle / end_angle 单位：度
    #   polygon    {points: [[x1,y1], [x2,y2], ...], color?, stroke_width?, fill_color?, fill_opacity?}
    # 坐标都在一个"自定义坐标系"里，由 figure.x_range / y_range 定义。
    # 若没给 x_range / y_range，默认 [-5, 5] x [-5, 5]。

    def _build_schematic(self) -> VGroup:
        from manim import (
            Rectangle, Circle, Line, Dot, Arrow, DashedLine, VGroup as VG, Group,
            Arc, Polygon, DEGREES,
        )
        f = self.figure
        elements = f.elements or []

        # 数据坐标系 → 本区域坐标系的线性映射
        x_min, x_max = (f.x_range[0], f.x_range[1]) if f.x_range else (-5.0, 5.0)
        y_min, y_max = (f.y_range[0], f.y_range[1]) if f.y_range else (-5.0, 5.0)

        data_w = x_max - x_min
        data_h = y_max - y_min
        avail_w = self.box.width * 0.88
        avail_h = self.box.height * 0.88
        scale = min(avail_w / data_w, avail_h / data_h)

        def tx(x: float) -> float:
            return self.center_x + (x - (x_min + x_max) / 2) * scale

        def ty(y: float) -> float:
            return self.center_y + (y - (y_min + y_max) / 2) * scale

        def tlen(v: float) -> float:
            return v * scale

        group = Group()
        for el in elements:
            t = el.get("type")
            try:
                if t == "rect":
                    mob = Rectangle(
                        width=tlen(el["width"]),
                        height=tlen(el["height"]),
                        color=el.get("color", "#1F2937"),
                        stroke_width=el.get("stroke_width", 2),
                        fill_color=el.get("fill_color", None) or "#FFFFFF",
                        fill_opacity=el.get("fill_opacity", 0.0),
                    )
                    mob.move_to([tx(el["x"]), ty(el["y"]), 0])
                elif t == "circle":
                    mob = Circle(
                        radius=tlen(el["radius"]),
                        color=el.get("color", "#1F2937"),
                        stroke_width=el.get("stroke_width", 2),
                        fill_color=el.get("fill_color", None) or "#FFFFFF",
                        fill_opacity=el.get("fill_opacity", 0.0),
                    )
                    mob.move_to([tx(el["x"]), ty(el["y"]), 0])
                elif t == "line":
                    start = [tx(el["x1"]), ty(el["y1"]), 0]
                    end = [tx(el["x2"]), ty(el["y2"]), 0]
                    if el.get("dashed", False):
                        mob = DashedLine(
                            start, end,
                            color=el.get("color", "#1F2937"),
                            stroke_width=el.get("stroke_width", 2),
                        )
                    else:
                        mob = Line(
                            start, end,
                            color=el.get("color", "#1F2937"),
                            stroke_width=el.get("stroke_width", 2),
                        )
                elif t == "dot":
                    mob = Dot(
                        point=[tx(el["x"]), ty(el["y"]), 0],
                        color=el.get("color", "#B91C1C"),
                        radius=el.get("radius", 0.06),
                    )
                elif t in ("arrow", "vector"):
                    mob = Arrow(
                        start=[tx(el["x1"]), ty(el["y1"]), 0],
                        end=[tx(el["x2"]), ty(el["y2"]), 0],
                        color=el.get("color", "#1F2937"),
                        buff=0,
                        stroke_width=el.get("stroke_width", 3),
                    )
                elif t == "label":
                    from ..blocks.text_mixin import create_mixed_tex
                    from ..theme import FONT_SIZE_KEYPOINT_ITEM
                    # 支持 $...$ 混排
                    fs = el.get("font_size", FONT_SIZE_KEYPOINT_ITEM)
                    mob = create_mixed_tex(
                        el["text"],
                        font_size=fs,
                        color=el.get("color", "#1F2937"),
                    )
                    mob.move_to([tx(el["x"]), ty(el["y"]), 0])
                elif t == "arc":
                    # 圆心 (x, y)，数据坐标系里的 radius，角度单位：度
                    sa = el.get("start_angle", 0) * DEGREES
                    ea = el.get("end_angle", 90) * DEGREES
                    angle = ea - sa
                    mob = Arc(
                        radius=tlen(el.get("radius", 0.3)),
                        start_angle=sa,
                        angle=angle,
                        color=el.get("color", "#1E40AF"),
                        stroke_width=el.get("stroke_width", 2),
                        arc_center=[tx(el["x"]), ty(el["y"]), 0],
                    )
                elif t == "polygon":
                    pts = el.get("points", [])
                    if len(pts) < 3:
                        continue
                    transformed = [[tx(p[0]), ty(p[1]), 0] for p in pts]
                    mob = Polygon(
                        *transformed,
                        color=el.get("color", "#1F2937"),
                        stroke_width=el.get("stroke_width", 2),
                        fill_color=el.get("fill_color", None) or "#FFFFFF",
                        fill_opacity=el.get("fill_opacity", 0.0),
                    )
                elif t == "image":
                    # 图片元素：加载位图/矢量图，缩放到指定宽高
                    img_path = el.get("path", "")
                    if not img_path:
                        continue
                    if img_path.lower().endswith(".svg"):
                        from manim import SVGMobject
                        mob = SVGMobject(img_path)
                    else:
                        mob = ImageMobject(img_path)
                    # 按数据坐标系的宽高缩放（先宽后高，独立拉伸）
                    target_w = tlen(el.get("width", 2.0))
                    target_h = tlen(el.get("height", 2.0))
                    mob.stretch_to_fit_width(target_w)
                    mob.stretch_to_fit_height(target_h)
                    mob.move_to([tx(el.get("x", 0)), ty(el.get("y", 0)), 0])
                else:
                    continue
                group.add(mob)
                eid = el.get("id")
                if eid is not None:
                    self._mob_by_id[eid] = mob
            except Exception as e:
                print(f"[FigureRegion] schematic element failed: {el} -> {e}")
                continue

        return self._finalize_content(group)


    # ------------------------------------------------------------------
    # geometry3d：通用 3D 几何
    # ------------------------------------------------------------------
    # 每个 element 是 dict，type 取值：
    #   sphere     {x, y, z, radius, color?, fill_opacity?, stroke_color?}
    #   cylinder   {x, y, z, radius, height, direction?='Z', color?, fill_opacity?}
    #   cube       {x, y, z, side, color?, fill_opacity?}     # 立方体
    #   box        {x, y, z, dx, dy, dz, color?, fill_opacity?}  # 长方体
    #   cone       {x, y, z, base_radius, height, direction?='Z', color?}
    #   prism      {x, y, z, dimensions:[a,b,c], color?}
    #   plane      {x_range:[a,b], y_range:[c,d], z=0, color?, fill_opacity?}
    #   segment3d  {p1:[x,y,z], p2:[x,y,z], color?, dashed?, stroke_width?}
    #   dot3d      {x, y, z, color?, radius?}
    #   label3d    {x, y, z, text, font_size?, color?}
    # 单位：直接用 manim 单位（不再做 data → display 缩放，3D 摄像机会处理透视）

    def _build_geometry3d(self):
        """3D 元素直接构建到世界坐标。要求 Scene 是 ThreeDScene。

        最后整组下移 GEOMETRY3D_Y_OFFSET，避免顶部超出屏幕。
        """
        from manim import (
            Sphere, Cylinder, Cube, Cone, Prism, Surface,
            Line3D, DashedLine, Dot3D, Arrow3D, Group as _Group,
            MathTex, Text as _Text, DOWN as _DOWN,
        )
        import numpy as np
        from ..theme import GEOMETRY3D_Y_OFFSET

        f = self.figure
        elements = f.elements or []

        group = _Group()
        for el in elements:
            t = el.get("type")
            try:
                if t == "sphere":
                    mob = Sphere(
                        center=np.array([el["x"], el["y"], el["z"]], dtype=float),
                        radius=el.get("radius", 1.0),
                        resolution=(20, 20),
                    )
                    color = el.get("color", "#1E40AF")
                    mob.set_fill(color, opacity=el.get("fill_opacity", 0.4))
                    mob.set_stroke(el.get("stroke_color", color), width=1)
                elif t == "cylinder":
                    direction_str = el.get("direction", "Z").upper()
                    direction = {"X": np.array([1.0, 0, 0]),
                                 "Y": np.array([0, 1.0, 0]),
                                 "Z": np.array([0, 0, 1.0])}.get(direction_str, np.array([0, 0, 1.0]))
                    mob = Cylinder(
                        radius=el.get("radius", 1.0),
                        height=el.get("height", 2.0),
                        direction=direction,
                        resolution=(24, 12),
                        show_ends=True,
                    )
                    mob.move_to([el["x"], el["y"], el["z"]])
                    color = el.get("color", "#9CA3AF")
                    mob.set_fill(color, opacity=el.get("fill_opacity", 0.25))
                    mob.set_stroke(color, width=1)
                elif t == "cube":
                    mob = Cube(
                        side_length=el.get("side", 2.0),
                        fill_opacity=el.get("fill_opacity", 0.3),
                        fill_color=el.get("color", "#9CA3AF"),
                        stroke_width=1,
                    )
                    mob.move_to([el["x"], el["y"], el["z"]])
                elif t == "box":
                    mob = Prism(
                        dimensions=[el["dx"], el["dy"], el["dz"]],
                        fill_opacity=el.get("fill_opacity", 0.3),
                        fill_color=el.get("color", "#9CA3AF"),
                        stroke_width=1,
                    )
                    mob.move_to([el["x"], el["y"], el["z"]])
                elif t == "cone":
                    direction_str = el.get("direction", "Z").upper()
                    direction = {"X": np.array([1.0, 0, 0]),
                                 "Y": np.array([0, 1.0, 0]),
                                 "Z": np.array([0, 0, 1.0])}.get(direction_str, np.array([0, 0, 1.0]))
                    mob = Cone(
                        base_radius=el.get("base_radius", 1.0),
                        height=el.get("height", 2.0),
                        direction=direction,
                        resolution=24,
                    )
                    mob.move_to([el["x"], el["y"], el["z"]])
                    color = el.get("color", "#9CA3AF")
                    mob.set_fill(color, opacity=el.get("fill_opacity", 0.3))
                elif t == "prism":
                    mob = Prism(
                        dimensions=el.get("dimensions", [2, 2, 2]),
                        fill_opacity=el.get("fill_opacity", 0.3),
                        fill_color=el.get("color", "#9CA3AF"),
                        stroke_width=1,
                    )
                    mob.move_to([el["x"], el["y"], el["z"]])
                elif t == "plane":
                    xr = el.get("x_range", [-2, 2])
                    yr = el.get("y_range", [-2, 2])
                    z = el.get("z", 0)
                    mob = Surface(
                        lambda u, v, _z=z: np.array([u, v, _z]),
                        u_range=xr, v_range=yr,
                        resolution=(2, 2),
                        fill_opacity=el.get("fill_opacity", 0.2),
                        fill_color=el.get("color", "#D6DEF5"),
                        checkerboard_colors=False,
                        stroke_width=0.5,
                    )
                elif t == "segment3d":
                    p1 = np.array(el["p1"], dtype=float)
                    p2 = np.array(el["p2"], dtype=float)
                    if el.get("dashed", False):
                        mob = DashedLine(
                            start=p1, end=p2,
                            color=el.get("color", "#B91C1C"),
                            stroke_width=el.get("stroke_width", 3),
                        )
                    else:
                        mob = Line3D(
                            start=p1, end=p2,
                            color=el.get("color", "#1F2937"),
                            thickness=el.get("stroke_width", 0.02),
                        )
                elif t == "dot3d":
                    mob = Dot3D(
                        point=[el["x"], el["y"], el["z"]],
                        color=el.get("color", "#B91C1C"),
                        radius=el.get("radius", 0.08),
                    )
                elif t == "label3d":
                    text = el.get("text", "")
                    fs = el.get("font_size", 28)
                    if "$" in text:
                        # 提取公式
                        formula = text.strip().strip("$")
                        mob = MathTex(formula, font_size=fs, color=el.get("color", "#1F2937"))
                    else:
                        mob = _Text(text, font_size=fs, color=el.get("color", "#1F2937"))
                    mob.move_to([el["x"], el["y"], el["z"]])
                elif t == "vector3d":
                    mob = Arrow3D(
                        start=np.array(el["p1"], dtype=float),
                        end=np.array(el["p2"], dtype=float),
                        color=el.get("color", "#1F2937"),
                    )
                else:
                    continue
                group.add(mob)
                eid = el.get("id")
                if eid is not None:
                    self._mob_by_id[eid] = mob
            except Exception as e:
                print(f"[FigureRegion] geometry3d element failed: {el} -> {e}")
                continue

        # 整组缩放到目标尺寸（让 max(width, height, depth) ≤ max_size）
        from ..theme import GEOMETRY3D_DEFAULT_MAX_SIZE, GEOMETRY3D_DEFAULT_SHIFT
        max_size = f.max_size if f.max_size is not None else GEOMETRY3D_DEFAULT_MAX_SIZE
        try:
            current_max = max(group.width, group.height, group.depth) if hasattr(group, "depth") else max(group.width, group.height)
        except Exception:
            current_max = 0
        if current_max > 0 and current_max > max_size:
            group.scale(max_size / current_max)

        # 整组先归零（移到原点），再做位移
        group.move_to([0, 0, 0])

        # 默认位移：让 figure 大致落到屏幕右侧偏下（与 2D 模式 FIGURE_BOX 概念对齐）
        if f.shift is None:
            group.shift(list(GEOMETRY3D_DEFAULT_SHIFT))
        else:
            # 用户自定义位移完全替换默认值
            group.shift([float(f.shift[0]), float(f.shift[1]), float(f.shift[2])])

        return self._finalize_content(group)
