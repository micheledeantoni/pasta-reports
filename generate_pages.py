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
TEMPLATE   = BASE_DIR / "assets/templates/player-report-template.html"
INDEX      = BASE_DIR / "assets/data/player_index.json"

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
    mins   = fmt_minutes(payload_minutes(player) or player.get("minutes", "–"))
    narr_source = player.get("narrative", "").strip() or payload_profile_reading(player)
    narr   = markdown_block(narr_source, "sr-narrative-p")
    note   = markdown_block(player.get("source_team_note", ""), "sr-source-team-note")

    og_desc = (
        f"Compatibilità {target} — {role_l} · "
        f"{comp} {season}"
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
        "PAYLOAD_URL":       player.get("payload_file", ""),
        "OG_DESCRIPTION":    og_desc,
        "REPORT_URL":        f"https://pasta-reports.com/{player['report_file']}",
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

        html     = render(template_text, slots)
        out_path = BASE_DIR / player["report_file"]
        out_path.write_text(html, encoding="utf-8")
        print(f"  ✓  {name:30s}  →  {player['report_file']}")

    print("\nDone.")


if __name__ == "__main__":
    main()
