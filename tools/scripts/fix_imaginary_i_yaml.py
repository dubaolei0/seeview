#!/usr/bin/env python3
r"""Fix \mathrm{i} -> \\mathrm{i} in YAML double-quoted strings."""
import sys
from pathlib import Path

def process_file(filepath):
    """Fix single backslash to double backslash in YAML."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace \mathrm{i} with \\mathrm{i} (for YAML double-quoted strings)
    new_content = content.replace('\\mathrm{i}', '\\\\mathrm{i}')

    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True
    return False

def main():
    base_dir = Path(r'Z:/_共享文件夹/community/team/PP/微课/虚数单位i和复数的概念/讲题')

    modified = []
    for yaml_file in base_dir.glob('*.yaml'):
        if process_file(yaml_file):
            modified.append(yaml_file.name)
            print(f'Fixed: {yaml_file.name}')

    print(f'\nTotal: {len(modified)} files fixed')

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
