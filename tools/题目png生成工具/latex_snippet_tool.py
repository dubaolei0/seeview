"""
LaTeX 例题快速导出工具
输入题干 → 编译 → 裁剪透明PNG → 复制到剪贴板
"""

import os
import re
import subprocess
import tempfile
import threading
import io
import hashlib
from pathlib import Path

# ── 在 import pdf2image 之前 patch Popen，确保子进程不弹黑框 ──
_orig_popen = subprocess.Popen

def _silent_popen(*args, **kwargs):
    kwargs.setdefault("creationflags", 0)
    kwargs["creationflags"] |= subprocess.CREATE_NO_WINDOW
    return _orig_popen(*args, **kwargs)

subprocess.Popen = _silent_popen

from pdf2image import convert_from_path
from PIL import Image

# ── customtkinter：延迟到 GUI 启动时才初始化，避免 MCP 等无头环境 import 时卡死 ──
ctk = None  # 在 App.__init__ 里按需 import + 初始化


def _init_ctk():
    """首次调用时导入并初始化 customtkinter（GUI 模式专用）。
    同时把模块级 App（占位基类 object）rebase 为 ctk.CTk 子类。"""
    global ctk
    if ctk is None:
        import customtkinter as _ctk
        _ctk.set_appearance_mode("dark")
        _ctk.set_default_color_theme("blue")
        ctk = _ctk
        # App 在模块级用 object 作占位基类（避免 import ctk），这里重绑到 ctk.CTk
        if "App" in globals():
            App.__bases__ = (ctk.CTk,)
    return ctk

# ── 默认参数 ──────────────────────────────────────────────────
DEFAULT_FONT_PT  = 12
DEFAULT_WIDTH_CM = 18
MARGIN_LEFT  = 1.89  # cm，20cm 宽度时基准；按微课PPT横线左留白(整图7.9%)校准
MARGIN_RIGHT = 2.12  # cm，20cm 宽度时基准；按微课PPT横线右留白(整图8.8%)校准

# ── AI Prompt ─────────────────────────────────────────────────
AI_PROMPT = """\
请将题目转换为以下格式，直接输出可粘贴的纯文本，不要加任何解释或代码块标记。

格式规则：
1. 如果有题目来源（如教材、卷子、年份等），写在第一行，用中文括号括起，例如：（2025年北京卷第3题）
2. 题干直接写在来源后，数学公式用 $...$ 包裹（行内公式），换行用空行分隔段落
3. 如果是选择题，选项单独一行，格式为：\\choices{选项A内容}{选项B内容}{选项C内容}{选项D内容}
4. 不要写"例"字，不要写 A. B. C. D. 标签（\\choices 会自动加）
5. 向量用 $\\vec{a}$ 表示，粗体字母用 $\\boldsymbol{a}$ 表示

示例输出（填空题）：
（2024年全国甲卷第12题）
已知向量 $\\vec{a} = (1, 2)$，$\\vec{b} = (3, 4)$，则 $\\vec{a} \\cdot \\vec{b} =$ ______．

示例输出（选择题）：
（2025年北京卷第3题）
下列向量中，与 $\\vec{a}$ 共线的是

\\choices{$2\\vec{a}$}{$\\vec{a} + \\vec{b}$}{$3\\vec{a}$}{$\\vec{b}$}
"""

# ── LaTeX 导言区 ───────────────────────────────────────────────
PREAMBLE = r"""
\documentclass[12pt]{article}
\usepackage{anyfontsize}
\usepackage[left=MARGIN_LEFT, right=MARGIN_RIGHT, top=0pt, bottom=0pt, paperwidth=PAPER_WIDTH, paperheight=60cm]{geometry}
\setlength{\parindent}{0pt}
\usepackage{amsmath}
\usepackage{circledsteps}
\usepackage{fontspec}
\usepackage{xeCJK}
\setCJKmainfont{SimSun}
\setCJKsansfont{SimHei}
\newCJKfontfamily\KaiTi{KaiTi}
\setmainfont{Times New Roman}
\usepackage{unicode-math}
\setmathfont{XITS Math}
\AtBeginDocument{\let\boldsymbol\pmb}
\usepackage[rgb]{xcolor}
\usepackage{tcolorbox}
\tcbuselibrary{skins, breakable}
\usepackage{fontawesome5}
\usepackage{graphicx}
\usepackage{tikz}
\everymath{\displaystyle}
\definecolor{mainblue}{RGB}{0, 112, 192}
\definecolor{bgblue}{RGB}{229, 242, 250}
\definecolor{bgyellow}{RGB}{253, 245, 230}
\newcommand{\thinkicon}{
    \tikz[baseline=(char.base)]\node[circle, fill=mainblue, text=white, inner sep=1.5pt] (char) {\small\faHourglassHalf};
}
\newcommand{\summaryicon}{
    \tikz[baseline=(char.base)]\node[circle, fill=mainblue, text=white, inner sep=2pt] (char) {\small\faBook};
}
\newtcolorbox{bluebox}{
    enhanced, breakable,
    colback=bgblue, colframe=bgblue,
    arc=0pt, outer arc=0pt, boxrule=0pt,
    top=4mm, bottom=4mm, left=4mm, right=4mm,
    before skip=1em, after skip=1em,
    before upper={\setlength{\parindent}{2em}}
}
\newtcolorbox{yellowbox}{
    enhanced, breakable,
    colback=bgyellow, colframe=bgyellow,
    arc=0pt, outer arc=0pt, boxrule=0pt,
    top=4mm, bottom=4mm, left=4mm, right=4mm,
    before skip=1em, after skip=1em,
    before upper={\setlength{\parindent}{2em}}
}
\linespread{1.2}
\setlength{\parskip}{0pt}
\setlength{\abovedisplayskip}{1.5em}
\setlength{\belowdisplayskip}{1.5em}
\setlength{\abovedisplayshortskip}{1.2em}
\setlength{\belowdisplayshortskip}{1.2em}
\setlength{\jot}{1em}
\renewcommand{\arraystretch}{1.4}
\pagestyle{empty}

% ── 选择题选项宏 ──────────────────────────────────────────────
\newlength{\choicelenA}
\newlength{\choicelenB}
\newlength{\choicelenC}
\newlength{\choicelenD}
\newlength{\choicemax}
\newcommand{\choicelabel}[1]{#1.\ }
\newcommand{\choices}[4]{%
  \par\vspace{0.3em}%
  \settowidth{\choicelenA}{\choicelabel{A}#1}%
  \settowidth{\choicelenB}{\choicelabel{B}#2}%
  \settowidth{\choicelenC}{\choicelabel{C}#3}%
  \settowidth{\choicelenD}{\choicelabel{D}#4}%
  \choicemax=\choicelenA%
  \ifdim\choicelenB>\choicemax \choicemax=\choicelenB \fi%
  \ifdim\choicelenC>\choicemax \choicemax=\choicelenC \fi%
  \ifdim\choicelenD>\choicemax \choicemax=\choicelenD \fi%
  \ifdim\choicemax<0.23\textwidth
    \makebox[0.25\textwidth][l]{\choicelabel{A}#1}%
    \makebox[0.25\textwidth][l]{\choicelabel{B}#2}%
    \makebox[0.25\textwidth][l]{\choicelabel{C}#3}%
    \makebox[0.25\textwidth][l]{\choicelabel{D}#4}%
  \else\ifdim\choicemax<0.48\textwidth
    \makebox[0.5\textwidth][l]{\choicelabel{A}#1}%
    \makebox[0.5\textwidth][l]{\choicelabel{B}#2}\\%
    \makebox[0.5\textwidth][l]{\choicelabel{C}#3}%
    \makebox[0.5\textwidth][l]{\choicelabel{D}#4}%
  \else
    \par\choicelabel{A}#1%
    \par\choicelabel{B}#2%
    \par\choicelabel{C}#3%
    \par\choicelabel{D}#4%
  \fi\fi%
  \vspace{0.3em}%
}
"""

BODY_TEMPLATE = r"""
\begin{document}
\fontsize{FONT_SIZEpt}{FONT_LEADINGpt}\selectfont
\setlength{\abovedisplayskip}{1.5em}
\setlength{\belowdisplayskip}{1.5em}
\setlength{\abovedisplayshortskip}{1.2em}
\setlength{\belowdisplayshortskip}{1.2em}
\setlength{\jot}{1em}
\renewcommand{\arraystretch}{1.4}

CONTENT

\end{document}
"""

# ── 示例文字 ───────────────────────────────────────────────────
SAMPLE = """\
（来源，如：2025年北京卷第3题）这里是题干，支持 LaTeX 公式，例如 $\\vec{a} + \\vec{b}$。

段落之间空一行分隔，多问题时：

(1) 第一问

(2) 第二问

选择题在题干后加选项：

\\choices{选项A}{选项B}{选项C}{选项D}\
"""


# ── TikZ 预清洗：修正 AI 常见的字号写法错误 ────────────────────
_TIKZ_FONT_NAMES = (
    "small", "normalsize", "footnotesize", "large", "Large", "LARGE",
    "huge", "Huge", "tiny", "scriptsize",
)
_TIKZ_EVERY_NODE_STYLE_FONT = re.compile(
    r"(every node\s*/\s*\.style\s*=\s*\{)([^}]*)(\})"
)
_TIKZ_NODE_LABEL_LEADING_FONT_WORD = re.compile(
    r"(node(?:\[[^\]]*\])?(?:\s+at\s+\([^()]*\))?\s*\{)(\$?)(\\?)(small|normalsize|footnotesize|large|Large|LARGE|huge|Huge|tiny|scriptsize)(?:\s+|(?=[A-Z\\$]))([^{}$]*)(\$?)(\})"
)
_TIKZ_DRAW_OPTIONS = re.compile(r"\\draw\[([^\n;]*)\](\s*[^;]*;)")


def _shorten_stealth_arrows(content: str) -> str:
    """避免 Stealth 箭头画到端点圆心后又被实心点覆盖。"""
    def fix(m):
        opts, rest = m.group(1), m.group(2)
        if "Stealth" not in opts:
            return m.group(0)
        additions = []
        if "shorten >=" not in opts:
            additions.append("shorten >=2pt")
        if "shorten <=" not in opts:
            additions.append("shorten <=2pt")
        if not additions:
            return m.group(0)
        return "\\draw[" + opts + ", " + ", ".join(additions) + "]" + rest

    return _TIKZ_DRAW_OPTIONS.sub(fix, content)


def _sanitize_tikz_content(content: str) -> str:
    """修正 TikZ 中会把字号词渲染成可见文本的常见错误。"""
    if not content or ("tikz" not in content and "node" not in content):
        return content

    content = _TIKZ_NODE_LABEL_LEADING_FONT_WORD.sub(
        lambda m: m.group(1) + m.group(2) + m.group(5) + m.group(6) + m.group(7),
        content,
    )
    content = _shorten_stealth_arrows(content)

    def fix_every_node_style(m):
        prefix, body, suffix = m.group(1), m.group(2), m.group(3)
        for name in _TIKZ_FONT_NAMES:
            body = re.sub(
                rf"(^|,)\s*\\{name}\b",
                rf"\1font=\\{name}",
                body,
            )
        for name in _TIKZ_FONT_NAMES:
            body = re.sub(
                rf"(^|,|\s)font\s*=\s*{name}(?=\s*(?:,|$))",
                lambda mm, n=name: mm.group(1) + "font=\\" + n,
                body,
            )
        return prefix + body + suffix

    return _TIKZ_EVERY_NODE_STYLE_FONT.sub(fix_every_node_style, content)


# ── 预处理：将第一个全角括号内容渲染为楷体 ────────────────────
def preprocess_content(content: str) -> str:
    """
    若输入开头以全角括号 （...） 开始，将该括号（含括号符号）包裹为楷体。
    例：（2025年北京卷）题干  ->  {\\KaiTi （2025年北京卷）}题干
    允许一层嵌套括号，正确处理 （2022年全国甲卷（理）第5题）这种来源——
    匹配到真正配对的最后一个 ），而非内层 （理） 的那个。
    """
    content = _sanitize_tikz_content(content)
    # 填空横线：连续 3 个及以上下划线(无论 ______ 还是 \_\_\_\_)统一渲成一条横线规则。
    # 文本模式下裸 _ 是下标符会被 LaTeX 吃掉、导致横线消失；单/双下划线(如 x_0)不动。
    content = re.sub(r'(?:\\_|_){3,}', r'\\rule[-0.5ex]{2.5em}{0.4pt}', content)
    # 选择题末尾空括号统一为「全角括号 + 两个全角空格」，避免半角空格被 LaTeX 压扁成 ()。
    # 只匹配括号内全是空白的情形，不动 （理）/（1）/（2025…） 这类有内容的括号。
    content = re.sub(r'[（(][ \t　]*[）)]', '（　　）', content)

    pattern = r'^(\s*)(（(?:[^（）]|（[^（）]*）)*）)'
    m = re.match(pattern, content)
    if m:
        prefix = m.group(1)
        source = m.group(2)
        rest = content[m.end():]
        return prefix + '{\\KaiTi ' + source + '}' + rest
    return content


# ── 编译 ───────────────────────────────────────────────────────

def build_latex(content: str, width_cm: int, font_pt: int) -> str:
    num = float(width_cm)
    ml = num * (MARGIN_LEFT  / 20.0)
    mr = num * (MARGIN_RIGHT / 20.0)
    paper_w = f"{num + ml + mr:.4f}cm"
    processed = preprocess_content(content)
    preamble = (PREAMBLE
                .replace("PAPER_WIDTH",  paper_w)
                .replace("MARGIN_LEFT",  f"{ml:.4f}cm")
                .replace("MARGIN_RIGHT", f"{mr:.4f}cm"))
    body = (BODY_TEMPLATE
            .replace("FONT_LEADING", f"{float(font_pt) * 1.3:.1f}")
            .replace("FONT_SIZE",    str(font_pt))
            .replace("CONTENT",      processed))
    return preamble + body


def _assemble_latex_multi(contents, width_cm: int, font_pt: int) -> str:
    """一份 preamble + 每段内容各占一页（\\clearpage 分隔）。contents 为列表。"""
    num = float(width_cm)
    ml = num * (MARGIN_LEFT / 20.0)
    mr = num * (MARGIN_RIGHT / 20.0)
    paper_w = f"{num + ml + mr:.4f}cm"
    preamble = (PREAMBLE
                .replace("PAPER_WIDTH",  paper_w)
                .replace("MARGIN_LEFT",  f"{ml:.4f}cm")
                .replace("MARGIN_RIGHT", f"{mr:.4f}cm"))
    head, tail = BODY_TEMPLATE.split("CONTENT")
    head = head.replace("FONT_LEADING", f"{float(font_pt) * 1.3:.1f}").replace("FONT_SIZE", str(font_pt))
    pages = "\n\\clearpage\n".join(preprocess_content(c) for c in contents)
    return preamble + head + pages + tail


# ── xelatex 调用：带超时，防止 MiKTeX 后台装包/字体缓存导致无限挂起 ──
_XELATEX_TIMEOUT = 120  # 秒。超时即判定卡死并中止报错，而非永久等待。


def _run_xelatex(latex_src: str, dpi: int):
    """编译一份（可能多页）文档，返回 RGBA 页面图片列表。带超时保护。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / "snippet.tex"
        pdf_path = Path(tmpdir) / "snippet.pdf"
        tex_path.write_text(latex_src, encoding="utf-8")
        try:
            result = subprocess.run(
                ["xelatex", "-interaction=nonstopmode", "-output-directory", tmpdir, str(tex_path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW, timeout=_XELATEX_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"XeLaTeX 编译超时（>{_XELATEX_TIMEOUT}s）已中止——多半是 MiKTeX 在后台"
                "装包/重建字体缓存被隐藏窗口卡住。请在命令行手动跑一次 xelatex 触发安装，"
                "或在 MiKTeX 设置里把宏包安装改为“总是安装/从不安装”（关掉“先询问”）。"
            )
        if not pdf_path.exists():
            raise RuntimeError("XeLaTeX 编译失败：\n" + result.stdout[-3000:])
        try:
            pages = convert_from_path(str(pdf_path), dpi=dpi, timeout=60)
        except Exception as e:
            raise RuntimeError(f"PDF 转图片失败：{e}")
        return [p.convert("RGBA") for p in pages]


# ── 渲染缓存：按 (内容+宽+字号+dpi) 哈希存 PNG，相同题目不重渲 ──
_CACHE_DIR = os.path.join(tempfile.gettempdir(), "math_render_cache")


def _cache_key(content: str, width_cm, font_pt, dpi) -> str:
    h = hashlib.sha256(f"{width_cm}|{font_pt}|{dpi}|{content}".encode("utf-8")).hexdigest()
    return os.path.join(_CACHE_DIR, h + ".png")


def _cache_load(key: str):
    if os.path.exists(key):
        try:
            return Image.open(key).convert("RGBA").copy()
        except Exception:
            return None
    return None


def _cache_save(key: str, img: "Image.Image"):
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        img.save(key)
    except Exception:
        pass  # 缓存写失败不影响主流程


def compile_and_render_many(contents, width_cm: int, font_pt: int, dpi: int = 300):
    """把多段内容合成**一份多页文档、一次 xelatex 编译**，返回裁剪后的图片列表（顺序对应）。
    重 preamble（中文字体/unicode-math/tikz）只加载一次，N 段从 N×单编译 降到≈1 次编译耗时；
    命中缓存的内容直接复用、完全不进编译。"""
    contents = list(contents)
    if not contents:
        return []
    results = [None] * len(contents)
    miss_idx, miss_contents = [], []
    for i, c in enumerate(contents):
        img = _cache_load(_cache_key(c, width_cm, font_pt, dpi))
        if img is not None:
            results[i] = img
        else:
            miss_idx.append(i); miss_contents.append(c)
    if miss_contents:
        pages = _run_xelatex(_assemble_latex_multi(miss_contents, width_cm, font_pt), dpi)
        if len(pages) >= len(miss_contents):
            # \clearpage 保证每题从新页开始，前 N 页即 N 道题各自的第一页；
            # 溢出页（某题内容过长）直接丢弃——PPT 上本来就只显示一屏
            rendered = [crop_to_content(p) for p in pages[:len(miss_contents)]]
        else:
            # 页数不足（xelatex 内部合并了某些页）→ 退回逐段编译
            rendered = [compile_and_render(c, width_cm, font_pt, dpi) for c in miss_contents]
        for j, i in enumerate(miss_idx):
            results[i] = rendered[j]
            _cache_save(_cache_key(contents[i], width_cm, font_pt, dpi), rendered[j])
    return results


def compile_and_render(content: str, width_cm: int, font_pt: int, dpi: int = 300, crop_x: bool = False) -> Image.Image:
    key = _cache_key(("CX" if crop_x else "") + content, width_cm, font_pt, dpi)
    img = _cache_load(key)
    if img is not None:
        return img
    pages = _run_xelatex(_assemble_latex_multi([content], width_cm, font_pt), dpi)
    img = crop_to_content(pages[0], h_crop=crop_x)
    _cache_save(key, img)
    return img


def crop_to_content(img: Image.Image, v_padding: int = 6, h_crop: bool = False, h_padding: int = 6) -> Image.Image:
    import numpy as np
    arr = np.array(img.convert("RGBA"))
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    non_white = ~((r > 245) & (g > 245) & (b > 245))
    rows = np.any(non_white, axis=1)
    if not rows.any():
        return img
    min_y = max(0, int(np.argmax(rows)) - v_padding)
    max_y = min(arr.shape[0], int(len(rows) - 1 - np.argmax(rows[::-1])) + v_padding + 1)
    # 水平裁剪（TikZ 配图用）：只保留有内容的列区间，去掉页面两侧空白，PNG 紧贴图形
    if h_crop:
        cols = np.any(non_white, axis=0)
        if cols.any():
            min_x = max(0, int(np.argmax(cols)) - h_padding)
            max_x = min(arr.shape[1], int(len(cols) - 1 - np.argmax(cols[::-1])) + h_padding + 1)
        else:
            min_x, max_x = 0, arr.shape[1]
    else:
        min_x, max_x = 0, arr.shape[1]
    cropped = arr[min_y:max_y, min_x:max_x].copy()
    white_mask = (cropped[:, :, 0] > 245) & (cropped[:, :, 1] > 245) & (cropped[:, :, 2] > 245)
    cropped[white_mask, 3] = 0
    return Image.fromarray(cropped, "RGBA")


# ── 剪贴板 ─────────────────────────────────────────────────────

def image_to_clipboard(img: Image.Image):
    import win32clipboard, win32con
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_data = buf.getvalue()
    dib_data = _rgba_to_dib24(img)
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.RegisterClipboardFormat("PNG"), png_data)
        win32clipboard.SetClipboardData(win32con.CF_DIB, dib_data)
    finally:
        win32clipboard.CloseClipboard()


def text_to_clipboard(text: str):
    import win32clipboard
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def _rgba_to_dib24(img: Image.Image) -> bytes:
    import struct
    bg = Image.new("RGB", img.size, (255, 255, 255))
    bg.paste(img, mask=img.split()[3])
    w, h = bg.size
    row_bytes = (w * 3 + 3) & ~3
    pad = row_bytes - w * 3
    rows = []
    for y in range(h - 1, -1, -1):
        row = bytearray()
        for x in range(w):
            rv, gv, bv = bg.getpixel((x, y))
            row += bytes([bv, gv, rv])
        row += b"\x00" * pad
        rows.append(bytes(row))
    pixel_data = b"".join(rows)
    header = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(pixel_data), 2835, 2835, 0, 0)
    return header + pixel_data


# ── GUI ────────────────────────────────────────────────────────

class App:  # 占位基类；_init_ctk() 会 rebase 为 ctk.CTk
    def __init__(self):
        _init_ctk()
        super().__init__()
        self.title("LaTeX 例题导出")
        self.geometry("780x580")
        self.minsize(560, 400)
        self._last_image: Image.Image | None = None
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # ── 顶栏 ──
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))

        # 字号滑块
        ctk.CTkLabel(top, text="字号", font=ctk.CTkFont(size=11),
                     text_color="gray60").pack(side="left")
        self._font_var = ctk.IntVar(value=DEFAULT_FONT_PT)
        self._font_label = ctk.CTkLabel(top, text=f"{DEFAULT_FONT_PT} pt",
                                        font=ctk.CTkFont(size=11), width=36)
        self._font_label.pack(side="left", padx=(4, 0))
        ctk.CTkSlider(
            top, from_=8, to=18, number_of_steps=10,
            variable=self._font_var,
            command=lambda v: self._font_label.configure(text=f"{int(v)} pt"),
            width=100, height=16,
        ).pack(side="left", padx=(4, 14))

        # 宽度滑块
        ctk.CTkLabel(top, text="宽度", font=ctk.CTkFont(size=11),
                     text_color="gray60").pack(side="left")
        self._width_var = ctk.IntVar(value=DEFAULT_WIDTH_CM)
        self._width_label = ctk.CTkLabel(top, text=f"{DEFAULT_WIDTH_CM} cm",
                                         font=ctk.CTkFont(size=11), width=40)
        self._width_label.pack(side="left", padx=(4, 0))
        ctk.CTkSlider(
            top, from_=10, to=35, number_of_steps=25,
            variable=self._width_var,
            command=lambda v: self._width_label.configure(text=f"{int(v)} cm"),
            width=130, height=16,
        ).pack(side="left", padx=(4, 14))

        self._btn_render = ctk.CTkButton(
            top, text="▶ 渲染",
            command=self._on_render,
            font=ctk.CTkFont(size=12, weight="bold"),
            width=80, height=30,
        )
        self._btn_render.pack(side="left", padx=(0, 6))

        self._btn_copy = ctk.CTkButton(
            top, text="复制图片",
            command=self._on_copy,
            font=ctk.CTkFont(size=12),
            width=80, height=30,
            fg_color="#107c10", hover_color="#0a5e0a",
            state="disabled",
        )
        self._btn_copy.pack(side="left", padx=(0, 6))

        self._btn_prompt = ctk.CTkButton(
            top, text="复制 Prompt",
            command=self._on_copy_prompt,
            font=ctk.CTkFont(size=12),
            width=100, height=30,
            fg_color="#5a4080", hover_color="#3d2a5e",
        )
        self._btn_prompt.pack(side="left")

        self._status = ctk.CTkLabel(
            top, text="Ctrl+Enter 渲染  ·  Ctrl+C 复制图片",
            font=ctk.CTkFont(size=11), text_color="gray50"
        )
        self._status.pack(side="left", padx=10)

        # ── 输入框 ──
        self._text = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
            height=120,
        )
        self._text.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 6))
        self._text.insert("0.0", SAMPLE)

        # ── 分隔线 ──
        ctk.CTkFrame(self, height=1, fg_color="gray30").grid(
            row=2, column=0, sticky="ew", padx=14, pady=0)

        # ── 预览区 ──
        import tkinter as tk
        canvas_bg = ctk.CTkFrame(self, corner_radius=6)
        canvas_bg.grid(row=3, column=0, sticky="nsew", padx=14, pady=(6, 14))
        canvas_bg.grid_columnconfigure(0, weight=1)
        canvas_bg.grid_rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(canvas_bg, bg="#e8e8e8", highlightthickness=0, bd=0)
        self._canvas.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

        self.bind("<Control-Return>", lambda e: self._on_render())
        self.bind("<Control-c>", lambda e: self._on_copy())

    def _set_status(self, msg: str, color: str = "gray60"):
        self._status.configure(text=msg, text_color=color)
        self.update_idletasks()

    def _on_render(self):
        content = self._text.get("0.0", "end").strip()
        if not content:
            return
        width = int(self._width_var.get())
        font  = int(self._font_var.get())
        self._btn_render.configure(state="disabled")
        self._btn_copy.configure(state="disabled")
        self._set_status("编译中，请稍候…", "#4da6ff")
        threading.Thread(target=self._render_thread, args=(content, width, font), daemon=True).start()

    def _render_thread(self, content: str, width: int, font: int):
        try:
            img = compile_and_render(content, width, font, dpi=300)
            self._last_image = img
            self.after(0, self._show_preview, img)
        except Exception as e:
            self.after(0, self._show_error, str(e))

    def _show_preview(self, img: Image.Image):
        self._btn_render.configure(state="normal")
        self._btn_copy.configure(state="normal")
        self._set_status("✓ 渲染完成", "#4caf50")

        self._canvas.update_idletasks()
        canvas_w = max(self._canvas.winfo_width(), 600)
        scale = min(1.0, canvas_w / img.width)
        disp_w = int(img.width * scale)
        disp_h = int(img.height * scale)

        checker = self._make_checker(disp_w, disp_h)
        preview = checker.copy()
        resized = img.resize((disp_w, disp_h), Image.LANCZOS)
        preview.paste(resized, (0, 0), resized)

        from PIL import ImageTk
        self._tk_img = ImageTk.PhotoImage(preview)
        self._canvas.configure(width=disp_w, height=disp_h)
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor="nw", image=self._tk_img)

    def _make_checker(self, w: int, h: int, size: int = 12) -> Image.Image:
        img = Image.new("RGB", (w, h))
        d = img.load()
        for y in range(h):
            for x in range(w):
                d[x, y] = (200, 200, 200) if (x // size + y // size) % 2 == 0 else (240, 240, 240)
        return img

    def _show_error(self, msg: str):
        self._btn_render.configure(state="normal")
        self._set_status("✗ 编译失败", "#f44336")
        import tkinter.messagebox as mb
        mb.showerror("编译错误", msg)

    def _on_copy(self):
        if self._last_image is None:
            return
        try:
            image_to_clipboard(self._last_image)
            self._set_status("✓ 已复制，Ctrl+V 粘贴到 PPT", "#4caf50")
        except Exception as e:
            import tkinter.messagebox as mb
            mb.showerror("复制失败", str(e))

    def _on_copy_prompt(self):
        try:
            text_to_clipboard(AI_PROMPT)
            self._set_status("✓ Prompt 已复制，粘贴给 AI 并附上题目截图或文字", "#a78bfa")
        except Exception as e:
            import tkinter.messagebox as mb
            mb.showerror("复制失败", str(e))


if __name__ == "__main__":
    import sys

    # ── CLI 模式：有参数时不启动 GUI ──────────────────────────
    if len(sys.argv) > 1:
        import argparse
        parser = argparse.ArgumentParser(description="LaTeX 例题导出 CLI")
        parser.add_argument("content", nargs="?", default=None,
                            help="题干内容（LaTeX）；省略时需提供 --file")
        parser.add_argument("--file", default=None,
                            help="从 UTF-8 文件读取题干内容（供 Java 等外部进程调用，规避命令行长度/编码问题）")
        parser.add_argument("--width", type=int, default=DEFAULT_WIDTH_CM,
                            help=f"排版宽度 cm，默认 {DEFAULT_WIDTH_CM}")
        parser.add_argument("--font",  type=int, default=DEFAULT_FONT_PT,
                            help=f"字号 pt，默认 {DEFAULT_FONT_PT}")
        parser.add_argument("--dpi",   type=int, default=300,
                            help="分辨率，默认 300")
        parser.add_argument("--out",   default="output.png",
                            help="输出文件路径，默认 output.png")
        parser.add_argument("--crop-x", action="store_true",
                            help="水平方向也裁剪到内容（TikZ 配图用，PNG 紧贴图形而非整页纸宽）")
        args = parser.parse_args()

        if args.content is not None:
            content = args.content
        elif args.file:
            content = Path(args.file).read_text(encoding="utf-8")
        else:
            parser.error("请提供题干内容（位置参数）或 --file 文件路径")

        print(f"编译中：宽度={args.width}cm，字号={args.font}pt，dpi={args.dpi}")
        img = compile_and_render(content, args.width, args.font, dpi=args.dpi, crop_x=args.crop_x)
        img.save(args.out, "PNG")
        print(f"已保存：{args.out}  ({img.width}x{img.height}px)")

    # ── GUI 模式 ──────────────────────────────────────────────
    else:
        app = App()
        app.mainloop()
