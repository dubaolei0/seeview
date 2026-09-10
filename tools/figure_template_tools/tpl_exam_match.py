# -*- coding: utf-8 -*-
"""
真题匹配 + 模板配图渲染 统一工具

功能：
  1. 从本地高考拆题目录构建轻量索引（index.json）
  2. 按 seeview 图库模板的考点关键词，精准匹配对应真题
  3. 用 tpl_preview + latex_snippet_tool 渲染模板配图

用法：
  python tpl_exam_match.py --build-index [高考拆题目录]
  python tpl_exam_match.py --list
  python tpl_exam_match.py --match <tpl_id>
  python tpl_exam_match.py --render <tpl_id> [k=v ...]

依赖：
  - tpl_preview.py（同目录）
  - latex_snippet_tool.py（tools/题目png生成工具/）
  - Python venv: g:\\IdeaProjects\\seeview\\lecture_pipeline\\.venv
"""
from __future__ import annotations
import json, os, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIGURES = REPO / "figure_library" / "figures"
OUT = REPO / ".tmp_compile_out"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO / "tools" / "题目png生成工具"))

# ── 默认高考拆题目录 ──────────────────────────────────────────────
DEFAULT_EXAM_DIR = Path(r"G:\爱学\高考拆题")
DEFAULT_INDEX = DEFAULT_EXAM_DIR / "index.json"

# ── 模板 → 考点关键词映射 ────────────────────────────────────────
TEMPLATE_KEYWORDS: dict[str, list[str]] = {
    "quadratic-function":      ["二次函数"],
    "linear-function":         ["一次函数"],
    "inverse-proportional":    ["反比例函数"],
    "exponential-function":    ["指数函数"],
    "logarithm-function":     ["对数函数"],
    "power-function-compare":  ["幂函数"],
    "trig-sine-wave":          ["正弦函数", "三角函数的图象", "三角函数图像"],
    "tangent-function":        ["正切函数"],
    "hook-function":           ["对勾函数", "打勾函数"],
    "piecewise-function":      ["分段函数"],
}

# ── 几何图库模板关键词（预留扩展） ────────────────────────────────
GEOMETRY_KEYWORDS: dict[str, list[str]] = {
    "ellipse":            ["椭圆"],
    "circle":             ["圆"],
    "parabola":           ["抛物线"],
    "hyperbola":           ["双曲线"],
    "circle-tangent":     ["圆的切线"],
    "circle-perp-chord":  ["垂径定理"],
    "circle-power-point": ["圆幂定理"],
    "chord-tangent-angle": ["弦切角"],
    "cyclic-quadrilateral": ["圆内接四边形"],
}


# ═══════════════════════════════════════════════════════════════
#  1. 索引构建
# ═══════════════════════════════════════════════════════════════

def build_index(exam_dir: Path, out_file: Path) -> int:
    """扫描 exam_dir 下所有 .md，抽取前 10 行的结构化标签，输出 JSON 索引。"""
    items = []
    for root, dirs, files in os.walk(str(exam_dir)):
        dirs[:] = [d for d in dirs if d not in (".obsidian", ".claude", ".git")]
        for fn in files:
            if not fn.endswith(".md"):
                continue
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, str(exam_dir)).replace("\\", "/")
            paper = rel.split("/")[0] if "/" in rel else "unknown"

            entry = {"file": rel, "paper": paper,
                     "title": "", "kaodian": "", "zhishi": "",
                     "kaodianyao": "", "miaosha": ""}

            try:
                with open(fp, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.rstrip()
                        if line.count("\n") > 10:
                            break
                        m = re.match(r'^#\s+(.+)', line)
                        if m: entry["title"] = m.group(1).strip(); continue
                        m = re.match(r'\*\*考点标签：\*\*\s*(.+)', line)
                        if m: entry["kaodian"] = m.group(1).strip(); continue
                        m = re.match(r'\*\*知识点标签：\*\*\s*(.+)', line)
                        if m: entry["zhishi"] = m.group(1).strip(); continue
                        m = re.match(r'\*\*考查要点：\*\*\s*(.+)', line)
                        if m: entry["kaodianyao"] = m.group(1).strip(); continue
                        m = re.match(r'\*\*秒杀技巧：\*\*\s*(.+)', line)
                        if m: entry["miaosha"] = m.group(1).strip(); continue
            except Exception:
                continue
            items.append(entry)

    items.sort(key=lambda x: x["paper"] + x["file"])
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(str(out_file), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return len(items)


# ═══════════════════════════════════════════════════════════════
#  2. 模板 ↔ 真题匹配
# ═══════════════════════════════════════════════════════════════

def load_index(index_path: Path) -> list[dict]:
    if not index_path.exists():
        print(f"索引文件不存在：{index_path}")
        print("请先运行：python tpl_exam_match.py --build-index")
        sys.exit(1)
    with open(str(index_path), "r", encoding="utf-8") as f:
        return json.load(f)


def match_template(tpl_id: str, index: list[dict],
                   keyword_map: dict[str, list[str]]) -> list[dict]:
    """返回 kaodian 直接命中关键词的题目列表。"""
    kws = keyword_map.get(tpl_id, [])
    if not kws:
        return []
    return [item for item in index
            if any(k in item["kaodian"] for k in kws)]


def match_all_templates(index: list[dict],
                        keyword_map: dict[str, list[str]]) -> dict[str, list[dict]]:
    results = {}
    for tpl_id in keyword_map:
        hits = match_template(tpl_id, index, keyword_map)
        results[tpl_id] = hits
    return results


def print_match(tpl_id: str, hits: list[dict]):
    print(f"\n{'='*70}")
    print(f"  {tpl_id}  →  kaodian 直接命中 {len(hits)} 题")
    print(f"{'='*70}")
    for h in hits:
        print(f"  [{h['paper']}] {h['file'].split('/')[-1]}")
        print(f"    考点: {h['kaodian']}")
        zs = h["zhishi"][:90] + ("…" if len(h["zhishi"]) > 90 else "")
        print(f"    知识: {zs}")
    if not hits:
        print("  (kaodian 未直接命中)")


# ═══════════════════════════════════════════════════════════════
#  3. 模板渲染（委托 tpl_preview + latex_snippet_tool）
# ═══════════════════════════════════════════════════════════════

def render_template(tpl_id: str, overrides: dict):
    """用 tpl_preview 的基础设施渲染模板配图。"""
    from tpl_preview import find_template, build_tex, ink_stats, ascii_preview
    import latex_snippet_tool as L

    t = find_template(tpl_id)
    if t is None:
        print(f"找不到模板：{tpl_id}")
        return 1

    try:
        tex = build_tex(t, overrides)
    except ValueError as ex:
        print(f"参数注入失败：{ex}")
        return 1

    img = L.compile_and_render(tex, 100, 12, dpi=150, crop_x=True)
    out = OUT / f"{tpl_id}.png"
    img.save(str(out))
    print(f"保存：{out}  {img.width}x{img.height}  {ink_stats(img)}")
    print(ascii_preview(img, 64, 26))
    return 0


# ═══════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════

def _parse_kvs(args: list[str]) -> dict:
    d = {}
    for a in args:
        if "=" not in a:
            continue
        k, v = a.split("=", 1)
        d[k.strip()] = v.strip()
    return d


def main():
    # 合并函数图库 + 几何图库关键词
    all_keywords = {**TEMPLATE_KEYWORDS, **GEOMETRY_KEYWORDS}

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "--build-index":
        exam_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_EXAM_DIR
        out_file = DEFAULT_INDEX
        n = build_index(exam_dir, out_file)
        print(f"Done: {n} files indexed -> {out_file}")

    elif cmd == "--list":
        index = load_index(DEFAULT_INDEX)
        results = match_all_templates(index, all_keywords)
        print(f"索引: {DEFAULT_INDEX}  ({len(index)} 题)")
        print(f"{'模板':<28} {'命中数':>6}  {'关键词'}")
        print("-" * 70)
        for tpl_id, hits in results.items():
            kws = all_keywords.get(tpl_id, [])
            print(f"{tpl_id:<28} {len(hits):>6}  {', '.join(kws)}")

    elif cmd == "--match":
        if len(sys.argv) < 3:
            print("用法: --match <tpl_id>")
            sys.exit(2)
        tpl_id = sys.argv[2]
        index = load_index(DEFAULT_INDEX)
        hits = match_template(tpl_id, index, all_keywords)
        print_match(tpl_id, hits)
        # 备用：zhishi 命中
        if not hits:
            kws = all_keywords.get(tpl_id, [])
            zh_hits = [item for item in index
                       if any(k in item["zhishi"] for k in kws)]
            if zh_hits:
                print(f"\n  zhishi 备用命中 {len(zh_hits)} 题:")
                for h in zh_hits[:5]:
                    print(f"    [{h['paper']}] {h['file'].split('/')[-1]}")
                    print(f"      考点: {h['kaodian']}")

    elif cmd == "--render":
        if len(sys.argv) < 3:
            print("用法: --render <tpl_id> [k=v ...]")
            sys.exit(2)
        tpl_id = sys.argv[2]
        overrides = _parse_kvs(sys.argv[3:])
        # 确保依赖路径
        sys.path.insert(0, str(Path(__file__).parent))
        sys.exit(render_template(tpl_id, overrides))

    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
