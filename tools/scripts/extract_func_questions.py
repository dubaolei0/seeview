#!/usr/bin/env python3
"""Extract function-related questions from master_database.jsonl and textbook_questions.jsonl."""
import json, sys, os

def extract_questions(filepath, label):
    func_questions = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except:
                continue
            chapter = d.get('knowledge_chapter') or ''
            kps = d.get('knowledge_points') or []
            is_func = False
            if '函数' in chapter:
                is_func = True
            keywords = ['函数','指数','对数','幂函数','奇偶','单调','零点','定义域','值域','图象','图像','复合','换底','对勾']
            if not is_func:
                for kp in kps:
                    for kw in keywords:
                        if kw in kp:
                            is_func = True
                            break
                    if is_func:
                        break
            if is_func:
                func_questions.append({
                    'source': label,
                    'year': d.get('source_year',''),
                    'exam': d.get('source_exam',''),
                    'qno': d.get('source_question_no',''),
                    'content': d.get('content',''),
                    'options': d.get('options'),
                    'answer': d.get('answer',''),
                    'qtype': d.get('type',''),
                    'kps': kps,
                    'fmt': d.get('question_format',''),
                })
    return func_questions

BASE = r'Z:\_共享文件夹'
master = extract_questions(os.path.join(BASE, 'knowledge','高考题目','题库','master_database.jsonl'), 'master')
textbook = extract_questions(os.path.join(BASE, 'knowledge','高考题目','题库','textbook_questions.jsonl'), 'textbook')

all_q = master + textbook
print(f"Total function-related questions: {len(all_q)}")
print(f"  master: {len(master)}, textbook: {len(textbook)}")

from collections import Counter
kp_counter = Counter()
for q in all_q:
    for kp in q['kps']:
        kp_counter[kp] += 1

for kp, count in kp_counter.most_common(100):
    print(f"  [{count}] {kp}")

with open(os.path.join(BASE, 'tools','scripts','func_questions.json'), 'w', encoding='utf-8') as f:
    json.dump(all_q, f, ensure_ascii=False, indent=2)
print(f"\nSaved {len(all_q)} questions.")
