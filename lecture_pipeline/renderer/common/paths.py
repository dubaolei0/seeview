"""
项目根定位（部署布局自适应）。

历史上 src/（tts_manager、clipped_plot_manager 等老代码）的位置随部署而变：
  - 开发仓库：src/ 与 lecture_pipeline/ 同级（.../question/src）
  - NAS 部署：src/ 被塞进 lecture_pipeline/ 内部（.../tools/lecture_pipeline/src）

以前各文件用硬编码的 parents[3] / parents[2] 适配，导致两份副本无法干净对拷。
本函数从自身位置向上寻找含 src/ 的目录，两种布局都能命中，从而消除该差异。
"""

from __future__ import annotations

from pathlib import Path


def find_project_root() -> Path:
    """向上寻找第一个包含 src/ 子目录的目录并返回；找不到则回退到 lecture_pipeline 包根。"""
    here = Path(__file__).resolve()
    for p in here.parents:
        if (p / "src").is_dir():
            return p
    # 兜底：renderer/common/paths.py 的 parents[2] = lecture_pipeline 包根
    return here.parents[2]
