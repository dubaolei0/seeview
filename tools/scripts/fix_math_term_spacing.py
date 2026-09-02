#!/usr/bin/env python3
"""Fix TTS: add spaces between adjacent English math terms."""
import re
import sys
from pathlib import Path

def fix_say_fields(text):
    """Add spaces between adjacent English math terms in say fields."""
    # Pattern: English math term + Chinese operator + English math term
    # Examples: sineA乘cosineA, cosineB加sineB
    # Should become: sineA 乘 cosineA, cosineB 加 sineB

    # Common English math terms
    terms = r'(?:sine|cosine|tangent)'

    # Pattern: (term+letter) + (Chinese operator) + (term+letter)
    # Add spaces around the Chinese operator
    pattern = rf'({terms}[A-Z])([一-龥]+)({terms}[A-Z])'

    def replacer(match):
        term1 = match.group(1)
        operator = match.group(2)
        term2 = match.group(3)
        return f'{term1} {operator} {term2}'

    # Apply the replacement multiple times to handle chained expressions
    for _ in range(3):  # Up to 3 passes to handle A乘B加C
        text = re.sub(pattern, replacer, text)

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
