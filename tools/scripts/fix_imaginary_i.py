#!/usr/bin/env python3
r"""Fix imaginary unit i -> \\mathrm{i} in YAML double-quoted strings."""
import re
import sys
from pathlib import Path

def replace_imaginary_i_in_math(text):
    """Replace imaginary unit i with \\mathrm{i} within $...$ math mode in YAML."""

    def process_math_segment(math_content):
        """Process math content inside $...$"""
        # Replace i that's the imaginary unit (not part of a command/identifier)
        # Pattern: not preceded by letter or backslash, not followed by letter
        result = re.sub(r'(?<![a-zA-Z\\])i(?![a-zA-Z])', r'\\\\mathrm{i}', math_content)
        return result

    # Split text into math and non-math segments
    parts = re.split(r'(\$[^$]+\$)', text)

    result = []
    for part in parts:
        if part.startswith('$') and part.endswith('$'):
            math_content = part[1:-1]
            processed = process_math_segment(math_content)
            result.append(f'${processed}$')
        else:
            result.append(part)

    return ''.join(result)

def process_file(filepath):
    """Process a single YAML file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    new_content = replace_imaginary_i_in_math(content)

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
            print(f'Modified: {yaml_file.name}')

    print(f'\nTotal: {len(modified)} files modified')

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
