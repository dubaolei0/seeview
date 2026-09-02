#!/usr/bin/env python3
"""Find remaining letter+i in math mode that should be \\mathrm{i}."""
import re
import sys
from pathlib import Path

def check_file(filepath):
    """Check a file for letter+i patterns in math mode."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    issues = []
    # Find all $...$ segments
    for match in re.finditer(r'\$([^$]+)\$', content):
        math_content = match.group(1)
        # Check if there's a letter followed by i (not part of identifier)
        # Pattern: letter + i + (non-letter or end)
        if re.search(r'[a-zA-Z]i(?![a-zA-Z])', math_content):
            # But exclude if it's already \mathrm{i}
            if '\\mathrm{i}' not in math_content or re.search(r'[a-zA-Z]i(?![a-zA-Z])(?!.*\\mathrm{i})', math_content):
                issues.append(math_content)

    return issues

def main():
    base_dir = Path(r'Z:/_共享文件夹/community/team/PP/微课/虚数单位i和复数的概念/讲题')

    for yaml_file in sorted(base_dir.glob('*.yaml')):
        issues = check_file(yaml_file)
        if issues:
            print(f'{yaml_file.name}:')
            for issue in issues:
                print(f'  {issue}')

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
