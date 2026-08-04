"""
Blocks · 内容块工厂

每种 Block type 对应一个构造函数 build_xxx(show, tex_template) → Mobject。
统一由 dispatch() 入口根据 show.type 调用。
"""

from __future__ import annotations

from ..schema import Show, BlockType

from .step import build_step
from .knowledge_card import build_knowledge_card
from .answer_box import build_answer_box
from .wow_formula import build_wow_formula
from .warning import build_warning
from .takeaway import build_takeaway
from .mindmap_node import build_mindmap_node


# 分派表
_BUILDERS = {
    BlockType.STEP: build_step,
    BlockType.KNOWLEDGE_CARD: build_knowledge_card,
    BlockType.ANSWER_BOX: build_answer_box,
    BlockType.WOW_FORMULA: build_wow_formula,
    BlockType.WARNING: build_warning,
    BlockType.TAKEAWAY: build_takeaway,
    BlockType.MINDMAP_NODE: build_mindmap_node,
}


_TARGET_WIDTH_BUILDERS = {
    BlockType.STEP,
    BlockType.WARNING,
}


def build(show: Show, tex_template=None, target_screen_width: float | None = None):
    """
    根据 show.type 分派到具体的构造函数。
    返回 Mobject（未摆位）。
    """
    builder = _BUILDERS.get(show.type)
    if builder is None:
        raise ValueError(f"[blocks.build] 未知 block type: {show.type}")
    if target_screen_width is not None and show.type in _TARGET_WIDTH_BUILDERS:
        return builder(
            show,
            tex_template=tex_template,
            target_screen_width=target_screen_width,
        )
    return builder(show, tex_template=tex_template)


__all__ = [
    "build",
    "build_step",
    "build_knowledge_card",
    "build_answer_box",
    "build_wow_formula",
    "build_warning",
    "build_takeaway",
    "build_mindmap_node",
]
