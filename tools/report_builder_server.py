#!/usr/bin/env python3
"""Local report builder GUI server.

This is a thin local-only wrapper around the existing resolver/export helpers.
It does not change analytics, payload structure, or frontend rendering.
"""

from __future__ import annotations

import json
import os
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
DOGANA_ROOT = Path("/Users/michele/Documents/soccerdb_experiments/dogana_visuals")
DOGANA_CONFIG_DIR = DOGANA_ROOT / "configs" / "players"
DOGANA_OUTPUT_ROOT = Path("/Users/michele/Documents/soccerdb_experiments/outputs/dogana")
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
OVERRIDE_CSV = SOCCERDB_ROOT / "config" / "manual_role_overrides.csv"
OVERRIDE_BUILDER = SOCCERDB_ROOT / "scripts" / "build_manual_role_override_artifacts.py"
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


def records_by_ids(role: str, ids: str, season: str | None) -> pd.DataFrame:
    wanted = split_ids(ids)
    if not wanted:
        return pd.DataFrame()
    df = apply_team_overrides(unique_players(metric_frame(role, season)), role)
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


def prompt_data(data: dict[str, Any], source_role: str, report_role: str, source_context_exported: bool) -> dict[str, Any]:
    season = str(data.get("season") or "")
    return {
        "subject_source_role_metrics": metric_highlights(source_role, str(data.get("player_id")), season),
        "subject_report_role_metrics": metric_highlights(report_role, str(data.get("player_id")), season),
        "target_team_peers_report_role": peer_group_summary(report_role, str(data.get("main_comparison_peer_ids") or ""), season),
        "source_context_peers_source_role": peer_group_summary(source_role, str(data.get("source_team_peer_ids") or ""), season),
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
    season = str(data.get("season") or "")
    player_id = str(data.get("player_id") or "")
    subject_rows = records_by_ids(report_role, player_id, season)
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
    target_peer_rows = records_by_ids(report_role, str(data.get("main_comparison_peer_ids") or ""), season)
    found_target_ids = set(target_peer_rows["player_id"].astype(str).tolist()) if not target_peer_rows.empty else set()
    missing_target = [pid for pid in split_ids(data.get("main_comparison_peer_ids")) if pid not in found_target_ids]
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
        source_rows = records_by_ids(source_role, source_ids, season)
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
    brief = asset_brief or planned_editorial_brief(data, data_block, source_role, report_role, reason)
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
    slug = slugify_name(data.get("player_name")) or str(data.get("slug") or "").strip()
    data["slug"] = slug
    cmd = [
        str(PYTHON if PYTHON.exists() else Path(sys.executable)),
        "scripts/create_player_page_from_export.py",
        "--role", report_role,
        "--source-role", source_role,
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
        "url": f"http://127.0.0.1:8001/{data.get('slug')}.html",
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
            "target_team_name": str(data["target_team"]).strip(),
            "target_same_role_player_ids": target_peer_ids,
            "min_minutes": 100,
            "meaningful_peer_minutes": 600,
            "top_n_metrics": 8,
            "context_visual_mode": "two_evidence_blocks",
            "show_target_peer_chip": False,
            "seriea_similarity_methods": ["pasta_distilled", "pca_knn", "euclidean_zscore"],
            "selected_seriea_similarity_method": None,
            "selected_seriea_comparable_player_id": None,
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
    return [str(path) for path in sorted(output_folder.iterdir()) if path.is_file()]


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
            elif parsed.path == "/api/check_role_override":
                self.send_json(check_role_override_status({
                    "player_id": params.get("player_id", [""])[0],
                    "source_role": params.get("source_role", [""])[0],
                    "report_role": params.get("report_role", [""])[0],
                    "season": params.get("season", [""])[0],
                }))
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


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8011
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Report builder: http://127.0.0.1:{port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
