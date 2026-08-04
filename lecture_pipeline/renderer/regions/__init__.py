"""
Regions · 屏幕分区

六个固定区域：
- HeaderRegion      顶栏（讲题/升华阶段常驻）
- AnchorRegion      锚点栏（布局 A）
- ConditionsRegion  已知条件栏（布局 D，右上方）
- FigureRegion      几何图栏（布局 C/D）
- BoardRegion       推导主区（讲题阶段，核心工作区，带滚动机制）
- SummaryRegion     升华主区（升华阶段替代 Board）

每个 Region 封装自己的位置、内容管理、Mobject 生命周期。
Pipeline 2 产生的 yaml 永远不写坐标；渲染器按 block type 自动路由到对应 Region。
"""

from .base import Region
from .header import HeaderRegion
from .anchor import AnchorRegion
from .conditions import ConditionsRegion
from .board import BoardRegion
from .figure import FigureRegion
from .summary import SummaryRegion

__all__ = [
    "Region",
    "HeaderRegion",
    "AnchorRegion",
    "ConditionsRegion",
    "BoardRegion",
    "FigureRegion",
    "SummaryRegion",
]
