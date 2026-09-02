#!/usr/bin/env python3
"""Match knowledge points to relevant questions from the extracted database."""
import json, os, re

BASE = r'Z:\_共享文件夹'
FUNC_DIR = os.path.join(BASE, 'knowledge', '函数')

# Load extracted questions
with open(os.path.join(BASE, 'tools', 'scripts', 'func_questions.json'), 'r', encoding='utf-8') as f:
    all_q = json.load(f)

print(f"Loaded {len(all_q)} function questions")

# Define keyword groups for each knowledge point file
# These are keyword groups where ALL keywords must appear (or most)
# For each knowledge point, we look for questions containing relevant keywords
topic_keywords = {
    '零点存在定理': ['零点','存在','定理'],
    '换底公式': ['换底','公式','对数'],
    '指数+二次函数': ['指数','二次','换元'],
    '根式函数+二次函数': ['根式','二次','换元'],
    '指对函数图像关系': ['指数','对数','图像','对称'],
    '对勾函数及其图像': ['对勾','x+1/x','基本不等式'],
    '已知函数解析式求定义域': ['定义域','解析式'],
    '函数定义域的概念': ['定义域','概念','三要素'],
    '指对比大小': ['指数','对数','比大小','比较'],
    '指数比大小': ['指数','比大小','比较'],
    '复合函数定义域': ['复合函数','定义域'],
    '复合函数的分步思想': ['复合函数','内层','外层'],
    '复合函数的奇偶性': ['复合函数','奇偶性'],
    '复合函数的概念与辨识': ['复合函数','概念','分解'],
    '求复合函数解析式': ['复合函数','解析式','代入'],
    '单调性的概念': ['单调性','定义','递增','递减'],
    '和函数的单调性': ['和函数','单调性','f+g'],
    '和函数的奇偶性': ['和函数','奇偶性','f+g'],
    '乘积函数的奇偶性': ['乘积','奇偶性','f*g'],
    '用奇偶性求表达式': ['奇偶性','表达式','区间'],
    '结合奇偶性的ff型函数值不等式': ['奇偶性','不等式','f('],
    '函数与方程': ['函数','方程','零点'],
    '函数图像变换方法': ['图像变换','平移','对称','伸缩'],
    '函数图象的对称性与图象变换的关系': ['对称性','图象变换','关系'],
    'fa型函数值不等式': ['函数值','不等式','常数'],
    'ff型函数值不等式': ['f(','不等式','单调性'],
    '二次函数在给定区间的值域': ['二次函数','值域','区间'],
    '分拆判断函数零点': ['零点','交点','图象'],
    '含参零点问题': ['含参','零点','参数'],
    '函数值域的概念': ['值域','概念'],
    '用定义判断奇偶性': ['定义','判断','奇偶性'],
    '用定义判断单调性': ['定义','判断','单调性'],
    '用奇偶性判断单调性': ['奇偶性','判断','单调性'],
    '函数的概念与判断': ['函数','概念','判断'],
    '函数图象的对称性与周期性的关系': ['对称性','周期性','关系'],
    '函数奇偶性的概念': ['奇偶性','概念','定义'],
    '分段函数单调性': ['分段函数','单调性'],
    '分段函数的分段思想': ['分段函数','分段','思想'],
    '分段函数的概念与图象': ['分段函数','概念','图象'],
    '复合函数的单调性': ['复合函数','单调性'],
    '对数函数图像与性质': ['对数函数','图像','性质'],
    '对数比大小': ['对数','比大小','比较'],
    '幂函数的概念': ['幂函数','概念'],
    '指数函数图像与性质': ['指数函数','图像','性质'],
    '指数计算应用题': ['指数','计算','应用'],
    '函数与不等式': ['函数','不等式'],
    '对数计算应用题': ['对数','计算','应用'],
    '指数与对数关系': ['指数','对数','关系','互逆'],
}

# Score each question against each topic
topic_matches = {topic: [] for topic in topic_keywords}

for q in all_q:
    text = json.dumps(q, ensure_ascii=False).lower()
    for topic, keywords in topic_keywords.items():
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score >= max(1, len(keywords) - 2):  # At least some keyword matches
            topic_matches[topic].append((score, q))

# For each topic, get top matches
for topic in topic_keywords:
    matches = sorted(topic_matches[topic], key=lambda x: -x[0])
    topic_matches[topic] = matches[:15]  # Keep top 15

# Output results
output = {}
for topic, matches in topic_matches.items():
    output[topic] = []
    for score, q in matches:
        output[topic].append({
            'score': score,
            'id': q.get('id', ''),
            'content': q['content'][:300],
            'year': q.get('year', ''),
            'exam': q.get('exam', ''),
            'qno': q.get('qno', ''),
            'source': q.get('source', ''),
            'options': str(q.get('options',''))[:200] if q.get('options') else '',
            'answer': q.get('answer', ''),
            'kps': q.get('kps', []),
        })
    print(f"\n=== {topic} ({len(matches)} matches) ===")
    for i, m in enumerate(output[topic][:5]):
        print(f"  [{m['score']}] {m['year']}{m['exam']}第{m['qno']}题 | {m['content'][:100]}")

with open(os.path.join(BASE, 'tools', 'scripts', 'topic_matches.json'), 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\nSaved topic matches.")
