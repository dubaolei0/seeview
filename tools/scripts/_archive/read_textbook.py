import fitz, sys
sys.stdout.reconfigure(encoding='utf-8')

# Read 不等式 chapters from A版必修第一册
for pdf_name, label in [
    (r'Z:\_共享文件夹\knowledge\教材\必修第一册\2_1_等式性质与不等式性质.pdf', '2_1'),
    (r'Z:\_共享文件夹\knowledge\教材\必修第一册\2_2_基本不等式.pdf', '2_2'),
]:
    doc = fitz.open(pdf_name)
    print(f'\n{"="*60}')
    print(f'文件: {label}  共 {doc.page_count} 页')
    print('='*60)
    for i, page in enumerate(doc):
        text = page.get_text()
        print(f'\n--- 第{i+1}页 ---')
        print(text[:2000])
    doc.close()
