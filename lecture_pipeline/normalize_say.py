"""normalize_say.py — say 字段 TTS 规范化（确定性后处理）。

只做 100% 可确定的转换，多位数一律不碰、只报警。

处理的（A 类·确定性）：
  - 孤立个位阿拉伯数字 → 汉字：2x→二x、l1→l一、等于0→等于零
  - 个位数后紧跟计量字母(m/t/k/g/l/s) → 字母大写防单位误读：2m→二M、3t→三T

不处理的（B 类·语义，留给生成阶段的大模型）：
  - 多位数读法（120度=一百二十 vs 编号=逐位）—— 脚本只 grep 报警，不转
  - 向量本体 vs 模长、数学符号口语化（二分之一 / cosine）、希腊字母

用法：
  python -m lecture_pipeline.normalize_say <yaml_path>          # 就地改写 + 报告
  python -m lecture_pipeline.normalize_say <yaml_path> --check  # 只检测不改写

退出码：发现多位数残留 → 1（需人工/agent 确认读法）；否则 0。
"""
import re
import sys
import pathlib

UNIT_LETTERS = set("mtkgls")  # 紧跟个位数时易被 TTS 读成单位：米/吨/千/克/升/秒
DIGIT_CN = {"0": "零", "1": "一", "2": "二", "3": "三", "4": "四",
            "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}

SAY_RE = re.compile(r"^(\s*-?\s*say:\s*)(.*)$")


def normalize_value(value):
    """规范化单个 say 值字符串。返回新串。"""
    # 1) 孤立个位数 → 汉字（+ 计量字母大写）；多位数原样保留
    out = []
    n = len(value)
    i = 0
    while i < n:
        c = value[i]
        if c.isdigit():
            prev_d = i > 0 and value[i - 1].isdigit()
            next_d = i + 1 < n and value[i + 1].isdigit()
            if not prev_d and not next_d:
                out.append(DIGIT_CN[c])
                if i + 1 < n and value[i + 1] in UNIT_LETTERS:
                    out.append(value[i + 1].upper())
                    i += 2
                    continue
            else:
                out.append(c)  # 多位数的一部分，不动
        else:
            out.append(c)
        i += 1
    return "".join(out)


def main():
    argv = sys.argv[1:]
    check_only = "--check" in argv
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        print("用法: python -m lecture_pipeline.normalize_say <yaml> [--check]")
        sys.exit(2)

    path = pathlib.Path(paths[0])
    lines = path.read_text(encoding="utf-8").splitlines()

    new_lines = []
    changed = 0
    multidigit = []  # (lineno, number, context)
    for idx, line in enumerate(lines, 1):
        m = SAY_RE.match(line)
        if not m:
            new_lines.append(line)
            continue
        prefix, value = m.group(1), m.group(2)
        new_value = normalize_value(value)
        if new_value != value:
            changed += 1
        for mm in re.finditer(r"\d{2,}", new_value):
            a = max(0, mm.start() - 12)
            b = min(len(new_value), mm.end() + 12)
            multidigit.append((idx, mm.group(), new_value[a:b]))
        new_lines.append(prefix + new_value)

    if not check_only:
        text = "\n".join(new_lines)
        if not text.endswith("\n"):
            text += "\n"
        path.write_text(text, encoding="utf-8")

    print(f"[normalize_say] {path.name}")
    print(f"  规范化 say 行: {changed}" + ("（--check 未写回）" if check_only else ""))
    if multidigit:
        print(f"  WARN 多位数残留 {len(multidigit)} 处（脚本不转，需确认基数/逐位读法）:")
        for ln, num, ctx in multidigit:
            print(f"     L{ln}  {num}  …{ctx}…")
        sys.exit(1)
    print("  OK 无多位数残留")
    sys.exit(0)


if __name__ == "__main__":
    main()
