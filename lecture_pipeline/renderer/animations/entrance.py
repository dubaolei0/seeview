"""
入场动画语义映射。

根据 block type 和 mode 返回合适的入场 Animation。
"""

from __future__ import annotations

from manim import Write, FadeIn, GrowFromCenter, Create, smooth

from ..schema import BlockType, Mode


def entrance_animation(mob, block_type: BlockType, mode: Mode = Mode.SPOTLIGHT):
    """
    选择合适的入场动画。返回 Animation，由调用方 scene.play。
    所有动画默认用 smooth 缓动，让节奏更自然。
    """
    # step 固定逐字写出（Write），不受 mode 影响 —— 板书推导就是要一笔一画出来
    if block_type == BlockType.STEP:
        return Write(mob, rate_func=smooth)

    # insight 模式统一 GrowFromCenter
    if mode == Mode.INSIGHT or block_type == BlockType.WOW_FORMULA:
        return GrowFromCenter(mob, rate_func=smooth)

    # construct 模式偏向 FadeIn（稳定出现）
    if mode == Mode.CONSTRUCT:
        return FadeIn(mob, rate_func=smooth)

    # 按类型分派（spotlight 默认）
    if block_type in (BlockType.KNOWLEDGE_CARD, BlockType.ANSWER_BOX):
        return GrowFromCenter(mob, rate_func=smooth)
    if block_type == BlockType.WARNING:
        return FadeIn(mob, rate_func=smooth)
    if block_type == BlockType.TAKEAWAY:
        from manim import DOWN
        return FadeIn(mob, shift=DOWN * 0.3, rate_func=smooth)
    if block_type == BlockType.MINDMAP_NODE:
        return GrowFromCenter(mob, rate_func=smooth)

    # 兜底
    return FadeIn(mob, rate_func=smooth)


def entrance_name(block_type: BlockType, mode: Mode = Mode.SPOTLIGHT) -> str:
    """用于 BoardRegion 的 animation 字符串参数"""
    # step 固定逐字写出，不受 mode 影响（与 entrance_animation 保持一致）
    if block_type == BlockType.STEP:
        return "write"
    if mode == Mode.INSIGHT or block_type == BlockType.WOW_FORMULA:
        return "grow_from_center"
    if mode == Mode.CONSTRUCT:
        return "fade_in"
    if block_type in (BlockType.KNOWLEDGE_CARD, BlockType.ANSWER_BOX):
        return "grow_from_center"
    return "fade_in"
