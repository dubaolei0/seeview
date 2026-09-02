import fitz, json, sys
sys.stdout.reconfigure(encoding='utf-8')

# ---- 1. 从数据库读出需要的考题 ----
db_path = r'Z:\_共享文件夹\knowledge\高考题目\题库\master_database.jsonl'
needed_ids = {
    'q_31895f887e', 'q_cf15c3953a', 'q_a378513eae', 'q_be5dddd8fe',
    'q_ab855d5c04', 'q_ea79394eb9', 'q_1324ddf93b',
    'q_e65f8f96f2', 'q_80c9d47e0f',
}
questions = {}
with open(db_path, encoding='utf-8') as f:
    for line in f:
        q = json.loads(line)
        if q['id'] in needed_ids:
            questions[q['id']] = q

def fmt_q(q):
    """格式化题目为简洁 markdown"""
    content = q['content'].strip()
    opts = q.get('options') or []
    if opts:
        content += '\n' + '  '.join(f'{chr(65+i)}. {o}' for i, o in enumerate(opts))
    ans = q.get('answer', '')
    return f"{content}\n\n**答案：{ans}**"

# ---- 2. 从教材 PDF 提取文字 ----
def get_pdf_text(path):
    doc = fitz.open(path)
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return pages

ch21 = get_pdf_text(r'Z:\_共享文件夹\knowledge\教材\必修第一册\2_1_等式性质与不等式性质.pdf')
ch22 = get_pdf_text(r'Z:\_共享文件夹\knowledge\教材\必修第一册\2_2_基本不等式.pdf')

all_text_21 = '\n'.join(ch21)
all_text_22 = '\n'.join(ch22)

print("=== 2_1 全文 ===")
print(all_text_21)
print("\n=== 2_2 全文 ===")
print(all_text_22)
