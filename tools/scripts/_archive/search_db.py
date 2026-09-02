import json, sys
sys.stdout.reconfigure(encoding='utf-8')

db_path = r'Z:\_共享文件夹\knowledge\高考题目\题库\master_database.jsonl'

targets = [
    {'year': 2024, 'exam_kw': '全国甲卷（理科）', 'qno': 23},
    {'year': 2025, 'exam_kw': '北京卷', 'qno': 6},
    {'year': 2022, 'exam_kw': '全国甲卷（文科）', 'qno': 14},
    {'year': 2022, 'exam_kw': '上海卷', 'qno': 14},
    {'year': 2021, 'exam_kw': '新高考I卷', 'qno': 5},
    {'year': 2021, 'exam_kw': '天津卷', 'qno': 13},
]

results = {}
with open(db_path, encoding='utf-8') as f:
    for line in f:
        q = json.loads(line)
        for t in targets:
            if (q.get('source_year') == t['year'] and
                t['exam_kw'] in q.get('source_exam','') and
                q.get('source_question_no') == t['qno']):
                key = f"{t['year']}_{t['exam_kw'][:4]}_q{t['qno']}"
                if key not in results:
                    results[key] = []
                results[key].append({
                    'id': q['id'],
                    'type': q['type'],
                    'depth': q['depth_level'],
                    'sibling': q['sibling_order'],
                    'parent': q.get('parent_question_id'),
                    'content': q['content'][:100],
                    'answer': q.get('answer',''),
                })

for k, v in results.items():
    print(f'=== {k} ({len(v)} entries) ===')
    for item in v:
        print(f'  [{item["type"]}] depth={item["depth"]} sib={item["sibling"]} id={item["id"]} parent={item["parent"]}')
        print(f'    {item["content"]}')
        print(f'    答案: {item["answer"]}')
