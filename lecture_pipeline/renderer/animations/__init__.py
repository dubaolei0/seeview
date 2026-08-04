"""
Animations · 动画词汇

按三类组织：入场 / 强调 / 退场，以及 Act/Stage 级的 transition。

使用风格：所有函数返回 Animation 对象，由 Scene.play(*anims) 执行。
这样可以多个动画合成、共享 run_time。
"""

from .entrance import entrance_animation
from .emphasis import emphasis_animation
from .exits import exit_animation
from .transitions import (
    transition_soft, transition_hard, transition_none,
    cover_to_teach, teach_to_summary,
)

__all__ = [
    "entrance_animation",
    "emphasis_animation",
    "exit_animation",
    "transition_soft",
    "transition_hard",
    "transition_none",
    "cover_to_teach",
    "teach_to_summary",
]
