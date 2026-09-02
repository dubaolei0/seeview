# 讲义输入 Markdown 自动生成工具

用途：根据微课标题、知识点标题和题源层级规划，从题库中推荐候选题，并生成 `讲义生成工具.exe` 需要的输入 md。

## 当前试点

当前配置文件是 `topics_derivative.json`，覆盖导数章节的考法分支课与原子基础微课试点。

## 推荐使用流程

先生成候选题报告，不写讲义输入文件：

```powershell
python generate_handout_inputs.py
```

人工检查 `候选题报告_导数.md` 后，再生成 md：

```powershell
python generate_handout_inputs.py --generate
```

默认输出目录：

```text
自动生成讲义工作区/哈斯工作区/讲义生成工具/输入
```

## 第二版能力

第二版支持按微课类型分层选题：

- `original`：高考原题（`depth_level=0`）
- `molecular`：分子题（`depth_level=1`）
- `atomic`：原子题（`depth_level=2`）
- `textbook`：教材题（来自教材题目索引；当前仅预留接口）

典型用法：

- 原子基础微课：优先 `atomic`，后续可接 `textbook + atomic`
- 考法分支课：优先 `molecular`，再补 `original`
- 情境化综合课：优先 `original`

## 配置格式

### 旧格式（兼容）

```json
{
  "id": "K-DS-001-C",
  "title": "由单调性反求参数",
  "knowledge_title": "把单调性条件转化为导数恒成立",
  "type": "考法分支课",
  "preferred_sources": ["2023新高考II6"],
  "include": ["单调", "参数", "恒成立", "导数"],
  "exclude": ["向量", "数列"],
  "example_count": 3
}
```

若仍使用旧格式，脚本会自动按：

```json
{"example_plan": [{"source": "original", "count": 3}]}
```

处理，保持第一版行为。

### 新格式（推荐）

```json
{
  "id": "K-DS-003-A",
  "title": "曲线上一点处切线",
  "knowledge_title": "用导数求已知切点处的切线方程",
  "lesson_type": "考法分支课",
  "example_plan": [
    {"source": "molecular", "count": 2},
    {"source": "original", "count": 1}
  ],
  "preferred_sources": ["2021全国甲卷理13", "2023全国甲卷文8"],
  "include": ["切线", "在点", "斜率", "导数"],
  "exclude": ["圆", "椭圆", "抛物线"]
}
```

原子基础微课示例：

```json
{
  "id": "B-DS-001",
  "title": "基本初等函数导数公式",
  "knowledge_title": "常用导数公式速记",
  "lesson_type": "原子基础微课",
  "example_plan": [
    {"source": "atomic", "count": 3}
  ],
  "include": ["导数公式", "导数", "求导"],
  "exclude": ["分类讨论", "恒成立", "零点"]
}
```

## 候选题报告

第二版报告会按 topic 内的 `example_plan` 分区展示，例如：

- 候选题源：分子题（计划取 2 题）
- 候选题源：原题（计划取 1 题）

并展示：

- 题源层级
- 分数
- 题型
- 匹配理由
- 题干预览

如果某个题源候选不足，报告中会直接提示。

## 正式输出 md

生成后的 md 仍只包含：

- 微课标题
- 知识点标题
- 例题
- 选项（如果有）

不会包含答案和解析。

第二版会在例题标题中标注题源类型，例如：

```markdown
**例 1**（分子题｜2022年新高考II卷第14题）
**例 2**（原题｜2021年全国甲卷（理科）第13题）
**例 3**（原子题｜2022年新高考II卷第22题）
```

## 教材题索引接口

脚本已预留教材题接入口，默认会尝试读取：

```text
knowledge/教材题目索引/选必第二册_导数题目索引.jsonl
```

当前该索引文件尚未建立，因此：

- 如果 topic 未使用 `textbook` 题源：不受影响
- 如果 topic 使用了 `textbook` 题源：默认给出 warning，并跳过该题源
- 如果希望严格检查教材索引是否存在，可加：

```powershell
python generate_handout_inputs.py --strict-textbook
```

也可以手动指定教材索引路径：

```powershell
python generate_handout_inputs.py --textbook-index "Z:\_共享文件夹\knowledge\教材题目索引\选必第二册_导数题目索引.jsonl"
```

## CLI 参数

- `--generate`：输出正式 md
- `--topics`：指定 topic 配置文件
- `--report`：指定候选题报告输出路径
- `--output-dir`：指定正式 md 输出目录
- `--textbook-index`：指定教材题索引 jsonl
- `--strict-textbook`：当需要教材题但索引缺失时直接报错退出

## 设计原则

- 保留“先报告、后生成”的人工审题流程
- 继续读取 `records/选题记录表.md`，跳过已占用原题
- 分子题 / 原子题按记录 id 去重，避免误删同一原题下不同拆解层级
- 生成的 md 只包含题目和选项，不包含答案解析，符合现有 exe 输入要求
- 教材题先接接口，不强行依赖尚未建立的索引文件

## 后续建议

下一步可以继续做两件事：

1. 建立 `knowledge/教材题目索引/选必第二册_导数题目索引.jsonl`
2. 把更多导数 topic 从旧格式逐步迁移到 `lesson_type + example_plan` 新格式
