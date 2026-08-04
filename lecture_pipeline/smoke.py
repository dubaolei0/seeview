"""渲染回归冒烟 —— 一键把样例 yaml 全渲一遍，断言成功，再抽关键帧拼成对照表。

用途：改了 renderer/ 任何东西后，跑一次就知道有没有把哪个布局/样例渲挂或渲歪。
不替代肉眼看片，但能把"逐个手动渲染+抓帧"的来回压成一条命令。

用法（在 tools/lecture_pipeline/ 下，用项目 venv 的 python）：
    python smoke.py                      # 渲 samples/yaml样例/*.yaml
    python smoke.py path/a.yaml b.yaml   # 只渲指定文件
    python smoke.py --quality medium     # 默认 low

产物：smoke_out/<yaml名>.mp4 + smoke_out/contact_sheet.png（每行一个样例：封面/讲解/结尾三帧）
退出码：全部成功=0，有失败=1。
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "smoke_out"


def _find(exe: str, *fallbacks: str) -> str:
    p = shutil.which(exe)
    if p:
        return p
    for fb in fallbacks:
        if Path(fb).exists():
            return fb
    return exe  # 交给系统，找不到时报错更直观


FFMPEG = _find("ffmpeg", r"F:/ffmpeg/bin/ffmpeg.exe")
FFPROBE = _find("ffprobe", r"F:/ffmpeg/bin/ffprobe.exe")


def _duration(mp4: Path) -> float:
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(mp4)],
            capture_output=True, text=True, timeout=60,
        )
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def _grab(mp4: Path, t: float, dst: Path) -> bool:
    try:
        subprocess.run(
            [FFMPEG, "-y", "-loglevel", "error", "-ss", f"{t:.2f}",
             "-i", str(mp4), "-frames:v", "1", str(dst)],
            capture_output=True, timeout=120,
        )
        return dst.exists()
    except Exception:
        return False


def render_one(yaml_path: Path, quality: str) -> tuple[bool, str]:
    """渲一个 yaml，返回 (是否成功, mp4 路径或错误信息)。"""
    proc = subprocess.run(
        [sys.executable, "-m", "renderer.render", str(yaml_path),
         "--quality", quality, "--no-audio"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=900,
    )
    tail = (proc.stdout or "")[-2000:] + (proc.stderr or "")[-1000:]
    if "✓ 视频渲染完成" not in (proc.stdout or ""):
        return False, tail.strip()[-600:]
    # 推断 mp4 位置：renderer 输出在 media/videos/<res>/<yaml名>.mp4
    sub = {"low": "480p15", "medium": "720p30", "high": "1080p60"}.get(quality, "480p15")
    mp4 = ROOT / "media" / "videos" / sub / (yaml_path.stem + ".mp4")
    return (mp4.exists(), str(mp4) if mp4.exists() else "mp4 未找到")


def contact_sheet(rows: list[tuple[str, list[Path]]], dst: Path) -> bool:
    """rows = [(标签, [帧png...]), ...]，每行三帧横排，纵向叠成对照表。需要 Pillow。"""
    try:
        from PIL import Image, ImageDraw
    except Exception as e:
        print(f"[smoke] 无 Pillow，跳过对照表：{e}")
        return False
    thumb_w, label_h, pad = 360, 26, 6
    cells = [imgs for _, imgs in rows]
    ncol = max((len(c) for c in cells), default=1)
    # 先算缩略图高度（按第一张可用图的宽高比）
    ratio = 9 / 16
    row_imgs = []
    for label, frames in rows:
        thumbs = []
        for fr in frames[:ncol]:
            try:
                im = Image.open(fr).convert("RGB")
                ratio = im.height / im.width
                im = im.resize((thumb_w, int(thumb_w * ratio)))
            except Exception:
                im = Image.new("RGB", (thumb_w, int(thumb_w * ratio)), (230, 230, 230))
            thumbs.append(im)
        row_imgs.append((label, thumbs))
    thumb_h = int(thumb_w * ratio)
    row_h = thumb_h + label_h
    W = ncol * thumb_w + (ncol + 1) * pad
    H = len(row_imgs) * (row_h + pad) + pad
    sheet = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    y = pad
    for label, thumbs in row_imgs:
        draw.text((pad, y), label, fill=(0, 0, 0))
        x = pad
        for im in thumbs:
            sheet.paste(im, (x, y + label_h))
            x += thumb_w + pad
        y += row_h + pad
    sheet.save(dst)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("yamls", nargs="*", help="指定 yaml；缺省渲 samples/yaml样例/*.yaml")
    ap.add_argument("--quality", default="low", choices=["low", "medium", "high"])
    args = ap.parse_args()

    if args.yamls:
        targets = [Path(p) for p in args.yamls]
    else:
        targets = sorted(Path(p) for p in glob.glob(str(ROOT / "samples" / "yaml样例" / "*.yaml")))
    if not targets:
        print("没找到要渲的 yaml")
        return 1

    OUT.mkdir(exist_ok=True)
    results, rows = [], []
    for y in targets:
        print(f"渲染 {y.name} …", flush=True)
        ok, info = render_one(y, args.quality)
        results.append((y.name, ok, info))
        if not ok:
            print(f"  ✗ 失败：{info}")
            rows.append((f"{y.name}  [失败]", []))
            continue
        print(f"  ✓ {info}")
        mp4 = Path(info)
        dur = _duration(mp4)
        frames = []
        for tag, t in (("cover", 3.0), ("teach", dur * 0.45), ("end", max(dur - 0.3, 0))):
            f = OUT / f"{y.stem}_{tag}.png"
            if _grab(mp4, t, f):
                frames.append(f)
        rows.append((y.name, frames))

    sheet = OUT / "contact_sheet.png"
    if contact_sheet(rows, sheet):
        print(f"\n对照表：{sheet}")

    npass = sum(1 for _, ok, _ in results if ok)
    print(f"\n=== 冒烟结果：{npass}/{len(results)} 通过 ===")
    for name, ok, info in results:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  → {info[:200]}"))
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
