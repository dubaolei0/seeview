"""
文本渲染公用：混合中英文 + LaTeX 的 Mobject 构造。

沿用老渲染器的 minipage 策略，因为它是目前对长文本 + 公式混排最稳的方案。
"""

from __future__ import annotations

import re
from typing import Optional

from manim import Tex, MathTex, Text, VGroup


def _pango_font(font):
    """把 font（可能是 xelatex 家族键，如 'kai'/'wenkai'）解析成 manim Text(Pango)
    能用的真实字体名；否则原样返回。家族键直接给 Text 会让 Pango 找不到、静默回退。"""
    try:
        from ..font_config import pango_name
        return pango_name(font)
    except Exception:
        return font


def _cjk_family_for(font):
    """把 font 关键字/字体名映射到 tex_template 里定义的 CJK 家族名；无匹配返回 None。

    先判 wenkai/mashan，再判 kai（"wenkai" 也含 "kai"），最后宋体类。
    """
    if not font:
        return None
    f = font.lower()
    if "wenkai" in f or "文楷" in font:
        return "wenkai"
    if "mashan" in f or "马善政" in font or "善政" in font:
        return "mashan"
    if "kai" in f or "楷" in font:
        return "kai"
    if "song" in f or "宋" in font or "simsun" in f or "serif" in f or "noto" in f:
        return "song"
    return None


def create_mixed_tex(
    content: str,
    font_size: int = 32,
    color="BLACK",
    tex_template=None,
    max_width_cm: Optional[float] = None,
    font: Optional[str] = None,
):
    """
    创建一个可能包含中英文 + LaTeX 公式的 Mobject。

    策略优先级：
    1. 如果有 max_width_cm，用 minipage 让 LaTeX 自动换行（最稳）
    2. 否则分割 $...$ 公式和普通文本，分别用 MathTex 和 Text，arrange 横排

    content 示例：
        "在 $\\triangle ABC$ 中，$|\\vec{AB}| = 6$"
    """
    # 预处理：
    # - yaml 块字符串里的真实换行符 \n → LaTeX \par（段落分隔）
    # - 文本里的字面 \n（反斜杠加字母 n，非转义）→ \par
    processed = content.replace("\n\n", " \\par ").replace("\n", " \\par ")
    processed = re.sub(r'\\n(?![a-zA-Z])', r' \\par ', processed)

    # Minipage 路径
    if max_width_cm and max_width_cm > 0:
        try:
            # 按角色把中文包进对应 CJK 家族（不影响数学公式）。注意先判 wenkai 再判 kai，
            # 因为 "wenkai" 也含 "kai"。家族名见 tex_template：wenkai/mashan/kai/song。
            fam = _cjk_family_for(font)
            content_latex = (
                r"{\CJKfamily{" + fam + "}" + processed + "}"
                if fam else processed
            )
            wrapped = (
                r"\begin{minipage}{" + f"{max_width_cm:.1f}cm" + r"}"
                + content_latex
                + r"\end{minipage}"
            )
            tex = Tex(
                wrapped,
                tex_template=tex_template,
                color=color,
                font_size=font_size,
            )
            return tex
        except Exception as e:
            print(f"[create_mixed_tex] minipage 失败，回退: {e}")

    # Fallback：切开混排
    parts = re.split(r'(\$[^$]+\$)', content)
    elements = VGroup()
    for part in parts:
        if not part.strip():
            continue
        if part.startswith("$") and part.endswith("$"):
            formula = part[1:-1]
            try:
                mob = MathTex(
                    formula, tex_template=tex_template,
                    color=color, font_size=font_size,
                )
            except Exception:
                fallback_kwargs = dict(color=color, font_size=font_size - 4)
                if font:
                    fallback_kwargs["font"] = _pango_font(font)
                mob = Text(part, **fallback_kwargs)
            elements.add(mob)
        else:
            text_kwargs = dict(color=color, font_size=font_size - 4)
            if font:
                text_kwargs["font"] = _pango_font(font)
            mob = Text(part, **text_kwargs)
            elements.add(mob)
    if len(elements) > 0:
        elements.arrange_submobjects(buff=0.1)
    return elements


_SCREEN_PER_CM_CACHE: dict = {}
# 一长串常用汉字，必然填满测试用 minipage（用于实测 cm→屏幕单位换算）
_SPC_PROBE = "一二三四五六七八九十甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥天地玄黄宇宙洪荒日月盈昃辰宿列张寒来暑往秋收冬藏"


def measure_screen_per_cm(font_size, color, tex_template, fallback: float = 0.763) -> float:
    """实测在给定字号下 minipage 一行填满时的"屏幕单位/cm"换算系数（按字号缓存）。

    旧做法是硬编码常量（只对字号 26 准，封面 36 还得手动按比例缩放，易碎）。这里直接量：
    用一长串汉字填满一个已知 cm 宽的 minipage，渲染宽 / cm 即换算系数。失败回退 fallback。
    """
    key = round(float(font_size), 2)
    if key in _SCREEN_PER_CM_CACHE:
        return _SCREEN_PER_CM_CACHE[key]
    spc = fallback
    try:
        cm = 10.0
        m = create_mixed_tex(_SPC_PROBE, font_size=font_size, color=color,
                             tex_template=tex_template, max_width_cm=cm)
        if m is not None and m.width > 0.1:
            spc = m.width / cm
    except Exception as e:
        print(f"[measure_screen_per_cm] 实测失败，用回退 {fallback}：{e}")
    _SCREEN_PER_CM_CACHE[key] = spc
    return spc


def statement_has_choices(text: Optional[str]) -> bool:
    """题干是否含 \\choices（multiple-choice 自动分列）。"""
    t = text or ""
    return ("\\choices" in t) or ("\\begin{mcq}" in t)


def resolve_choices_minipage_cm(
    text, target_screen_w, *, font_size, color, tex_template, screen_per_cm, font=None,
):
    """含 \\choices 的题干：按"题干前缀"实际宽度反推 minipage 的 cm（即选项分列用的 \\linewidth）。

    - 题干前缀（\\choices 之前那段）在 target 宽下若已铺满 → 选项按 target 整宽分列；
    - 前缀没铺满（短、就一行）→ 选项按前缀那行的实际宽度分列，块对齐在题干下方不强行拉满。
    multiple-choice 的分列阈值是"最宽选项 / \\linewidth"，而 \\linewidth = minipage 宽，
    所以这里只需把"有效屏宽"换算成 minipage 的 cm（cm = 屏宽 / screen_per_cm）。

    返回 minipage_cm（float）。调用方应已确认 statement_has_choices(text) 为真。
    """
    cut = text.find("\\choices")
    stem = text[:cut].strip() if cut >= 0 else text
    stem_mob = create_mixed_tex(
        stem, font_size=font_size, color=color,
        tex_template=tex_template, max_width_cm=target_screen_w / screen_per_cm,
        font=font,
    )
    fills = stem_mob.width >= target_screen_w * 0.95
    effective_w = target_screen_w if fills else stem_mob.width
    return effective_w / screen_per_cm


def screen_width_to_minipage_cm(
    target_screen_w: float,
    *,
    font_size: int,
    color,
    tex_template,
) -> float:
    """把 Manim 屏幕宽度换算成 TeX minipage 的厘米宽度。"""
    target_screen_w = max(float(target_screen_w), 0.1)
    screen_per_cm = measure_screen_per_cm(font_size, color, tex_template)
    return target_screen_w / screen_per_cm


def create_mixed_tex_for_screen_width(
    content: str,
    target_screen_w: float,
    *,
    font_size: int,
    color,
    tex_template,
    font: Optional[str] = None,
):
    """按 Manim 屏幕宽度构建普通混排 Tex。"""
    return create_mixed_tex(
        content,
        font_size=font_size,
        color=color,
        tex_template=tex_template,
        max_width_cm=screen_width_to_minipage_cm(
            target_screen_w,
            font_size=font_size,
            color=color,
            tex_template=tex_template,
        ),
        font=font,
    )


def create_statement_tex_for_screen_width(
    content: str,
    target_screen_w: float,
    *,
    font_size: int,
    color,
    tex_template,
    font: Optional[str] = None,
):
    """按 Manim 屏幕宽度构建题干 Tex。

    create_mixed_tex 的 max_width_cm 是 LaTeX cm，不是 Manim 屏幕单位。
    题干横幅统一先把目标屏幕宽换算为 minipage cm，再交给 LaTeX 自动换行；
    含 choices 的题干保留按题干前缀宽度决定选项分列的逻辑。
    """
    target_screen_w = max(float(target_screen_w), 0.1)
    screen_per_cm = measure_screen_per_cm(font_size, color, tex_template)
    if statement_has_choices(content):
        mp_cm = resolve_choices_minipage_cm(
            content,
            target_screen_w,
            font_size=font_size,
            color=color,
            tex_template=tex_template,
            screen_per_cm=screen_per_cm,
            font=font,
        )
    else:
        mp_cm = screen_width_to_minipage_cm(
            target_screen_w,
            font_size=font_size,
            color=color,
            tex_template=tex_template,
        )

    return create_mixed_tex(
        content,
        font_size=font_size,
        color=color,
        tex_template=tex_template,
        max_width_cm=mp_cm,
        font=font,
    )
