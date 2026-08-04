"""common · 复用老代码的桥接模块"""

from .tex_template import get_chinese_template
from .audio_timeline import build_audio_timeline

__all__ = [
    "get_chinese_template",
    "build_audio_timeline",
]
