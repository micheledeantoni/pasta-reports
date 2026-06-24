#!/usr/bin/env python3
"""Local report builder GUI server.

This is a thin local-only wrapper around the existing resolver/export helpers.
It does not change analytics, payload structure, or frontend rendering.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unicodedata
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOCCERDB_ROOT = Path("/Users/michele/Documents/SoccerDB")
FEATURES = SOCCERDB_ROOT / "data" / "features"
PYTHON = SOCCERDB_ROOT / ".venv" / "bin" / "python"
PLAYER_INDEX = ROOT / "assets" / "data" / "player_index.json"
ANALYTICS_DB = SOCCERDB_ROOT / "data" / "analytics.duckdb"
CORE_DB = SOCCERDB_ROOT / "data" / "football_core.duckdb"
ROLE_FILES = {
    "GK": "scouting_view_metrics_v1_gk.parquet",
    "DEF": "scouting_view_metrics_v1_def.parquet",
    "MID": "scouting_view_metrics_v1_mid.parquet",
    "ATT": "scouting_view_metrics_v1_att.parquet",
}
ROLE_CHOICES = tuple(ROLE_FILES)
EDITORIAL_FIELDS = [
    "narrative",
    "source_team_note",
    "note_confronto",
    "note_heatmap",
    "note_context",
    "note_similarity",
]


def season_variants(raw: str | None) -> set[str]:
    if not raw:
        return set()
    value = str(raw).strip()
    variants = {value}
    if len(value) == 9 and value[:4].isdigit() and value[5:].isdigit():
        variants.add(value[2:4] + value[7:9])
    if len(value) == 4 and value.isdigit():
        variants.add(f"20{value[:2]}-20{value[2:]}")
    return variants


def role_df(role: str) -> pd.DataFrame:
    role = role.upper()
    path = FEATURES / ROLE_FILES[role]
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_parquet(path)
    if "minutes_played" in df.columns and "minutes" not in df.columns:
        df = df.rename(columns={"minutes_played": "minutes"})
    return df


def role_pool(role: str) -> pd.DataFrame:
    role = role.upper()
    if role == "ALL":
        frames = []
        for candidate in ROLE_CHOICES:
            frames.append(apply_team_overrides(unique_players(role_df(candidate)), candidate))
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return apply_team_overrides(unique_players(role_df(role)), role)


def unique_players(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ["player_id", "player_name", "team_id", "team_name", "competition", "season", "macro_role", "minutes"] if c in df.columns]
    return df[cols].drop_duplicates(subset=["player_id", "team_id", "competition", "season", "macro_role"])


def split_ids(raw: Any) -> list[str]:
    return [part.strip() for part in str(raw or "").split(",") if part.strip()]


def search_key(value: Any) -> str:
    text = str(value or "").casefold()
    text = text.replace("ø", "o").replace("đ", "d").replace("ð", "d").replace("ß", "ss")
    return "".join(
        char for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )


def db_team_names() -> dict[str, str]:
    names: dict[str, str] = {}
    try:
        import duckdb
    except Exception:
        return names
    for db_path, table in [(CORE_DB, "teams"), (ANALYTICS_DB, "dim_team")]:
        if not db_path.exists():
            continue
        try:
            con = duckdb.connect(str(db_path), read_only=True)
            rows = con.execute(f"select team_id, team_name from {table}").fetchall()
            con.close()
        except Exception:
            continue
        for team_id, team_name in rows:
            if team_id is not None and team_name:
                names[str(int(team_id))] = str(team_name)
    return names


def team_name_overrides(role: str) -> dict[str, str]:
    overrides: dict[str, str] = db_team_names()
    if PLAYER_INDEX.exists():
        players = json.loads(PLAYER_INDEX.read_text(encoding="utf-8"))
        df = unique_players(role_df(role))
        for entry in players:
            if str(entry.get("macro_role", "")).upper() != role.upper():
                continue
            for field, name_field in [
                ("target_team_peer_ids", "target_team"),
                ("source_team_peer_ids", "source_club"),
            ]:
                ids = split_ids(entry.get(field))
                label = entry.get(name_field) or entry.get("team_name")
                if not ids or not label:
                    continue
                rows = df[df["player_id"].astype(str).isin(ids)]
                for team_id in rows.get("team_id", pd.Series(dtype=str)).dropna().astype(str).unique():
                    overrides[team_id] = str(label)
            subject_rows = df[df["player_id"].astype(str).eq(str(entry.get("player_id")))]
            source_label = entry.get("source_club") or entry.get("team_name")
            if source_label:
                for team_id in subject_rows.get("team_id", pd.Series(dtype=str)).dropna().astype(str).unique():
                    overrides[team_id] = str(source_label)
    return overrides


def apply_team_overrides(df: pd.DataFrame, role: str) -> pd.DataFrame:
    overrides = team_name_overrides(role)
    if not overrides or "team_id" not in df.columns or "team_name" not in df.columns:
        return df
    df = df.copy()
    mapped = df["team_id"].astype(str).map(overrides)
    df.loc[mapped.notna(), "team_name"] = mapped[mapped.notna()]
    return df


def apply_season(df: pd.DataFrame, season: str | None) -> pd.DataFrame:
    variants = season_variants(season)
    if variants and "season" in df.columns:
        return df[df["season"].astype(str).isin(variants)]
    return df


def rows_for_response(df: pd.DataFrame, limit: int = 50) -> list[dict[str, Any]]:
    out = []
    for row in df.head(limit).to_dict("records"):
        clean = {}
        for key, value in row.items():
            if pd.isna(value):
                clean[key] = ""
            elif key in {"player_id", "team_id"}:
                clean[key] = int(value)
            elif key == "minutes":
                clean[key] = int(float(value))
            else:
                clean[key] = value
        clean["availability"] = "metrics"
        out.append(clean)
    return out


def search_players(params: dict[str, list[str]]) -> dict[str, Any]:
    role = params.get("role", ["ALL"])[0].upper()
    query = params.get("query", [""])[0]
    season = params.get("season", ["2025-2026"])[0]
    df = apply_season(role_pool(role), season)
    if query:
        needle = search_key(query)
        df = df[df["player_name"].map(search_key).str.contains(needle, regex=False, na=False)]
    df = df.sort_values(["minutes", "player_name"], ascending=[False, True])
    return {"players": rows_for_response(df)}


def target_peers(params: dict[str, list[str]]) -> dict[str, Any]:
    role = params.get("role", ["DEF"])[0].upper()
    team = params.get("team", [""])[0]
    season = params.get("season", ["2025-2026"])[0]
    min_minutes = float(params.get("min_minutes", ["300"])[0] or 0)
    df = apply_team_overrides(unique_players(apply_season(role_df(role), season)), role)
    if team:
        matching_ids = [
            team_id for team_id, team_name in team_name_overrides(role).items()
            if search_key(team) in search_key(team_name)
        ]
        by_name = df["team_name"].map(search_key).str.contains(search_key(team), regex=False, na=False)
        by_id = df["team_id"].astype(str).isin(matching_ids) if matching_ids else False
        df = df[by_name | by_id]
    if min_minutes:
        df = df[pd.to_numeric(df["minutes"], errors="coerce").fillna(0) >= min_minutes]
    df = df.sort_values(["minutes", "player_name"], ascending=[False, True])
    return {"players": rows_for_response(df)}


def source_peers(params: dict[str, list[str]]) -> dict[str, Any]:
    role = params.get("role", ["DEF"])[0].upper()
    player_id = params.get("player_id", [""])[0]
    season = params.get("season", ["2025-2026"])[0]
    min_minutes = float(params.get("min_minutes", ["300"])[0] or 0)
    df = apply_team_overrides(unique_players(apply_season(role_df(role), season)), role)
    subject_rows = df[df["player_id"].astype(str).eq(str(player_id))]
    if subject_rows.empty:
        return {"players": [], "subject": None, "error": "subject not found in role layer"}
    subject = subject_rows.sort_values("minutes", ascending=False).iloc[0]
    peers = df[
        (df["team_id"].astype(str) == str(subject["team_id"]))
        & (df["competition"].astype(str) == str(subject["competition"]))
        & (df["season"].astype(str) == str(subject["season"]))
        & (df["macro_role"].astype(str) == str(subject["macro_role"]))
        & (df["player_id"].astype(str) != str(subject["player_id"]))
    ]
    if min_minutes:
        peers = peers[pd.to_numeric(peers["minutes"], errors="coerce").fillna(0) >= min_minutes]
    peers = peers.sort_values(["minutes", "player_name"], ascending=[False, True])
    return {"subject": rows_for_response(pd.DataFrame([subject]))[0], "players": rows_for_response(peers)}


def validate_workflow_payload(data: dict[str, Any]) -> tuple[str, str, str, bool]:
    source_role = str(data.get("source_role") or data.get("role") or "").upper()
    report_role = str(data.get("report_role") or data.get("role") or "").upper()
    allow_cross_role = bool(data.get("allow_cross_role_report"))
    reason = str(data.get("role_override_reason") or "").strip()
    if report_role not in ROLE_CHOICES:
        raise ValueError("report_role must be one of GK, DEF, MID, ATT")
    if source_role not in ROLE_CHOICES:
        raise ValueError("source_role must be one of GK, DEF, MID, ATT")
    if source_role != report_role and not allow_cross_role:
        raise ValueError("source_role and report_role differ. Enable cross-role report before generating.")
    if source_role != report_role and not reason:
        raise ValueError("source_role and report_role differ. Add a role override reason before generating.")
    if not str(data.get("main_comparison_peer_ids") or "").strip():
        raise ValueError("select at least one main/radar peer for report_role")
    source_context_exported = source_role == report_role
    return source_role, report_role, reason, source_context_exported


def prompt_from_payload(data: dict[str, Any]) -> str:
    source_role, report_role, reason, source_context_exported = validate_workflow_payload(data)
    return f"""Return only JSON with these exact keys:
{{
  "narrative": "",
  "source_team_note": "",
  "note_confronto": "",
  "note_heatmap": "",
  "note_context": "",
  "note_similarity": ""
}}

Context:
- Player: {data.get('player_name')} ({data.get('player_id')})
- Source/detected role: {source_role}
- Report/analysis role: {report_role}
- Role override reason: {reason or "(none; source role and report role match)"}
- Source team: {data.get('team_name')}
- Main/radar comparison peers: {data.get('comparison_label')} = {data.get('main_comparison_peer_ids')}
- Source-team context peers: {data.get('source_team_peer_label')} = {data.get('source_team_peer_ids')}
- Source-context peers exported as context IDs: {"yes" if source_context_exported else "no; stored as editorial workflow metadata only because source_role differs from report_role"}
- Target team: {data.get('target_team')}
- Competition: {data.get('competition')}
- Season: {data.get('season')}

Rules:
- The report is built in report_role, not necessarily source_role.
- The radar/main comparison is against target-team same-role peers in report_role.
- The source role may differ from report_role; do not describe this as a data error.
- Explain the tactical conversion clearly with language such as "in the source team he is used as..." and "in the target context he is evaluated as...".
- Source-team peers are source-context peers only.
- Do not describe the radar as a source-team comparison.
- Explain what the player brings/adds/changes compared with target-team peers.
- Use source-team context only to explain how the profile emerged in the source team.
- Avoid better/worse language; prefer brings, adds, changes, fits, differs from.
"""


def build_create_command(data: dict[str, Any], dry_run: bool) -> list[str]:
    source_role, report_role, reason, source_context_exported = validate_workflow_payload(data)
    cmd = [
        str(PYTHON if PYTHON.exists() else Path(sys.executable)),
        "scripts/create_player_page_from_export.py",
        "--role", report_role,
        "--source-role", source_role,
        "--player-id", str(data["player_id"]),
        "--player-name", data["player_name"],
        "--slug", data["slug"],
        "--main-comparison-peer-ids", data["main_comparison_peer_ids"],
        "--comparison-label", data["comparison_label"],
        "--team-name", data["team_name"],
        "--source-club", data.get("source_club") or data["team_name"],
        "--competition", data["competition"],
        "--season", str(data["season"]),
        "--target-team", data["target_team"],
        "--visibility", data.get("visibility", "hidden"),
        "--report-status", data.get("report_status", "live"),
        "--overwrite",
    ]
    if reason:
        cmd.extend(["--role-override-reason", reason])
    if data.get("source_team_peer_ids"):
        cmd.extend(["--source-team-peer-ids", data.get("source_team_peer_ids", "")])
        cmd.extend(["--source-team-peer-label", data.get("source_team_peer_label", "")])
    if not source_context_exported:
        cmd.append("--source-context-editorial-only")
    for field in EDITORIAL_FIELDS:
        value = data.get(field)
        if value:
            cmd.extend(["--" + field.replace("_", "-"), value])
    if dry_run:
        cmd.append("--dry-run")
    return [part for part in cmd if part != ""]


def run_create(data: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    cmd = build_create_command(data, dry_run)
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "command": cmd,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "url": f"http://127.0.0.1:8001/{data.get('slug')}.html",
    }


def regenerate_cards(data: dict[str, Any]) -> dict[str, Any]:
    slug = data.get("slug", "")
    cmd = [str(PYTHON if PYTHON.exists() else Path(sys.executable)), "assets/cards/generate_cards.py", "--slug", slug, "--version", "all"]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    return {"ok": result.returncode == 0, "returncode": result.returncode, "command": cmd, "stdout": result.stdout, "stderr": result.stderr}


class Handler(BaseHTTPRequestHandler):
    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        try:
            if parsed.path == "/":
                self.serve_file(ROOT / "tools" / "report_builder.html", "text/html")
            elif parsed.path == "/report_builder.js":
                self.serve_file(ROOT / "tools" / "report_builder.js", "text/javascript")
            elif parsed.path == "/report_builder.css":
                self.serve_file(ROOT / "tools" / "report_builder.css", "text/css")
            elif parsed.path == "/api/search_players":
                self.send_json(search_players(params))
            elif parsed.path == "/api/target_peers":
                self.send_json(target_peers(params))
            elif parsed.path == "/api/source_peers":
                self.send_json(source_peers(params))
            elif parsed.path == "/api/status":
                self.send_json({"ok": True, "root": str(ROOT), "soccerdb_root": str(SOCCERDB_ROOT)})
            else:
                self.send_error(404)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, 500)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        data = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        try:
            if self.path == "/api/prompt":
                self.send_json({"prompt": prompt_from_payload(data)})
            elif self.path == "/api/dry_run":
                self.send_json(run_create(data, True))
            elif self.path == "/api/create_page":
                self.send_json(run_create(data, False))
            elif self.path == "/api/regenerate_cards":
                self.send_json(regenerate_cards(data))
            else:
                self.send_error(404)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, 500)

    def serve_file(self, path: Path, content_type: str) -> None:
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8011
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Report builder: http://127.0.0.1:{port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
