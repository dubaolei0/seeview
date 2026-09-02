# LaTeX 例题导出工具

将数学例题排版为透明背景 PNG，直接 Ctrl+V 粘贴到 PPT。

---

## 快速开始

### 方式一：直接使用 exe（推荐）

1. 安装 [MiKTeX](https://miktex.org/download)，安装时选择 **Install missing packages on-the-fly: Yes**
2. 双击 `dist/LaTeX例题导出.exe`
3. 在输入框里写题干，点 **▶ 渲染**，再点 **复制图片**，Ctrl+V 粘贴到 PPT

> 第一次渲染会自动联网下载所需宏包，可能需要 1-2 分钟，之后正常。

### 方式二：Python 脚本

安装依赖：

```bash
pip install -r requirements.txt
```

还需要安装 [MiKTeX](https://miktex.org/download)。

---

## 输入格式

```
（来源，如：2025年北京卷第3题）题干内容，公式用 $...$ 包裹。

多段落之间空一行。

选择题选项：
\choices{选项A}{选项B}{选项C}{选项D}
```

- 开头的全角括号 `（...）` 会自动用**楷体**渲染
- 向量：`$\vec{a}$`
- 粗体：`$\boldsymbol{a}$`
- 选项自动判断排一行、两行或四行（按最长选项宽度决定）

---

## 界面说明

| 控件 | 说明 |
|------|------|
| 字号滑块 | 8–18 pt，默认 12 pt |
| 宽度滑块 | 10–35 cm，默认 18 cm |
| ▶ 渲染 | 编译 LaTeX，Ctrl+Enter |
| 复制图片 | 写入剪贴板，Ctrl+C |
| 复制 Prompt | 复制给 AI 的指令，发给 AI 附上题目截图或文字，AI 会输出符合本工具格式的内容 |

---

## 命令行用法

```bash
python latex_snippet_tool.py "题干内容" --width 18 --font 12 --out output.png
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `content` | 题干（LaTeX） | 必填 |
| `--width` | 排版宽度 cm | 18 |
| `--font` | 字号 pt | 12 |
| `--dpi` | 分辨率 | 300 |
| `--out` | 输出路径 | output.png |

## 作为模块调用

```python
from latex_snippet_tool import compile_and_render

img = compile_and_render(
    content="（2025年北京卷）已知 $\\vec{a}=(1,2)$，求模长。",
    width_cm=18,
    font_pt=12,
    dpi=300        # 可选，默认 300
)
img.save("output.png")
```

---

## 依赖

- [MiKTeX](https://miktex.org)（提供 xelatex 和 pdftoppm，**必须安装**）
- Python 依赖见 `requirements.txt`（仅脚本模式需要，exe 已内置）
