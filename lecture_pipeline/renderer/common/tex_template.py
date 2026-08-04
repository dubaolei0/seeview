"""
LaTeX 模板工厂。基于老代码 src.latex_config，扩展了 v3 渲染器需要的自定义命令。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 让老代码可被 import（src/ 位置随部署而变，用自适应定位）
from .paths import find_project_root

_PROJECT_ROOT = find_project_root()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def get_chinese_template():
    """
    返回支持中英文混排 + v3 自定义命令 的 xelatex 模板。

    字体：中文用 SimSun 作为 CJK 主字体（装了思源后可改成思源宋体）。
    """
    from manim import TexTemplate

    template = TexTemplate()
    template.add_to_preamble(r"""
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{cancel}
\usepackage{multiple-choice}
\usepackage{xeCJK}
\usepackage{fontspec}

% 中文主字体 + 各角色家族都来自 renderer/font_config.py（改字体只动那个文件）。
% 这里只放固定项；主字体与家族定义在下方按配置自动注入。
% 中文无衬线字体（如需使用 \sffamily 切换）
\setCJKsansfont{SimHei}
% 中文等宽字体
\setCJKmonofont{NSimSun}
% 英文主字体（和中文搭配的西文）
\setmainfont{Times New Roman}

% 带圈/带括号数字（①②③ ⑴⑵ ⒈⒉ 等，Unicode 2460–24FF "Enclosed Alphanumerics"）默认会被
% 当成西文丢给 Times 渲染而缺字（显示成豆腐块）。声明为 CJK 类，改由中文字体渲染（都含这些字形）。
\xeCJKDeclareCharClass{CJK}{"2460 -> "24FF}

% 分式线厚度（适中清晰，不过粗）
\makeatletter
\renewcommand{\frac}[2]{\genfrac{}{}{0.6pt}{}{#1}{#2}}
\renewcommand{\dfrac}[2]{\genfrac{}{}{0.8pt}{0}{#1}{#2}}
\renewcommand{\tfrac}[2]{\genfrac{}{}{0.6pt}{1}{#1}{#2}}
\makeatother

% v3 渲染器扩展：\choices 命令（选择题四选项，自动 1×4 / 2×2 / 4×1 排版）
% 分列逻辑直接用 CTAN 宏包 multiple-choice（按选项宽度对 \linewidth 取阈值：
% >0.5 用 1 列、>0.25 用 2 列、否则 4 列），不自造。
% 该宏包以 choices 环境 + \choice 列项提供，且靠 bidi 的 body 收集器扫描 \end{...} 收尾，
% 所以必须走真正的 \begin..\end。这里把它的 begin/end 另存为环境 mcq，再用一层 4 参
% \choices{}{}{}{} 适配本管线的单行写法（4 参命令与 choices 环境同名，故另起 mcq）。
\makeatletter
\let\mc@beginchoices\choices
\let\mc@endchoices\endchoices
\newenvironment{mcq}{\mc@beginchoices}{\mc@endchoices}
\renewcommand{\choices}[4]{\begin{mcq}\choice #1\choice #2\choice #3\choice #4\end{mcq}}
\makeatother
""")

    # 主字体 + 各 CJK 家族按 font_config 自动注入（family 注册表 + 自带字体路径都在那）。
    from ..font_config import main_font_latex, latex_family_defs, FONTS_DIR
    template.add_to_preamble(main_font_latex())
    template.add_to_preamble(latex_family_defs(FONTS_DIR.as_posix()))

    template.tex_compiler = "xelatex"
    template.output_format = ".xdv"

    return template
