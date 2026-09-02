import fitz, sys, re
sys.stdout.reconfigure(encoding='utf-8')

PATH = r'D:\_共享文件夹\knowledge\教材\必修第二册\8_3_简单几何体的表面积与体积.pdf'
doc = fitz.open(PATH)

# Page-by-page extraction with better heuristics
for page_idx, page in enumerate(doc):
    text = page.get_text()
    text = text.replace('', '-')  # Fix encoding artifact for dash

    # Look for exercise block markers
    # 1. 练习/习题 sections typically start after ጷ˸ or a clear heading
    # 2. Exercise numbers are standalone fullwidth digits followed by ．

    # Find ᛸ˸ marker (exercise heading)
    ex_start = text.find('ጷ˸')
    if ex_start < 0:
        ex_start = text.find('习题')
        if ex_start < 0:
            continue

    ex_block = text[ex_start:]

    # Extract exercise items: match lines starting with fullwidth digit + ．
    # but NOT section numbers like ８．３ or decimals like ０．５
    lines = ex_block.split('\n')
    exercises = []
    current_num = None
    current_content = []

    for line in lines:
        # Check if line starts with a standalone exercise number
        m = re.match(r'^\s*([０-９])．(.*)', line)
        if m:
            # Save previous exercise
            if current_num:
                exercises.append((current_num, ' '.join(current_content).strip()))
            current_num = m.group(1)
            current_content = [m.group(2).strip()]
        else:
            if current_num:
                current_content.append(line.strip())

    if current_num:
        exercises.append((current_num, ' '.join(current_content).strip()))

    # Determine section type
    if '习题' in ex_block[:50]:
        section = '习题'
    else:
        section = '练习'

    if exercises:
        print(f"\n=== Page {page_idx+1} [{section}] - {len(exercises)} exercises ===")
        for num, content in exercises:
            clean = re.sub(r'\s+', ' ', content)[:200]
            print(f"  第{num}题: {clean}")
