#!/usr/bin/env python3
"""
Generate PASTA player report HTML pages from a template.

Reads player_index.json, substitutes placeholders in the template, and writes
one HTML file per player (or one specific player with --slug).
When the external payload exists, banner minutes are read from
PLAYER_META[SUBJECT_ID].mins and player_index.json is used only as fallback.

Usage:
    python generate_pages.py                        # all players with report_file set
    python generate_pages.py --slug curtis-jones    # single player
    python generate_pages.py --slug curtis-jones --dry-run  # preview slots, no write

Requirements:
    Python 3.8+  (no external dependencies)

Template file:  assets/templates/player-report-template.html
Index file:     assets/data/player_index.json
Output:         {player["report_file"]}  (e.g. curtis_jones.html, at repo root)
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent          # html5up-forty/
TEMPLATE    = BASE_DIR / "assets/templates/player-report-template.html"
GK_TEMPLATE = BASE_DIR / "gk_report.html"
INDEX       = BASE_DIR / "assets/data/player_index.json"

# ── Role labels (IT) ──────────────────────────────────────────────────────────
ROLE_LABELS = {
    "MID": "Centrocampista",
    "ATT": "Attaccante",
    "DEF": "Difensore",
    "GK":  "Portiere",
}
ROLE_PLURAL = {
    "MID": "centrocampisti",
    "ATT": "attaccanti",
    "DEF": "difensori",
    "GK":  "portieri",
}
HEATMAP_FOURTH_TITLES = {
    "DEF": "Azioni difensive",
}
PLAYER_IMAGE_EXTS = (".webp", ".jpg", ".jpeg", ".png")


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_season(raw: str) -> str:
    """'2526' → '2025–26'"""
    s = raw.strip()
    if len(s) == 4 and s.isdigit():
        return f"20{s[:2]}–26"   # en-dash
    return raw


def fmt_competition(raw: str) -> str:
    """'ENG-Premier League' → 'ENG · Premier League'"""
    return raw.replace("-", " · ", 1)


def fmt_minutes(raw) -> str:
    """Format numeric minutes with a thin human-readable thousands separator."""
    if raw is None or raw == "":
        return "–"
    try:
        return f"{int(float(raw)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(raw)


def player_image_url(slug: str) -> str:
    """Return the first available player image path for the report hero."""
    for ext in PLAYER_IMAGE_EXTS:
        path = BASE_DIR / "images" / "players" / f"{slug}{ext}"
        if path.exists():
            return f"images/players/{slug}{ext}"
    return f"images/players/{slug}.webp"


def inline_markdown(text: str) -> str:
    """Render a small editorial Markdown subset after escaping HTML."""
    value = html.escape(text, quote=False)
    value = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(r"\*(.+?)\*", r"<em>\1</em>", value)
    return value


def markdown_block(text: str, paragraph_class: str | None = None) -> str:
    """Render compact Markdown for editorial copy without external deps."""
    raw = text.strip()
    if not raw:
        return ""

    blocks = re.split(r"\n\s*\n", raw)
    rendered: list[str] = []
    p_class = f' class="{paragraph_class}"' if paragraph_class else ""

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        if all(line.startswith(("- ", "* ")) for line in lines):
            items = "".join(f"<li>{inline_markdown(line[2:].strip())}</li>" for line in lines)
            rendered.append(f"<ul>{items}</ul>")
            continue

        text_line = " ".join(lines)
        rendered.append(f"<p{p_class}>{inline_markdown(text_line)}</p>")

    return "\n".join(rendered)


def payload_minutes(player: dict):
    """Return SUBJECT_ID PLAYER_META minutes from the external payload, if present."""
    payload_file = player.get("payload_file")
    if not payload_file:
        return None
    path = BASE_DIR / payload_file
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    subject_id = str(payload.get("SUBJECT_ID") or player.get("player_id") or "")
    meta = payload.get("PLAYER_META", {})
    if not isinstance(meta, dict):
        return None
    subject = meta.get(subject_id)
    if not isinstance(subject, dict):
        return None
    return subject.get("mins")


def gk_payload_minutes(player: dict):
    """Return GK Page V1 header minutes from the external payload, if present."""
    payload_file = player.get("payload_file")
    if not payload_file:
        return None
    path = BASE_DIR / payload_file
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    players = payload.get("GK_PAGE_V1_PLAYERS", {}).get("players", [])
    player_id = str(player.get("player_id") or "")
    player_name = str(player.get("player_name") or "")
    for item in players:
        header = item.get("header", {}) if isinstance(item, dict) else {}
        if str(header.get("player_id") or "") == player_id or header.get("player_name") == player_name:
            return header.get("minutes")
    return None


def payload_profile_reading(player: dict) -> str:
    """Return PROFILE_READING paragraphs from the external payload, if present."""
    payload_file = player.get("payload_file")
    if not payload_file:
        return ""
    path = BASE_DIR / payload_file
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    profile = payload.get("PROFILE_READING", {})
    if not isinstance(profile, dict):
        return ""
    paragraphs = profile.get("paragraphs", [])
    if not isinstance(paragraphs, list):
        return ""
    return "\n\n".join(str(paragraph).strip() for paragraph in paragraphs if str(paragraph).strip())


def note_block(text: str) -> str:
    """Wrap editorial note in a paragraph, or return empty string."""
    return markdown_block(text, "sr-section-intro")


def build_slots(player: dict) -> dict:
    """Return the substitution dict for one player."""
    macro  = player.get("macro_role", "MID")
    target = player.get("target_team", "")
    source = player.get("source_club") or player.get("team_name") or ""
    season = fmt_season(player.get("season", ""))
    comp   = fmt_competition(player.get("competition", ""))
    role_l = ROLE_LABELS.get(macro, macro)
    role_p = ROLE_PLURAL.get(macro, macro.lower() + "s")
    mins   = fmt_minutes(gk_payload_minutes(player) or payload_minutes(player) or player.get("minutes", "–"))
    narr_source = player.get("narrative", "").strip() or payload_profile_reading(player)
    narr   = markdown_block(narr_source, "sr-narrative-p")
    note   = markdown_block(player.get("source_team_note", ""), "sr-source-team-note")

    og_desc = (
        f"Compatibilità {target} — {role_l} · "
        f"{comp} {season}"
    )

    # ── Role-specific CSS and JS runtime ──────────────────────────────────
    if macro == "GK":
        role_css = "sr-gk-report.css"
        role_scripts = (
            '<script>\n'
            f'  window.SR_GK_EXTERNAL_PAYLOAD_URL = "{player.get("payload_file", "")}";\n'
            '</script>\n'
            '<script src="assets/js/sr-gk-report-loader.js"></script>\n'
            '<script src="assets/js/sr-gk-runtime.js"></script>'
        )
    else:
        role_css = "sr-role-report.css"
        role_scripts = (
            '<script>\n'
            f'  window.SR_EXTERNAL_PAYLOAD_URL = "{player.get("payload_file", "")}";\n'
            '</script>\n'
            '<script src="assets/js/sr-report-loader.js"></script>\n'
            '<script src="assets/js/sr-role-runtime.js?v=radar-mobile-20260604"></script>'
        )

    return {
        "PLAYER_NAME":       player["player_name"],
        "PLAYER_SLUG":       player["slug"],
        "PLAYER_IMAGE_URL":  player_image_url(player["slug"]),
        "SOURCE_CLUB":       source,
        "TARGET_CLUB":       target,
        "ROLE_LABEL":        role_l,
        "ROLE_PLURAL":       role_p,
        "MACRO_ROLE":        macro,
        "COMPETITION_LABEL": comp,
        "SEASON_LABEL":      season,
        "MINUTES":           mins,
        "NARRATIVE":         narr,
        "SOURCE_TEAM_NOTE":  note,
        "HEATMAP_FOURTH_TITLE": HEATMAP_FOURTH_TITLES.get(macro, "Progressione via passaggio"),
        "PAYLOAD_URL":       player.get("payload_file", ""),
        "OG_DESCRIPTION":    og_desc,
        "REPORT_URL":        f"https://pasta-reports.com/{player['report_file']}",
        "ROLE_CSS":          role_css,
        "ROLE_SCRIPTS":      role_scripts,
        # ── Editorial section notes (optional, populated via generate_editorial_brief.py) ──
        "NOTE_CONFRONTO":  note_block(player.get("note_confronto", "")),
        "NOTE_HEATMAP":    note_block(player.get("note_heatmap", "")),
        "NOTE_CONTEXT":    note_block(player.get("note_context", "")),
        "NOTE_SIMILARITY": note_block(player.get("note_similarity", "")),
    }


def render(template_text: str, slots: dict) -> str:
    """Replace all {{KEY}} placeholders."""
    result = template_text
    for key, value in slots.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    # Warn about any remaining unfilled placeholders
    remaining = re.findall(r"\{\{[A-Z_]+\}\}", result)
    if remaining:
        print(f"  ⚠  Unfilled placeholders: {sorted(set(remaining))}")
    return result


def render_gk(template_text: str, player: dict, slots: dict) -> str:
    """Render a GK page from the validated GK HTML structure."""
    name = html.escape(player["player_name"], quote=False)
    source = html.escape(slots["SOURCE_CLUB"], quote=False)
    target = html.escape(slots["TARGET_CLUB"], quote=False)
    role = html.escape(slots["ROLE_LABEL"], quote=False)
    competition = html.escape(slots["COMPETITION_LABEL"], quote=False)
    season = html.escape(slots["SEASON_LABEL"], quote=False)
    minutes = html.escape(slots["MINUTES"], quote=False)
    payload_url = html.escape(slots["PAYLOAD_URL"], quote=True)
    image_url = html.escape(slots["PLAYER_IMAGE_URL"], quote=True)
    narrative = slots["NARRATIVE"] or ""
    note_confronto = slots["NOTE_CONFRONTO"]
    note_heatmap = slots["NOTE_HEATMAP"]
    og_description = html.escape(slots["OG_DESCRIPTION"], quote=True)
    report_url = html.escape(slots["REPORT_URL"], quote=True)
    slug = html.escape(slots["PLAYER_SLUG"], quote=True)

    out = template_text
    out = re.sub(r"<title>.*?</title>", f"<title>Player Report · {name} | PASTA</title>", out, count=1, flags=re.S)
    out = out.replace(
        '<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no" />',
        (
            '<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no" />\n'
            '    <!-- Open Graph -->\n'
            f'    <meta property="og:title"       content="{name} · Analisi PASTA" />\n'
            f'    <meta property="og:description" content="{og_description}" />\n'
            f'    <meta property="og:image"       content="https://pasta-reports.com/images/cards/{slug}.png" />\n'
            '    <meta property="og:image:width"  content="1200" />\n'
            '    <meta property="og:image:height" content="630" />\n'
            '    <meta property="og:type"        content="article" />\n'
            f'    <meta property="og:url"         content="{report_url}" />\n'
            '    <!-- Twitter / X card -->\n'
            '    <meta name="twitter:card"        content="summary_large_image" />\n'
            '    <meta name="twitter:site"        content="@macnonesiste" />\n'
            f'    <meta name="twitter:title"       content="{name} · Analisi PASTA" />\n'
            f'    <meta name="twitter:description" content="{og_description}" />\n'
            f'    <meta name="twitter:image"       content="https://pasta-reports.com/images/cards/{slug}.png" />'
        ),
        1,
    )
    if "assets/css/pasta-theme.css" not in out:
        out = out.replace(
            '<link rel="stylesheet" href="assets/css/sr-gk-report.css" />',
            '<link rel="stylesheet" href="assets/css/sr-gk-report.css" />\n'
            '    <link rel="stylesheet" href="assets/css/pasta-theme.css" />',
            1,
        )
    out = re.sub(
        r"<style>.*?</style>",
        (
            "<style>\n"
            f"        /* Banner: player photo (template-specific - uses {slug}) */\n"
            "        #banner.style2 {\n"
            f"            background-image: url('{image_url}') !important;\n"
            "            background-attachment: scroll !important;\n"
            "            background-position: right 3.5rem !important;\n"
            "            background-size: auto 90% !important;\n"
            "            background-repeat: no-repeat !important;\n"
            "            min-height: 400px !important;\n"
            "            padding-top: 8rem !important;\n"
            "            padding-bottom: 4rem !important;\n"
            "        }\n"
            "        #banner.style2::after,\n"
            "        #banner.style2:after {\n"
            "            display: block !important;\n"
            "            opacity: 1 !important;\n"
            "            background: linear-gradient(\n"
            "                to right,\n"
            "                #f6f2ec 42%,\n"
            "                rgba(246, 242, 236, 0.80) 62%,\n"
            "                rgba(246, 242, 236, 0.10) 100%\n"
            "            ) !important;\n"
            "        }\n"
            "        @media screen and (max-width: 768px) {\n"
            "            #banner.style2 {\n"
            "                background-position: center top !important;\n"
            "                min-height: 0 !important;\n"
            "            }\n"
            "            #banner.style2::after, #banner.style2:after {\n"
            "                background: rgba(246, 242, 236, 0.82) !important;\n"
            "            }\n"
            "            .sr-heatmap-grid { grid-template-columns: 1fr; }\n"
            "            .sr-dot-row { grid-template-columns: 7rem 1fr 4rem; }\n"
            "        }\n"
            "        @media screen and (max-width: 480px) {\n"
            "            .sr-dot-row { grid-template-columns: 6rem 1fr 3.5rem; }\n"
            "        }\n"
            "    </style>"
        ),
        out,
        count=1,
        flags=re.S,
    )
    out = re.sub(r'\s*<span class="image"><img src="[^"]+" alt="" /></span>\n', "\n", out, count=1)
    out = re.sub(r'<header class="major"><h1>.*?</h1></header>', f'<header class="major"><h1>{name}</h1></header>', out, count=1)
    out = re.sub(
        r'<div class="content"><p>.*?</p></div>',
        (
            '<div class="content">\n'
            '                <div class="sr-banner-meta">\n'
            f'                    <span class="sr-banner-chip sr-banner-clubs">{source} → {target}</span>\n'
            f'                    <span class="sr-banner-chip">{role}</span>\n'
            f'                    <span class="sr-banner-chip">{competition}</span>\n'
            f'                    <span class="sr-banner-chip">Stagione {season}</span>\n'
            f'                    <span class="sr-banner-chip">{minutes} min</span>\n'
            '                </div>\n'
            '            </div>'
        ),
        out,
        count=1,
        flags=re.S,
    )
    out = re.sub(
        r'<p class="sr-narrative" id="gkProfileParagraph">.*?</p>',
        f'<div class="sr-narrative sr-editorial-markdown" id="gkProfileParagraph">{narrative}</div>',
        out,
        count=1,
        flags=re.S,
    )
    out = re.sub(
        r'(<p class="sr-section-label">Confronto individuale vs portieri Inter · 2025–26</p>)',
        r"\1\n            " + note_confronto,
        out,
        count=1,
    )
    out = re.sub(
        r'(<p class="sr-section-label">Visualizzazioni portiere</p>)',
        r"\1\n            " + note_heatmap,
        out,
        count=1,
    )
    out = out.replace("parte da Vicario", f"parte da {name}")
    out = re.sub(
        r'window\.SR_GK_EXTERNAL_PAYLOAD_URL = "[^"]*";',
        f'window.SR_GK_EXTERNAL_PAYLOAD_URL = "{payload_url}";',
        out,
        count=1,
    )
    out = out.replace(
        '<script src="assets/js/sr-gk-runtime.js"></script>',
        '<script src="assets/js/sr-gk-runtime.js?v=cream-theme-20260604"></script>',
        1,
    )
    return out


def validate(player: dict) -> list[str]:
    """Return a list of missing required fields."""
    required = ["player_name", "slug", "report_file", "payload_file", "macro_role"]
    return [f for f in required if not player.get(f)]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate PASTA player report pages")
    parser.add_argument("--slug",    help="Player slug to generate (e.g. curtis-jones)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print substitution slots without writing files")
    args = parser.parse_args()

    if not TEMPLATE.exists():
        sys.exit(f"Template not found: {TEMPLATE}")
    if not INDEX.exists():
        sys.exit(f"Index not found: {INDEX}")

    template_text = TEMPLATE.read_text(encoding="utf-8")
    players       = json.loads(INDEX.read_text(encoding="utf-8"))

    # Filter
    if args.slug:
        targets = [p for p in players if p["slug"] == args.slug]
        if not targets:
            available = [p["slug"] for p in players]
            sys.exit(f"Slug '{args.slug}' not found.\nAvailable: {available}")
    else:
        targets = [p for p in players if p.get("report_file")]

    print(f"Generating {len(targets)} page(s)…\n")

    for player in targets:
        name = player["player_name"]

        # Validate
        missing = validate(player)
        if missing:
            print(f"  ✗  {name:30s}  missing fields: {missing}")
            continue

        slots = build_slots(player)

        if args.dry_run:
            print(f"  ─  {name}")
            for k, v in slots.items():
                preview = (v[:60] + "…") if len(v) > 60 else v
                print(f"       {k:<22s} = {preview!r}")
            print()
            continue

        if slots["MACRO_ROLE"] == "GK":
            if not GK_TEMPLATE.exists():
                sys.exit(f"GK template source not found: {GK_TEMPLATE}")
            html = render_gk(GK_TEMPLATE.read_text(encoding="utf-8"), player, slots)
        else:
            html = render(template_text, slots)
        out_path = BASE_DIR / player["report_file"]
        out_path.write_text(html, encoding="utf-8")
        print(f"  ✓  {name:30s}  →  {player['report_file']}")

    print("\nDone.")


if __name__ == "__main__":
    main()
