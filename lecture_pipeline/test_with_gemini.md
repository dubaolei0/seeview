# Pipeline 端到端验证 · Gemini CLI 测试脚本

> 用 Gemini CLI 真跑一遍 Pipeline 1 + Pipeline 2，验证 prompt 是否能落地。
>
> 用法：在项目根目录启动 `gemini` CLI（保证它能读项目文件），然后依次粘贴下面三段。

---

## 第 1 段 · 让 Gemini 理解项目和 Pipeline 1

```
我现在要测试一个数学讲题视频流水线。这是 Pipeline 1，你要扮演备课老师，根据下面的 prompt 和样例做事。

请先读 `lecture_pipeline/prompts/pipeline1_备课.md` 这份 prompt 完整理解你的角色。

再读这 4 份备课样例理解风格：
- `lecture_pipeline/samples/备课样例/problem_01_备课.md` 便签版
- `lecture_pipeline/samples/备课样例/problem_17_备课.md` 标准版
- `lecture_pipeline/samples/备课样例/problem_19_备课.md` 压轴版
- `lecture_pipeline/samples/备课样例/problem_cylinder_备课.md` 标准版含示意图

读完简单告诉我你理解了。然后我会给你一道新题，你按 prompt 输出备课笔记。
```

等 Gemini 回应后：

## 第 2 段 · 给一道新题

任意挑一道 `data/襄阳期中讲解/` 里没做过备课的题，例如 problem_18：

```
题目：

【襄阳期中 第 18 题】（中档大题，立体几何）

如图，在四棱锥 P-ABCD 中，底面 ABCD 是边长为 2 的正方形，PA ⊥ 底面 ABCD，PA = 2，E 是 PD 的中点。
（1）证明：PB ∥ 平面 ACE；
（2）求二面角 D-AE-C 的正弦值。

请按 Pipeline 1 prompt 输出这道题的备课笔记。难度自判，结构自选。
```

把输出存到 `lecture_pipeline/samples/备课样例/_test_problem_18_备课.md`。

---

## 第 3 段 · 让 Gemini 转 Pipeline 2

```
现在切换到 Pipeline 2 角色——把刚才那份备课笔记转成可渲染的 yaml。

请先读 `lecture_pipeline/prompts/pipeline2_讲稿.md` 这份 prompt 完整理解你的角色。

再读 schema 和示例：
- `lecture_pipeline/docs/schema规范.md` 字段定义
- `lecture_pipeline/samples/yaml样例/simple_fast_complex_subtraction.yaml` 简单题快车道示例
- `lecture_pipeline/samples/yaml样例/_mini_show_in_read_draw.yaml` show_in_read + 分步画图示例
- `lecture_pipeline/samples/yaml样例/直三棱柱-向量法求平面夹角-T1.yaml` 较新的复杂题示例

注意：`lecture_pipeline/samples/yaml样例/_archive/legacy_20260703/` 是旧样例归档，只作历史追溯，不作为新稿风格参考。

然后基于刚才你产出的 `_test_problem_18_备课.md` 输出符合 schema 的完整 yaml，
保存到 `lecture_pipeline/samples/yaml样例/_test_problem_18.yaml`。
```

---

## 第 4 段 · 验证渲染

回到本机 PowerShell 执行：

```powershell
py -m lecture_pipeline.renderer.render lecture_pipeline\samples\yaml样例\_test_problem_18.yaml --validate-only
```

如果通过，再跑：

```powershell
py -m lecture_pipeline.renderer.render lecture_pipeline\samples\yaml样例\_test_problem_18.yaml --quality low --no-audio
```

观察：
- schema 校验是否一次过
- 软约束警告条数（理想 < 5 条）
- 渲染是否能正常出 mp4
- 视觉表现（acts 数量、beat 节拍、figure 是否合理）

---

## 验证收尾

如果两段都没问题，MVP 闭环就算端到端验证完成。把测试产物 `_test_problem_18_备课.md` 和 `_test_problem_18.yaml` 留在 samples 里作为"AI 实跑"成果案例。

如果出问题（比如 Gemini 写的 yaml 缺字段、产出风格偏差大），把不一致的地方反馈，我们改进 prompt。
