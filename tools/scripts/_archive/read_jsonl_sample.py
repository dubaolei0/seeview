import json, sys
sys.stdout.reconfigure(encoding='utf-8')
path = r'Z:\_共享文件夹\knowledge\高考题目\题库\textbook_questions.jsonl'
with open(path, encoding='utf-8') as f:
    lines = [l.strip() for l in f if l.strip()]
print(f'总条数: {len(lines)}')
for i, line in enumerate(lines[:3]):
    q = json.loads(line)
    print(f'--- 第{i+1}条 ---')
    print(json.dumps(q, ensure_ascii=False, indent=2))
    print()
# Also print all keys present across all records
all_keys = set()
for line in lines:
    all_keys.update(json.loads(line).keys())
print('全部字段:', sorted(all_keys))
