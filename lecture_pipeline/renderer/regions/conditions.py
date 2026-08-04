"""
ConditionsRegion · 已知条件栏

布局 D 中右侧上方区域，显示题干的关键已知条件。
讲题阶段常驻，内容不变。

视觉上与 AnchorRegion 完全一致（"已知"标签 + 分割线 + 条目列表），
只是位置用 CONDITIONS_BOX、数据来源是 conditions 而非 keypoint。
"""

from __future__ import annotations

from ..theme import CONDITIONS_BOX
from .anchor import AnchorRegion


class ConditionsRegion(AnchorRegion):
    """已知条件栏。布局 D 下使用（右上方）。复用 AnchorRegion 的全部视觉逻辑。"""

    def __init__(self, conditions: list[str], tex_template=None, box=None):
        super().__init__(
            keypoints=conditions,
            tex_template=tex_template,
            box=box or CONDITIONS_BOX,
        )
        self.name = "Conditions"
