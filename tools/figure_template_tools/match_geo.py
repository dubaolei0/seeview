# -*- coding: utf-8 -*-
"""圆 + 圆锥曲线模板 → 真题快速匹配"""
import json
from pathlib import Path

MAPPING = {
    'circle': ['圆', '半径', '圆心', '弦', '弧', '直径', '圆周角'],
    'two-circles': ['两圆', '圆与圆', '位置关系', '外离', '外切', '内切', '同心圆'],
    'incircle': ['内切圆', '内心', '三角形的内切', '三角形内切'],
    'circle-inscribed-triangle': ['外接圆', '圆内接三角形', '外心'],
    'cyclic-quadrilateral': ['内接四边形', '圆内接', '对角互补'],
    'power-point': ['圆幂定理', '切割线', '相交弦', '割线'],
    'circle-tangent': ['圆的切线', '切线长', '切点', '两切线'],
    'circle-perp-chord': ['垂径定理', '垂直于弦', '弦的垂直'],
    'regular-polygon-circle': ['正多边形', '正n边形', '正六边形', '内接正'],
    'ellipse': ['椭圆', '焦点', '长轴', '短轴', '离心率'],
    'hyperbola': ['双曲线', '渐近线', '实轴', '虚轴', '离心率'],
    'parabola': ['抛物线', '准线', '焦点', '焦准距'],
}

idx = json.loads(Path(r'G:\爱学\高考拆题\index.json').read_text(encoding='utf-8'))
print(f"index.json 共 {len(idx)} 题\n")

results = {}
for tpl_id, kws in MAPPING.items():
    hits = []
    for q in idx:
        blob = (q.get('kaodian', '') + ' ' + q.get('zhishi', '') + ' ' + q.get('kaodianyao', ''))
        score = sum(1 for kw in kws if kw in blob)
        if score >= 1:
            hits.append((q, score))
    hits.sort(key=lambda x: -x[1])
    results[tpl_id] = hits[:5]  # top 5
    print(f"  {tpl_id:<30s} → {len(hits)} 命中  top3: ", end="")
    for h in hits[:3]:
        fname = h[0].get('file', '').split('\\')[-1][:30]
        print(f"[{h[1]}分]{fname} ", end="")
    print()

# 存 JSON
Path(r"G:\爱学\图库对应测试题整理").mkdir(parents=True, exist_ok=True)
with open(r"G:\爱学\图库对应测试题整理\几何模板→真题候选.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2, default=str)
print(f"\n候选列表已存: 几何模板→真题候选.json")
