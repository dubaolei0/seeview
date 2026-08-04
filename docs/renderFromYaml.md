# renderFromYaml 接口业务逻辑梳理

> 接口：`POST /seeview/render`（multipart 上传 maths 讲题 yaml，同步返回带配音 mp4）
> 涉及模块：`seeview`（Controller）· `manim-renderer`（Service）· `lecture_pipeline`（Python 渲染引擎）

## 一、整体调用链

```
HTTP POST /seeview/render (multipart: file=讲题yaml, quality, voice)
   │
   ▼  SeeViewController.renderFromYaml()
YamlRenderService.renderYaml(yaml, quality, voice)        ← Java 侧
   │  ① 校验画质 -> ② 写临时 yaml -> ③ ProcessBuilder 起子进程 -> ④ 等待 -> ⑤ 找 mp4 -> ⑥ 清理
   │
   ▼  子进程：python -m renderer.render <yaml> --quality <q> [--tts-voice <v>]
lecture_pipeline/renderer/render.py  render_lecture()     ← Python 侧（唯一被直接调起的脚本）
   │  解析 yaml -> TTS 生成音频时间线 -> Manim 渲染无声视频 -> ffmpeg 合并音视频
   ▼
返回 mp4 字节流（HTTP 直接回传 video/mp4）
```

Java 侧只做「透传 + 编排 + 回读」：**yaml 不在 Java 解析**，schema 校验、TTS、渲染全交给 Python 引擎。

---

## 二、Java 侧业务逻辑

### 1. `SeeViewController.renderFromYaml`
（`seeview/src/main/java/com/yuanxuan/seeview/controller/SeeViewController.java:54-84`）

- 入参：`file`(yaml 文件)、`quality`(默认 `medium`)、`voice`(可选 TTS 音色)。
- `parseQuality`（`:86-92`）把 `low/l`、`high/h`、其它 -> `MEDIUM` 映射成 `Quality` 枚举；非法值直接返回 **400 JSON**。
- 调 `yamlRenderService.renderYaml(...)`，拿到 mp4 字节后以 `attachment; filename="lecture.mp4"`、`video/mp4` 直接回传（**同步阻塞返回二进制**，不是下载链接）。
- 渲染抛 `ManimRenderException` -> 返回 **500 JSON**（`escapeJson` 转义错误信息）。

### 2. `YamlRenderService.renderYaml`
（`manim-renderer/src/main/java/com/yuanxuan/manim/service/YamlRenderService.java:51-125`）

1. **提前校验画质**：`mapQuality`（`:144-152`）只接受 `LOW/MEDIUM/HIGH -> low/medium/high`；`PRODUCTION/FOUR_K` 直接抛 `IllegalArgumentException`（renderer.render 不支持）。
2. **环境检查**：`engineDir` 必须存在；`resolvePython`（`:170-173`）解析 python 路径（相对路径基于 engineDir），不可执行就抛带 venv 建议的错误。
3. **写临时 yaml**：`problemId = "see_"+UUID前16位`，写到 `engineDir/<problemId>.yaml`。这个文件名 stem 就是 renderer 的输出 mp4 名（`config.output_file = problem_id`，render.py:509）。
4. **构造命令**（`buildCommand` `:128-141`）：
   `python -m renderer.render <yaml绝对路径> --quality <q> [--tts-voice <v>]`
5. **起子进程**（`:78-89`）：`cwd=engineDir`、`redirectErrorStream(true)`、输出重定向到 `<problemId>.log`（避免管道死锁）。
6. **注入环境变量**（`applyEnvironment` `:162-167`）：`PYTHONIOENCODING=utf-8`（防 Windows GBK 乱码）、`DASHSCOPE_API_KEY`（阿里云 TTS key，未配则不注入）。
7. **等待**（`:93-106`）：`waitFor(timeout)`；超时 `destroyForcibly` + 抛异常；非 0 退出抛含 stdout/stderr 的异常。
8. **找 mp4**（`findMp4` `:176-186`）：在 `media/videos/**` 下 walk 找 `<problemId>.mp4`（manim 按画质分子目录，所以必须递归）。
9. **读字节返回**，`finally` 清理临时 yaml、log、mp4（`:114-124`）。
10. 另有 `checkEnvironment()`（`:194-215`）做启动预检：python、engineDir、ffmpeg、xelatex、TTS key。

> 注意命令里 **没有传 `--tts-provider`**，render.py 侧默认 `auto`：未指定音色走阿里云，`zh_` 开头音色自动推断为豆包（render.py:624-628）。

---

## 三、直接被调起的 Python 脚本

**只有一个：`lecture_pipeline/renderer/render.py`**，以模块 `renderer.render` 方式运行（`cwd=lecture_pipeline`，所以包名是 `renderer`；它的 docstring 里写的 `-m lecture_pipeline.renderer.render` 是 cwd 在上一层时的等价写法，同一文件）。

`main()`（render.py:608-683）解析命令行后调 `render_lecture()`（:423-524），这是整个渲染的主流程：

| 步骤 | 做的事 |
|---|---|
| 0 | `_ensure_vendored_texmf()`：把引擎自带的 `renderer/common/texmf` 前置到 `TEXINPUTS`，让 xelatex 优先用随引擎的宏包（如 multiple-choice.sty），免联网 |
| 0b | `register_vendored_fonts()`：注册自带中文字体给 Manim Text(Pango)，标题等不依赖系统装字 |
| 1 | `LectureDoc.from_yaml_file()`：解析 yaml -> `LectureDoc` 数据模型 |
| 2 | `validate(doc)`：软约束校验，只打印警告不阻断 |
| 3 | `build_audio_timeline()`：**TTS 先行**，把所有 `say` 文本合成音频并算出每段时间轴（声轨驱动画面） |
| 4 | 按 quality 设置 manim 像素/帧率（low=480p/15fps、medium=720p/30fps、high=1080p/60fps） |
| 5 | 选场景类（含 `geometry3d` 用 `LectureScene3D`，否则 `LectureScene2D`），`scene.render()` 出无声 mp4 |
| 6 | `_merge_audio()`：用 ffmpeg 把无声 mp4 + 混合 wav 合并成最终带配音 mp4 |

`_run_lecture()`（:127-388）是场景 `construct` 的主流程，按 **读题 -> cover_to_teach 转场 -> 讲题 -> teach_to_summary 转场 -> 升华** 五段编排画面，每段时长由音频时间线驱动。

---

## 四、render.py 内部调用的 Python 模块及作用

按调用层次整理（均在 `lecture_pipeline/` 内，自包含）：

### Schema / 数据层
- `renderer/schema.py` - `LectureDoc`/`Core`/`Teach`/`Act`/`Beat`/`Figure` 等数据类 + `from_yaml_file()` 解析器 + `validate()` 软约束。定义枚举 `Transition`(soft/hard)、`FigureType`(tikz/image/plot/schematic/geometry3d) 等。yaml 的「合法不合法」全由它定。

### 音频 / TTS 层（声轨驱动核心）
- `renderer/common/audio_timeline.py` - `build_audio_timeline()`：遍历 read/teach/summary 全部 `say`，逐段调 TTS，按 `INTRO_SILENCE` 起点串联，段间塞静音，输出 `<id>_mixed.wav` + `AudioTimeline`（每段的 stage/act/beat/start/duration）。`_compute_gaps()` 是关键：在 stage 转场、act 转场处按视觉动画时长插入静音，**防止声画错位**。
- `src/tts_manager.py` - `TTSManager` + 两个 driver：
  - `CosyVoiceDriver`：阿里云百炼 CosyVoice v3（默认，用 `DASHSCOPE_API_KEY`，阻塞 websocket 调用放守护线程 + join 超时防永久挂起）。
  - `DoubaoDriver`：火山引擎豆包 TTS v3（流式 HTTP，支持 `[pause:2s]` 停顿标记拆分拼接、`context_texts` 引用上文保持语气连贯）。
  - `resolve_tts_config()`：解析音色短名别名（`longwan`/`liufei` 等 -> provider+voice），`auto` 推断 provider。
  - 带缓存索引（`cache_index.json`）、静音/失败检测、重试、失败日志（`failures.jsonl`）。
- `src/config.py` - `Config`：路径（`CACHE_DIR`/`OUTPUT_DIR`）、`load_dotenv()` 读 `.env`、TTS 凭据（`DOUBAO_APPID/TOKEN/CLUSTER/VOICE`，环境变量优先）。导入时即 `ensure_directories()`。
- `src/audio_silence_guard.py` - `enforce_tts_silence_quality()`：TTS 音频静音质量门，拒绝内部长静音的音频，触发重试；`append_shadow_log` 留证、`_quarantine_audio` 隔离坏音频。
- `renderer/common/paths.py` - `find_project_root()`：向上找含 `src/` 的目录，兼容「src 与 lecture_pipeline 同级」和「src 在 lecture_pipeline 内」两种部署布局（消除硬编码 `parents[3]` 的对拷问题）。

### 渲染 / 画面层
- `renderer/common/tex_template.py` - `get_chinese_template()`：给 manim 的 `Tex` 生成中文 xelatex 模板（CJK 字体）。
- `renderer/font_config.py` - `register_vendored_fonts()`：注册自带中文字体给 Manim 的 Pango Text。
- `renderer/theme.py` - 全局常量：颜色（`EYE_WHITE` 底色）、时序（`INTRO_SILENCE`/`BEAT_GAP`/`COVER_TO_TEACH_RUN_TIME` 等）、布局盒子（A/B/C/D 的 `FIGURE_BOX`/`BOARD_BOX`/`ANCHOR_BOX`…）、3D 相机参数。
- `renderer/stages/read.py`、`teach.py`、`summary.py` - 三阶段渲染函数 `render_read_stage`/`render_teach_stage`/`render_summary_stage`，按时间线播放各 beat 的 Show/Recall 动画。
- `renderer/animations/transitions.py` - `cover_to_teach`、`teach_to_summary` 阶段间转场动画。
- `renderer/regions/`（`header`/`anchor`/`conditions`/`board`/`figure`/`summary`）- 画面分区控件（标题栏、关键点、条件栏、主讲解区、题图、升华区）。
- `renderer/blocks/`（`step`/`knowledge_card`/`answer_box`/`wow_formula`/`warning`/`takeaway`/`mindmap_node` 等）- 讲解区/升华区内的具体内容块。
- `renderer/schema.py` 里的 `BlockType`/`Mode`/`RecallAction` 枚举驱动这些 block 的渲染。

### 外部依赖（非引擎内脚本，但被调用）
- `manim`（Scene/ThreeDScene 渲染）、`ffmpeg`（`_merge_audio` 子进程合并音视频）、`xelatex`（LaTeX 公式）、`pydub`（音频拼接）、`dashscope`（阿里云 SDK）。

---

## 五、几个易踩的点

1. **yaml 不在 Java 解析**：Java 是透传，schema 不合法的错误只能从子进程 stderr（`ManimRenderException`）里看到，不会在 400 阶段拦下。
2. **同步阻塞**：medium 画质要几分钟，HTTP 连接一直占着，靠 `timeout`（配置默认 600s）兜底，超时强杀进程。
3. **输出 mp4 用完即删**：`finally` 里把临时 yaml、log、mp4 都删了，只把字节留在内存返回；磁盘不留痕（但 `media/cache/tts` 下的 TTS 缓存会保留）。
4. **画质限制**：只支持 low/medium/high，`PRODUCTION/FOUR_K` 在 Java 阶段就拦掉。
5. **`normalize_say.py` 不在这条链路上**：它是独立的离线预处理工具（`python -m lecture_pipeline.normalize_say <yaml>`），用来把 say 里的孤立个位数字转汉字（`2x`->`二x`）防 TTS 误读，**renderFromYaml 不会调用它**——如果要用它得在上传前单独跑。同理 `smoke.py`、`audit_tts_silence.py`、`scripts/check_math_env_cjk.py` 也都是离线工具，不在渲染链路里。

---

## 附：关键配置（application.yaml）

```yaml
manim:
  python: ${user.dir}/lecture_pipeline/.venv/Scripts/python.exe   # Linux 为 .venv/bin/python
  engine-dir: ${user.dir}/lecture_pipeline
  timeout: 600s
  dashscope-key: ${DASHSCOPE_API_KEY:}
```

部署前置：装 Python 3.12 + XeLaTeX(MiKTeX) + ffmpeg 并入 PATH；在 `lecture_pipeline` 下建 venv 并 `pip install -r requirements.txt`；配 `DASHSCOPE_API_KEY`。
