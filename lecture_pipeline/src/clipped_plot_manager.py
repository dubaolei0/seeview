"""
ClippedPlotManager - 受限绘图管理器

创建受限的绘图区域，防止图像与其他元素冲突。

核心特性：
- 图像限制在指定区域
- 坐标轴黑色数字
- 自动裁剪超出部分（可选）
"""

from manim import *
from manim.mobject.geometry.tips import ArrowTriangleFilledTip
import numpy as np
import logging

logger = logging.getLogger(__name__)


class ClippedPlotManager:
    """受限绘图管理器
    
    特性：
    - 图像限制在指定区域
    - 坐标轴黑色数字
    - 自动裁剪超出部分
    
    示例：
        >>> plot_mgr = ClippedPlotManager(
        ...     x_range=[0, 4, 1],
        ...     y_range=[-1, 3, 1],
        ...     position=[-3.6, -1.2, 0],
        ...     width=5.0,
        ...     height=4.5
        ... )
        >>> axes = plot_mgr.create_axes()
    """
    
    def __init__(
        self,
        x_range: list,
        y_range: list,
        position: list,
        width: float,
        height: float
    ):
        """初始化绘图管理器
        
        Args:
            x_range: X 轴范围 [min, max, step]
            y_range: Y 轴范围 [min, max, step]
            position: 位置 [x, y, z]
            width: 宽度
            height: 高度
        """
        self.x_range = x_range
        self.y_range = y_range
        self.position = position
        self.width = width
        self.height = height
        
        logger.info(f"ClippedPlotManager initialized: {width}×{height} at {position}")
    
    def create_axes(self, show_numbers: bool = True, show_tips: bool = True) -> Axes:
        """创建坐标轴（黑色数字，带箭头）
        
        Args:
            show_numbers: 是否显示数字
            show_tips: 是否显示箭头
        
        Returns:
            Axes: 坐标轴对象
        """
        axes = Axes(
            x_range=self.x_range,
            y_range=self.y_range,
            x_length=self.width,
            y_length=self.height,
            axis_config={
                "color": BLACK,
                "stroke_width": 1.5,
                "include_numbers": show_numbers,
                "font_size": 20,
                "tick_size": 0.05,  # 刻度线长度（缩短）
                "include_ticks": True,
                "numbers_to_exclude": [],  # 稍后处理
            },
            x_axis_config={
                "tip_shape": ArrowTriangleFilledTip,
                "tip_length": 0.12,  # 等边三角形：长度和宽度相近
                "tip_width": 0.12,
            },
            y_axis_config={
                "tip_shape": ArrowTriangleFilledTip,
                "tip_length": 0.12,
                "tip_width": 0.12,
            },
            tips=show_tips
        )
        
        # 设置数字颜色为黑色，并移除负半轴最后一个刻度
        if show_numbers:
            x_min = self.x_range[0]
            y_min = self.y_range[0]
            
            # 移除 x 轴负半轴最后一个刻度数字
            labels_to_remove = []
            for label in axes.x_axis.numbers:
                label.set_color(BLACK)
                if abs(label.get_value() - x_min) < 0.01:
                    labels_to_remove.append(label)
            for label in labels_to_remove:
                axes.x_axis.numbers.remove(label)
            
            # 移除 y 轴负半轴最后一个刻度数字
            labels_to_remove = []
            for label in axes.y_axis.numbers:
                label.set_color(BLACK)
                if abs(label.get_value() - y_min) < 0.01:
                    labels_to_remove.append(label)
            for label in labels_to_remove:
                axes.y_axis.numbers.remove(label)
        
        # 修改刻度线方向，并移除负半轴最后一个刻度线
        x_step = self.x_range[2] if len(self.x_range) > 2 else 1
        y_step = self.y_range[2] if len(self.y_range) > 2 else 1
        
        ticks_to_remove = []
        for i, tick in enumerate(axes.x_axis.ticks):
            tick.shift(UP * tick.get_height() / 2)
            # 检查是否是最小值位置的刻度
            tick_x = axes.x_axis.p2n(tick.get_center())
            if abs(tick_x - self.x_range[0]) < x_step * 0.5:
                ticks_to_remove.append(tick)
        for tick in ticks_to_remove:
            axes.x_axis.ticks.remove(tick)
        
        ticks_to_remove = []
        for i, tick in enumerate(axes.y_axis.ticks):
            tick.shift(LEFT * tick.get_width() / 2)
            # 检查是否是最小值位置的刻度
            tick_y = axes.y_axis.p2n(tick.get_center())
            if abs(tick_y - self.y_range[0]) < y_step * 0.5:
                ticks_to_remove.append(tick)
        for tick in ticks_to_remove:
            axes.y_axis.ticks.remove(tick)
        
        axes.move_to(self.position)
        
        logger.debug(f"Axes created at {self.position}")
        
        return axes
    
    def create_axis_labels(self, axes: Axes) -> VGroup:
        """创建坐标轴标签 x 和 y
        
        Args:
            axes: 坐标轴对象
        
        Returns:
            VGroup: 包含 x 和 y 标签的组
        """
        # x 标签放在箭头下方
        x_label = MathTex("x", color=BLACK, font_size=28)
        x_label.next_to(axes.x_axis.get_end(), DOWN, buff=0.15)
        
        # y 标签放在箭头右方
        y_label = MathTex("y", color=BLACK, font_size=28)
        y_label.next_to(axes.y_axis.get_end(), RIGHT, buff=0.15)
        
        return VGroup(x_label, y_label)
    
    def create_grid(self) -> NumberPlane:
        """创建网格
        
        Returns:
            NumberPlane: 网格对象
        """
        grid = NumberPlane(
            x_range=self.x_range,
            y_range=self.y_range,
            x_length=self.width,
            y_length=self.height,
            background_line_style={
                "stroke_color": GREY,
                "stroke_width": 1,
                "stroke_opacity": 0.3
            }
        )
        grid.move_to(self.position)
        
        return grid
    
    def create_clipped_group(self, *mobjects) -> VGroup:
        """创建裁剪组（可选功能）
        
        Args:
            *mobjects: 要裁剪的对象
        
        Returns:
            VGroup: 裁剪后的组
        """
        # 创建裁剪矩形
        clip_rect = Rectangle(
            width=self.width,
            height=self.height,
            stroke_width=0
        ).move_to(self.position)
        
        # 创建组并应用裁剪
        group = VGroup(*mobjects)
        # 注意：set_clip_path 在某些 Manim 版本中可能不可用
        # 如果不可用，可以注释掉这行
        try:
            group.set_clip_path(clip_rect)
        except AttributeError:
            logger.warning("set_clip_path not available, skipping clipping")
        
        return group
    
    def plot_function(
        self,
        axes: Axes,
        func,
        color=BLUE,
        x_range=None,
        **kwargs
    ):
        """绘制函数
        
        Args:
            axes: 坐标轴对象
            func: 函数（lambda 或可调用对象）
            color: 颜色
            x_range: X 范围（如果为 None，使用坐标轴范围）
            **kwargs: 传递给 plot 的其他参数
        
        Returns:
            ParametricFunction: 函数图像
        """
        if x_range is None:
            x_range = [self.x_range[0], self.x_range[1]]
        
        graph = axes.plot(func, color=color, x_range=x_range, **kwargs)
        
        return graph
    
    def mark_point(
        self,
        axes: Axes,
        point: list,
        color=RED,
        label: str = None,
        label_direction=UR,
        tex_template=None
    ) -> VGroup:
        """标记点
        
        Args:
            axes: 坐标轴对象
            point: 点坐标 [x, y]
            color: 颜色
            label: 标签文本（LaTeX 或纯文本）
            label_direction: 标签方向
            tex_template: LaTeX 模板（支持中文）
        
        Returns:
            VGroup: 点和标签的组
        """
        dot = Dot(
            axes.coords_to_point(*point),
            color=color,
            radius=0.08
        )
        
        group = VGroup(dot)
        
        if label:
            # 如果提供了 tex_template，使用 Tex；否则使用 MathTex
            if tex_template:
                label_mob = Tex(label, tex_template=tex_template, color=BLACK).scale(0.6)
            else:
                # 默认使用 MathTex，支持数学公式
                label_mob = MathTex(label, color=BLACK).scale(0.6)
            label_mob.next_to(dot, label_direction, buff=0.1)
            group.add(label_mob)
        
        return group
    
    def draw_line(
        self,
        axes: Axes,
        start_point: list,
        end_point: list,
        color=ORANGE,
        **kwargs
    ):
        """绘制直线
        
        Args:
            axes: 坐标轴对象
            start_point: 起点 [x, y]
            end_point: 终点 [x, y]
            color: 颜色
            **kwargs: 传递给 Line 的其他参数
        
        Returns:
            Line: 直线对象
        """
        line = Line(
            axes.coords_to_point(*start_point),
            axes.coords_to_point(*end_point),
            color=color,
            **kwargs
        )
        
        return line
