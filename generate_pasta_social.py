#!/usr/bin/env python3
"""
Generate images/pasta-social.png for the PASTA home page OG / Twitter card.

Uses a local HTTP server + Chrome headless to screenshot
tools/social_export/pasta-home-banner.html at 1200×630px
(standard social card dimensions) with full CSS variable support.

Usage:
    python generate_pasta_social.py
"""

import shutil
import subprocess
import tempfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

ROOT   = Path(__file__).resolve().parent
BANNER = ROOT / "tools" / "social_export" / "pasta-home-banner.html"
OUTPUT = ROOT / "images" / "pasta-social.png"
REL    = "tools/social_export/pasta-home-banner.html"


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *_): pass


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
        raise SystemExit("Chrome / Chromium not found. Install Google Chrome and retry.")
    print(f"Chrome: {chrome}")

    # Local server so CSS variables and relative paths resolve correctly
    handler = partial(_Quiet, directory=str(ROOT))
    server  = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    url  = f"http://127.0.0.1:{port}/{REL}"

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists():
        OUTPUT.unlink()

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
            "--virtual-time-budget=4000",
            f"--screenshot={OUTPUT}",
            url,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=15)
        except subprocess.TimeoutExpired:
            pass  # Chrome on macOS may linger; check file existence below

    server.shutdown()

    if not OUTPUT.exists() or OUTPUT.stat().st_size == 0:
        raise SystemExit(f"Chrome didn't produce output at {OUTPUT}")

    print(f"✓  {OUTPUT.relative_to(ROOT)}  ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
