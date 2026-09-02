import os
import re
import fitz

TEXTBOOK_DIR = r"D:\_共享文件夹\knowledge\教材\必修第二册"
EXAM_DIR = r"D:\_共享文件夹\knowledge\高考拆题"
OUTPUT = r"D:\_共享文件夹\knowledge_points_result.md"

# Chapter -> knowledge points mapping
CHAPTER_KPS = {
    "8_1_基本立体图形.pdf": ["1", "2", "3", "4"],
    "8_2_立体图形的直观图.pdf": ["1", "2", "3", "4"],
    "8_3_简单几何体的表面积与体积.pdf": ["1", "2", "3", "4"],
    "8_4_空间点、直线、平面之间的位置关系.pdf": ["8", "9", "10", "11", "12"],
    "8_5_空间直线、平面的平行.pdf": ["13", "14", "15"],
    "8_6_空间直线、平面的垂直.pdf": ["5", "13", "14", "15"],
}

KP_PATTERNS = {
    "1. 球体的表面积和体积": [r"球.*表面积", r"球.*体积"],
    "2. 柱体的表面积和体积": [r"柱.*表面积", r"柱.*体积", r"圆柱", r"棱柱.*体积"],
    "3. 椎体的表面积和体积": [r"锥.*表面积", r"锥.*体积", r"圆锥", r"棱锥.*体积"],
    "4. 台体的表面积和体积": [r"台.*表面积", r"台.*体积", r"圆台", r"棱台"],
    "5. 椎体与台体棱长计算": [r"棱长"],
    "6. 内切球问题": [r"内切球"],
    "7. 外接球问题": [r"外接球"],
    "8. 球的截面问题": [r"球的截面", r"截面.*球", r"球.*截面"],
    "9. 几何体的截面问题": [r"截面"],
    "10. 共点问题": [r"三线共点", r"三条直线.*交于一点"],
    "11. 在几何体中作线面交点和面面交线": [r"交线", r"线面交", r"面面交"],
    "12. 平面": [r"平面的基本性质", r"公理.*确定平面", r"确定.*平面", r"不共线.*确定"],
    "13. 直线与平面位置关系": [r"线面.*平行", r"线面.*垂直", r"直线与平面"],
    "14. 平面与平面位置关系": [r"面面.*平行", r"面面.*垂直", r"二面角"],
    "15. 直线与直线位置关系": [r"异面", r"线线.*角", r"线线平行", r"线线垂直"],
}


def extract_textbook_exercises():
    """Extract exercises from textbook PDFs."""
    exercises = {k: [] for k in KP_PATTERNS}

    for filename, kp_nums in CHAPTER_KPS.items():
        fpath = os.path.join(TEXTBOOK_DIR, filename)
        if not os.path.exists(fpath):
            continue

        doc = fitz.open(fpath)
        chapter_name = filename.replace('.pdf', '').split('_', 1)[1]

        for page_idx, page in enumerate(doc):
            text = page.get_text()
            text = text.replace('', '-').replace('', '.')

            # Find exercise sections
            # Look for ጷ˸ or 习题/练习 headings
            ex_start_positions = []
            for marker in ['ጷ˸']:
                pos = text.find(marker)
                if pos >= 0:
                    ex_start_positions.append(pos)
            # Also find 习题 headings
            for m in re.finditer(r'习题[０-９．]*', text):
                ex_start_positions.append(m.start())

            if not ex_start_positions:
                continue

            # Extract exercise blocks
            for start_pos in sorted(ex_start_positions):
                block = text[start_pos:]

                # Find numbered exercises (single fullwidth digit + ．)
                # Exclude section numbers like ８．３ and decimals like ０．５
                items = list(re.finditer(r'(?<![０-９．])([１-９])．(.*?)(?=(?<![０-９．])[１-９]．|$)', block, re.DOTALL))

                if not items:
                    continue

                # Determine section type
                first_50 = block[:50]
                if '习题' in first_50:
                    section = '习题'
                else:
                    section = '练习'

                for item in items:
                    num = item.group(1)
                    content = item.group(2).strip()
                    # Clean up - remove figure references and trailing page numbers
                    content = re.sub(r'（第[０-９]+题）', '', content)
                    content = re.sub(r'[０-９]{1,3}[１-９]', '', content)  # page numbers at end
                    content = re.sub(r'[Ａ-Ｚ]{1,6}', '', content)  # remove pure letter labels
                    content = content.strip()[:200]

                    if len(content) < 10:
                        continue

                    # Classify into knowledge points based on chapter and content
                    for kp_num in kp_nums:
                        kp = None
                        for k in KP_PATTERNS:
                            if k.startswith(kp_num + '.'):
                                kp = k
                                break
                        if not kp:
                            continue

                        # Check if content matches this KP
                        matched = False
                        for pat in KP_PATTERNS[kp]:
                            if re.search(pat, content, re.IGNORECASE):
                                matched = True
                                break

                        if matched:
                            exercises[kp].append({
                                "source": f"必修二·{chapter_name}·{section}",
                                "no": num,
                                "content": content.replace('\n', ' ').replace('|', '\\|'),
                                "type": "教材",
                            })

        doc.close()

    return exercises


def extract_exam_questions():
    """Extract exam questions from 高考拆题 markdown files."""
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
        "10. 共点问题": [r"三线共点", r"三条直线.*交于一点", r"线共点.*立体", r"视线共点"],
        "11. 在几何体中作线面交点和面面交线": [r"交线", r"线面交", r"面面交", r"线面.*交点", r"面面.*交点"],
        "12. 平面": [r"平面的基本性质", r"公理[1234].*平面", r"公理.*确定平面", r"不共线.*确定", r"平行线确定.*平面", r"两条相交.*确定.*平面"],
        "13. 直线与平面位置关系": [r"线面.*平行", r"线面.*垂直", r"直线与平面", r"线面角"],
        "14. 平面与平面位置关系": [r"面面.*平行", r"面面.*垂直", r"平面与平面", r"二面角"],
        "15. 直线与直线位置关系": [r"异面", r"线线.*角", r"线线平行", r"线线垂直", r"直线与直线"],
    }

    EXCLUDE = {
        "10. 共点问题": [r"导数", r"切线", r"椭圆", r"双曲线", r"抛物线", r"函数.*单调", r"极坐标", r"海岛", r"重差"],
        "12. 平面": [r"线性规划", r"可行域", r"二元一次不等式", r"目标函数"],
    }

    results = {k: [] for k in KEYWORDS}
    seen = set()

    for root, dirs, files in os.walk(EXAM_DIR):
        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    full_text = f.read()

                m = re.search(r"(.+?)第(.+?)题", fname)
                exam = m.group(1) if m else fname.replace(".md", "")
                qno = m.group(2) if m else "?"

                kd_match = re.search(r"\*\*考点标签：\*\*\s*(.+?)\n", full_text)
                zs_match = re.search(r"\*\*知识点标签：\*\*\s*(.+?)\n", full_text)
                kd = kd_match.group(1).strip() if kd_match else ""
                zs = zs_match.group(1).strip() if zs_match else ""

                title_match = re.search(r"##\s*题目\s*\n(.*?)(?:\n##|\Z)", full_text, re.DOTALL)
                question_text = title_match.group(1).strip() if title_match else ""

                for kp, patterns in KEYWORDS.items():
                    matched = False
                    for pat in patterns:
                        if re.search(pat, full_text, re.IGNORECASE):
                            matched = True
                            break
                    if matched:
                        if kp in EXCLUDE:
                            excluded = False
                            for ex_pat in EXCLUDE[kp]:
                                if re.search(ex_pat, full_text, re.IGNORECASE):
                                    excluded = True
                                    break
                            if excluded:
                                continue

                        key = (kp, exam, qno)
                        if key not in seen:
                            seen.add(key)
                            results[kp].append({
                                "source": f"{exam}第{qno}题",
                                "no": qno,
                                "content": kd[:80].replace('\n', ' ') if kd else "",
                                "question": question_text.replace('\n', ' ')[:200] if question_text else "",
                                "type": "高考真题",
                                "kd": kd,
                                "zs": zs,
                            })
            except Exception as e:
                pass

    return results


# Main
print("Extracting textbook exercises...")
textbook = extract_textbook_exercises()
for kp, items in textbook.items():
    if items:
        print(f"  {kp}: {len(items)} 题")

print("\nExtracting exam questions...")
exams = extract_exam_questions()

KP_ORDER = [
    "1. 球体的表面积和体积", "2. 柱体的表面积和体积",
    "3. 椎体的表面积和体积", "4. 台体的表面积和体积",
    "5. 椎体与台体棱长计算", "6. 内切球问题", "7. 外接球问题",
    "8. 球的截面问题", "9. 几何体的截面问题",
    "10. 共点问题", "11. 在几何体中作线面交点和面面交线",
    "12. 平面", "13. 直线与平面位置关系",
    "14. 平面与平面位置关系", "15. 直线与直线位置关系",
]

lines = []
lines.append("# 立体几何知识点 - 真题&教材题对照表\n")
lines.append("> 来源说明：**高考真题** = 2021-2025 年高考数学卷拆解训练 | **教材题** = 人教A版必修二第八章练习题/习题\n")

total_exam = 0
total_textbook = 0

for kp in KP_ORDER:
    exam_items = exams.get(kp, [])
    tb_items = textbook.get(kp, [])
    count = len(exam_items) + len(tb_items)
    total_exam += len(exam_items)
    total_textbook += len(tb_items)

    lines.append(f"\n## {kp}（{count} 题：高考真题 {len(exam_items)} / 教材题 {len(tb_items)}）\n")
    lines.append("| 序号 | 来源 | 高考真题题目 | 考点 | 知识点标签 |")
    lines.append("|------|------|-------------|------|------------|")

    idx = 0
    for item in exam_items:
        idx += 1
        src = f"📝 {item['source']}"
        question = item.get('question', '').replace('|', '\\|')[:150]
        content = item['content'].replace('|', '\\|')[:80]
        zs = item.get('zs', '').replace('|', '\\|')[:80]
        lines.append(f"| {idx} | {src} | {question} | {content} | {zs} |")

    for item in tb_items:
        idx += 1
        src = f"📖 {item['source']}"
        content = item['content'][:150]
        lines.append(f"| {idx} | {src} | | {content} | |")

    lines.append("")

lines.append(f"\n---\n")
lines.append(f"**总计：{total_exam + total_textbook} 题（高考真题 {total_exam} / 教材题 {total_textbook}）**\n")
lines.append(f"\n> 注：同一道题可能同时属于多个知识点，故各知识点数量之和 ≠ 总题数。\n")

with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"\n\nDone: {total_exam + total_textbook} total ({total_exam} exam, {total_textbook} textbook)")
print(f"Saved to: {OUTPUT}")
for kp in KP_ORDER:
    ec = len(exams.get(kp, []))
    tc = len(textbook.get(kp, []))
    print(f"  {kp}: {ec + tc} (高考 {ec} / 教材 {tc})")
