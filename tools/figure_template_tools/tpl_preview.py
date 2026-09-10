"""
FigureTemplate 试编译 + 预览：
  - find_template(id)      : 在 figure_library/figures/ 下递归查找
  - build_tex(tpl, overrides) : 注入 \def 声明区 + 模板体，返回完整 TeX 源
  - ascii_preview(img, cols, rows) : 降采样到字符
  - ink_stats(img)        : 四象限墨量百分比
  - main(tpl_id, **k=v)   : 渲染 PNG 保存到 .tmp_compile_out/

用法：
    python tpl_preview.py <tpl_id> [k=v ...]
    python tpl_preview.py quadratic-function a=2 h=1 k=-1 showpoint=true

批量内联：
    import sys; sys.path.insert(0, 'tools/figure_template_tools')
    from tpl_preview import find_template, build_tex, ascii_preview, ink_stats, OUT
    import latex_snippet_tool as L
    img = L.compile_and_render(tex, 100, 12, dpi=150, crop_x=True)
"""
from __future__ import annotations
import json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIGURES = REPO / "figure_library" / "figures"
OUT = REPO / ".tmp_compile_out"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO / "tools" / "题目png生成工具"))


def find_template(tpl_id: str) -> dict | None:
    for f in FIGURES.rglob("*.json"):
        try:
            t = json.loads(f.read_text(encoding="utf-8"))
            if t.get("id") == tpl_id:
                return t
        except Exception:
            continue
    return None


def build_tex(t: dict, overrides: dict | None = None) -> str:
    """按后端 appendDefs 规则拼 \def 声明区 + 模板体。"""
    overrides = overrides or {}
    lines = []
    for p in t.get("params", []):
        name = p["name"]
        ptype = p.get("type") or "number"
        raw = overrides.get(name, p.get("default"))
        if raw is None:
            raise ValueError(f"参数 {name} 未提供且无默认值")
        val = str(raw).strip()
        if ptype == "number":
            import re
            if not re.match(r"^-?\d+(\.\d+)?$", val):
                raise ValueError(f"参数 {name} 需要数字，收到：{val}")
        elif ptype == "bool":
            if val.lower() in ("true", "1"):
                val = "1"
            elif val.lower() in ("false", "0"):
                val = "0"
            else:
                raise ValueError(f"参数 {name} 需要 true/false，收到：{val}")
        elif ptype == "string":
            opts = p.get("options") or []
            if val not in opts:
                raise ValueError(f"参数 {name} 取值必须是 {'/'.join(opts)}，收到：{val}")
        else:
            raise ValueError(f"参数 {name} 类型不支持：{ptype}")
        lines.append(f"\\def\\{name}{{{val}}}")
    defs = "\n".join(lines)
    return f"{defs}\n{t['template']}"


def ascii_preview(img, cols: int = 64, rows: int = 26) -> str:
    """把 PIL Image 降采样到 cols×rows 字符，用 .,:=-*# 表示墨量。"""
    import numpy as np
    a = np.asarray(img.convert("L"))
    h, w = a.shape
    ch, cw = max(1, h // rows), max(1, w // cols)
    out = []
    for r in range(rows):
        line = []
        for c in range(cols):
            y0, y1 = r * ch, (r + 1) * ch
            x0, x1 = c * cw, (c + 1) * cw
            block = a[y0:y1, x0:x1]
            if block.size == 0:
                line.append(" "); continue
            v = int(block.mean())
            line.append(" " if v > 250 else ("." if v > 230 else (":" if v > 180 else ("-" if v > 120 else "#"))))
        out.append("".join(line))
    return "\n".join(out)


def ink_stats(img) -> str:
    """四象限墨量百分比，便于定位渲染失衡。"""
    import numpy as np
    a = np.asarray(img.convert("L"))
    h, w = a.shape
    dark = (a < 180).sum()
    total = a.size
    if total == 0:
        return "ink=0%"
    mid_y, mid_x = h // 2, w // 2

    def q(x0, x1, y0, y1):
        sub = a[y0:y1, x0:x1]
        return f"{100 * (sub < 180).sum() / sub.size:.1f}%"

    quads = [q(0, mid_x, 0, mid_y), q(mid_x, w, 0, mid_y),
             q(0, mid_x, mid_y, h), q(mid_x, w, mid_y, h)]
    return f"ink={100 * dark / total:.1f}%  左上/右上/左下/右下={quads}"


def _parse_kvs(args: list[str]) -> dict:
    d = {}
    for a in args:
        if "=" not in a:
            continue
        k, v = a.split("=", 1)
        d[k.strip()] = v.strip()
    return d


def main(tpl_id: str, **overrides) -> int:
    t = find_template(tpl_id)
    if t is None:
        print(f"找不到模板：{tpl_id}"); return 1
    try:
        tex = build_tex(t, overrides)
    except ValueError as ex:
        print(f"参数注入失败：{ex}"); return 1
    import latex_snippet_tool as L
    img = L.compile_and_render(tex, 100, 12, dpi=150, crop_x=True)
    out = OUT / f"{tpl_id}.png"
    img.save(out)
    print(f"保存：{out}  {img.width}x{img.height}  {ink_stats(img)}")
    print(ascii_preview(img, 64, 26))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python tpl_preview.py <tpl_id> [k=v ...]"); sys.exit(2)
    sys.exit(main(sys.argv[1], **_parse_kvs(sys.argv[2:])))
