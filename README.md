# seeview 项目 README（新手指南）

> 适用对象：新接手本项目的开发者（含换新机器 / 重新 clone）。
> 目标：clone 下来后，用 IDEA 打开 `seeview` 模块、配置好 JDK 21，即可直接运行 `SeeviewApplication`。所有配置都维护在 `seeview/src/main/resources/application.yaml` 一个文件里。

---

## 0. 项目是什么

seeview 是一个 **AI 生题 / 讲题系统**（Spring Boot 后端），核心能力：

- 生题：调用大模型生成数理化题目 + TikZ 配图（`LangChainController`）
- 讲题：调用本地讲题视频引擎 `lecture_pipeline`（Python/manim）生成讲解视频
- 图库：`figure_library`（参数化 TikZ 模板），供生题时注入给大模型参考

**端口**：`8899`

**技术栈**：Java 21 · Spring Boot 3.5.6 · Maven 多模块 · Python 3.12（子进程） · TinyTeX(xelatex) · manim

---

## 1. 目录结构（关键部分）

```
seeview/
├── pom.xml                  # 根聚合 pom（模块：manim-renderer）
├── mvnw.cmd / mvnw          # Maven Wrapper（推荐用这个，版本固定）
├── README.md                # 本文件
├── manim-renderer/          # 本地模块：manim 渲染（需先 mvn install）
├── figure_library/          # 参数化图库（figures/*.json + _build 工具脚本，位于项目根）
├── seeview/                 # ★ Spring Boot 主模块（IDEA 打开这个）
│   ├── src/main/resources/
│   │   └── application.yaml # ★ 唯一配置入口（路径 / 密钥 / 模型 / 图库全在这，含注释）
│   └── question_output/     # 生题产物（图片等，gitignore）
├── lecture_pipeline/        # 讲题视频引擎（Python），需建 .venv
└── tools/题目png生成工具/
    └── latex_snippet_tool.py  # TikZ→PNG 编译脚本（自动探测 xelatex，无需配置路径）
```

---

## 2. 依赖环境清单

| 依赖 | 版本要求 | 说明 |
|---|---|---|
| **JDK** | **17+（本项目用 21）** | 用 IDEA 时在 `Project Structure → SDK` 选 JDK 21（本机为 `D:\.jdks\ms-21.0.12.1`）。⚠️ 系统 `JAVA_HOME` 是 JDK 8，命令行跑需先 `$env:JAVA_HOME="D:\.jdks\ms-21.0.12.1"` |
| Maven | 3.8+（推荐用项目 `mvnw`） | 用 `mvnw.cmd` 可免装 |
| **Python** | **3.12**（venv） | 位置 `lecture_pipeline\.venv\Scripts\python.exe`。TikZ 编译 / yaml 校验 / manim 渲染全靠它。首次需按 `lecture_pipeline/bootstrap.ps1` 建 venv |
| **TinyTeX** | 含 `xelatex` | 本机 `D:\Program Files\TinyTeX\TinyTeX\bin\windows\xelatex.exe`。**无需配 PATH**——编译脚本自动探测常见安装位置 |
| ffmpeg | 可选 | 仅 manim 出片需要；不做视频可缺省 |

---

## 3. 配置：全部在 `application.yaml`

**唯一配置入口**：`seeview/src/main/resources/application.yaml`（已写好详细注释）。

包括：
- **路径**：python 引擎 / TikZ 编译脚本 / 图库目录 / 产物目录 —— 基于 `${user.dir}`（Java 工作目录 = **项目根**）解析，与远程仓库一致。IDEA 里把运行配置的 Working directory 设为项目根即可（见下）
- **密钥**：LLM（生题主模型）/ VISION（材料图转述）/ DASHSCOPE / DOUBAO（TTS）—— 直接明文写在此文件
- **模型**：生题模型名、base-url、超时、重试等

> ⚠️ **安全提醒**：本文件含真实密钥，提交 git 前请确认仓库私有。换 key 直接改这里。

---

## 4. 启动方式

### 方式 A：IDEA 启动（推荐，日常开发）

1. 用 IDEA 打开项目根（`seeview/`），Maven 自动加载根聚合 pom + `seeview` 模块
2. 确认 Project SDK = JDK 21（`File → Project Structure → Project`）
3. 首次需先 install 本地模块（否则 `seeview` 编译找不到 `manim-renderer`）：在项目根终端跑
   ```
   .\mvnw.cmd install -DskipTests
   ```
4. **设置运行配置工作目录**：`Run → Edit Configurations → SeeviewApplication`，把 **Working directory** 设为项目根（`$PROJECT_DIR$`，即 `E:\...\seeview`）。本机已预置 `.idea/runConfigurations/SeeviewApplication.xml`（Working directory = 项目根）；⚠️ 该文件在 `.idea/` 下不随 git 提交，**新人 clone 后需手动设一次**（否则 `${user.dir}` 会按模块目录解析导致路径错）
5. 运行 `com.yuanxuan.seeview.SeeviewApplication`
6. 访问 `http://localhost:8899`

### 方式 B：纯命令行（不用 IDEA）

```powershell
$env:JAVA_HOME="D:\.jdks\ms-21.0.12.1"
cd seeview
..\mvnw.cmd spring-boot:run
```

---

## 5. 启动类与配置

- **启动类**：`com.yuanxuan.seeview.SeeviewApplication`
  （`seeview/src/main/java/com/yuanxuan/seeview/SeeviewApplication.java`）
- **配置文件**：`seeview/src/main/resources/application.yaml`
  - 端口 `server.port: 8899`
  - 路径 / 密钥 / 模型 / 图库目录全部在此，见各配置项注释
- **本地 Maven 依赖**：`manim-renderer:0.0.1-SNAPSHOT`
  - 不在公共仓库，需先本地 `mvnw.cmd install`（根聚合 pom 会把它装好）

---

## 6. 验证是否跑通

启动后访问：

- 后端/前端页面：`http://localhost:8899/`
- 生题接口：`POST http://localhost:8899/api/langchain/generate`（需 LLM key 有效）
- TikZ 编译：生题时若 `tools/题目png生成工具/latex_snippet_tool.py` 能找到 xelatex，会输出 PNG；否则日志打 `TikZ 编译失败，保留代码块`（WARN，不崩溃）

日志里看到这两行即启动成功（无红字报错）：

```
Started SeeviewApplication in x.x seconds
Tomcat started on port 8899
```

---

## 7. 常见问题（FAQ）

**Q1：启动报 Java 版本错误 / 编译失败 "invalid target release: 21"**
→ `JAVA_HOME` 是 JDK 8。IDEA 里把 SDK 选成 JDK 21；命令行先设 `$env:JAVA_HOME="D:\.jdks\ms-21.0.12.1"`。

**Q2：找不到 `manim-renderer:0.0.1-SNAPSHOT`**
→ 本地模块没 install。项目根跑 `.\mvnw.cmd install -DskipTests`。

**Q3：生题日志 WARN "TikZ 编译失败，保留代码块"**
→ 大多是 xelatex 没找到或 TikZ 代码本身有错。TinyTeX 装好后脚本会自动探测；可单独跑 `python tools/题目png生成工具/latex_snippet_tool.py --file <你的tex> --out test.png` 定位错误。

**Q4：`python` 命令无效（微软商店跳板）**
→ 项目一律用 `lecture_pipeline\.venv\Scripts\python.exe`（application.yaml 里 `manim.python` / `question.tikz-python` 指定），不要依赖系统 `python`。

**Q5：改了 `application.yaml` 不生效？**
→ 重启应用。配置只在启动时读取。

**Q6：`mvn` 构建卡死 / 一直下载不动？**
→ 本机全局 `settings.xml` 曾把 `mirrorOf=*` 指向内网 Nexus（不可达会卡死），已改为统一走阿里云镜像（备份 `settings.xml.bak_20260831`）。新机器若全局配置有内网镜像，删掉即可。

**Q7：编译报 `Could not find artifact com.example.yuanxuan.see:see:jar`**
→ 根 `pom.xml` 是聚合器（只聚合 manim-renderer），不产出 `see` 的 jar；`seeview/pom.xml` 里对该 `see:jar` 的依赖是历史遗留冗余，已移除。若未来真要用根项目的类，需先把它改成独立产 jar 的模块。

---

## 8. 图库相关（本项目的另一条主线）

- **参数化图库（主方案，入库提交）**：`figure_library/`（项目根）
  - `figures/*.json`：参数化 TikZ 模板（椭圆/双曲线/抛物线/正弦/指数/正方体/圆柱/三角形等）
  - `_build/*.py`：模板生成/校验/预览工具（相对项目根推导路径，clone 后直接用）
- **静态图形卡（本地留存，暂不提交 git）**：`seeview/src/main/resources/graphics-lib/` 与 `graphics-lib-verify/`、`seeview/docs/图库方案.md`——已 gitignore，如需要再启用
- 图库工具脚本需要 Python 环境 + xelatex。
