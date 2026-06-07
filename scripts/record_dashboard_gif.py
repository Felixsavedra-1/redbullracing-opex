#!/usr/bin/env python3
"""Record the README hero GIF: a scroll-tour of the full HTML dashboard.

Loads the self-contained ``f1opex_dashboard.html`` in headless Chromium, holds at
the top while the KPI count-up plays, then smoothly scrolls through every section
(gauge, charts, variance ranking, savings cards) capturing one frame per step.
The PNG sequence is assembled into ``dashboard.gif`` with ffmpeg using a two-pass
palette for size/quality.

Run with the system Python that has Playwright + Chromium installed:

    python3 scripts/record_dashboard_gif.py

Requires: playwright (+ chromium browser), ffmpeg on PATH.
"""

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

# Capture / output knobs
VIEW_W = 1000  # capture viewport width (matches the original framing)
VIEW_H = 560  # capture viewport height
SCALE = 2  # device scale factor for crisp text
FPS = 12  # output GIF frame rate
OUT_W = 720  # final GIF width (scaled down from capture)
MAX_COLORS = 128  # palette size cap (smaller file)

TOP_HOLD_FRAMES = 18  # ~1.5s on the cockpit while KPIs count up
SCROLL_FRAMES = 60  # ~5.0s scrolling through the dashboard
BOTTOM_HOLD_FRAMES = 12  # ~1.0s resting on the savings cards


def _ease(p: float) -> float:
    """Ease-in-out so the scroll accelerates then settles."""
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
        # Freeze the looping *background* fx (scanline sweep, glow pulse) so the
        # GIF compresses between frames — without touching the KPI count-up or the
        # entrance reveals, which are not in this selector list.
        page.add_style_tag(
            content=(
                ".fx .scan, .fx .pulse, .banner .title::after, "
                ".live .dot { animation: none !important; }"
            )
        )
        # Let Plotly finish its first paint and the CSS reveals settle.
        page.wait_for_timeout(400)

        def shot() -> None:
            nonlocal idx
            page.screenshot(path=str(frame_dir / f"frame_{idx:04d}.png"))
            idx += 1

        # 1) Hold at the top — the 1s KPI count-up + entrance reveals.
        page.evaluate("window.scrollTo(0, 0)")
        for _ in range(TOP_HOLD_FRAMES):
            shot()
            page.wait_for_timeout(1000 // FPS)

        # 2) Scroll tour from top to bottom, eased.
        max_scroll = page.evaluate("Math.max(0, document.body.scrollHeight - window.innerHeight)")
        for i in range(SCROLL_FRAMES):
            p = (i + 1) / SCROLL_FRAMES
            y = round(max_scroll * _ease(p))
            page.evaluate(f"window.scrollTo(0, {y})")
            page.wait_for_timeout(1000 // FPS)
            shot()

        # 3) Rest on the savings cards at the bottom.
        for _ in range(BOTTOM_HOLD_FRAMES):
            shot()
            page.wait_for_timeout(1000 // FPS)

        browser.close()
    return idx


def build_gif(frame_dir: Path) -> None:
    palette = frame_dir / "palette.png"
    vf = f"fps={FPS},scale={OUT_W}:-1:flags=lanczos"
    # Pass 1: generate an optimized palette from the frames.
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
    # Pass 2: apply the palette with light dithering.
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
