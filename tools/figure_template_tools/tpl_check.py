"""
FigureTemplate 结构校验：按 FigureLibraryService.validateTemplate 的规则
逐项检查单个 JSON 模板，输出 PASS/FAIL 与问题清单。

用法：
    python tpl_check.py <tpl_id>            # 按 id 查找
    python tpl_check.py <path/to/x.json>    # 按路径
    python tpl_check.py --all               # 校验全部
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIGURES = REPO / "figure_library" / "figures"

TEMPLATE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
PARAM_NAME = re.compile(r"^[a-z][a-z0-9]{0,30}$")
NUMBER_VALUE = re.compile(r"^-?\d+(\.\d+)?$")   # 锚定结尾，避免 "1a" 误判
OPTION_VALUE = re.compile(r"^[A-Za-z0-9-]{1,30}$")


def _ok(cond, msg, errors):
    if not cond:
        errors.append(msg)
        return False
    return True


def check_constraint_names(expr: str, names: set[str]) -> str | None:
    for tok in re.split(r"[^A-Za-z0-9.]+", expr):
        if not tok or re.match(r"^\d+(\.\d+)?$", tok):
            continue
        if tok not in names:
            return f"约束表达式引用了未定义的参数：{tok}"
    return None


def validate(t: dict) -> list[str]:
    e: list[str] = []
    if not isinstance(t, dict):
        return ["模板不是 JSON 对象"]
    _ok(isinstance(t.get("id"), str) and TEMPLATE_ID.match(t["id"]),
        "id 必须是小写字母/数字/连字符（作文件名）", e)
    _ok(isinstance(t.get("name"), str) and t["name"].strip(),
        "name 不能为空", e)
    desc = t.get("desc")
    _ok(isinstance(desc, str) and len(desc.strip()) >= 20,
        "desc 必填且不少于 20 字", e)
    params = t.get("params")
    if not isinstance(params, list) or not params:
        e.append("params 不能为空（无参数图形建议直接用自由 TikZ）")
        return e
    names: set[str] = set()
    for p in params:
        if not isinstance(p, dict):
            e.append(f"参数项不是对象：{p}"); continue
        pn = p.get("name")
        if not isinstance(pn, str) or not PARAM_NAME.match(pn):
            e.append(f"参数名 {pn!r} 不合法（小写字母开头，限小写字母数字）"); continue
        names.add(pn)
        ptype = p.get("type") or "number"
        pdef = p.get("default")
        if ptype == "number":
            if not isinstance(pdef, str) or not NUMBER_VALUE.match(pdef):
                e.append(f"参数 {pn} 默认值需为数字字符串，收到 {pdef!r}")
            mn, mx = p.get("min"), p.get("max")
            if mn is not None and not NUMBER_VALUE.match(str(mn)):
                e.append(f"参数 {pn} min 不是数字：{mn!r}")
            if mx is not None and not NUMBER_VALUE.match(str(mx)):
                e.append(f"参数 {pn} max 不是数字：{mx!r}")
        elif ptype == "bool":
            if not isinstance(pdef, str) or pdef.lower() not in {"true", "false", "0", "1"}:
                e.append(f"参数 {pn} 默认值需为 true/false")
        elif ptype == "string":
            opts = p.get("options")
            if not isinstance(opts, list) or not opts:
                e.append(f"string 参数 {pn} 必须配置 options 白名单")
            else:
                for o in opts:
                    if not isinstance(o, str) or not OPTION_VALUE.match(o):
                        e.append(f"string 参数 {pn} 的选项须为字母数字连字符：{o!r}")
            if not isinstance(pdef, str) or (opts and pdef not in opts):
                e.append(f"string 参数 {pn} 默认值 {pdef!r} 不在 options 内")
        else:
            e.append(f"参数 {pn} 类型不支持：{ptype}")
    tpl = t.get("template")
    if not isinstance(tpl, str) or "\\begin{tikzpicture}" not in tpl:
        e.append("template 必须含 \\begin{tikzpicture}")
    else:
        code = "\n".join(l for l in tpl.splitlines() if not l.strip().startswith("%"))
        if "\\def" in code:
            e.append("模板体（非注释行）不要写 \\def（参数声明区由后端自动注入）")
    constraints = t.get("constraints") or []
    if not isinstance(constraints, list):
        e.append("constraints 必须是数组")
    else:
        for c in constraints:
            err = check_constraint_names(c, names)
            if err:
                e.append(err)
    return e


def find_by_id(tpl_id: str) -> Path | None:
    if not FIGURES.is_dir():
        return None
    for f in FIGURES.rglob("*.json"):
        try:
            t = json.loads(f.read_text(encoding="utf-8"))
            if t.get("id") == tpl_id:
                return f
        except Exception:
            continue
    return None


def run(target: str) -> int:
    p = Path(target)
    if not p.exists():
        p = find_by_id(target)
        if p is None:
            print(f"[FAIL] 找不到模板：{target}")
            return 1
    try:
        t = json.loads(p.read_text(encoding="utf-8"))
    except Exception as ex:
        print(f"[FAIL] JSON 解析失败：{ex}")
        return 1
    errs = validate(t)
    if errs:
        print(f"[FAIL] {t.get('id', p.stem)}")
        for m in errs:
            print(f"  - {m}")
        return 1
    print(f"[PASS] {t['id']}")
    return 0


def run_all() -> int:
    if not FIGURES.is_dir():
        print(f"图库目录不存在：{FIGURES}")
        return 1
    files = sorted(FIGURES.rglob("*.json"))
    if not files:
        print("图库为空"); return 0
    rc = 0
    for f in files:
        try:
            t = json.loads(f.read_text(encoding="utf-8"))
        except Exception as ex:
            print(f"[FAIL] {f.name} JSON 解析失败：{ex}"); rc = 1; continue
        errs = validate(t)
        if errs:
            print(f"[FAIL] {t.get('id', f.stem)}")
            for m in errs:
                print(f"  - {m}")
            rc = 1
        else:
            print(f"[PASS] {t['id']}")
    return rc


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    if len(sys.argv) < 2:
        print("用法：python tpl_check.py <tpl_id|path> | --all"); sys.exit(2)
    if sys.argv[1] == "--all":
        sys.exit(run_all())
    sys.exit(run(sys.argv[1]))
