#!/usr/bin/env python3
"""Local report builder GUI server.

This is a thin local-only wrapper around the existing resolver/export helpers.
It does not change analytics, payload structure, or frontend rendering.
"""

from __future__ import annotations

import json
import os
import argparse
import errno
import subprocess
import sys
import unicodedata
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PLAYER_INDEX = ROOT / "assets" / "data" / "player_index.json"
ROLE_FILES = {
    "GK": "scouting_view_metrics_v1_gk.parquet",
    "DEF": "scouting_view_metrics_v1_def.parquet",
    "MID": "scouting_view_metrics_v1_mid.parquet",
    "ATT": "scouting_view_metrics_v1_att.parquet",
}
ROLE_CHOICES = tuple(ROLE_FILES)
COMBINED_CHAMPIONS_COMPETITION = "ENG-Premier League + UEFA-Champions League"
EDITORIAL_FIELDS = [
    "narrative",
    "source_team_note",
    "note_confronto",
    "note_heatmap",
    "note_context",
    "note_similarity",
]


def _bundle_root() -> Path:
    return ROOT.parent.parent


def _path_from(value: Any, base: Path) -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _executable_path_from(value: Any, base: Path) -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.absolute()


def _load_runtime_config(config_path: Path | None = None) -> dict[str, Any]:
    candidates = []
    if config_path is not None:
        candidates.append(config_path)
    else:
        candidates.extend([
            ROOT / "config" / "report_builder_paths.json",
            ROOT / "tools" / "report_builder_paths.json",
        ])
    for candidate in candidates:
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    return {}


def _python_for(root: Path) -> Path:
    current = Path(sys.executable)
    candidates = [
        current,
        root / ".venv" / "bin" / "python",
        root / ".venv" / "Scripts" / "python.exe",
        Path("/Users/michele/.pyenv/versions/lewagon/bin/python3"),
    ]
    for candidate in candidates:
        if candidate.exists() and _python_has_report_deps(candidate):
            return candidate
    return current


def _python_has_report_deps(python: Path) -> bool:
    code = "import numpy, pandas, duckdb, pyarrow"
    try:
        result = subprocess.run([str(python), "-c", code], text=True, capture_output=True, timeout=10)
    except Exception:
        return False
    return result.returncode == 0


def apply_runtime_paths(config_path: Path | None = None) -> None:
    config = _load_runtime_config(config_path)
    bundle = _path_from(config.get("bundle_root") or os.environ.get("VACATION_BUNDLE_ROOT") or _bundle_root(), ROOT)
    experiments = _path_from(
        config.get("experiments_root") or os.environ.get("SOCCERDB_EXPERIMENTS_ROOT") or bundle / "soccerdb_experiments",
        bundle,
    )
    soccerdb = _path_from(config.get("soccerdb_root") or os.environ.get("SOCCERDB_ROOT") or bundle / "SoccerDB", bundle)
    dogana = _path_from(config.get("dogana_root") or os.environ.get("DOGANA_ROOT") or experiments / "dogana_visuals", bundle)
    dogana_output = _path_from(
        config.get("dogana_output_root") or os.environ.get("DOGANA_OUTPUT_ROOT") or experiments / "outputs" / "dogana",
        bundle,
    )

    global BUNDLE_ROOT, SOCCERDB_ROOT, EXPERIMENTS_ROOT, DOGANA_ROOT, DOGANA_CONFIG_DIR
    global DOGANA_OUTPUT_ROOT, FEATURES, PYTHON, ANALYTICS_DB, CORE_DB, OVERRIDE_CSV, OVERRIDE_BUILDER
    BUNDLE_ROOT = bundle
    SOCCERDB_ROOT = soccerdb
    EXPERIMENTS_ROOT = experiments
    DOGANA_ROOT = dogana
    DOGANA_CONFIG_DIR = DOGANA_ROOT / "configs" / "players"
    DOGANA_OUTPUT_ROOT = dogana_output
    FEATURES = SOCCERDB_ROOT / "data" / "features"
    PYTHON = _executable_path_from(
        config.get("python") or os.environ.get("SOCCERDB_PYTHON") or _python_for(SOCCERDB_ROOT),
        ROOT,
    )
    ANALYTICS_DB = SOCCERDB_ROOT / "data" / "analytics.duckdb"
    CORE_DB = SOCCERDB_ROOT / "data" / "football_core.duckdb"
    OVERRIDE_CSV = SOCCERDB_ROOT / "config" / "manual_role_overrides.csv"
    OVERRIDE_BUILDER = SOCCERDB_ROOT / "scripts" / "build_manual_role_override_artifacts.py"


apply_runtime_paths()


def status_payload() -> dict[str, Any]:
    exporter = SOCCERDB_ROOT / "scripts" / "exports" / "export_role_report_data.py"
    create_script = ROOT / "scripts" / "create_player_page_from_export.py"
    template = ROOT / "assets" / "templates" / "player-report-template.html"
    checks = {
        "soccerdb_found": SOCCERDB_ROOT.is_dir(),
        "export_script_found": exporter.is_file(),
        "features_found": FEATURES.is_dir(),
        "frontend_template_found": template.is_file(),
        "player_index_found": PLAYER_INDEX.is_file(),
        "create_page_script_found": create_script.is_file(),
        "export_command_executable": PYTHON.exists() and exporter.is_file(),
        "dogana_found": DOGANA_ROOT.is_dir(),
    }
    return {
        "ok": all(checks.values()),
        "root": str(ROOT),
        "bundle_root": str(BUNDLE_ROOT),
        "soccerdb_root": str(SOCCERDB_ROOT),
        "experiments_root": str(EXPERIMENTS_ROOT),
        "dogana_root": str(DOGANA_ROOT),
        "dogana_output_root": str(DOGANA_OUTPUT_ROOT),
        "features": str(FEATURES),
        "python": str(PYTHON),
        "export_script": str(exporter),
        "create_page_script": str(create_script),
        "frontend_template": str(template),
        "player_index": str(PLAYER_INDEX),
        "checks": checks,
        "export_help_command": [str(PYTHON), str(exporter), "--help"],
    }


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


def index_player_pool(role: str, season: str | None) -> pd.DataFrame:
    if not PLAYER_INDEX.exists():
        return pd.DataFrame()
    variants = season_variants(season)
    rows = []
    for entry in json.loads(PLAYER_INDEX.read_text(encoding="utf-8")):
        entry_role = str(entry.get("macro_role") or entry.get("report_role") or entry.get("source_role") or "").upper()
        if role.upper() != "ALL" and entry_role != role.upper():
            continue
        entry_season = str(entry.get("season") or "")
        if variants and entry_season not in variants:
            continue
        rows.append(
            {
                "player_id": entry.get("player_id"),
                "player_name": entry.get("player_name"),
                "team_name": entry.get("source_club") or entry.get("team_name"),
                "competition": entry.get("competition"),
                "season": entry.get("season"),
                "macro_role": entry_role,
                "minutes": -1,
                "availability": "index",
            }
        )
    return pd.DataFrame(rows)


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


def slugify_name(value: Any) -> str:
    text = search_key(value)
    chars = []
    previous_dash = False
    for char in text:
        if char.isalnum():
            chars.append(char)
            previous_dash = False
        elif not previous_dash:
            chars.append("-")
            previous_dash = True
    return "".join(chars).strip("-")


def slugify_underscore(value: Any) -> str:
    return slugify_name(value).replace("-", "_")


def season_to_int(raw: Any) -> int:
    value = str(raw or "").strip()
    if len(value) == 4 and value.isdigit():
        return int(value)
    variants = season_variants(value)
    compact = next((item for item in variants if len(item) == 4 and item.isdigit()), "")
    if compact:
        return int(compact)
    raise ValueError(f"invalid season for Dogana config: {raw!r}")


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
                    overrides.setdefault(team_id, str(label))
            subject_rows = df[df["player_id"].astype(str).eq(str(entry.get("player_id")))]
            source_label = entry.get("source_club") or entry.get("team_name")
            if source_label:
                for team_id in subject_rows.get("team_id", pd.Series(dtype=str)).dropna().astype(str).unique():
                    overrides.setdefault(team_id, str(source_label))
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


def combined_minutes_peer_pool(role: str, season: str | None) -> pd.DataFrame:
    """Aggregate domestic + UEFA Champions League minutes for peer loading.

    This powers builder selection only; report export still needs governed
    combined artifacts before the final HTML can render aggregate metrics.
    """
    variants = [item for item in season_variants(season) if len(item) == 4 and item.isdigit()]
    if not variants:
        return pd.DataFrame()
    season_code = variants[0]
    player_dir = SOCCERDB_ROOT / "data" / "players"
    features_dir = SOCCERDB_ROOT / "data" / "features"
    minutes_paths = [
        path for path in sorted(player_dir.glob(f"minutes_*_{season_code}.parquet"))
        if "UEFA-Europa_League" not in path.name
    ]
    if not minutes_paths:
        return pd.DataFrame()

    role_positions = {
        "DEF": {"CB", "FB"},
        "MID": {"MID"},
        "ATT": {"ATT", "ST"},
        "GK": {"GK"},
    }.get(role.upper(), set())
    frames = []
    name_frames = []
    for path in minutes_paths:
        df = pd.read_parquet(path)
        if not {"player_id", "team_id", "minutes_played", "position_code"}.issubset(df.columns):
            continue
        if role_positions:
            df = df[df["position_code"].astype(str).isin(role_positions)].copy()
        if df.empty:
            continue
        frames.append(df[["player_id", "team_id", "minutes_played"]])

        slug = path.stem.removeprefix("minutes_")
        events_path = features_dir / f"player_events_{slug}.parquet"
        if events_path.exists():
            events = pd.read_parquet(events_path, columns=["player_id", "player"])
            name_frames.append(events.dropna(subset=["player_id"]).drop_duplicates("player_id"))

    if not frames:
        return pd.DataFrame()
    minutes = pd.concat(frames, ignore_index=True)
    out = (
        minutes.assign(minutes_played=pd.to_numeric(minutes["minutes_played"], errors="coerce").fillna(0.0))
        .groupby(["player_id", "team_id"], as_index=False)["minutes_played"]
        .sum()
        .rename(columns={"minutes_played": "minutes", "player": "player_name"})
    )
    if name_frames:
        names = pd.concat(name_frames, ignore_index=True).drop_duplicates("player_id")
        out = out.merge(names.rename(columns={"player": "player_name"}), on="player_id", how="left")
    else:
        out["player_name"] = out["player_id"].map(lambda x: f"Player {int(x)}")
    out["player_name"] = out["player_name"].fillna(out["player_id"].map(lambda x: f"Player {int(x)}"))
    out["team_name"] = out["team_id"].map(lambda x: f"Team {int(x)}")
    out["competition"] = "Domestic leagues + UEFA-Champions League"
    out["season"] = int(season_code)
    out["macro_role"] = role.upper()
    out = apply_team_overrides(out, role)
    return out[["player_id", "player_name", "team_id", "team_name", "competition", "season", "macro_role", "minutes"]]


def combined_champions_metric_pool(role: str, season: str | None) -> pd.DataFrame:
    if role.upper() == "ALL":
        frames = [combined_champions_metric_pool(candidate, season) for candidate in ROLE_CHOICES]
        frames = [frame for frame in frames if not frame.empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    df = apply_team_overrides(unique_players(apply_season(role_df(role), season)), role)
    if "competition" not in df.columns:
        return pd.DataFrame()
    return df[df["competition"].astype(str).eq(COMBINED_CHAMPIONS_COMPETITION)].copy()


def domestic_metric_pool(role: str, season: str | None) -> pd.DataFrame:
    if role.upper() == "ALL":
        frames = [domestic_metric_pool(candidate, season) for candidate in ROLE_CHOICES]
        frames = [frame for frame in frames if not frame.empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    df = apply_team_overrides(unique_players(apply_season(role_df(role), season)), role)
    if "competition" in df.columns:
        df = df[~df["competition"].astype(str).eq(COMBINED_CHAMPIONS_COMPETITION)].copy()
    return df


def filter_peer_pool(df: pd.DataFrame, role: str, team: str, min_minutes: float) -> pd.DataFrame:
    out = df.copy()
    if team:
        matching_ids = [
            team_id for team_id, team_name in team_name_overrides(role).items()
            if search_key(team) in search_key(team_name)
        ]
        if {"team_name", "team_id"}.issubset(out.columns):
            by_name = out["team_name"].map(search_key).str.contains(search_key(team), regex=False, na=False)
            by_id = out["team_id"].astype(str).isin(matching_ids) if matching_ids else False
            out = out[by_name | by_id]
    if min_minutes and "minutes" in out.columns:
        out = out[pd.to_numeric(out["minutes"], errors="coerce").fillna(0) >= min_minutes]
    if {"minutes", "player_name"}.issubset(out.columns):
        out = out.sort_values(["minutes", "player_name"], ascending=[False, True])
    return out


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
                numeric = float(value)
                clean[key] = "" if numeric < 0 else int(numeric)
            else:
                clean[key] = value
        if not clean.get("availability"):
            clean["availability"] = "metrics"
        out.append(clean)
    return out


def metric_frame(role: str, season: str | None = None) -> pd.DataFrame:
    df = role_df(role)
    if "minutes_played" in df.columns and "minutes" not in df.columns:
        df = df.rename(columns={"minutes_played": "minutes"})
    return apply_season(df, season)


def player_records(role: str, ids: str, season: str | None) -> list[dict[str, Any]]:
    wanted = split_ids(ids)
    if not wanted:
        return []
    df = apply_team_overrides(unique_players(metric_frame(role, season)), role)
    rows = df[df["player_id"].astype(str).isin(wanted)].copy()
    if rows.empty:
        return [{"player_id": pid, "availability": "missing in role metrics"} for pid in wanted]
    order = {pid: idx for idx, pid in enumerate(wanted)}
    rows["_order"] = rows["player_id"].astype(str).map(order).fillna(999)
    return rows_for_response(rows.sort_values("_order"))


def records_by_ids(role: str, ids: str, season: str | None, competition: str | None = None) -> pd.DataFrame:
    wanted = split_ids(ids)
    if not wanted:
        return pd.DataFrame()
    df = apply_team_overrides(unique_players(metric_frame(role, season)), role)
    if competition and "competition" in df.columns:
        df = df[df["competition"].astype(str).eq(str(competition))]
    rows = df[df["player_id"].astype(str).isin(wanted)].copy()
    if rows.empty:
        return rows
    order = {pid: idx for idx, pid in enumerate(wanted)}
    rows["_order"] = rows["player_id"].astype(str).map(order).fillna(999)
    return rows.sort_values("_order")


def metric_highlights(role: str, player_id: str, season: str | None, limit: int = 8) -> dict[str, Any]:
    df = metric_frame(role, season)
    rows = df[df["player_id"].astype(str).eq(str(player_id))].copy()
    if rows.empty:
        return {"available": False, "message": f"player not found in {role} metrics"}
    cols = [c for c in ["metric_group", "metric_label", "raw_value", "percentile_global"] if c in rows.columns]
    rows = rows[cols].dropna(subset=["metric_label"]).copy()
    rows["percentile_global"] = pd.to_numeric(rows.get("percentile_global"), errors="coerce")
    rows["raw_value"] = pd.to_numeric(rows.get("raw_value"), errors="coerce")
    high = rows.sort_values("percentile_global", ascending=False).head(limit)
    low = rows.sort_values("percentile_global", ascending=True).head(max(3, limit // 2))

    def compact(frame: pd.DataFrame) -> list[dict[str, Any]]:
        out = []
        for row in frame.to_dict("records"):
            out.append(
                {
                    "group": row.get("metric_group", ""),
                    "metric": row.get("metric_label", ""),
                    "raw": None if pd.isna(row.get("raw_value")) else round(float(row.get("raw_value")), 3),
                    "percentile": None
                    if pd.isna(row.get("percentile_global"))
                    else round(float(row.get("percentile_global")), 1),
                }
            )
        return out

    return {"available": True, "top_strengths": compact(high), "lower_percentiles": compact(low)}


def peer_group_summary(role: str, ids: str, season: str | None, limit: int = 8) -> dict[str, Any]:
    wanted = split_ids(ids)
    if not wanted:
        return {"players": [], "metric_averages": []}
    df = metric_frame(role, season)
    rows = df[df["player_id"].astype(str).isin(wanted)].copy()
    players = player_records(role, ids, season)
    if rows.empty:
        return {"players": players, "metric_averages": []}
    rows["percentile_global"] = pd.to_numeric(rows.get("percentile_global"), errors="coerce")
    rows["raw_value"] = pd.to_numeric(rows.get("raw_value"), errors="coerce")
    grouped = (
        rows.groupby(["metric_group", "metric_label"], dropna=False)
        .agg(avg_raw=("raw_value", "mean"), avg_percentile=("percentile_global", "mean"), players=("player_id", "nunique"))
        .reset_index()
    )
    grouped = grouped[grouped["players"].ge(1)].sort_values("avg_percentile", ascending=False).head(limit)
    averages = []
    for row in grouped.to_dict("records"):
        averages.append(
            {
                "group": row.get("metric_group", ""),
                "metric": row.get("metric_label", ""),
                "avg_raw": None if pd.isna(row.get("avg_raw")) else round(float(row.get("avg_raw")), 3),
                "avg_percentile": None
                if pd.isna(row.get("avg_percentile"))
                else round(float(row.get("avg_percentile")), 1),
            }
        )
    return {"players": players, "metric_averages": averages}


def target_similarity_summary(
    role: str,
    player_id: str,
    comparison_ids: str,
    use_overrides: bool = False,
    top_n: int = 4,
) -> dict[str, Any]:
    wanted = [int(pid) for pid in split_ids(comparison_ids)]
    if not wanted:
        return {"available": False, "reason": "no target comparison peers selected", "spaces": []}
    exporter_path = SOCCERDB_ROOT / "scripts" / "exports" / "export_role_report_data.py"
    if not exporter_path.exists():
        return {"available": False, "reason": f"exporter not found: {exporter_path}", "spaces": []}
    try:
        import importlib.util

        module_name = "_pasta_export_role_report_data"
        spec = importlib.util.spec_from_file_location(module_name, exporter_path)
        if spec is None or spec.loader is None:
            return {"available": False, "reason": "could not load role exporter module", "spaces": []}
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        module.DATA = FEATURES
        module.PLAYER_DATA = SOCCERDB_ROOT / "data" / "players"
        files = module.role_files(role, use_overrides=use_overrides)
        dfs = module.load_files(files)
        spaces = module.get_direct_similarity(dfs, role, int(player_id), wanted, top_n)
    except Exception as exc:
        return {"available": False, "reason": str(exc), "spaces": []}

    compact_spaces = []
    for space in spaces:
        matches = [
            {
                "player_id": item.get("id"),
                "player_name": item.get("name"),
                "score": item.get("score"),
            }
            for item in space.get("matches", [])
        ]
        compact_spaces.append(
            {
                "key": space.get("key"),
                "space": space.get("space"),
                "description": space.get("description", ""),
                "matches": matches,
            }
        )
    return {
        "available": any(space["matches"] for space in compact_spaces),
        "scope": "selected target-team comparison peers",
        "spaces": compact_spaces,
    }


def prompt_data(data: dict[str, Any], source_role: str, report_role: str, source_context_exported: bool) -> dict[str, Any]:
    season = str(data.get("season") or "")
    return {
        "subject_source_role_metrics": metric_highlights(source_role, str(data.get("player_id")), season),
        "subject_report_role_metrics": metric_highlights(report_role, str(data.get("player_id")), season),
        "target_team_peers_report_role": peer_group_summary(report_role, str(data.get("main_comparison_peer_ids") or ""), season),
        "source_context_peers_source_role": peer_group_summary(source_role, str(data.get("source_team_peer_ids") or ""), season),
        "target_similarity_report_role": target_similarity_summary(
            report_role,
            str(data.get("player_id")),
            str(data.get("main_comparison_peer_ids") or ""),
            bool(data.get("use_manual_role_overrides")),
        ),
        "source_context_exported": source_context_exported,
    }


def existing_asset_editorial_brief(slug: str) -> str:
    if not slug or not PLAYER_INDEX.exists():
        return ""
    try:
        sys.path.insert(0, str(ROOT))
        from generate_editorial_brief import build_brief  # noqa: PLC0415

        players = json.loads(PLAYER_INDEX.read_text(encoding="utf-8"))
        player = next((item for item in players if item.get("slug") == slug), None)
        if not player or not player.get("payload_file"):
            return ""
        payload_path = ROOT / player["payload_file"]
        if not payload_path.exists():
            return ""
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        return build_brief(player, payload)
    except Exception:
        return ""


def planned_editorial_brief(data: dict[str, Any], data_block: dict[str, Any], source_role: str, report_role: str, reason: str) -> str:
    heatmap_fourth = "Azioni difensive" if report_role == "DEF" else "Progressione via passaggio"
    heatmap_focus = (
        "work-rate difensivo e altezza della difesa attiva"
        if report_role == "DEF"
        else "progressione tramite passaggio, non azioni difensive"
    )
    role_plural = {"GK": "portieri", "DEF": "difensori", "MID": "centrocampisti", "ATT": "attaccanti"}.get(report_role, "giocatori")
    return f"""# Brief editoriale pianificato — {data.get('player_name')}
**Ruolo sorgente**: {source_role} · **Ruolo report**: {report_role} · **Destinazione**: {data.get('target_team')} · **Stagione**: {data.get('season')} · **Campionato**: {data.get('competition')}
**Club di provenienza**: {data.get('team_name')}
**Motivo role override**: {reason or "nessuno; ruolo sorgente e ruolo report coincidono"}

---
## § Profilo radar
Il radar del report verrà costruito nel ruolo **{report_role}** contro il gruppo target **{data.get('comparison_label')}**.
Target-team peers selezionati: {data.get('main_comparison_peer_ids')}.

Usare questa sezione per leggere il profilo nel contesto target: cosa porta, cosa cambia, dove differisce dal gruppo del club target.

---
## § Confronto individuale vs {data.get('target_team')}
Il confronto tecnico principale usa i peer del target team nel ruolo report.
Non descrivere questo gruppo come source-team peers.

---
## § Impronta spaziale
Mappe previste: impronta posizionale, direzione conduzioni, distribuzione passaggi, **{heatmap_fourth}**.
Focus editoriale per {report_role}: {heatmap_focus}.

---
## § Contesto {data.get('team_name')}
Source-context peers selezionati: {data.get('source_team_peer_label')} = {data.get('source_team_peer_ids') or "(nessuno)"}.
Questi peer servono a spiegare come il profilo emerge nel club sorgente.
Source-context esportato come context IDs: {data_block.get('source_context_exported')}.

---
## § Similarità vs {data.get('target_team')}
La similarità, quando il payload verrà generato, va letta nel ruolo report **{report_role}** e rispetto al gruppo target.

---
## Dati disponibili prima della generazione payload
```json
{json.dumps(data_block, ensure_ascii=False, indent=2)}
```

---
## PROMPT PER L'AI

Sei il redattore di una pubblicazione italiana di scouting calcistico.
Usa il brief qui sopra per scrivere una narrative iniziale e 4 note editoriali in italiano per il report di **{data.get('player_name')}**.

**Regole:**
- Tono: interpretativo, editoriale. Guida il lettore, non elencare dati.
- Lunghezza narrative: 1 paragrafo da 3–4 frasi.
- Lunghezza note: 2–3 frasi compatte per nota.
- Usa i dati come base di ragionamento, non come lista.
- Audience: direttori sportivi e analisti calcistici.
- Evita frasi come «i dati mostrano» o «il grafico indica».
- Se source_role e report_role differiscono, non descriverlo come errore dati: spiega la conversione tattica.

**Campi da produrre:**

1. **narrative** — Incipit editoriale: che tipo di profilo è {data.get('player_name')}, perché è interessante per {data.get('target_team')}, e quale cautela interpretativa serve?
2. **source_team_note** — Nota breve opzionale sul contesto del club sorgente.
3. **note_confronto** — Come si colloca {data.get('player_name')} rispetto ai {role_plural} del {data.get('target_team')}?
4. **note_heatmap** — Cosa rivela l'impronta spaziale? Attenzione al quarto riquadro: **{heatmap_fourth}**.
5. **note_context** — Cosa dice il confronto/source context nel club di provenienza?
6. **note_similarity** — Come leggere la similarità rispetto al gruppo target?
"""


def search_players(params: dict[str, list[str]]) -> dict[str, Any]:
    role = params.get("role", ["ALL"])[0].upper()
    query = params.get("query", [""])[0]
    season = params.get("season", ["2025-2026"])[0]
    include_champions = params.get("include_champions", ["0"])[0] in {"1", "true", "yes", "on"}
    if include_champions:
        df = combined_champions_metric_pool(role, season)
        if df.empty:
            df = domestic_metric_pool(role, season)
    else:
        df = domestic_metric_pool(role, season)
    index_df = index_player_pool(role, season)
    if not index_df.empty:
        if df.empty:
            df = index_df
        else:
            df = pd.concat([df, index_df], ignore_index=True)
            subset = [col for col in ["player_id", "competition", "season", "macro_role"] if col in df.columns]
            if subset:
                df = df.drop_duplicates(subset=subset, keep="first")
    if query:
        needle = search_key(query)
        df = df[df["player_name"].map(search_key).str.contains(needle, regex=False, na=False)]
        if include_champions and df.empty:
            fallback = domestic_metric_pool(role, season)
            df = fallback[fallback["player_name"].map(search_key).str.contains(needle, regex=False, na=False)]
    if "minutes" in df.columns:
        df = df.assign(_minutes_sort=pd.to_numeric(df["minutes"], errors="coerce").fillna(-1))
        df = df.sort_values(["_minutes_sort", "player_name"], ascending=[False, True]).drop(columns=["_minutes_sort"])
    elif "player_name" in df.columns:
        df = df.sort_values("player_name")
    return {"players": rows_for_response(df)}


def target_peers(params: dict[str, list[str]]) -> dict[str, Any]:
    role = params.get("role", ["DEF"])[0].upper()
    team = params.get("team", [""])[0]
    season = params.get("season", ["2025-2026"])[0]
    min_minutes = float(params.get("min_minutes", ["300"])[0] or 0)
    include_champions = params.get("include_champions", ["0"])[0] in {"1", "true", "yes", "on"}
    warning = ""
    if include_champions:
        df = combined_champions_metric_pool(role, season)
        if df.empty:
            df = combined_minutes_peer_pool(role, season)
        filtered = filter_peer_pool(df, role, team, min_minutes)
        if filtered.empty:
            df = domestic_metric_pool(role, season)
            filtered = filter_peer_pool(df, role, team, min_minutes)
            if not filtered.empty:
                warning = "Champions League scope unavailable for this team/season; using domestic league only."
    else:
        df = domestic_metric_pool(role, season)
        filtered = filter_peer_pool(df, role, team, min_minutes)
    players = rows_for_response(filtered)
    error = ""
    if not players:
        parts = [role]
        if team:
            parts.append(f"team '{team}'")
        if season:
            parts.append(f"season '{season}'")
        if min_minutes:
            parts.append(f"min {int(min_minutes)} minutes")
        scope = "domestic + Champions League" if include_champions else "domestic role artifact"
        error = "No target-team peers found for " + ", ".join(parts) + f" in {scope}."
    competition_scope = ""
    if players:
        competition_scope = str(filtered.iloc[0].get("competition", ""))
    return {
        "players": players,
        "error": error,
        "warning": warning,
        "include_champions": include_champions and competition_scope == COMBINED_CHAMPIONS_COMPETITION,
        "competition_scope": competition_scope,
    }


def source_peers(params: dict[str, list[str]]) -> dict[str, Any]:
    role = params.get("role", ["DEF"])[0].upper()
    player_id = params.get("player_id", [""])[0]
    season = params.get("season", ["2025-2026"])[0]
    min_minutes = float(params.get("min_minutes", ["300"])[0] or 0)
    include_champions = params.get("include_champions", ["0"])[0] in {"1", "true", "yes", "on"}
    warning = ""
    if include_champions:
        df = combined_champions_metric_pool(role, season)
        subject_rows = df[df["player_id"].astype(str).eq(str(player_id))] if "player_id" in df.columns else pd.DataFrame()
        if subject_rows.empty:
            df = domestic_metric_pool(role, season)
            warning = "Champions League scope unavailable for this source team/season; using domestic league only."
    else:
        df = domestic_metric_pool(role, season)
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
    competition_scope = str(subject.get("competition", ""))
    return {
        "subject": rows_for_response(pd.DataFrame([subject]))[0],
        "players": rows_for_response(peers),
        "warning": warning,
        "include_champions": include_champions and competition_scope == COMBINED_CHAMPIONS_COMPETITION,
        "competition_scope": competition_scope,
    }


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
    season = str(data.get("season") or "")
    comparison_season = str(data.get("comparison_season") or season)
    subject_competition = str(data.get("subject_competition_scope") or data.get("competition") or "")
    comparison_competition = str(data.get("comparison_competition_scope") or data.get("competition") or "")
    context_competition = str(data.get("source_context_competition_scope") or subject_competition or data.get("competition") or "")
    player_id = str(data.get("player_id") or "")
    subject_rows = records_by_ids(report_role, player_id, season, subject_competition)
    if subject_rows.empty:
        override_path = FEATURES / f"scouting_view_metrics_v1_{report_role.lower()}_with_overrides.parquet"
        if override_path.exists():
            override_df = pd.read_parquet(override_path)
            override_match = override_df[override_df["player_id"].astype(str).eq(str(player_id))]
            if not override_match.empty:
                data["use_manual_role_overrides"] = True
            else:
                raise ValueError(
                    f"player_id {player_id} is not present in {report_role} metrics or override artifacts. "
                    f"Run build_manual_role_override_artifacts.py first."
                )
        else:
            raise ValueError(
                f"player_id {player_id} is not present in {report_role} metrics. "
                f"Generate the report as {source_role} or rebuild the analytics role layer before using {report_role}."
            )
    target_peer_rows = records_by_ids(
        report_role,
        str(data.get("main_comparison_peer_ids") or ""),
        comparison_season,
        comparison_competition,
    )
    found_target_ids = set(target_peer_rows["player_id"].astype(str).tolist()) if not target_peer_rows.empty else set()
    missing_target = [pid for pid in split_ids(data.get("main_comparison_peer_ids")) if pid not in found_target_ids]
    if missing_target and comparison_competition:
        fallback_target_rows = records_by_ids(
            report_role,
            str(data.get("main_comparison_peer_ids") or ""),
            comparison_season,
            None,
        )
        fallback_ids = set(fallback_target_rows["player_id"].astype(str).tolist()) if not fallback_target_rows.empty else set()
        if all(pid in fallback_ids for pid in split_ids(data.get("main_comparison_peer_ids"))):
            scopes = fallback_target_rows["competition"].dropna().astype(str).unique().tolist() if "competition" in fallback_target_rows.columns else []
            if len(scopes) == 1:
                comparison_competition = scopes[0]
                data["comparison_competition_scope"] = comparison_competition
                target_peer_rows = fallback_target_rows
                found_target_ids = fallback_ids
                missing_target = []
    if missing_target:
        override_path = FEATURES / f"scouting_view_metrics_v1_{report_role.lower()}_with_overrides.parquet"
        if override_path.exists():
            override_df = pd.read_parquet(override_path)
            override_ids = set(override_df["player_id"].astype(str).unique())
            still_missing = [pid for pid in missing_target if pid not in override_ids]
            if still_missing:
                raise ValueError(f"main/radar peer IDs missing in {report_role} metrics and overrides: {','.join(still_missing)}")
            data["use_manual_role_overrides"] = True
        else:
            raise ValueError(f"main/radar peer IDs missing in {report_role} metrics: {','.join(missing_target)}")
    target_team = str(data.get("target_team") or "").strip()
    if target_team and not target_peer_rows.empty:
        bad_team = target_peer_rows[
            ~target_peer_rows["team_name"].map(search_key).str.contains(search_key(target_team), regex=False, na=False)
        ]
        if not bad_team.empty:
            bad = ", ".join(
                f"{int(row.player_id)} {row.player_name} ({row.team_name})"
                for row in bad_team.itertuples()
            )
            raise ValueError(f"main/radar peers must belong to target team {target_team}: {bad}")
    source_ids = str(data.get("source_team_peer_ids") or "").strip()
    if source_ids:
        source_rows = records_by_ids(source_role, source_ids, season, context_competition)
        found_source_ids = set(source_rows["player_id"].astype(str).tolist()) if not source_rows.empty else set()
        missing_source = [pid for pid in split_ids(source_ids) if pid not in found_source_ids]
        if missing_source:
            raise ValueError(f"source-context peer IDs missing in {source_role} metrics: {','.join(missing_source)}")
    source_context_exported = source_role == report_role or bool(data.get("use_manual_role_overrides"))
    return source_role, report_role, reason, source_context_exported


def prompt_from_payload(data: dict[str, Any]) -> str:
    source_role, report_role, reason, source_context_exported = validate_workflow_payload(data)
    data_block = prompt_data(data, source_role, report_role, source_context_exported)
    asset_brief = existing_asset_editorial_brief(str(data.get("slug") or ""))
    if asset_brief:
        brief = f"""{asset_brief}

---
## Dati disponibili per questo prompt
```json
{json.dumps(data_block, ensure_ascii=False, indent=2)}
```
"""
    else:
        brief = planned_editorial_brief(data, data_block, source_role, report_role, reason)
    brief_source = "asset/generated payload brief" if asset_brief else "planned GUI brief"
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

Manual role override: {"yes — player was recomputed in " + report_role + " from raw events; original classification was " + source_role if data.get("use_manual_role_overrides") else "no — player is in canonical " + report_role + " metrics"}
Available blocks: radar, metric bars, {"heatmap (may be unavailable for override players)" if data.get("use_manual_role_overrides") else "heatmap"}, volume similarity, action mix similarity, {"territorial similarity (may be unavailable)" if data.get("use_manual_role_overrides") else "territorial similarity"}, {"PCA (may be unavailable)" if data.get("use_manual_role_overrides") else "PCA"}

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
- If this is a manual role override, do not describe it as a data error. Explain it as a tactical role projection. Mention that the player has been recomputed in the report role where relevant.

Editorial brief source: {brief_source}

{brief}
"""


def build_create_command(data: dict[str, Any], dry_run: bool) -> list[str]:
    source_role, report_role, reason, source_context_exported = validate_workflow_payload(data)
    slug = str(data.get("slug") or "").strip() or slugify_name(data.get("player_name"))
    data["slug"] = slug
    cmd = [
        str(PYTHON if PYTHON.exists() else Path(sys.executable)),
        "scripts/create_player_page_from_export.py",
        "--role", report_role,
        "--source-role", source_role,
        "--soccerdb-root", str(SOCCERDB_ROOT),
        "--player-id", str(data["player_id"]),
        "--player-name", data["player_name"],
        "--slug", slug,
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
    if data.get("subject_competition_scope"):
        cmd.extend(["--subject-competition", str(data["subject_competition_scope"])])
    if data.get("comparison_competition_scope"):
        cmd.extend(["--comparison-competition", str(data["comparison_competition_scope"])])
    if data.get("source_context_competition_scope"):
        cmd.extend(["--context-competition", str(data["source_context_competition_scope"])])
    if reason:
        cmd.extend(["--role-override-reason", reason])
    if data.get("source_team_peer_ids"):
        cmd.extend(["--source-team-peer-ids", data.get("source_team_peer_ids", "")])
        cmd.extend(["--source-team-peer-label", data.get("source_team_peer_label", "")])
    if not source_context_exported:
        cmd.append("--source-context-editorial-only")
    if data.get("use_manual_role_overrides"):
        cmd.append("--use-manual-role-overrides")
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
        "url": f"/{data.get('slug')}.html",
    }


def check_role_override_status(data: dict[str, Any]) -> dict[str, Any]:
    """Check whether canonical and override metrics exist for a player in report_role."""
    report_role = str(data.get("report_role") or data.get("role") or "").upper()
    player_id = str(data.get("player_id") or "")
    season = str(data.get("season") or "")
    source_role = str(data.get("source_role") or "").upper()

    result: dict[str, Any] = {
        "player_id": player_id,
        "source_role": source_role,
        "report_role": report_role,
        "in_canonical": False,
        "in_overrides": False,
        "override_artifacts_exist": False,
        "override_registered": False,
        "available_blocks": {
            "radar": False,
            "metric_bars": False,
            "heatmap": False,
            "volume_similarity": False,
            "action_mix_similarity": False,
            "territorial_similarity": False,
            "pca": False,
        },
    }

    canonical_rows = records_by_ids(report_role, player_id, season)
    result["in_canonical"] = not canonical_rows.empty

    r = report_role.lower()
    override_metrics_path = FEATURES / f"scouting_view_metrics_v1_{r}_with_overrides.parquet"
    override_bench_path = FEATURES / f"global_benchmarks_{report_role}_with_overrides.parquet"
    override_heatmap_path = FEATURES / f"{r}_heatmap_view_v2_with_overrides.parquet"
    override_sim_vol_path = FEATURES / f"{r}_similarity_volume_v1_with_overrides.parquet"
    override_sim_mix_path = FEATURES / f"{r}_similarity_action_mix_v1_with_overrides.parquet"
    override_sim_ter_path = FEATURES / f"{r}_similarity_territorial_v1_with_overrides.parquet"
    override_pca_path = FEATURES / f"player_global_pca_projection_v1_{r}_with_overrides.parquet"

    result["override_artifacts_exist"] = override_metrics_path.exists()

    if override_metrics_path.exists():
        override_df = pd.read_parquet(override_metrics_path)
        override_match = override_df[override_df["player_id"].astype(str).eq(player_id)]
        result["in_overrides"] = not override_match.empty

    if OVERRIDE_CSV.exists():
        import csv as csv_mod
        with open(OVERRIDE_CSV, newline="", encoding="utf-8") as f:
            for row in csv_mod.DictReader(f):
                if str(row.get("player_id", "")) == player_id and row.get("enabled", "").strip().lower() == "true":
                    result["override_registered"] = True
                    break

    available = result["in_canonical"] or result["in_overrides"]
    result["available_blocks"]["radar"] = available
    result["available_blocks"]["metric_bars"] = available

    if result["in_canonical"]:
        heatmap_path = FEATURES / f"{r}_heatmap_view_v2.parquet"
        if not heatmap_path.exists():
            heatmap_path = FEATURES / f"{r}_heatmap_view_v1.parquet"
        if heatmap_path.exists():
            hm_df = pd.read_parquet(heatmap_path, columns=["player_id"])
            result["available_blocks"]["heatmap"] = player_id in hm_df["player_id"].astype(str).values
    elif result["in_overrides"] and override_heatmap_path.exists():
        hm_df = pd.read_parquet(override_heatmap_path, columns=["player_id"])
        result["available_blocks"]["heatmap"] = player_id in hm_df["player_id"].astype(str).values

    def _player_in_parquet(path: Path) -> bool:
        if not path.exists():
            return False
        try:
            df = pd.read_parquet(path, columns=["player_id"])
            return player_id in df["player_id"].astype(str).values
        except Exception:
            return False

    if result["in_canonical"]:
        result["available_blocks"]["volume_similarity"] = _player_in_parquet(FEATURES / f"{r}_similarity_volume_v1.parquet")
        result["available_blocks"]["action_mix_similarity"] = _player_in_parquet(FEATURES / f"{r}_similarity_action_mix_v1.parquet")
        result["available_blocks"]["territorial_similarity"] = _player_in_parquet(FEATURES / f"{r}_similarity_territorial_v1.parquet")
        result["available_blocks"]["pca"] = _player_in_parquet(FEATURES / f"player_global_pca_projection_v1_{r}.parquet")
    elif result["in_overrides"]:
        result["available_blocks"]["volume_similarity"] = _player_in_parquet(override_sim_vol_path) or _player_in_parquet(FEATURES / f"{r}_similarity_volume_v1.parquet")
        result["available_blocks"]["action_mix_similarity"] = _player_in_parquet(override_sim_mix_path) or _player_in_parquet(FEATURES / f"{r}_similarity_action_mix_v1.parquet")
        result["available_blocks"]["territorial_similarity"] = _player_in_parquet(override_sim_ter_path) or _player_in_parquet(FEATURES / f"{r}_similarity_territorial_v1.parquet")
        result["available_blocks"]["pca"] = _player_in_parquet(override_pca_path) or _player_in_parquet(FEATURES / f"player_global_pca_projection_v1_{r}.parquet")

    return result


def upsert_role_override(data: dict[str, Any]) -> dict[str, Any]:
    """Write or update a row in the manual role overrides CSV."""
    import csv as csv_mod

    required = ["player_id", "player_name", "source_role", "report_role", "season", "competition", "team_name", "target_team", "reason"]
    missing = [k for k in required if not str(data.get(k, "")).strip()]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

    new_row = {
        "player_id": str(data["player_id"]).strip(),
        "player_name": str(data["player_name"]).strip(),
        "source_role": str(data["source_role"]).upper().strip(),
        "report_role": str(data["report_role"]).upper().strip(),
        "season": str(data["season"]).strip(),
        "competition": str(data["competition"]).strip(),
        "team_name": str(data["team_name"]).strip(),
        "target_team": str(data["target_team"]).strip(),
        "reason": str(data["reason"]).strip(),
        "enabled": "true",
    }

    fieldnames = ["player_id", "player_name", "source_role", "report_role", "season", "competition", "team_name", "target_team", "reason", "enabled"]
    rows: list[dict[str, str]] = []
    updated = False

    if OVERRIDE_CSV.exists():
        with open(OVERRIDE_CSV, newline="", encoding="utf-8") as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                if str(row.get("player_id", "")) == new_row["player_id"]:
                    rows.append(new_row)
                    updated = True
                else:
                    rows.append(row)

    if not updated:
        rows.append(new_row)

    OVERRIDE_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OVERRIDE_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv_mod.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return {"ok": True, "action": "updated" if updated else "created", "row": new_row}


def run_override_builder() -> dict[str, Any]:
    """Run build_manual_role_override_artifacts.py and return output."""
    python = str(PYTHON if PYTHON.exists() else Path(sys.executable))
    cmd = [python, str(OVERRIDE_BUILDER)]
    result = subprocess.run(cmd, cwd=str(SOCCERDB_ROOT), text=True, capture_output=True, timeout=300)
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "command": cmd,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def regenerate_cards(data: dict[str, Any]) -> dict[str, Any]:
    slug = data.get("slug", "")
    cmd = [sys.executable, "assets/cards/generate_cards.py", "--slug", slug, "--version", "all"]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    return {"ok": result.returncode == 0, "returncode": result.returncode, "command": cmd, "stdout": result.stdout, "stderr": result.stderr}


def _path_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def assert_dogana_output_allowed(output_root: Path) -> None:
    if _path_inside(output_root, SOCCERDB_ROOT):
        raise ValueError(f"output path rejected: Dogana output root cannot be inside SoccerDB: {output_root}")


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def write_simple_yaml(path: Path, payload: dict[str, Any]) -> None:
    lines: list[str] = []
    for key, value in payload.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            if value:
                lines.extend(f"  - {_yaml_scalar(item)}" for item in value)
            else:
                lines.append("  []")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def dogana_required_field_errors(data: dict[str, Any]) -> list[str]:
    required = {
        "player_id": "player id",
        "player_name": "player name",
        "role": "report role",
        "competition": "source competition",
        "season": "source season",
        "target_team": "target team",
    }
    return [label for key, label in required.items() if not str(data.get(key) or "").strip()]


POSITION_TO_DOGANA_SPATIAL_FAMILY = {
    "CB": "centre_back",
    "LCB": "centre_back",
    "RCB": "centre_back",
    "FB": "fullback",
    "LB": "fullback",
    "RB": "fullback",
    "LWB": "wingback",
    "RWB": "wingback",
    "WB": "wingback",
    "DM": "holding_midfielder",
    "CDM": "holding_midfielder",
    "MID": "central_midfielder",
    "CM": "central_midfielder",
    "AM": "attacking_midfielder",
    "CAM": "attacking_midfielder",
    "LM": "wide_midfielder",
    "RM": "wide_midfielder",
    "ST": "striker",
    "CF": "striker",
    "ATT": "wide_forward",
    "LW": "wide_forward",
    "RW": "wide_forward",
    "SS": "second_striker",
}


def dogana_target_team_id(role: str, ids: list[int], season: str | None) -> tuple[int | None, list[str]]:
    rows = records_by_ids(role, ",".join(str(pid) for pid in ids), season)
    if rows.empty or "team_id" not in rows.columns:
        return None, []
    team_ids = sorted({int(value) for value in rows["team_id"].dropna().tolist()})
    if len(team_ids) == 1:
        return team_ids[0], []
    if len(team_ids) > 1:
        return None, [f"Dogana target_team_id not set because selected peers span multiple team IDs: {team_ids}"]
    return None, []


def dogana_spatial_role_family(role: str, player_id: str, season: str | None) -> str | None:
    rows = records_by_ids(role, player_id, season)
    if not rows.empty and "dominant_position" in rows.columns:
        position = str(rows.iloc[0].get("dominant_position") or "").strip().upper()
        family = POSITION_TO_DOGANA_SPATIAL_FAMILY.get(position)
        if family:
            return family
    benchmark_path = FEATURES / f"global_benchmarks_{role}.parquet"
    if not benchmark_path.exists():
        return None
    try:
        benchmark = pd.read_parquet(benchmark_path, columns=["player_id", "season", "minutes_played", "dominant_position"])
    except Exception:
        return None
    rows = benchmark[benchmark["player_id"].astype(str).eq(str(player_id))].copy()
    variants = season_variants(season)
    if variants and "season" in rows.columns:
        rows = rows[rows["season"].astype(str).isin(variants)]
    if rows.empty:
        return None
    rows["minutes_played"] = pd.to_numeric(rows.get("minutes_played"), errors="coerce").fillna(0.0)
    position = str(rows.sort_values("minutes_played", ascending=False).iloc[0].get("dominant_position") or "").strip().upper()
    return POSITION_TO_DOGANA_SPATIAL_FAMILY.get(position)


def build_dogana_config(data: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], list[str], str]:
    warnings: list[str] = []
    errors = dogana_required_field_errors(data)
    if errors:
        return None, warnings, [f"missing required fields: {', '.join(errors)}"], "missing required fields"

    target_peer_ids = [int(pid) for pid in split_ids(data.get("main_comparison_peer_ids"))]
    if not target_peer_ids:
        return None, warnings, ["no target peers selected"], "no target peers selected"

    report_role = str(data.get("report_role") or data.get("role") or "").upper()
    source_role = str(data.get("source_role") or report_role).upper()
    if report_role not in ROLE_CHOICES:
        return None, warnings, [f"missing required fields: report role must be one of {', '.join(ROLE_CHOICES)}"], "missing required fields"

    season = season_to_int(data.get("season"))
    slug = slugify_underscore(data.get("dogana_slug") or data.get("player_name") or data.get("slug"))
    target_team_id, team_id_warnings = dogana_target_team_id(report_role, target_peer_ids, str(data.get("season") or ""))
    warnings.extend(team_id_warnings)
    spatial_role_family = dogana_spatial_role_family(report_role, str(data.get("player_id")), str(data.get("season") or ""))
    use_manual_role_overrides = bool(data.get("use_manual_role_overrides")) or bool(data.get("role_override_reason"))
    if use_manual_role_overrides:
        warnings.append(
            "Manual role override present. Dogana V1 uses canonical role artifacts; _with_overrides artifacts are not read yet."
        )

    return (
        {
            "player_id": int(data["player_id"]),
            "player_name": str(data["player_name"]).strip(),
            "player_slug": slug,
            "macro_role": report_role,
            "source_competition": str(data["competition"]).strip(),
            "source_season": season,
            "target_competition": "ITA-Serie A",
            "target_season": season,
            "target_team_id": target_team_id,
            "target_team_name": str(data["target_team"]).strip(),
            "target_same_role_player_ids": target_peer_ids,
            "min_minutes": 100,
            "meaningful_peer_minutes": 600,
            "top_n_metrics": 8,
            "context_visual_mode": "two_evidence_blocks",
            "show_target_peer_chip": False,
            "enable_context_threshold_lines": False,
            "enable_context_quadrant_labels": False,
            "seriea_similarity_methods": ["pasta_distilled", "pca_knn", "euclidean_zscore"],
            "selected_seriea_similarity_method": None,
            "selected_seriea_comparable_player_id": None,
            "spatial_role_family": spatial_role_family,
            "enable_origin_uniqueness": False,
            "origin_uniqueness_root": str(EXPERIMENTS_ROOT / "player_uniqueness"),
            "origin_uniqueness_scope": "local",
            "origin_uniqueness_top_pairs": 3,
            "origin_uniqueness_min_minutes": 300,
            "origin_uniqueness_method_status": "provisional",
            "slide03_extreme_metric_count": 3,
            "generate_short_video_pack": bool(data.get("generate_short_video_pack")),
            "short_video_mode": bool(data.get("short_video_mode")),
            "context_status": str(data.get("context_status") or "stable"),
            "context_note": str(data.get("context_note") or ""),
            "use_manual_role_overrides": use_manual_role_overrides,
            "source_role": source_role,
            "role_override_reason": str(data.get("role_override_reason") or "").strip(),
        },
        warnings,
        [],
        "config ready",
    )


def dogana_generated_files(output_folder: Path) -> list[str]:
    if not output_folder.exists():
        return []
    return [str(path) for path in sorted(output_folder.rglob("*")) if path.is_file()]


def dogana_summary_warnings(output_folder: Path) -> list[str]:
    summary_path = output_folder / "dogana_summary.json"
    if not summary_path.exists():
        return []
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"Could not read Dogana summary warnings: {exc}"]

    warnings: list[str] = []
    quality_maps = summary.get("part_1_player_quality", {}).get("quality_maps", {})
    missing_warning = quality_maps.get("missing_heatmap_warning")
    if missing_warning:
        warnings.append(f"Heatmap warning: {missing_warning}")
    if quality_maps.get("fallback_used"):
        warnings.append(
            "Heatmap fallback used: "
            f"{quality_maps.get('selected_heatmap_block') or 'unknown'} "
            f"instead of {quality_maps.get('preferred_heatmap_block') or 'preferred block'}."
        )
    missing_blocks = quality_maps.get("missing_panels_or_blocks") or []
    if missing_blocks:
        warnings.append(f"Missing heatmap blocks: {', '.join(str(item) for item in missing_blocks)}")

    summary_warnings = summary.get("warnings", {})
    missing_panels = summary_warnings.get("missing_heatmap_panels") or []
    if missing_panels and missing_panels != missing_blocks:
        warnings.append(f"Missing heatmap panels: {', '.join(str(item) for item in missing_panels)}")
    return warnings


def dogana_clean_failure(stderr: str, config: dict[str, Any]) -> dict[str, Any] | None:
    artifact = f"global_benchmarks_{config.get('macro_role')}.parquet"
    needle = f"Player {config.get('player_id')} not found in global_benchmarks_{config.get('macro_role')}."
    if needle not in stderr:
        return None
    error: dict[str, Any] = {
        "message": "Player not found in canonical role artifacts for selected role.",
        "player_id": config.get("player_id"),
        "selected_macro_role": config.get("macro_role"),
        "source_competition": config.get("source_competition"),
        "source_season": config.get("source_season"),
        "artifact": artifact,
    }
    if config.get("use_manual_role_overrides"):
        error["hint"] = "Manual role overrides are passed as metadata, but Dogana does not yet read _with_overrides artifacts."
    return {
        "status": "missing canonical role artifact player",
        "errors": [error],
    }


def run_dogana(data: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    stdout = ""
    stderr = ""
    config_path = ""
    output_folder = ""

    try:
        assert_dogana_output_allowed(DOGANA_OUTPUT_ROOT)
    except Exception as exc:
        return {
            "ok": False,
            "status": "output path rejected",
            "config_path": config_path,
            "output_folder": output_folder,
            "generated_files": [],
            "stdout": stdout,
            "stderr": stderr,
            "warnings": warnings,
            "errors": [str(exc)],
        }

    try:
        config, cfg_warnings, cfg_errors, status = build_dogana_config(data)
    except Exception as exc:
        return {
            "ok": False,
            "status": "missing required fields",
            "config_path": config_path,
            "output_folder": output_folder,
            "generated_files": [],
            "stdout": stdout,
            "stderr": stderr,
            "warnings": warnings,
            "errors": [str(exc)],
        }

    warnings.extend(cfg_warnings)
    errors.extend(cfg_errors)
    if config is None:
        return {
            "ok": False,
            "status": status,
            "config_path": config_path,
            "output_folder": output_folder,
            "generated_files": [],
            "stdout": stdout,
            "stderr": stderr,
            "warnings": warnings,
            "errors": errors,
        }

    slug = str(config["player_slug"])
    config_file = DOGANA_CONFIG_DIR / f"{slug}.yml"
    out_dir = DOGANA_OUTPUT_ROOT / slug
    config_path = str(config_file)
    output_folder = str(out_dir)
    write_simple_yaml(config_file, config)

    python = str(Path(sys.executable))
    cmd = [
        python,
        "-m",
        "dogana_visuals.cli",
        "--config",
        str(config_file),
        "--soccerdb-root",
        str(SOCCERDB_ROOT),
        "--output-root",
        str(DOGANA_OUTPUT_ROOT),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(DOGANA_ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    result = subprocess.run(cmd, cwd=DOGANA_ROOT, env=env, text=True, capture_output=True, timeout=300)
    stdout = result.stdout
    stderr = result.stderr
    ok = result.returncode == 0
    clean_failure = None if ok else dogana_clean_failure(stderr, config)
    if ok:
        warnings.extend(dogana_summary_warnings(out_dir))
    if not ok:
        if clean_failure:
            errors.extend(clean_failure["errors"])
        else:
            errors.append(f"generation failed with exit code {result.returncode}")
    return {
        "ok": ok,
        "status": "Dogana generated" if ok else clean_failure["status"] if clean_failure else "generation failed",
        "config_path": config_path,
        "output_folder": output_folder,
        "generated_files": dogana_generated_files(out_dir),
        "stdout": stdout,
        "stderr": "" if clean_failure else stderr,
        "debug_stderr": stderr if clean_failure else "",
        "warnings": warnings,
        "errors": errors,
        "command": cmd,
        "returncode": result.returncode,
    }


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
            if parsed.path in {"/", "/report_builder.html"}:
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
                self.send_json(status_payload())
            elif parsed.path == "/api/check_role_override":
                self.send_json(check_role_override_status({
                    "player_id": params.get("player_id", [""])[0],
                    "source_role": params.get("source_role", [""])[0],
                    "report_role": params.get("report_role", [""])[0],
                    "season": params.get("season", [""])[0],
                }))
            elif self.serve_root_asset(parsed.path):
                return
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
            elif self.path == "/api/generate_dogana":
                self.send_json(run_dogana(data))
            elif self.path == "/api/upsert_role_override":
                self.send_json(upsert_role_override(data))
            elif self.path == "/api/rebuild_override_artifacts":
                self.send_json(run_override_builder())
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

    def serve_root_asset(self, raw_path: str) -> bool:
        relative = urllib.parse.unquote(raw_path.lstrip("/"))
        if not relative or relative.startswith("tools/") or ".." in Path(relative).parts:
            return False
        path = (ROOT / relative).resolve()
        try:
            path.relative_to(ROOT)
        except ValueError:
            return False
        if not path.is_file():
            return False
        suffix_types = {
            ".html": "text/html",
            ".css": "text/css",
            ".js": "text/javascript",
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
            ".ttf": "font/ttf",
            ".eot": "application/vnd.ms-fontobject",
        }
        self.serve_file(path, suffix_types.get(path.suffix.lower(), "application/octet-stream"))
        return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local PASTA report builder server.")
    parser.add_argument("legacy_port", nargs="?", type=int, help="Backward-compatible positional port.")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--config", type=Path, help="Optional JSON path config for portable roots.")
    parser.add_argument("--check", action="store_true", help="Print portable path checks and exit.")
    return parser.parse_args()


def bind_server(host: str, start_port: int, end_port: int = 8020) -> tuple[ThreadingHTTPServer, int]:
    last_error: OSError | None = None
    stop_port = max(start_port, end_port) if start_port == 8011 else start_port
    for port in range(start_port, stop_port + 1):
        try:
            return ThreadingHTTPServer((host, port), Handler), port
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE:
                raise
            last_error = exc
    if last_error is not None:
        raise OSError(errno.EADDRINUSE, f"no free report-builder port in range {start_port}-{stop_port}") from last_error
    raise OSError(f"could not bind report-builder server on {host}:{start_port}")


def main() -> int:
    args = parse_args()
    if args.config:
        apply_runtime_paths(args.config)
    if args.check:
        payload = status_payload()
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if payload["ok"] else 1
    requested_port = args.port or args.legacy_port or 8011
    server, port = bind_server(args.host, requested_port)
    print(f"Report builder: http://{args.host}:{port}/")
    print(f"SoccerDB: {SOCCERDB_ROOT}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
