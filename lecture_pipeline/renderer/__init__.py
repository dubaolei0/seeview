"""
Renderer v3 · 讲题视频渲染器

从 v3 schema yaml 渲染成 mp4 视频。
详细设计见 ../docs/能力地图.md 和 ../docs/schema规范.md。

模块结构：
- schema:     yaml 解析和数据类
- theme:      视觉主题（基于 templates.tex 的复刻）
- regions:    屏幕分区（顶栏/锚点/推导主区/几何图/升华）
- blocks:     内容块（step/knowledge_card/wow_formula 等）
- animations: 动画词汇（入场/强调/退场/转场）
- stages:     阶段主控（读题/讲题/升华 + 转场）
- render:     主入口
- common:     复用老代码的 util（tts/latex/plot）
"""

__version__ = "0.1.0-skeleton"
