#!/usr/bin/env python3
"""
Generate PASTA scouting card PNGs using Playwright.

Versions:
  a  — 1200×630  homepage tile  (card-template.html)
  b  — 1200×628  social/Twitter (card-template-social.html, with radar)
  all — both

Usage:
    python assets/cards/generate_cards.py                          # all live, version a
    python assets/cards/generate_cards.py --slug curtis-jones
    python assets/cards/generate_cards.py --slug curtis-jones --version b
    python assets/cards/generate_cards.py --slug curtis-jones --version all
    python assets/cards/generate_cards.py --slug curtis-jones --target "Napoli"

Requirements:
    pip install playwright && playwright install chromium

Images:
    images/players/{slug}.webp|jpg|jpeg|png
    images/clubs/{club}.webp|jpg|jpeg|png
"""

import argparse
import base64
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR    = Path(__file__).resolve().parent.parent.parent   # html5up-forty/
TMPL_A      = BASE_DIR / "assets/cards/card-template.html"
TMPL_B      = BASE_DIR / "assets/cards/card-template-social.html"
OUTPUT_DIR  = BASE_DIR / "images/cards"
INDEX       = BASE_DIR / "assets/data/player_index.json"

VIEWPORTS   = { "a": (1200, 630), "b": (1200, 628) }

CLUB_SLUGS  = {
    "Inter":    "inter",
    "Milan":    "milan",
    "Juventus": "juventus",
    "Napoli":   "napoli",
}

ROLE_LABELS = {
    "MID": "Centrocampista",
    "ATT": "Attaccante",
    "DEF": "Difensore",
    "GK":  "Portiere",
}

IMG_EXTS = [".webp", ".jpg", ".jpeg", ".png"]


# ── helpers ──────────────────────────────────────────────────────────────────

def split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split()
    return ("", parts[0]) if len(parts) == 1 else (" ".join(parts[:-1]), parts[-1])


def lastname_font_size(lastname: str) -> str:
    compact_len = len(lastname.replace(" ", ""))
    if compact_len <= 6:
        return "6.2rem"
    if compact_len <= 8:
        return "5.55rem"
    if compact_len <= 10:
        return "4.85rem"
    if compact_len <= 12:
        return "4.25rem"
    return "3.75rem"


def find_image(folder: Path, stem: str) -> Path | None:
    for ext in IMG_EXTS:
        p = folder / f"{stem}{ext}"
        if p.exists():
            return p
    return None


def image_to_data_url(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    data = path.read_bytes()
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        mime = "image/webp"
    elif data[:2] == b'\xff\xd8':
        mime = "image/jpeg"
    elif data[:8] == b'\x89PNG\r\n\x1a\n':
        mime = "image/png"
    else:
        mime = f"image/{path.suffix.lower().lstrip('.')}"
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def load_radar(player: dict) -> dict | None:
    pf = player.get("payload_file")
    if not pf:
        return None
    path = BASE_DIR / pf
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "axes":   payload.get("RADAR_AXES", []),
        "data":   payload.get("RADAR_DATA", {}),
        "ranges": payload.get("RADAR_AXIS_RANGES", []),
    }


# ── renderers ────────────────────────────────────────────────────────────────

def _base_slots(player: dict, target_override: str | None) -> dict:
    firstname, lastname = split_name(player["player_name"])
    club  = target_override or player.get("target_team", "")
    role  = ROLE_LABELS.get(player.get("macro_role", ""), player.get("macro_role", ""))
    slug  = player["slug"]
    photo = image_to_data_url(find_image(BASE_DIR / "images/players", slug))
    badge = image_to_data_url(find_image(BASE_DIR / "images/clubs", CLUB_SLUGS.get(club, club.lower())))
    return dict(
        PLAYER_FIRSTNAME=firstname,
        PLAYER_LASTNAME=lastname,
        PLAYER_LASTNAME_FONT_SIZE=lastname_font_size(lastname),
        PLAYER_PHOTO=photo,
        CLUB_NAME=club,
        CLUB_BADGE=badge,
        PLAYER_ROLE=role,
    )


def render_version_a(page, player: dict, target_override: str | None) -> Path:
    slots = _base_slots(player, target_override)
    html  = TMPL_A.read_text(encoding="utf-8")
    for k, v in slots.items():
        html = html.replace(f"{{{{{k}}}}}", v)

    w, h = VIEWPORTS["a"]
    page.set_viewport_size({"width": w, "height": h})
    page.set_content(html, wait_until="networkidle")

    out = OUTPUT_DIR / f"{player['slug']}.png"
    page.locator(".card").screenshot(path=str(out))
    return out


def render_version_b(page, player: dict, target_override: str | None) -> Path:
    slots  = _base_slots(player, target_override)
    radar  = load_radar(player)
    html   = TMPL_B.read_text(encoding="utf-8")

    for k, v in slots.items():
        html = html.replace(f"{{{{{k}}}}}", v)

    # inject radar data
    html = html.replace("{{RADAR_AXES_JSON}}",        json.dumps(radar["axes"]   if radar else []))
    html = html.replace("{{RADAR_DATA_JSON}}",        json.dumps(radar["data"]   if radar else {}))
    html = html.replace("{{RADAR_AXIS_RANGES_JSON}}", json.dumps(radar["ranges"] if radar else []))

    w, h = VIEWPORTS["b"]
    page.set_viewport_size({"width": w, "height": h})
    page.set_content(html, wait_until="networkidle")
    page.wait_for_timeout(400)   # let Chart.js finish drawing

    out = OUTPUT_DIR / f"{player['slug']}-social.png"
    page.locator(".card").screenshot(path=str(out))
    return out


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate PASTA scouting card PNGs")
    parser.add_argument("--slug",    help="Player slug (e.g. curtis-jones)")
    parser.add_argument("--target",  help="Override target club (e.g. 'Napoli')")
    parser.add_argument("--version", choices=["a", "b", "all"], default="a",
                        help="a = homepage tile | b = social/Twitter | all = both (default: a)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    players = json.loads(INDEX.read_text(encoding="utf-8"))

    if args.slug:
        targets = [p for p in players if p["slug"] == args.slug]
        if not targets:
            print(f"  ✗  slug '{args.slug}' not found.")
            print(f"     available: {[p['slug'] for p in players]}")
            return
    else:
        targets = [p for p in players if p.get("report_status") == "live"]

    versions = ["a", "b"] if args.version == "all" else [args.version]

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page    = browser.new_page()

        for player in targets:
            for ver in versions:
                try:
                    if ver == "a":
                        out = render_version_a(page, player, args.target)
                    else:
                        out = render_version_b(page, player, args.target)
                    print(f"  ✓  [{ver}]  {player['player_name']:28s}  →  {out.name}")
                except Exception as e:
                    print(f"  ✗  [{ver}]  {player['player_name']:28s}  →  {e}")

        browser.close()

    print(f"\nDone — output in {OUTPUT_DIR.relative_to(BASE_DIR)}/")


if __name__ == "__main__":
    main()
