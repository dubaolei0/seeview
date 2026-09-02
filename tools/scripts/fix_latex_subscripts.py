"""Fix _\text{Chinese} -> _{\text{Chinese}} in YAML body fields."""
import re
import glob
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

base = 'Z:/_共享文件夹/community/team/雪妹/统计课后/课后视频'
dirs = [
    f'{base}/基于样本统计量的决策判断/中间产物',
    f'{base}/分层随机抽样的总体均值和方差估计/中间产物',
    f'{base}/极差、方差和标准差/中间产物',
    f'{base}/利用频率分布表计算统计量/中间产物',
]

files = []
for d in dirs:
    files.extend(glob.glob(os.path.join(d, '*.yaml')))

# Build regex safely: use re.escape for the backslash character
BS = re.escape(chr(92))  # produces '\\\\' which regex engine matches as literal backslash
pattern = re.compile(r'_(?!\{)(' + BS + r'text\{[^}]+\})')

total_fixes = 0
fixed_files = []

for f in sorted(files):
    with open(f, 'r', encoding='utf-8') as fh:
        lines = fh.readlines()

    changed = False
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith('body:'):
            new_line = pattern.sub(r'_{\1}', line)
            if new_line != line:
                old_body = line.strip()
                new_body = new_line.strip()
                print(f'{os.path.basename(f)}:')
                print(f'  L{i+1}: {old_body}')
                print(f'     -> {new_body}')
                lines[i] = new_line
                changed = True
                total_fixes += 1

    if changed:
        with open(f, 'w', encoding='utf-8') as fh:
            fh.writelines(lines)
        fixed_files.append(os.path.basename(f))

print(f'\nTotal fixes: {total_fixes} in {len(fixed_files)} files')
