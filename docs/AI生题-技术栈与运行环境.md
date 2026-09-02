# AI 生题 · 技术栈与运行环境

> 适用对象:新机器部署 / 环境排障时对照检查。
> 范围:**AI 生题**功能(智能命题工作台 + 图库配图),不含讲题视频(manim/TTS)部分。
> 唯一配置入口:`seeview/src/main/resources/application.yaml`(下文简称 yaml)。

---

## 1. 技术栈总览

| 层 | 技术 | 作用 |
|---|---|---|
| 后端 | Java 21 + Spring Boot 3.5.6(`seeview` 模块,端口 8899) | Web 服务、生题编排 |
| LLM 接入 | LangChain4j 1.8.0(OpenAI 兼容协议) | 调大模型出题、图库选图、配图修正轮 |
| 材料解析 | Apache POI 5.4.1 | 上传 docx 转 Markdown(段落/表格/OMML 公式/内嵌图片) |
| 前端 | 纯静态 HTML/JS(`ai-question.html`),vendor 自带 KaTeX + marked + pdfjs | 生题工作台,无构建步骤 |
| 配图渲染 | 图库 JSON 模板 → `\def` 参数注入 → Python 编译脚本 → xelatex → pdf2image → PIL/numpy 按内容裁剪 → PNG | 题干配图(模板图与自由 TikZ 共用管线) |

**生题数据流**:上传材料(docx/md/文字)→ 视觉模型转述材料图片(可选,按图片哈希缓存)→ 大模型生成题目 JSON(含 `fig` 图库引用或自由 ```tikz 代码块)→ `FigureLibraryService` 按参数渲染图库模板为 PNG 插回题干;渲染失败项把题干+错误回传模型修正一轮,仍失败则回退自由 TikZ 轨道。

**配图编译链**(后端 `TikzCompiler` 子进程调用):

```
question_output/images 目录
  ↑ latex_snippet_tool.py(xelatex 编译 + 透明背景裁剪)
  ↑ lecture_pipeline/.venv/Scripts/python.exe
  ↑ FigureLibraryService(\def 参数注入 / 自由 TikZ 直传)
```

---

## 2. 必装软件

| 软件 | 版本/位置 | 说明 |
|---|---|---|
| **JDK** | **21**(pom 指定) | ⚠️ 本机系统 `JAVA_HOME` 是 JDK 8,命令行跑需先指向 JDK 21 |
| Maven | 用项目自带 `mvnw.cmd` | 版本固定,免单独安装 |
| **Python venv** | `lecture_pipeline\.venv` | README 说按 `lecture_pipeline/bootstrap.ps1` 建;当前机器实际 Python 3.13。生题依赖包:**pdf2image、pillow、numpy** |
| **TeX 发行版** | xelatex + TikZ 宏包 | README 写 TinyTeX,当前机器实际是 **MiKTeX 25.12**;编译脚本自动探测常见安装位置,免配 PATH |
| manim-renderer 模块 | 项目内 Maven 模块 | seeview 的 pom 依赖它,构建前需 `mvnw install` 一次(只做生题也绕不开) |

TeX 侧两个易踩的点:

- MiKTeX 的宏包安装要设成"**总是安装**",否则首次编译 TikZ 会卡在后台装包询问上(编译脚本 120s 超时即中止报错);
- `pdftoppm`(pdf2image 依赖的 poppler 工具)本机用 MiKTeX 自带的,**需保证它在 PATH 上**。

ffmpeg 仅讲题视频出片需要,生题可缺省。

---

## 3. 必配参数(yaml)

| 配置 | 说明 |
|---|---|
| `langchain4j.open-ai.chat-model` | 生题主模型 api-key / model-name / base-url(OpenAI 兼容网关) |
| `question.tikz-python` / `question.tikz-script` / `question.image-dir` | TikZ 编译 python、脚本、产物目录;默认基于 `${user.dir}` 解析 |
| `figure.library-dir` | 图库模板目录(默认 `figure_library/`,一模板一 JSON) |
| `question.vision.*`(可选) | 视觉模型(材料图片转述),`model-name` 留空即禁用 |

⚠️ **运行时工作目录必须是项目根**(IDEA 里把 `SeeviewApplication` 运行配置的 Working directory 设为项目根),否则 `${user.dir}` 相对路径全部失效。

---

## 4. 启动与访问

```
运行 SeeviewApplication → 浏览器打开 http://localhost:8899/ai-question.html
```

---

## 5. 环境排障速查

| 症状 | 排查方向 |
|---|---|
| 生题请求全部超时 | 本机 Clash 系统代理(127.0.0.1:7890)经常挂,Python/HTTP 请求会走死代理;先关代理或修 Clash 再试 |
| TikZ 编译超时(>120s) | 多半是 MiKTeX 后台装包/重建字体缓存被隐藏窗口卡住;命令行手动跑一次 xelatex 触发安装,或改 MiKTeX 装包策略为"总是安装" |
| 配图渲染失败、模板加载失败 | 检查工作目录是否为项目根(`figure_library`、`tools/题目png生成工具` 等相对路径找不到) |
| docx 内嵌图片不显示 | 检查格式是否在白名单(png/jpg/gif/bmp/webp/svg;emf/wmf 会落为占位说明) |

---

## 6. 图库模板约定(写模板须知)

- 一模板一 JSON(`figure_library/figures/*.json`),id 即文件名;
- 模板体不写 `\def`(参数声明区由后端按参数值自动生成注入),坐标全部由 `\pgfmathsetmacro` 从参数算出,保证数量关系与题干一致;
- **视觉归一化**:模板自行把最长边缩放到 6 个坐标单位(默认 1 单位 = 1cm,即最长边恒约 6cm);整体物理大小不要依赖外部缩放;
- **装饰尺寸必须做 figscale 补偿**:直角记号、角弧等小装饰的尺寸要写成 `min(0.3/\figscale, 边长*0.2, ...)`——否则装饰定义在原始参数坐标系里,会被归一化二次缩放,题目数字越大符号越小(2026-09 修复过 general-triangle / right-triangle 全套);
- 高线垂足字母是参数(`heightafoot/heightbfoot/heightcfoot`,默认 H/P/Q),AI 按题干字母填参保证图文一致;
- string 参数必须配 `options` 白名单(单字母 A~Z 这类),防止 TeX 注入。
