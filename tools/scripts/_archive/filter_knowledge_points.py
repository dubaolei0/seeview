import os
import re

BASE_DIR = r"D:\_共享文件夹\knowledge\高考拆题"
OUTPUT = r"D:\_共享文件夹\knowledge_points_result.md"

# Each keyword: patterns to search in full document content
# All patterns are spatial-geometry specific
KEYWORDS = {
    "1. 球体的表面积和体积": [r"球.*表面积", r"球.*体积", r"球体"],
    "2. 柱体的表面积和体积": [r"柱.*表面积", r"柱.*体积", r"圆柱.*表面积", r"圆柱.*体积", r"棱柱.*表面积", r"棱柱.*体积"],
    "3. 椎体的表面积和体积": [r"锥.*表面积", r"锥.*体积", r"圆锥.*表面积", r"圆锥.*体积", r"棱锥.*表面积", r"棱锥.*体积", r"椎.*表面积", r"椎.*体积"],
    "4. 台体的表面积和体积": [r"台.*表面积", r"台.*体积", r"圆台.*表面积", r"圆台.*体积", r"棱台.*表面积", r"棱台.*体积"],
    "5. 椎体与台体棱长计算": [r"棱长"],
    "6. 内切球问题": [r"内切球"],
    "7. 外接球问题": [r"外接球"],
    "8. 球的截面问题": [r"球的截面", r"截面.*球", r"球.*截面"],
    "9. 几何体的截面问题": [r"截面"],
    # Only spatial geometry concurrent point problems
    "10. 共点问题": [r"三线共点", r"三条直线.*交于一点", r"线共点.*立体", r"视线共点"],
    # Only spatial geometry intersection problems
    "11. 在几何体中作线面交点和面面交线": [r"交线", r"线面交", r"面面交", r"线面.*交点", r"面面.*交点"],
    # Plane axioms and coplanarity (spatial geometry only)
    "12. 平面": [r"平面的基本性质", r"公理[1234].*平面", r"公理.*确定平面", r"不共线.*确定", r"平行线确定.*平面", r"两条相交.*确定.*平面"],
    "13. 直线与平面位置关系": [r"线面.*平行", r"线面.*垂直", r"直线与平面", r"线面角"],
    "14. 平面与平面位置关系": [r"面面.*平行", r"面面.*垂直", r"平面与平面", r"二面角"],
    "15. 直线与直线位置关系": [r"异面", r"线线.*角", r"线线平行", r"线线垂直", r"直线与直线"],
}

# Exclusion patterns - if a file is clearly analytic geometry / calculus, skip for spatial keywords
EXCLUDE_PATTERNS = {
    "10. 共点问题": [r"导数", r"切线", r"椭圆", r"双曲线", r"抛物线", r"函数.*单调", r"极坐标", r"海岛", r"重差"],
    "12. 平面": [r"线性规划", r"可行域", r"二元一次不等式", r"目标函数"],
}

results = {k: [] for k in KEYWORDS}
seen = set()

for root, dirs, files in os.walk(BASE_DIR):
    for fname in sorted(files):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(root, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                full_text = f.read()

            m = re.search(r"(.+?)第(.+?)题", fname)
            if m:
                exam = m.group(1)
                qno = m.group(2)
            else:
                exam = fname.replace(".md", "")
                qno = "?"

            kd_match = re.search(r"\*\*考点标签：\*\*\s*(.+?)\n", full_text)
            zs_match = re.search(r"\*\*知识点标签：\*\*\s*(.+?)\n", full_text)
            kd = kd_match.group(1).strip() if kd_match else ""
            zs = zs_match.group(1).strip() if zs_match else ""

            for kp, patterns in KEYWORDS.items():
                matched = False
                for pat in patterns:
                    if re.search(pat, full_text, re.IGNORECASE):
                        matched = True
                        break
                if matched:
                    # Apply exclusion filters
                    if kp in EXCLUDE_PATTERNS:
                        excluded = False
                        for ex_pat in EXCLUDE_PATTERNS[kp]:
                            if re.search(ex_pat, full_text, re.IGNORECASE):
                                excluded = True
                                break
                        if excluded:
                            continue

                    key = (kp, exam, qno)
                    if key not in seen:
                        seen.add(key)
                        results[kp].append({
                            "exam": exam,
                            "qno": qno,
                            "kd": kd,
                            "zs": zs,
                            "file": fname,
                        })
        except Exception as e:
            print(f"Error reading {fpath}: {e}")

lines = []
lines.append("# 知识点 - 高考真题对照表\n")
lines.append(f"共 15 个知识点，匹配到 {len(seen)} 条不重复记录（全文搜索，排除解析几何/导数干扰）\n")

total_count = 0
for kp, items in results.items():
    lines.append(f"\n## {kp}（{len(items)} 题）\n")
    lines.append("| 序号 | 年份-卷名 | 题号 | 考点标签 | 知识点标签 |")
    lines.append("|------|----------|------|----------|------------|")
    for i, item in enumerate(items, 1):
        exam = item['exam']
        qno = item['qno']
        kd = item['kd'].replace('|', '\\|')[:80]
        zs = item['zs'].replace('|', '\\|')[:80]
        lines.append(f"| {i} | {exam} | {qno} | {kd} | {zs} |")
    total_count += len(items)
    lines.append("")

lines.append(f"\n---\n**总计：{total_count} 条匹配**（同一道题可能同时属于多个知识点）\n")

with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Done: {len(seen)} unique records, {total_count} total matches")
print(f"Saved to: {OUTPUT}")
for kp, items in results.items():
    print(f"  {kp}: {len(items)}")
