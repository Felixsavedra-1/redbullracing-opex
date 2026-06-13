#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "f1opex_dashboard.html"
OUT_GIF = ROOT / "dashboard.gif"

VIEW_W = 1000
VIEW_H = 560
SCALE = 2
FPS = 12
OUT_W = 720
MAX_COLORS = 96

TOP_HOLD_FRAMES = 24
SCROLL_FRAMES = 120
BOTTOM_HOLD_FRAMES = 18


def _ease(p: float) -> float:
    return 3 * p * p - 2 * p * p * p


def capture_frames(frame_dir: Path) -> int:
    if not HTML.exists():
        sys.exit(f"Dashboard not found: {HTML}\nRun `python3 main.py` first.")

    idx = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": VIEW_W, "height": VIEW_H},
            device_scale_factor=SCALE,
        )
        page.goto(HTML.as_uri(), wait_until="networkidle")
        # Freeze the looping background fx so frames compress; the KPI count-up
        # and entrance reveals are not in this selector list and still play.
        page.add_style_tag(
            content=(
                ".fx .scan, .fx .pulse, .banner .title::after, "
                ".live .dot { animation: none !important; }"
            )
        )
        page.wait_for_timeout(400)

        def shot() -> None:
            nonlocal idx
            page.screenshot(path=str(frame_dir / f"frame_{idx:04d}.png"))
            idx += 1

        page.evaluate("window.scrollTo(0, 0)")
        for _ in range(TOP_HOLD_FRAMES):
            shot()
            page.wait_for_timeout(1000 // FPS)

        max_scroll = page.evaluate("Math.max(0, document.body.scrollHeight - window.innerHeight)")
        for i in range(SCROLL_FRAMES):
            p = (i + 1) / SCROLL_FRAMES
            y = round(max_scroll * _ease(p))
            page.evaluate(f"window.scrollTo(0, {y})")
            page.wait_for_timeout(1000 // FPS)
            shot()

        for _ in range(BOTTOM_HOLD_FRAMES):
            shot()
            page.wait_for_timeout(1000 // FPS)

        browser.close()
    return idx


def build_gif(frame_dir: Path) -> None:
    palette = frame_dir / "palette.png"
    vf = f"fps={FPS},scale={OUT_W}:-1:flags=lanczos"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            str(frame_dir / "frame_%04d.png"),
            "-vf",
            f"{vf},palettegen=max_colors={MAX_COLORS}:stats_mode=diff",
            str(palette),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            str(frame_dir / "frame_%04d.png"),
            "-i",
            str(palette),
            "-lavfi",
            f"{vf}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3",
            str(OUT_GIF),
        ],
        check=True,
        capture_output=True,
    )


def main() -> None:
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH.")
    frame_dir = Path(tempfile.mkdtemp(prefix="opex_gif_"))
    try:
        n = capture_frames(frame_dir)
        print(f"Captured {n} frames → assembling GIF…")
        build_gif(frame_dir)
        size_mb = OUT_GIF.stat().st_size / 1e6
        print(f"Wrote {OUT_GIF.name} ({size_mb:.1f} MB)")
    finally:
        shutil.rmtree(frame_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
