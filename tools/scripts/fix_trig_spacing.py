#!/usr/bin/env python3
"""Fix TTS: add space between sine/cosine/tangent and variable letter."""
import re
import sys
from pathlib import Path

def fix_say_fields(text):
    """Add space between sine/cosine/tangent and variable letter in say fields."""
    # Pattern: sineA -> sine A, cosineB -> cosine B, tangentC -> tangent C
    # But NOT in show.body (LaTeX), only in say fields

    # Replace sineX -> sine X
    text = re.sub(r'sine([A-Z])', r'sine \1', text)

    # Replace cosineX -> cosine X
    text = re.sub(r'cosine([A-Z])', r'cosine \1', text)

    # Replace tangentX -> tangent X
    text = re.sub(r'tangent([A-Z])', r'tangent \1', text)

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
