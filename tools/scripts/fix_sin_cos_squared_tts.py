#!/usr/bin/env python3
"""Fix TTS pronunciation: sine平方A -> sineA的平方, cosine平方A -> cosineA的平方."""
import re
import sys
from pathlib import Path

def fix_say_fields(text):
    """Fix pronunciation of sin²/cos² in say fields."""
    # Pattern: sine平方X or cosine平方X (where X is a letter like A, B, C)
    # Replace with: sineX的平方 or cosineX的平方

    # Fix sine平方X -> sineX的平方
    text = re.sub(r'sine平方([A-Z])', r'sine\1的平方', text)

    # Fix cosine平方X -> cosineX的平方
    text = re.sub(r'cosine平方([A-Z])', r'cosine\1的平方', text)

    return text

def process_file(filepath):
    """Process a single YAML file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    new_content = fix_say_fields(content)

    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True
    return False

def main():
    base_dir = Path(r'Z:/_共享文件夹/community/team/PP/微课/二倍角公式化简求角/讲题')

    modified = []
    for yaml_file in base_dir.glob('*.yaml'):
        if process_file(yaml_file):
            modified.append(yaml_file.name)
            print(f'Fixed: {yaml_file.name}')

    print(f'\nTotal: {len(modified)} files fixed')

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
