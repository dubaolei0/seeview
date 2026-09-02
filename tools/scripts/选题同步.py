# -*- coding: utf-8 -*-
r"""
选题同步：让 _选题.md(纯题目正文) 与 题库 按 ID 对账。ID 不存在选题里。

分工(与团队讨论一致)：
- 讲义(_讲义.md) 里有一份【选题ID台账】：有序 ID 列表，第 N 个 ID ↔ 选题第 N 题。
- 选题(_选题.md) 只放按格式的题目正文，**不掺 ID**，保持干净、可手改。
- 人想改题：直接在选题里改正文，不用管 ID。
- 同步：按顺序把 选题第N题 与 台账第N个ID 配对，做【全文归一化比对】(题干+选项+答案+解析)：
    · 一致         → 不动
    · 改过 / 无对应ID → 报告；--apply 时写新增库拿新 u_ID，回写到讲义台账(不动选题)
- 比对用全文归一化直接比对，不取前缀——后半段(解析/答案)的改动也跑不掉。
- 改主库 q_ 原题不改写主库：派生带 parent 的 u_ 变体，溯源链保留。

用法：
    python 选题同步.py <选题.md>                 # 只 check(默认)；讲义路径自动取同目录 _讲义.md
    python 选题同步.py <选题.md> --讲义 <讲义.md> # 显式指定讲义
    python 选题同步.py <选题.md> --apply --user 哈斯
"""
import argparse, importlib.util, json, os, re, sys, uuid, datetime

sys.stdout.reconfigure(encoding="utf-8")
_HERE = os.path.dirname(os.path.abspath(__file__))
_BASE = os.path.normpath(os.path.join(_HERE, "..", ".."))
CONTRIB_PATH = os.path.join(_BASE, "knowledge", "高考题目", "题库", "contributions.jsonl")
PATCH_PATH = os.path.join(_BASE, "knowledge", "高考题目", "题库", "patches.jsonl")

LEDGER_HEADING = "选题ID台账"     # 讲义里这一节的标题
_FMT = {"单选题": "single_choice", "多选题": "multiple_choice",
        "填空题": "fill_in_blank", "解答题": "short_answer", "证明题": "proof"}
_PUNC = str.maketrans("，。；：（）！？、％　", ",.;:()!?,% ")


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, fname))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def norm(s):
    """全文归一化(用于内容比对)：去全部空白(含字面 \\n)、统一全角标点。实质改一字符必变。"""
    if not s:
        return ""
    s = s.replace("\\n", "").replace("\r", "").translate(_PUNC)
    return re.sub(r"\s+", "", s).strip()


# ── 选题 md 解析(纯内容) ──────────────────────────────────────────────────
def _field(block, name):
    m = re.search(rf"【{name}】(.*?)(?=\n\s*【|\Z)", block, re.S)
    return m.group(1).strip() if m else ""


def split_stem(fmt, stem_region):
    """选择题：把题干区拆成 (纯题干, 选项列表)；其余题型选项为 None。与库的 content/options 同口径。"""
    if fmt in ("single_choice", "multiple_choice"):
        opts = re.findall(r"\n\s*[ABCD][\.、]\s*(.+)", stem_region)
        if opts:
            stem = re.split(r"\n\s*A[\.、]", stem_region)[0].strip()
            return stem, [o.strip() for o in opts]
    return stem_region, None


def parse_选题(md_text):
    out = []
    for m in re.finditer(r"(?m)^#{2,3}\s.*?(?=^#{2,3}\s|\Z)", md_text, re.S):
        block = m.group(0)
        if "【题干】" not in block:
            continue
        fmt_m = re.search(r"【(单选题|多选题|填空题|解答题|证明题)】", block)
        fmt = _FMT.get(fmt_m.group(1)) if fmt_m else "fill_in_blank"
        stem_m = re.search(r"【题干】(.*?)(?=\n\s*【答案】)", block, re.S)
        stem_region = stem_m.group(1).strip() if stem_m else _field(block, "题干")
        stem, options = split_stem(fmt, stem_region)
        out.append({
            "fmt": fmt, "stem_region": stem_region, "stem": stem, "options": options,
            "answer": _field(block, "答案"), "analysis": _field(block, "解析"),
            "source": _field(block, "题目来源"),
        })
    return out


# ── 讲义 ID 台账解析 / 回写 ───────────────────────────────────────────────
def parse_ledger(handout_text):
    """取【选题ID台账】小节里、按出现顺序的 q_/u_ ID 列表；返回 (ids, section_span or None)。"""
    sec = re.search(rf"(?ms)^#{{1,6}}\s*{LEDGER_HEADING}\s*$(.*?)(?=^#{{1,6}}\s|^---\s*$|\Z)", handout_text)
    if not sec:
        return [], None
    ids = re.findall(r"\b((?:q_|u_)[0-9a-f]+)\b", sec.group(1))
    return ids, sec.span(1)


def write_ledger(handout_path, handout_text, span, ids):
    """用新的有序 ID 列表重写台账小节正文(span 指向标题之后的正文区)。"""
    lines = "\n> 顺序严格对应 `_选题.md`；ID 由 选题同步.py 维护，请勿手改顺序。\n\n"
    lines += "\n".join(f"{i}. {qid}" for i, qid in enumerate(ids, 1)) + "\n\n"
    new = handout_text[:span[0]] + lines + handout_text[span[1]:]
    with open(handout_path, "w", encoding="utf-8") as f:
        f.write(new)


# ── 库侧签名 ─────────────────────────────────────────────────────────────
def db_stem_region(q):
    s = (q.get("content") or "")
    opts = q.get("options")
    if opts and q.get("question_format") in ("single_choice", "multiple_choice"):
        s += "".join(str(o) for o in opts)
    return s


def sig(stem, ans, ana):
    return norm(stem) + "|" + norm(ans) + "|" + norm(ana)


def md_sig(it):
    stem = (it["stem"] or "") + "".join(str(o) for o in (it["options"] or []))
    return sig(stem, it["answer"], it["analysis"])


def db_sig(q):
    return sig(db_stem_region(q), q.get("answer"), q.get("analysis"))


# ── 对账(按顺序配对) ──────────────────────────────────────────────────────
def reconcile(items, ids, db):
    rep = []
    for i, it in enumerate(items):
        qid = ids[i] if i < len(ids) else None
        if qid is None:
            st, detail = "new", "选题多出此题，台账无对应 ID(待登记)"
        elif qid not in db:
            st, detail = "missing", f"台账 ID {qid} 不在库中"
        elif md_sig(it) == db_sig(db[qid]):
            st, detail = "unchanged", f"{qid} 内容一致"
        else:
            st, detail = "changed", f"{qid} 内容已改"
        rep.append({"no": i + 1, "status": st, "detail": detail, "item": it, "id": qid})
    return rep


def _append(path, rec):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _append_contrib(rec):
    _append(CONTRIB_PATH, rec)


def patch_existing(it, qid, user, reason="选题同步：内容更新"):
    """同题写得更好 → 打补丁覆盖原记录(主库不动、可回溯)，ID 不变。"""
    fields = {"content": it["stem"], "answer": it["answer"], "analysis": it["analysis"]}
    if it["options"]:
        fields["options"] = it["options"]
    _append(PATCH_PATH, {
        "target_id": qid, "fields": fields, "by": user, "reason": reason,
        "at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    })


def make_contribution(it, user, parent_id=None):
    new_id = "u_" + uuid.uuid4().hex[:10]
    stem, options = it["stem"], it["options"]
    _append_contrib({
        "id": new_id, "type": "molecular", "parent_question_id": parent_id,
        "content": stem, "options": options, "answer": it["answer"],
        "analysis": it["analysis"], "question_format": it["fmt"],
        "knowledge_chapter": None, "knowledge_points": [],
        "source_exam": it["source"] or None,
        "contributed_by": user, "status": "user_contributed",
        "created_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tagging_status": "pending",
    })
    return new_id


def main():
    ap = argparse.ArgumentParser(description="选题.md 与题库按顺序对账(ID 存讲义台账)")
    ap.add_argument("选题", help="_选题.md 路径")
    ap.add_argument("--讲义", dest="handout", default=None, help="_讲义.md(默认同目录)")
    ap.add_argument("--apply", action="store_true", help="写新增库并回写讲义台账(默认只 check)")
    ap.add_argument("--user", default="未知")
    a = ap.parse_args()

    handout = a.handout or a.选题.replace("_选题.md", "_讲义.md")
    pptx = _load("lianxi", "练习题PPT.py")
    db = pptx.load_db()
    md_text = open(a.选题, encoding="utf-8").read()
    items = parse_选题(md_text)
    handout_text = open(handout, encoding="utf-8").read() if os.path.exists(handout) else ""
    ids, span = parse_ledger(handout_text)
    if not items:
        sys.exit(f"❌ 选题没解析出题目：{a.选题}")
    if span is None:
        print(f"⚠ 讲义里没找到【{LEDGER_HEADING}】小节：{handout}\n  请先在讲义加该小节(可空)，再 --apply 让本工具填充。")

    rep = reconcile(items, ids, db)
    icon = {"unchanged": "✓", "changed": "✎", "new": "＋", "missing": "✗"}
    print(f"\n选题 {os.path.basename(a.选题)}  {len(items)} 题  ↔  台账 {len(ids)} 个 ID\n" + "-" * 58)
    for r in rep:
        head = r["item"]["stem_region"][:28].replace("\n", " ")
        print(f"  {r['no']:>2}. [{icon[r['status']]} {r['status']:<9}] {r['detail']}")
        print(f"       {head}…")
    todo = [r for r in rep if r["status"] in ("changed", "new")]
    print("-" * 58)
    print(f"  一致 {sum(1 for r in rep if r['status']=='unchanged')} | 待登记 {len(todo)} "
          f"| ID缺失 {sum(1 for r in rep if r['status']=='missing')}")

    if not a.apply:
        print("\n（--check 模式，未改动任何文件。确认后 --apply --user <姓名> 执行登记+回写讲义台账。）")
        return
    if span is None:
        sys.exit("❌ 讲义缺台账小节，无法回写。请先建【选题ID台账】小节。")

    new_ids = list(ids) + [None] * (len(items) - len(ids))
    n_patch = n_new = 0
    for r in todo:
        it = r["item"]
        if r["status"] == "changed":     # 同题写得更好 → 打补丁，ID 不变
            patch_existing(it, r["id"], a.user)
            n_patch += 1
            print(f"  ✎ 第{r['no']}题 → 补丁覆盖 {r['id']}（主库不动、可回溯）")
        else:                            # 无对应 ID 的新题 → 进新增库，回写 ID
            nid = make_contribution(it, a.user)
            new_ids[r["no"] - 1] = nid
            n_new += 1
            print(f"  ＋ 第{r['no']}题 → 新增库 {nid}")
    if n_new:
        write_ledger(handout, handout_text, span, new_ids)
    print(f"\n✅ 补丁 {n_patch} 题、新增 {n_new} 题" + ("，并回写讲义台账。" if n_new else "。"))


if __name__ == "__main__":
    main()
