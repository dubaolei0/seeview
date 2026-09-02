import json, sys
sys.stdout.reconfigure(encoding='utf-8')

db_path = r'Z:\_共享文件夹\knowledge\高考题目\题库\master_database.jsonl'
needed = {
    'q_31895f887e', 'q_cf15c3953a', 'q_a378513eae', 'q_be5dddd8fe',
    'q_ab855d5c04', 'q_ea79394eb9', 'q_1324ddf93b', 'q_e65f8f96f2', 'q_80c9d47e0f',
}
with open(db_path, encoding='utf-8') as f:
    for line in f:
        q = json.loads(line)
        if q['id'] in needed:
            print(f"ID: {q['id']}")
            print(f"内容: {q['content']}")
            opts = q.get('options') or []
            for i, o in enumerate(opts):
                print(f"  {chr(65+i)}. {o}")
            print(f"答案: {q.get('answer','')}")
            print()
