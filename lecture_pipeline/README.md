# 讲题视频生成流水线（v3）

一条把数学题目变成讲解视频的 AI 流水线。从原题输入到最终 mp4 输出分三步：**备课 → 讲稿 → 渲染**。

---

## 在团队共享文件夹中（部署说明）

本流水线已搬入共享工作区 `tools/lecture_pipeline/`，作为团队共享的视频生成资产。

- **自包含**：原本依赖父项目的 `src/`（`tts_manager` / `config` / `clipped_plot_manager`）已一并搬入 `tools/lecture_pipeline/src/`，导入路径已改为自包含（无需父项目）。
- **本地渲染**：Manim + XeLaTeX + FFmpeg 较重，**不要直接在网络盘 Z: 上渲染**。请把本目录拷到本地或在本地 clone 后运行；渲染产物（`media/`、`output/`、`*.mp4`）已被 `.gitignore` 挡在仓库外。
- **环境准备**：
  1. 装依赖：`pip install -r requirements.txt`（另需本机有 XeLaTeX 和 FFmpeg）
  2. 配密钥：复制 `.env.example` 为 `.env`，填入 `DASHSCOPE_API_KEY`（CosyVoice TTS 主驱动）
- **运行渲染**（在本目录下）：
  ```
  python -m renderer.render <yaml路径> --quality medium     # 出片
  python -m renderer.render <yaml路径> --no-audio           # 跳过 TTS 调试
  python -m renderer.render <yaml路径> --validate-only      # 只做 schema 校验
  ```

  TTS 音色是渲染配置，不写进讲稿 yaml。默认使用阿里云 CosyVoice 的 `longcheng_v3`。`--tts-voice` 可传完整音色 ID，也可传 `tts_voice_aliases.json` 里的短名：
  ```
  python -m renderer.render <yaml路径> --quality medium --tts-voice longwan
  python -m renderer.render <yaml路径> --quality medium --tts-voice liufei
  python -m renderer.render <yaml路径> --quality medium --tts-provider doubao --tts-voice zh_male_taocheng_uranus_bigtts
  ```
  如果只传 `--tts-voice`，短名会自动解析平台；完整音色 ID 以 `zh_` 开头时自动推断为豆包，否则默认阿里云。
  TTS 不做跨平台回退，失败时只重试当前音色 2 次。最终失败会返回非零退出码，并记录到 `media/cache/tts/failures.jsonl`。

> 终局规划见 `TODO.md`：渲染器 v3 跑通端到端后封装为 MCP/Power，挂到共享 `.mcp.json`。

---

## 整条流水线的全貌

```
[数学题目原文]
       │
       │  Pipeline 1（备课 AI）
       │  prompt: prompts/pipeline1_备课.md
       │  参考:   samples/备课样例/
       ▼
[备课笔记 .md]           ← 教学蓝图：卡点、跳跃、心法、讲解路径
       │
       │  Pipeline 2（讲稿 AI）
       │  prompt: prompts/pipeline2_讲稿.md
       │  参考:   docs/schema规范.md + samples/yaml样例/
       ▼
[讲稿 .yaml]             ← 符合 v3 schema 的结构化讲稿
       │
       │  渲染器 v3（工程代码，开发中）
       │  能力: docs/能力地图.md
       │  视觉: docs/templates.tex
       ▼
[讲解视频 .mp4]
```

---

## 设计哲学

### Pipeline 1（备课）做什么

像老师**在黑板前备课**。它不产出任何"讲课内容"，只产出一份教学蓝图：
- 这道题考什么
- 完整解法（教师风格，不是学生保姆版也不是跳跃的答案细则）
- 学生会卡在哪
- 关键跳跃点和它的 Why
- 易错点
- 通用心法

### Pipeline 2（讲稿）做什么

像老师**真正走上讲台**。它把 Pipeline 1 的备课翻译成:
- 具体 narration（台词）
- 屏幕呈现（板书、卡片、公式、思维导图）
- 节奏与演出（spotlight / construct / tour / insight 四种模式）

遵循**声画分工**：听觉牵引思维流动，视觉凝固认知结构，两者分工互补。

### 渲染器 v3 做什么

把 Pipeline 2 的 yaml 变成 mp4。内部有**状态机**——AI 看不见，Pipeline 2 只声明"这一拍该显示什么"，渲染器自己维护所有 Mobject 的位置、动画、转场。

---

## 文件地图

```
lecture_pipeline/
├── README.md                       # 本文件（入口）
│
├── docs/                           # 设计文档
│   ├── 能力地图.md                  # 渲染器 v3 的能力范围
│   ├── schema规范.md                # Pipeline 2 输出的 yaml 字段定义
│   └── templates.tex                # 视觉语言参考（颜色/字体/卡片样式）
│
├── prompts/                        # AI 使用的 Prompt
│   ├── pipeline1_备课.md            # 备课 AI 系统提示词
│   └── pipeline2_讲稿.md            # 讲稿 AI 系统提示词
│
└── samples/                        # 参考样例（AI 和人都可读）
    ├── 备课样例/                    # Pipeline 1 的产出样本
    │   ├── problem_01_备课.md      # ★ 简单题（便签版）
    │   ├── problem_08_备课.md      # ★★★★ 压轴（费马点情景题）
    │   ├── problem_17_备课.md      # ★★★ 中档（菱形向量三问）
    │   └── problem_19_备课.md      # ★★★★★ 压轴（布洛卡点）
    └── yaml样例/                    # Pipeline 2 的产出样本（v3 schema）
        ├── simple_fast_complex_subtraction.yaml  # 简单题快车道：短、准、有教师主体性
        ├── _mini_show_in_read_draw.yaml          # show_in_read + 分步画图能力样例
        ├── 直三棱柱-向量法求平面夹角-T1.yaml       # 较新空间向量/立体几何样例
        └── _archive/legacy_20260703/             # 旧版样例归档，只作追溯
```

---

## 当前进度

- ✅ Pipeline 1 prompt 写完，有 4 份备课样例
- ✅ v3 schema 规范定稿
- ✅ Pipeline 2 prompt 写完，有当前样例；旧版 yaml 样例已归档
- ✅ 渲染器 v3 能力地图定稿
- ✅ 渲染器 v3 工程实现（`renderer/` 已落地，自包含）
- ✅ 端到端验证（已在本地从 yaml 跑通出 mp4）
- ⬜ **打包为 Kiro Power**（见下文 TODO，渲染已通，可推进）

---

## 如何使用（当前阶段）

### Step 1：准备一道题

把题目原文写在任意位置（比如 `input/题目.md`）。

### Step 2：跑 Pipeline 1 得到备课笔记

用任意 AI Agent（Kiro / Claude Code / Cursor / ChatGPT）：

1. 加载 `prompts/pipeline1_备课.md` 作为系统提示
2. 让 AI 读一下 `samples/备课样例/` 下几份理解风格
3. 把题目原文粘进去
4. 获得备课 markdown，保存为 `your_project/备课.md`

### Step 3：跑 Pipeline 2 得到讲稿 yaml

同样的工具：

1. 加载 `prompts/pipeline2_讲稿.md` 作为系统提示
2. 让 AI 读 `docs/schema规范.md` 和 `samples/yaml样例/`
3. 把备课 markdown 贴进去
4. 获得讲稿 yaml

### Step 4：渲染成视频（已可用）

渲染器 v3 已实现并在本地跑通。**Z 盘不渲染，渲染在本地**：

1. 首次在本机配环境（一次即可）：
   ```
   powershell -ExecutionPolicy Bypass -File "Z:\_共享文件夹\tools\lecture_pipeline\bootstrap.ps1"
   ```
   它会复制引擎到本地、建 Python 3.12 venv 装依赖、检查 ffmpeg/xelatex、准备 `.env`。
2. 渲染一道题（yaml 可直接指向 Z 盘，成片自动拷回 yaml 同目录）：
   ```
   powershell -ExecutionPolicy Bypass -File "Z:\_共享文件夹\tools\lecture_pipeline\render.ps1" "<yaml路径>" -Quality medium -Sync
   ```
   `-NoAudio` 跳过 TTS 冒烟调试；`-Sync` 渲染前先同步最新引擎代码，建议保留，避免本地旧引擎未更新。

也可手动跑底层命令（见上文「部署说明」的 `python -m renderer.render ...`）。音色属于渲染参数，例如 `--tts-voice longwan`、`--tts-voice liufei` 或 `--tts-provider doubao --tts-voice zh_male_taocheng_uranus_bigtts`，不要写进讲稿 yaml。

---

## 与老资产的关系

本流水线（v3）是为新渲染器设计的。项目根目录下的老资产（**仅作参考，不再新增操作**）：

| 老资产 | 状态 | 与 v3 的关系 |
|---|---|---|
| `skills/讲题Skills.md` | legacy 参考 | 教学原理仍有效，格式部分过时 |
| `skills/YAML讲题规范.md` | legacy 参考 | 格式规范针对老渲染器 |
| `data/襄阳期中讲解/` | legacy yaml | 17 道题的旧格式 yaml，历史记录 |
| `scripts/batch_generate_write.py` | 在用 | 老渲染器，新渲染器未完成前仍用 |
| `docs/YAML生成助手Prompt.md` | 废弃 | 老版 prompt，新流水线不再用 |
| `新版提示词.md`（根目录） | 历史讨论 | 项目讨论记录，非当前规范 |

所有新产物**只在 `lecture_pipeline/` 内**增减。

---

## TODO · 项目完成时

**当渲染器 v3 跑通端到端后，把整条流水线打包成 Kiro Power**：

- 创建 `POWER.md`（本 README 的 Power 版本）
- 打包 `prompts/` 为 steering 文件
- 实现 `pipeline_server.py` 作为 MCP server，暴露 `run_pipeline1` / `run_pipeline2` / `render_video` 三个 tool
- 配置 `power.json`
- 发布成可分享的 Kiro Power

这样其他数学老师装一个 Power 就能用整套流水线。

（暂不要动，进度到位再提醒用户）

---

## 给 AI Agent 的阅读指引

如果你是一个 AI Agent（Kiro / Claude Code / Cursor）第一次打开这个项目：

1. **先读本文件**（`lecture_pipeline/README.md`）获得全貌
2. 用户要**备课**：读 `prompts/pipeline1_备课.md` + `samples/备课样例/`
3. 用户要**讲稿**：读 `prompts/pipeline2_讲稿.md` + `docs/schema规范.md` + `samples/yaml样例/`
4. 用户要**改渲染器**：读 `docs/能力地图.md` + `docs/templates.tex` + `samples/yaml样例/`
5. 用户**不说用新流水线就用老的**：读根目录 `skills/` 下的老文档

核心原则：**新增内容只在 `lecture_pipeline/` 内**，不要在其他根目录散落新文件。
