import json, sys
sys.stdout.reconfigure(encoding='utf-8')
from collections import Counter
with open(r'Z:\_共享文件夹\knowledge\高考题目\题库\textbook_questions.jsonl', encoding='utf-8') as f:
    qs = [json.loads(l) for l in f if l.strip()]
exams = Counter(q.get('source_exam') for q in qs)
for k, v in sorted(exams.items(), key=lambda x: -x[1])[:25]:
    print(f'{v:4d}  {k}')
