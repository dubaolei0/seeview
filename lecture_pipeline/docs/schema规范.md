# 渲染器 v3 · YAML Schema 规范

> Pipeline 2 生成的 yaml 所遵循的格式。本文档定义所有字段的含义、约束和默认值。
>
> 状态：**v1 草案**。待你审阅通过后锁定。

---

## 顶层结构

一份 yaml 对应**一道题**（或一个知识点讲解——未来扩展）。顶层 `core`、`teach` 必填，`summary` **可选**：

```yaml
core:       # 题目/知识点的元信息（必填）
  ...

teach:      # 讲题主体（必填）
  acts:
    - ...

summary:    # 升华总结（可选！套路/纯计算/无可迁移方法的题可整段省略，讲到答案干净收尾）
  beats:
    - ...
```

---

## 第一部分：`core`

读题阶段和讲题常驻区域需要的所有信息。

### 字段清单

```yaml
core:
  title: string           # 必填。顶栏文字。
                          # 例："襄阳期中 · 第 17 题" 或 "知识点1：共轭复数"
  
  statement: string       # 必填。题干（或知识点引入文本），含 LaTeX。
                          # 读题阶段完整显示，转场后根据 keypoint 决定去向。
  
  say: string             # 必填。读题阶段的 TTS 文本。
                          # 纯口语，不含 LaTeX 符号，不含双引号。
  
  keypoint: [string]      # 可选。讲题阶段右侧锚点卡片的内容列表。
                          # 每条可以是一行 LaTeX 文本。
                          # 如果省略 → 使用布局分支 B（题干缩到顶栏下）或 C（题干含图）
  
  figure: object          # 可选。题干自带的图。
                          # 详见下文"figure 字段"
```

### 布局分支自动选择

渲染器根据 `keypoint` 和 `figure` 自动选择三种布局之一：

| 情况 | 分支 | 讲题阶段主区布局 |
|---|---|---|
| 有 keypoint | A | 左 70% 推导主区 + 右 30% 锚点卡片 |
| 无 keypoint，有 figure | C | 左 70% 推导主区 + 右 30% 几何图 |
| 无 keypoint，无 figure | B | 全宽推导主区，题干缩到顶栏下一行 |

AI 不写布局名，只决定是否提供 keypoint / figure。

### keypoint 什么时候给

- **题干条件 3 条以上 + 每条简短**：给。如 Q19 的布洛卡点（3 个边长 + 1 个点的定义）
- **题干是概念说明 + 少量条件**：给少而精。如 Q8 费马点（只把"$|\vec a|=2$、$|\vec b|=3$、$\vec a\perp\vec b$"作为 keypoint，不把费马点定义放进去）
- **题干本身就是一行**：不给。如 Q1、Q5、Q6

### figure 字段

```yaml
figure:
  type: tikz | image | plot   # 必填。图的来源。
  
  # type=tikz 时
  source: string              # TikZ 源码
  
  # type=image 时
  path: string                # 图片文件路径（相对 yaml 文件）
  
  # type=plot 时（Manim 原生绘图，复用 plot_manager）
  x_range: [min, max, step]
  y_range: [min, max, step]
  elements:
    - type: function
      expression: "x**2"
      color: BLUE
    - type: point
      position: [1, 2]
      label: "$A$"
    - type: line
      points: [[0, 0], [2, 3]]
    # 等等
```

MVP 支持 type=image 和 type=plot。type=tikz 复用老渲染器能力，Phase 2 加。

---

## 第二部分：`teach`

讲题主体。结构是一个 acts 数组。

### 顶层

```yaml
teach:
  acts:
    - title: string       # 必填。此 act 的教学主题名。
      transition: string  # 可选。act 入场转场类型。默认 soft。
                          # 取值：none | soft | hard
      beats: [...]        # 必填。此 act 内的节拍列表。
```

### Transition 三种取值

| 值 | 含义 | 使用场景 |
|---|---|---|
| `none` | 无转场。板书连续，旧内容继续滚动累积 | 内容强连续的 act 切换（如"第一问"→"第一问推广"） |
| `soft` | 温和过渡。旧 Mobject 淡化（stroke_opacity 降到 0.3），不移除，新内容从空白位置开始 | 大部分 act 切换 |
| `hard` | 硬切。推导主区所有 Mobject fade out + 0.3-0.5 秒空白 + 新 act 从空画布开始 | 方法彻底换（如"解法一"→"解法二"）、进入顿悟时刻 |

注意：**顶栏、锚点卡片、几何图栏**在所有 transition 下都保持不变。

### beats 列表

beats 是 act 内的节拍列表。每个 beat 对应一次 TTS 播放 + 对应的屏幕变化。

---

## 第三部分：`beat`

最小节拍单位。渲染器按 beats 顺序执行，每个 beat 是一次音画同步。

### 字段清单

```yaml
- say: string           # 必填。TTS 文本。
                        # 不含 LaTeX 符号（翻译成口语："二分之一"而非 $\frac{1}{2}$）
                        # 不含双引号（破坏 YAML 结构 + TTS 不读）
                        # 长度根据 mode 决定：
                        #   spotlight 模式：10-40 字
                        #   construct 模式：允许 100-200 字
                        #   tour 模式：允许 50-150 字
  
  show: object          # 可选。这一拍新登场的内容。
                        # 详见下文"show 字段"
  
  recall: object        # 可选。强调已有内容（替代 show）。
                        # 详见下文"recall 字段"
                        # 注意：show 和 recall 二选一，不能同时出现
  
  mode: string          # 可选。演出模式。默认根据所在 stage 推断：
                        #   teach 默认 spotlight
                        #   summary 默认 construct
                        # 取值：spotlight | construct | tour | insight
```

### Mode 四种取值（演出风格）

| mode | 节奏 | say 长度 | 典型动画 | 使用场景 |
|---|---|---|---|---|
| `spotlight` | 说得短、画一小块 | 10-40 字 | Write / FadeIn / Indicate | 常规推导、铺垫、讲步骤 |
| `construct` | 说得长、画稳定结构 | 100-200 字 | GrowFromCenter / 整组 FadeIn | 升华总结、知识地图、稳定展示 |
| `tour` | 说得长、不画新的、指已有 | 50-150 字 | Indicate / FocusOn / CircleAround | 回顾、反思、引用上文 |
| `insight` | 戏剧性、单一聚焦 | 30-80 字 | ScaleUp + Flash + Pause | wow 时刻、核心公式登场 |

**默认值推断规则**：
- teach.acts 里的 beat 未指定 mode → `spotlight`
- summary.beats 里的 beat 未指定 mode → `construct`
- show.type == wow_formula 时自动为 `insight`（不需要显式写）

### `show` 字段

show 描述这一拍新登场的内容。结构：

```yaml
show:
  type: string          # 必填。block 类型。见下文"Block 类型清单"
  # 后续字段取决于 type
```

### `recall` 字段

recall 强调已有内容，不创建新 block。结构：

```yaml
recall:
  of: string            # 可选。指定引用哪个 block。默认 "prev"（上一个 show）
                        # 取值：prev / prev_N（倒数第 N 个）/ block 的 id（如有）
  action: string        # 可选。强调方式。默认 indicate
                        # 取值：indicate | circle | focus | highlight | underline
```

简化形式（action 以字符串直接给）：

```yaml
recall: indicate        # 等价于 {of: prev, action: indicate}
```

---

## 第四部分：Block 类型清单

每种 block 对应一种视觉语义 + 一套默认样式和动画。

### 读题阶段 / 常驻区

| type | 归属 | 字段 |
|---|---|---|
| `problem_statement` | core.statement（自动生成，不由 beat 创建） | body |
| `keypoint_item` | core.keypoint（自动生成，不由 beat 创建） | body |

### 讲题主区

#### `step`
推导的一步。板书式默认字体显示。

```yaml
show:
  type: step
  body: string          # 必填。含 LaTeX 的文本。
  emphasis: [string]    # 可选。body 中需要高亮的片段（逐字匹配）。
                        # 高亮在 Write 动画完成后用 Indicate 触发。
```

#### `knowledge_card`
知识点卡片。YellowBox 黄底无框圆角样式。

```yaml
show:
  type: knowledge_card
  title: string         # 必填。卡片标题（蓝色粗体）。
  body: string          # 可选。主体文本。
  points: [string]      # 可选。要点列表（项目符号）。
  icon: string          # 可选。图标类型。取值：summary | think。默认 summary。
```

#### `answer_box`
答案框。YellowBox + 加粗大号。

```yaml
show:
  type: answer_box
  body: string          # 必填。答案内容。
```

#### `wow_formula`
顿悟公式。超大号居中 + 金色 + Flash 动画。

```yaml
show:
  type: wow_formula
  formula: string       # 必填。LaTeX 公式本体（不含 $ 包裹）。
  caption: string       # 可选。下方小字说明。
```

触发 `mode: insight`（自动）。

#### `warning`
易错提示。ExerciseBox 粉边虚线框。

```yaml
show:
  type: warning
  body: string          # 必填。警告内容。
  label: string         # 可选。前缀，如 "易错"、"注意"。默认"注意"。
```

### 升华主区

#### `takeaway`
心法条。楷体大号 + 箭头前缀。

```yaml
show:
  type: takeaway
  body: string          # 必填。心法内容。
  number: int           # 可选。序号（"第一层启发"）。如提供则自动加编号。
```

#### `mindmap_node`
思维导图节点。与其他 mindmap_node 自动连线成树。

```yaml
show:
  type: mindmap_node
  body: string          # 必填。节点文字。
  parent: string        # 可选。父节点的引用。默认空（即根节点或孤立节点）。
  level: int            # 可选。层级。默认 1。
```

---

## 第五部分：`summary`（可选）

升华阶段。结构更简单——直接 beats 列表，无 acts。

**整段可省略**：`summary` 不是必填。套路/纯计算/无可迁移方法论的题，**直接不写 `summary:` 这一段**——渲染时讲到答案就干净淡出收尾（讲解→升华的转场仍会把内容淡出清屏）。判断依据见备课「八、核心心法」：写了「无核心心法」就不写 summary。

⚠️ 但**一旦写了 `summary`，其 `beats` 不能为空**：要么整段不写，要么至少一条 takeaway。

```yaml
summary:                  # 可选；不需要升华就整段删掉
  beats:
    - say: string
      show: object        # 通常是 takeaway 或 mindmap_node
      mode: string        # 可选。默认 construct。
```

---

## 完整字段树（一眼看全）

```
root
├── core                              <必>
│   ├── title: str                    <必>
│   ├── statement: str                <必>
│   ├── say: str                      <必>
│   ├── keypoint: [str]               <可选>
│   └── figure: object                <可选>
│
├── teach                             <必>
│   └── acts: [                       <必>
│       - title: str                  <必>
│         transition: none|soft|hard  <可选，默认 soft>
│         beats: [                    <必>
│           - say: str                <必>
│             show: object            <可选>
│             recall: object | str    <可选；与 show 互斥>
│             mode: str               <可选，默认 spotlight>
│         ]
│       ]
│
└── summary                           <可选；不需要升华就整段省略>
    └── beats: [                      <若写了 summary 则必填、且非空>
        - say: str                    <必>
          show: object                <可选>
          mode: str                   <可选，默认 construct>
      ]
```

---

## 约束清单

**硬约束**（违反则 yaml 无效）：

1. say 内部**绝对不能**出现双引号 `"`（包括中文引号 "……"）
2. say 内部**绝对不能**出现 `$` 符号或 LaTeX 命令
3. show 和 recall **不能同时**出现在一个 beat 里
4. acts 数组至少有 1 个 act
5. 每个 act 的 beats 至少有 1 个 beat
6. `summary` 可整段省略；但**一旦写了 `summary`，其 beats 不能为空**（至少 1 个 beat）

**软约束**（违反会警告，不阻止渲染）：

1. mode=spotlight 时 say 不宜超过 60 字
2. mode=construct 时 say 不宜超过 250 字
3. wow_formula 每道题建议不超过 2 处
4. 单个 act 的 beats 不宜超过 15 个（过多建议拆成两个 act）

---

## 示例一览（完整示例见独立文件）

当前风格样例保留在 `tools/lecture_pipeline/samples/yaml样例/` 顶层：

- **简单题快车道** → `simple_fast_complex_subtraction.yaml`
  - 1 个 act，3 个 beat，无 summary
  - 重点示范：短、准、有教师主体性，不硬堆结构
- **show_in_read + 分步画图** → `_mini_show_in_read_draw.yaml`
  - 题图随读题出现，讲解阶段分步引用图形元素
- **空间向量/立体几何** → `直三棱柱-向量法求平面夹角-T1.yaml`
  - 较新的复杂题样例

旧版样例已归档到 `samples/yaml样例/_archive/legacy_20260703/`，只作追溯，不作为新稿风格参考。

---

## 和老 yaml 的对应

给习惯老 yaml 的开发者一个转换参照：

| 老 yaml 字段 | 新 yaml 对应 |
|---|---|
| `problem.title` | `core.title` |
| `problem.content` | `core.statement` |
| `problem.narration` | `core.say` |
| `solution.steps[i].content` | `teach.acts[j].beats[k].show.body`（含结构化 type）|
| `solution.steps[i].narration` | `teach.acts[j].beats[k].say` |
| `solution.steps[i]`（纯过渡） | `teach.acts[j].beats[k]`（无 show）|
| `solution.steps[i]` (type=plot) | `teach.acts[j].beats[k].show` (type=plot) |

主要变化：
- steps 升级成 beats + acts 分层
- content 字段统一成 show（带 type 的结构化对象）
- narration 改名 say
- 新增 core.keypoint、recall、mode 等概念
