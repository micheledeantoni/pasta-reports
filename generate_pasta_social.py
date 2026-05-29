#!/usr/bin/env python3
"""
Generate images/pasta-social.png for the PASTA home page OG / Twitter card.

Uses Chrome headless to screenshot tools/social_export/pasta-home-banner.html
at 1200×630px (standard social card dimensions).

Usage:
    python generate_pasta_social.py
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT   = Path(__file__).resolve().parent
BANNER = ROOT / "tools" / "social_export" / "pasta-home-banner.html"
OUTPUT = ROOT / "images" / "pasta-social.png"


def find_chrome() -> str | None:
    candidates = [
        shutil.which("google-chrome"),
        shutil.which("chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def main() -> None:
    if not BANNER.exists():
        raise SystemExit(f"Banner template not found: {BANNER}")

    chrome = find_chrome()
    if not chrome:
        raise SystemExit(
            "Chrome / Chromium not found. Install Google Chrome and retry."
        )
    print(f"Chrome: {chrome}")

    url = BANNER.as_uri()   # file:// — no server needed for static HTML

    with tempfile.TemporaryDirectory(prefix="pasta-social-chrome-") as udd:
        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--disable-background-networking",
            "--no-first-run",
            "--hide-scrollbars",
            "--default-background-color=00000000",
            f"--user-data-dir={udd}",
            "--window-size=1200,630",
            "--force-device-scale-factor=1",
            "--virtual-time-budget=3000",
            f"--screenshot={OUTPUT}",
            url,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=12)
        except subprocess.TimeoutExpired:
            pass  # Chrome on macOS may linger; check file existence below

    if not OUTPUT.exists() or OUTPUT.stat().st_size == 0:
        raise SystemExit(f"Chrome didn't produce output at {OUTPUT}")

    print(f"✓  {OUTPUT.relative_to(ROOT)}  ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
