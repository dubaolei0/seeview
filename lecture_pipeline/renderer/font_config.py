"""字体配置 —— 改字体只动这一个文件。

两张表：
  FONT_FAMILIES  家族注册：family 名 -> 字体来源
                 {"name": "系统字体名"}  或  {"file": "自带字体文件名"}（放在 common/fonts/）
  FONT_ROLE      角色分配：渲染里的角色 -> 用哪个 family

要换某个角色的字体：改 FONT_ROLE 对应的一行。
要加一款新字体：把字体文件丢进 common/fonts/，在 FONT_FAMILIES 加一行（模板会自动加载），
                 再在 FONT_ROLE 把某角色指过去即可，不用动渲染代码。

不改代码也能临时覆盖：
  - 在 common/fonts/fonts.local.json 写 {"families": {...}, "roles": {...}}
  - 或设环境变量 LECTURE_FONTS='{"roles": {"step": "kai"}}'
两者都会浅合并进下面的默认表（local.json 优先级最高）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

FONTS_DIR = Path(__file__).parent / "common" / "fonts"

# ── 家族注册表 ──────────────────────────────────────────────
# name = 系统已安装字体名（manim Text 也能用）；file = 自带字体文件（随渲染器分发）
# file = 自带字体文件（放 common/fonts/，xelatex 按 Path 加载、并 register 给 manim Text）
# pango = 该文件的真实字体家族名（manim Text/Pango 用；与 file 配对）
# name = 仅系统已装字体（如 Windows 内置 KaiTi），xelatex 和 Pango 都按名找
FONT_FAMILIES = {
    "song":   {"file": "NotoSerifSC-Regular.otf", "pango": "Noto Serif SC"},  # 思源宋体（自带）
    "kai":    {"name": "KaiTi"},                                              # 系统楷体（Windows 内置）
    "wenkai": {"file": "LXGWWenKai-Regular.ttf", "pango": "LXGW WenKai"},     # 霞鹜文楷（自带）
    "mashan": {"file": "MaShanZheng.ttf", "pango": "Ma Shan Zheng"},          # 马善政毛笔（自带）
}

# ── 角色分配 ────────────────────────────────────────────────
FONT_ROLE = {
    "title":     "song",     # 标题（封面大标题、顶栏标题）
    "statement": "wenkai",   # 题干（封面 + 讲解常驻）
    "step":      "song",     # 讲解步骤
    "wow":       "mashan",   # wow 顿悟卡的强调汉字
    "takeaway":  "kai",      # 升华心法
}


def _merge(base: dict, override) -> None:
    if isinstance(override, dict):
        base.update(override)


def _load_overrides() -> None:
    """local.json 与环境变量覆盖默认表（浅合并）。"""
    local = FONTS_DIR / "fonts.local.json"
    for src in (local, os.environ.get("LECTURE_FONTS")):
        try:
            if isinstance(src, Path):
                if not src.exists():
                    continue
                data = json.loads(src.read_text(encoding="utf-8"))
            elif isinstance(src, str) and src.strip():
                data = json.loads(src)
            else:
                continue
            _merge(FONT_FAMILIES, data.get("families"))
            _merge(FONT_ROLE, data.get("roles"))
        except Exception as e:  # 配置坏了不该让整条渲染挂掉
            print(f"[font_config] 覆盖配置解析失败，忽略：{e}")


_load_overrides()


def role_family(role: str) -> str:
    """角色 -> family 名（传给 create_mixed_tex 的 font= 参数）。"""
    return FONT_ROLE.get(role, "song")


def family_system_name(family: str) -> str:
    """family -> 给 manim Text(Pango) 用的字体家族名。
    自带 file 字体在 register_vendored_fonts() 后 Pango 可按其 pango 名找到。"""
    spec = FONT_FAMILIES.get(family, {})
    return spec.get("pango") or spec.get("name") or "Noto Serif SC"


def pango_name(font) -> str:
    """把 create_mixed_tex 的 font 参数（可能是 family 键，也可能已是字体名）解析成
    manim Text(Pango) 能用的字体名。family 键 -> 其 pango/name；否则原样返回。"""
    if font in FONT_FAMILIES:
        return family_system_name(font)
    return font


_REGISTERED = False


def register_vendored_fonts() -> None:
    """把所有 file 自带字体注册给 manimpango，使 manim Text（标题/caption 等 Pango 渲染）
    也能用这些字体——否则 Text 只认系统已安装字体，自带字体会静默回退。幂等。"""
    global _REGISTERED
    if _REGISTERED:
        return
    try:
        import manimpango
    except Exception as e:
        print(f"[font_config] manimpango 不可用，跳过自带字体注册：{e}")
        _REGISTERED = True
        return
    for fam, spec in FONT_FAMILIES.items():
        f = spec.get("file")
        if not f:
            continue
        path = FONTS_DIR / f
        if not path.exists():
            print(f"[font_config] 自带字体缺失：{path}（{fam}）")
            continue
        try:
            manimpango.register_font(str(path))
        except Exception as e:
            print(f"[font_config] 注册字体失败 {f}：{e}")
    _REGISTERED = True


def latex_family_defs(fonts_dir_posix: str) -> str:
    """按 FONT_FAMILIES 生成 xeCJK 的 \\setCJKfamilyfont 定义 + \\textXxx 包裹命令。"""
    lines = []
    for fam, spec in FONT_FAMILIES.items():
        if spec.get("file"):
            lines.append(
                r"\setCJKfamilyfont{%s}{%s}[Path=%s/]" % (fam, spec["file"], fonts_dir_posix)
            )
        else:
            lines.append(r"\setCJKfamilyfont{%s}{%s}" % (fam, spec["name"]))
        lines.append(r"\newcommand{\text%s}[1]{{\CJKfamily{%s}#1}}" % (fam, fam))
    return "\n".join(lines) + "\n"


def main_font_latex() -> str:
    """主字体（默认正文）用 song 家族。"""
    spec = FONT_FAMILIES.get("song", {"name": "Noto Serif SC"})
    if spec.get("file"):
        return r"\setCJKmainfont{%s}[Path=%s/]" % (spec["file"], FONTS_DIR.as_posix())
    return r"\setCJKmainfont{%s}" % spec["name"]
