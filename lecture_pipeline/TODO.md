# 渲染器 v3 + 流水线 · 待办清单

> 持续追踪。完成项划掉，新增项追加。第一期目标：把襄阳期中卷子全量跑出来（不含 3D 图，2D 辅助图为主）。

---

## P0 · 第一期阻塞项

- [x] 锚点框稳定（位置 / 字体不溢出 / 顶对齐）
- [x] schematic 2D 示意图（rect/circle/line/dot/arrow/label）
- [x] figure 延迟出场 `reveal_at_act`
- [x] TransformMatchingTex（`step.replace_prev: true`）
- [x] 升华阶段 takeaway 整体居中
- [x] 渲染器 2D 端到端：cylinder yaml + TTS 顺利出片
- [ ] **Pipeline 2 prompt 加 figure 写作章节**（schematic 元素表 + 1 个完整示例）
- [ ] **schema 规范文档更新**（schematic/replace_prev/reveal_at_act 字段补齐）
- [ ] **能力地图文档更新**（v2 → v3：3D / 替换 / figure 延迟出场）
- [ ] **第 19 题端到端**：备课 + yaml + 渲染 + 出片，作为完整测试样本

## P0 · 渲染器稳定性收尾

- [ ] minipage 单位换算的修复（已知问题：当前是"自然渲染 + 溢出缩放"，没用 minipage——这条改为"长 keypoint 的优化"）
- [ ] step 文本超出 BOARD 区域时的处理（当前用 `max_width_cm = BOARD_BOX_A.width * 0.95`，cm 单位换算同样不准；要改成"自然渲染 + 溢出缩放"或者真正算清 cm/manim 比率）
- [ ] 软约束警告处理：超字数的 say 当前只警告不阻塞；考虑给 prompt 提示"不要超长"

## P1 · Phase 2 候选（第一期跑完后再做）

- [ ] 思维导图渲染（`mindmap_node` block，summary 替代 takeaway 列表）
- [ ] 3D 几何（`geometry3d` figure）—— 已做基础但视觉有"侧棱倾斜"未解决，**第一期暂不用**
  - [ ] 相机角度/默认 shift/自旋稳定性
  - [ ] AI 端到端写 3D yaml 的可行性验证
- [ ] 动点滑动（MoveAlongPath 封装到 schema）
- [ ] wow_formula → 下一步的 TransformMatchingTex 衔接
- [ ] AI 端到端验证（用 Gemini CLI 跑一遍 Pipeline 1 + 2）

## P2 · 长尾

- [ ] 思源字体替换（装好字体后改 theme.py 的 `FONT_SONG / FONT_KAI` 常量）
- [ ] 打包成 Kiro Power
- [ ] 字数超限自动拆 beat（当前只警告）
- [ ] TikZ 内嵌（`figure.type: tikz`，目前 schema 里有但 figure.py 不支持）
- [ ] 视频封面（Windows 资源管理器看到的第一帧）质量提升

---

## 第一期作战计划

按用户决定：
1. **当下**：渲染器稳定 + prompt 完善 + 19 题端到端测试样本
2. **跑全量**：用户自己跑（AI 写 yaml + 渲染）
3. **观察问题**：跑出片后看视觉/节奏问题，迭代
