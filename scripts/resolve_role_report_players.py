#!/usr/bin/env python3
"""Resolve role report player IDs and suggest same-role peers.

This is a read-only helper for the role report workflow. It searches the
governed parquet feature layer first and uses DuckDB only as a last-resort
lookup when the requested player cannot be found in parquet.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


ROLE_CHOICES = ("GK", "DEF", "MID", "ATT")
ROLE_TO_SUFFIX = {"GK": "gk", "DEF": "def", "MID": "mid", "ATT": "att"}
DEFAULT_SOCCERDB_ROOT = Path("/Users/michele/Documents/SoccerDB")
FRONTEND_ROOT = Path(__file__).resolve().parents[1]

DISPLAY_COLUMNS = [
    "player_name",
    "player_id",
    "team_name",
    "competition",
    "season",
    "macro_role",
    "minutes",
    "source_file",
]
TARGET_PEER_COLUMNS = [
    "player_name",
    "player_id",
    "team_name",
    "team_id",
    "competition",
    "season",
    "macro_role",
    "minutes",
    "source_file",
]
TEAM_COLUMNS = ["team_name", "team_id", "competition", "season", "source_file"]


class ResolverError(RuntimeError):
    pass


@dataclass(frozen=True)
class DataRoots:
    root: Path
    features: Path
    duckdb_files: tuple[Path, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find role-report player IDs and manually chosen candidate groups."
    )
    parser.add_argument("--query", help="Partial player name to search for.")
    parser.add_argument("--query-team", help="Partial team name to search for.")
    parser.add_argument("--player-id", type=int, help="Known subject player ID.")
    parser.add_argument(
        "--list-peers",
        action="store_true",
        help="Deprecated alias for --list-external-comparison-candidates.",
    )
    parser.add_argument(
        "--list-role-candidates",
        action="store_true",
        help="Suggest generic same-role external comparison candidates.",
    )
    parser.add_argument(
        "--list-external-comparison-candidates",
        action="store_true",
        help="Suggest generic same-role external comparison candidates.",
    )
    parser.add_argument(
        "--list-squad-role-peers",
        action="store_true",
        help="Suggest source/current-team same-role peers for source context.",
    )
    parser.add_argument(
        "--list-target-role-peers",
        action="store_true",
        help="Suggest target-team same-role peers for main radar/export comparison.",
    )
    parser.add_argument("--target-team", help="Target team name for destination-squad peer lookup.")
    parser.add_argument("--target-team-id", type=int, help="Known target team ID.")
    parser.add_argument("--team-id", type=int, help="Disambiguate the analyzed player's team ID.")
    parser.add_argument("--role", choices=ROLE_CHOICES, help="Restrict lookup to one macro role.")
    parser.add_argument("--competition", help="Restrict candidates to this competition.")
    parser.add_argument("--season", help="Restrict candidates to this season, e.g. 2025-2026 or 2526.")
    parser.add_argument("--min-minutes", type=float, default=0.0, help="Minimum minutes for candidates.")
    parser.add_argument(
        "--same-competition",
        action="store_true",
        help="For peer lookup, require the subject competition.",
    )
    parser.add_argument(
        "--same-league-only",
        action="store_true",
        help="For peer lookup, require the subject league/competition across seasons.",
    )
    parser.add_argument("--limit", type=int, default=30, help="Maximum rows to print.")
    parser.add_argument(
        "--sort",
        choices=("smart", "minutes", "same-competition", "similarity", "global-benchmark"),
        default="smart",
        help="Peer sort mode. smart = same competition, similarity, benchmark availability, minutes.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        help="Repository root containing data/features. Defaults to /Users/michele/Documents/SoccerDB if present.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print planned data sources without scanning rows.")
    args = parser.parse_args()

    if not any([args.query, args.query_team, args.player_id, args.target_team, args.target_team_id]):
        parser.error("Provide --query, --query-team, --player-id, --target-team, or --target-team-id.")
    if args.list_peers:
        args.list_external_comparison_candidates = True
    if args.list_role_candidates:
        args.list_external_comparison_candidates = True
    if args.list_external_comparison_candidates and not args.player_id:
        parser.error("--list-external-comparison-candidates requires --player-id.")
    if args.list_squad_role_peers and not args.player_id:
        parser.error("--list-squad-role-peers requires --player-id.")
    if args.list_target_role_peers and not (args.target_team or args.target_team_id):
        parser.error("--list-target-role-peers requires --target-team or --target-team-id.")
    if args.list_target_role_peers and not args.role:
        parser.error("--list-target-role-peers requires --role.")
    if args.limit < 1:
        parser.error("--limit must be >= 1.")
    return args


def season_variants(value: str | None) -> set[str]:
    if not value:
        return set()
    raw = str(value).strip()
    compact = raw.replace("/", "-").replace("_", "-")
    variants = {raw, compact}
    parts = compact.split("-")
    if len(parts) == 2 and all(part.isdigit() for part in parts):
        left, right = parts
        variants.add(f"{left[-2:]}{right[-2:]}")
        variants.add(f"{left}-{right}")
    if compact.isdigit() and len(compact) == 4:
        variants.add(compact)
        variants.add(f"20{compact[:2]}-20{compact[2:]}")
    return {v for v in variants if v}


def display_season(value: Any) -> str:
    text = str(value).strip()
    if text.isdigit() and len(text) == 4:
        return f"20{text[:2]}-20{text[2:]}"
    return text


def canonical_text(value: Any) -> str:
    return str(value or "").strip()


def norm_contains(series: pd.Series, needle: str) -> pd.Series:
    return series.fillna("").astype(str).str.casefold().str.contains(needle.casefold(), regex=False)


def find_data_roots(args: argparse.Namespace) -> DataRoots:
    if args.data_root:
        root = args.data_root.resolve()
    elif DEFAULT_SOCCERDB_ROOT.exists():
        root = DEFAULT_SOCCERDB_ROOT
    else:
        root = FRONTEND_ROOT
    features = root / "data" / "features"
    duckdb_files = (root / "data" / "analytics.duckdb", root / "data" / "football_core.duckdb")
    return DataRoots(root=root, features=features, duckdb_files=duckdb_files)


def role_profile_paths(features: Path, roles: list[str]) -> list[tuple[str, str, Path]]:
    paths: list[tuple[str, str, Path]] = []
    for role in roles:
        suffix = ROLE_TO_SUFFIX[role]
        paths.append(("metrics", role, features / f"scouting_view_metrics_v1_{suffix}.parquet"))
        paths.append(("benchmark", role, features / f"global_benchmarks_{role}.parquet"))
        if role == "GK":
            paths.extend(("analysis", role, p) for p in sorted(features.glob("gk_player_season_*.parquet")))
        else:
            paths.extend(
                ("analysis", role, p)
                for p in sorted(features.glob(f"{suffix}_player_season_analysis_ready_*"))
            )
    return paths


def require_primary_lane(features: Path, roles: list[str]) -> None:
    missing = [
        features / f"scouting_view_metrics_v1_{ROLE_TO_SUFFIX[role]}.parquet"
        for role in roles
        if not (features / f"scouting_view_metrics_v1_{ROLE_TO_SUFFIX[role]}.parquet").exists()
    ]
    if missing:
        joined = "\n  ".join(str(path) for path in missing)
        raise ResolverError(f"required parquet file missing:\n  {joined}")


def normalize_frame(df: pd.DataFrame, path: Path, source_kind: str, role_hint: str) -> pd.DataFrame:
    if "player_id" not in df.columns:
        return pd.DataFrame(columns=DISPLAY_COLUMNS + ["team_id", "benchmark_available"])

    out = pd.DataFrame()
    out["player_id"] = pd.to_numeric(df["player_id"], errors="coerce")
    name_col = "player_name" if "player_name" in df.columns else "player" if "player" in df.columns else None
    out["player_name"] = df[name_col].astype(str) if name_col else out["player_id"].map(lambda v: f"Player {v}")
    out["team_name"] = (
        df["team_name"].astype(str)
        if "team_name" in df.columns
        else df["team_id"].map(lambda v: f"Team {int(v)}" if pd.notna(v) else "")
        if "team_id" in df.columns
        else ""
    )
    out["team_id"] = pd.to_numeric(df["team_id"], errors="coerce") if "team_id" in df.columns else pd.NA
    out["competition"] = df["competition"].astype(str) if "competition" in df.columns else ""
    out["season"] = df["season"].astype(str) if "season" in df.columns else ""
    out["macro_role"] = (
        df["macro_role"].fillna("").astype(str).str.upper()
        if "macro_role" in df.columns
        else role_hint
    )
    out["minutes"] = (
        pd.to_numeric(df["minutes_played"], errors="coerce")
        if "minutes_played" in df.columns
        else pd.Series([math.nan] * len(df))
    )
    out["source_file"] = str(path)
    out["source_kind"] = source_kind
    out["benchmark_available"] = source_kind == "benchmark"
    out = out.dropna(subset=["player_id"]).copy()
    out["player_id"] = out["player_id"].astype(int)
    out["macro_role"] = out["macro_role"].replace("", role_hint)
    return out


def load_candidate_pool(features: Path, roles: list[str], dry_run: bool = False) -> pd.DataFrame:
    paths = role_profile_paths(features, roles)
    existing = [(kind, role, path) for kind, role, path in paths if path.exists()]
    if dry_run:
        print(f"Data root: {features.parent.parent}")
        print("Would read parquet sources in this order:")
        for kind, role, path in paths:
            status = "exists" if path.exists() else "missing"
            print(f"  [{status}] {role} {kind}: {path}")
        return pd.DataFrame()
    if not existing:
        raise ResolverError(f"required parquet file missing: no role-profile parquet files under {features}")

    frames = []
    for kind, role, path in existing:
        try:
            df = pd.read_parquet(path)
        except Exception as exc:  # pragma: no cover - message is operationally useful.
            raise ResolverError(f"failed to read parquet file {path}: {exc}") from exc
        frames.append(normalize_frame(df, path, kind, role))
    if not frames:
        return pd.DataFrame(columns=DISPLAY_COLUMNS)
    pool = pd.concat(frames, ignore_index=True)
    pool = pool.dropna(subset=["player_id"]).copy()
    pool["season_display"] = pool["season"].map(display_season)

    source_rank = {"metrics": 0, "benchmark": 1, "analysis": 2}
    pool["_source_rank"] = pool["source_kind"].map(source_rank).fillna(9)
    pool["_minutes_rank"] = pd.to_numeric(pool["minutes"], errors="coerce").fillna(-1)
    pool = pool.sort_values(
        ["player_id", "macro_role", "competition", "season", "_source_rank", "_minutes_rank"],
        ascending=[True, True, True, True, True, False],
    )
    deduped = pool.drop_duplicates(
        subset=["player_id", "macro_role", "competition", "season"], keep="first"
    ).reset_index(drop=True)

    benchmark_ids = set(pool.loc[pool["source_kind"].eq("benchmark"), "player_id"].astype(int))
    deduped["benchmark_available"] = deduped["player_id"].isin(benchmark_ids)
    return deduped


def apply_common_filters(df: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    out = df.copy()
    if args.role:
        out = out[out["macro_role"].str.upper().eq(args.role)]
    if args.competition:
        out = out[out["competition"].str.casefold().eq(args.competition.casefold())]
    seasons = season_variants(args.season)
    if seasons:
        out = out[out["season"].astype(str).isin(seasons) | out["season_display"].astype(str).isin(seasons)]
    if args.min_minutes:
        out = out[pd.to_numeric(out["minutes"], errors="coerce").fillna(0) >= args.min_minutes]
    return out


def search_players(pool: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    rows = apply_common_filters(pool, args)
    if args.query:
        rows = rows[norm_contains(rows["player_name"], args.query)]
    if args.player_id:
        rows = rows[rows["player_id"].eq(args.player_id)]
    rows = rows.sort_values(["player_name", "season", "competition", "minutes"], ascending=[True, False, True, False])
    return rows


def subject_candidates(pool: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    rows = pool[pool["player_id"].eq(args.player_id)].copy()
    if args.role:
        rows = rows[rows["macro_role"].str.upper().eq(args.role)]
    if args.team_id:
        rows = rows[pd.to_numeric(rows["team_id"], errors="coerce").eq(args.team_id)]
    if args.competition:
        rows = rows[rows["competition"].str.casefold().eq(args.competition.casefold())]
    seasons = season_variants(args.season)
    if seasons:
        rows = rows[rows["season"].astype(str).isin(seasons) | rows["season_display"].astype(str).isin(seasons)]
    return rows


def choose_unambiguous_subject(rows: pd.DataFrame, player_id: int) -> pd.Series:
    if rows.empty:
        raise ResolverError(f"no player found for player_id={player_id}")
    keys = ["team_id", "competition", "season", "macro_role"]
    unique = rows.drop_duplicates(subset=keys)
    if len(unique) > 1:
        print("Analyzed player has multiple role/team/competition/season rows")
        print_table(unique.sort_values(["season", "competition", "team_id"], ascending=[False, True, True]), TARGET_PEER_COLUMNS)
        sys.stdout.flush()
        raise ResolverError(
            "ambiguous analyzed player context. Re-run with explicit --team-id, --competition, and/or --season."
        )
    row = unique.iloc[0].copy()
    if not canonical_text(row["macro_role"]):
        raise ResolverError(f"player found but missing role: player_id={player_id}")
    return row


def squad_role_peers(pool: pd.DataFrame, subject: pd.Series, args: argparse.Namespace) -> pd.DataFrame:
    rows = pool.copy()
    rows = rows[rows["player_id"].ne(int(subject["player_id"]))]
    rows = rows[pd.to_numeric(rows["team_id"], errors="coerce").eq(int(subject["team_id"]))]
    rows = rows[rows["competition"].eq(str(subject["competition"]))]
    rows = rows[rows["season"].eq(str(subject["season"]))]
    rows = rows[rows["macro_role"].str.upper().eq(str(subject["macro_role"]).upper())]
    if args.min_minutes:
        rows = rows[pd.to_numeric(rows["minutes"], errors="coerce").fillna(0) >= args.min_minutes]
    if rows.empty:
        raise ResolverError("squad role peer candidates not found")
    rows = rows.copy()
    rows["_minutes"] = pd.to_numeric(rows["minutes"], errors="coerce").fillna(0)
    return rows.sort_values(["_minutes", "player_name"], ascending=[False, True]).head(args.limit)


def search_teams_in_pool(pool: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    rows = apply_common_filters(pool, args)
    if args.target_team_id:
        rows = rows[pd.to_numeric(rows["team_id"], errors="coerce").eq(args.target_team_id)]
    query = args.query_team or args.target_team
    if query:
        rows = rows[norm_contains(rows["team_name"], query)]
    if rows.empty:
        return pd.DataFrame(columns=TEAM_COLUMNS)
    rows = rows.copy()
    rows["_minutes"] = pd.to_numeric(rows["minutes"], errors="coerce").fillna(0)
    teams = (
        rows.sort_values(["team_id", "season", "_minutes"], ascending=[True, False, False])
        .groupby(["team_id", "team_name", "competition", "season", "source_file"], as_index=False, dropna=False)
        .agg(minutes=("minutes", "sum"))
        .sort_values(["team_name", "season", "competition"], ascending=[True, False, True])
    )
    return teams[TEAM_COLUMNS].reset_index(drop=True)


def duckdb_team_fallback(args: argparse.Namespace, roots: DataRoots) -> pd.DataFrame:
    db_path = next((path for path in roots.duckdb_files if path.exists()), None)
    if db_path is None:
        return pd.DataFrame(columns=TEAM_COLUMNS)
    try:
        import duckdb
    except ImportError:
        return pd.DataFrame(columns=TEAM_COLUMNS)

    query = args.query_team or args.target_team
    frames = []
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = con.execute(
            """
            select table_schema, table_name
            from information_schema.tables
            where table_type = 'BASE TABLE'
            """
        ).fetchall()
        for schema, table in tables:
            cols = {
                row[3]
                for row in con.execute(
                    """
                    select * from information_schema.columns
                    where table_schema = ? and table_name = ?
                    """,
                    [schema, table],
                ).fetchall()
            }
            if not {"team_id", "team_name"}.issubset(cols):
                continue
            qualified = f'"{schema}"."{table}"'
            where = []
            params: list[Any] = []
            if args.target_team_id:
                where.append("team_id = ?")
                params.append(args.target_team_id)
            if query:
                where.append("lower(cast(team_name as varchar)) like ?")
                params.append(f"%{query.casefold()}%")
            if not where:
                continue
            sql = f"""
                select distinct
                    cast(team_name as varchar) as team_name,
                    team_id,
                    '' as competition,
                    '' as season,
                    '{db_path}:{schema}.{table}' as source_file
                from {qualified}
                where {' and '.join(where)}
                order by team_name
                limit 200
            """
            frames.append(con.execute(sql, params).fetchdf())
    finally:
        con.close()
    if not frames:
        return pd.DataFrame(columns=TEAM_COLUMNS)
    return pd.concat(frames, ignore_index=True).drop_duplicates(subset=["team_id", "team_name"])


def resolve_team(pool: pd.DataFrame, args: argparse.Namespace, roots: DataRoots) -> pd.Series:
    teams = search_teams_in_pool(pool, args)
    used_duckdb = False
    if teams.empty:
        teams = duckdb_team_fallback(args, roots)
        used_duckdb = not teams.empty
    if teams.empty:
        target = f"team_id={args.target_team_id}" if args.target_team_id else f"team query={args.query_team or args.target_team!r}"
        raise ResolverError(f"no team found for {target}")

    unique = teams.drop_duplicates(subset=["team_id", "team_name"]).reset_index(drop=True)
    if len(unique) > 1:
        print("Team candidates" + (" (DuckDB fallback)" if used_duckdb else ""))
        print_table(teams.head(args.limit), TEAM_COLUMNS)
        sys.stdout.flush()
        raise ResolverError(
            f"team name is ambiguous: {len(unique)} teams match. "
            "Refine with --target-team-id or a more specific --target-team/--query-team."
        )
    team = unique.iloc[0].copy()
    team["used_duckdb"] = used_duckdb
    return team


def target_role_peers(pool: pd.DataFrame, team: pd.Series, args: argparse.Namespace) -> pd.DataFrame:
    rows = apply_common_filters(pool, args)
    rows = rows[pd.to_numeric(rows["team_id"], errors="coerce").eq(int(team["team_id"]))]
    if rows.empty:
        raise ResolverError("target role peer candidates not found")
    rows = rows.copy()
    if canonical_text(team.get("team_name")):
        rows["team_name"] = canonical_text(team["team_name"])
    rows["_minutes"] = pd.to_numeric(rows["minutes"], errors="coerce").fillna(0)
    return rows.sort_values(["_minutes", "player_name"], ascending=[False, True]).head(args.limit)


def load_similarity_scores(features: Path, role: str, player_id: int) -> dict[int, float]:
    suffix = ROLE_TO_SUFFIX[role]
    scores: dict[int, float] = {}
    for path in (
        features / f"{suffix}_similarity_volume_v1.parquet",
        features / f"{suffix}_similarity_territorial_v1.parquet",
        features / f"{suffix}_similarity_action_mix_v1.parquet",
    ):
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=None)
        required = {"player_id", "similar_player_id", "similarity_score"}
        if not required.issubset(df.columns):
            continue
        rows = df[df["player_id"].eq(player_id)]
        for _, row in rows.iterrows():
            sid = int(row["similar_player_id"])
            score = float(row["similarity_score"])
            scores[sid] = max(scores.get(sid, float("-inf")), score)
    return scores


def choose_subject(rows: pd.DataFrame, player_id: int, min_minutes: float) -> pd.Series:
    if rows.empty:
        raise ResolverError(f"no player found for player_id={player_id}")
    rows = rows.copy()
    if rows["macro_role"].fillna("").astype(str).str.strip().eq("").all():
        raise ResolverError(f"player found but missing role: player_id={player_id}")
    rows["_minutes"] = pd.to_numeric(rows["minutes"], errors="coerce").fillna(0)
    subject = rows.sort_values(["_minutes", "season", "competition"], ascending=[False, False, True]).iloc[0]
    if min_minutes and float(subject["_minutes"]) < min_minutes:
        raise ResolverError(
            f"player found but below minute threshold: player_id={player_id} has "
            f"{float(subject['_minutes']):.0f} minutes, threshold is {min_minutes:.0f}"
        )
    if not canonical_text(subject["macro_role"]):
        raise ResolverError(f"player found but missing role: player_id={player_id}")
    return subject


def peer_candidates(pool: pd.DataFrame, subject: pd.Series, args: argparse.Namespace, features: Path) -> pd.DataFrame:
    role = args.role or str(subject["macro_role"]).upper()
    if role not in ROLE_CHOICES:
        raise ResolverError(f"player found but missing role: player_id={int(subject['player_id'])}")

    peer_args = argparse.Namespace(**vars(args))
    peer_args.role = role
    rows = apply_common_filters(pool, peer_args)
    rows = rows[rows["player_id"].ne(int(subject["player_id"]))]
    subject_comp = canonical_text(subject["competition"])
    if args.same_competition or args.same_league_only:
        rows = rows[rows["competition"].eq(subject_comp)]
    if rows.empty:
        raise ResolverError("peer candidates not found")

    sim_scores = load_similarity_scores(features, role, int(subject["player_id"]))
    rows = rows.copy()
    rows["same_competition"] = rows["competition"].eq(subject_comp)
    rows["similarity_score"] = rows["player_id"].map(sim_scores).fillna(-1.0)
    rows["_minutes"] = pd.to_numeric(rows["minutes"], errors="coerce").fillna(0)
    rows["global_benchmark_available"] = rows["benchmark_available"].astype(bool)

    if args.sort == "minutes":
        sort_cols, ascending = ["_minutes"], [False]
    elif args.sort == "same-competition":
        sort_cols, ascending = ["same_competition", "_minutes"], [False, False]
    elif args.sort == "similarity":
        sort_cols, ascending = ["similarity_score", "_minutes"], [False, False]
    elif args.sort == "global-benchmark":
        sort_cols, ascending = ["global_benchmark_available", "_minutes"], [False, False]
    else:
        sort_cols = ["same_competition", "similarity_score", "global_benchmark_available", "_minutes"]
        ascending = [False, False, False, False]

    return rows.sort_values(sort_cols + ["player_name"], ascending=ascending + [True]).head(args.limit)


def print_table(df: pd.DataFrame, columns: list[str]) -> None:
    if df.empty:
        print("(no rows)")
        return
    printable = df[columns].copy()
    for col in printable.columns:
        if col in {"minutes"}:
            printable[col] = pd.to_numeric(printable[col], errors="coerce").map(
                lambda v: "" if pd.isna(v) else f"{v:.0f}"
            )
        elif col.endswith("_id") or col == "player_id":
            printable[col] = pd.to_numeric(printable[col], errors="coerce").map(
                lambda v: "" if pd.isna(v) else f"{v:.0f}"
            )
        elif col == "similarity_score":
            printable[col] = pd.to_numeric(printable[col], errors="coerce").map(
                lambda v: "" if pd.isna(v) or v < 0 else f"{v:.3f}"
            )
        elif col == "season":
            printable[col] = printable[col].map(display_season)
        else:
            printable[col] = printable[col].fillna("").astype(str)
    widths = {
        col: max(len(col), *(len(str(value)) for value in printable[col].tolist()))
        for col in printable.columns
    }
    header = "  ".join(col.ljust(widths[col]) for col in printable.columns)
    print(header)
    print("  ".join("-" * widths[col] for col in printable.columns))
    for _, row in printable.iterrows():
        print("  ".join(str(row[col]).ljust(widths[col]) for col in printable.columns))


def print_orchestrator_command(role: str, player_id: int, peers: pd.DataFrame | None = None) -> None:
    ids = ""
    if peers is not None and not peers.empty:
        ids = ",".join(str(int(pid)) for pid in peers["player_id"].head(5).tolist())
    print("\nCopy-paste orchestrator command:")
    print("python scripts/orchestrate_role_report.py \\")
    print(f"  --role {role} \\")
    print(f"  --player-id {player_id} \\")
    print(f"  --comparison-player-ids {ids or '111,222,333'} \\")
    print("  --mode export")


def duckdb_fallback(args: argparse.Namespace, roots: DataRoots) -> pd.DataFrame:
    db_path = next((path for path in roots.duckdb_files if path.exists()), None)
    if db_path is None:
        return pd.DataFrame()
    try:
        import duckdb
    except ImportError:
        return pd.DataFrame()

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = con.execute(
            """
            select table_schema, table_name
            from information_schema.tables
            where table_type = 'BASE TABLE'
            """
        ).fetchall()
        frames = []
        for schema, table in tables:
            cols = {
                row[1]
                for row in con.execute(
                    """
                    select * from information_schema.columns
                    where table_schema = ? and table_name = ?
                    """,
                    [schema, table],
                ).fetchall()
            }
            if "player_id" not in cols:
                continue
            name_col = next((c for c in ("player_name", "player", "name") if c in cols), None)
            if not name_col:
                continue
            qualified = f'"{schema}"."{table}"'
            where = []
            params: list[Any] = []
            if args.player_id:
                where.append("player_id = ?")
                params.append(args.player_id)
            if args.query:
                where.append(f"lower(cast({name_col} as varchar)) like ?")
                params.append(f"%{args.query.casefold()}%")
            if not where:
                continue
            sql = f"""
                select distinct
                    player_id,
                    cast({name_col} as varchar) as player_name,
                    '' as team_name,
                    '' as competition,
                    '' as season,
                    '' as macro_role,
                    null as minutes,
                    '{db_path}:{schema}.{table}' as source_file
                from {qualified}
                where {' and '.join(where)}
                limit 200
            """
            frames.append(con.execute(sql, params).fetchdf())
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    finally:
        con.close()


def main() -> int:
    args = parse_args()
    roles = [args.role] if args.role else list(ROLE_CHOICES)
    roots = find_data_roots(args)

    try:
        require_primary_lane(roots.features, roles)
        pool = load_candidate_pool(roots.features, roles, dry_run=args.dry_run)
        if args.dry_run:
            return 0

        if args.query_team and not args.list_target_role_peers:
            teams = search_teams_in_pool(pool, args)
            used_duckdb = False
            if teams.empty:
                teams = duckdb_team_fallback(args, roots)
                used_duckdb = not teams.empty
            if teams.empty:
                raise ResolverError(f"no team found for query={args.query_team!r}")
            if len(teams.drop_duplicates(subset=["team_id", "team_name"])) > args.limit:
                print_table(teams.head(args.limit), TEAM_COLUMNS)
                sys.stdout.flush()
                raise ResolverError(
                    f"too many ambiguous teams: {len(teams)} matches. "
                    "Refine with a more specific --query-team."
                )
            print("Team candidates" + (" (DuckDB fallback)" if used_duckdb else ""))
            print_table(teams.head(args.limit), TEAM_COLUMNS)
            return 0

        if args.list_target_role_peers:
            team = resolve_team(pool, args, roots)
            peers = target_role_peers(pool, team, args)
            print("Target team")
            print_table(pd.DataFrame([team]), TEAM_COLUMNS)
            print("\nTarget-team same-role peer candidates for main/radar comparison (suggestions only; choose manually)")
            print_table(peers, TARGET_PEER_COLUMNS)
            ids = ",".join(str(int(pid)) for pid in peers["player_id"].head(6).tolist())
            print("\nCopy-paste main comparison args:")
            print(f'  --target-team "{team["team_name"]}" \\')
            print(f"  --target-team-id {int(team['team_id'])} \\")
            print(f"  --main-comparison-peer-ids {ids or '444,555,666'}")
            return 0

        if args.list_squad_role_peers:
            subject = choose_unambiguous_subject(subject_candidates(pool, args), args.player_id)
            peers = squad_role_peers(pool, subject, args)
            print("Analyzed player context")
            print_table(pd.DataFrame([subject]), TARGET_PEER_COLUMNS)
            print("\nSource-team role peers for source context (same team, role, competition, and season)")
            print_table(peers, TARGET_PEER_COLUMNS)
            ids = ",".join(str(int(pid)) for pid in peers["player_id"].tolist())
            print("\nCopy-paste source context args:")
            print(f"  --source-team-peer-ids {ids or '111,222,333'}")
            return 0

        if not args.list_external_comparison_candidates:
            rows = search_players(pool, args)
            used_duckdb = False
            if rows.empty:
                fallback = duckdb_fallback(args, roots)
                if not fallback.empty:
                    used_duckdb = True
                    rows = fallback
                else:
                    target = f"player_id={args.player_id}" if args.player_id else f"query={args.query!r}"
                    raise ResolverError(f"no player found for {target}")
            if len(rows) > args.limit:
                print_table(rows.head(args.limit), DISPLAY_COLUMNS)
                sys.stdout.flush()
                raise ResolverError(
                    f"too many ambiguous players: {len(rows)} matches. "
                    "Refine with --role, --competition, --season, or a more specific --query."
                )
            print("Player candidates" + (" (DuckDB fallback)" if used_duckdb else ""))
            print_table(rows.head(args.limit), DISPLAY_COLUMNS)
            if len(rows) == 1 and not used_duckdb:
                row = rows.iloc[0]
                print_orchestrator_command(str(row["macro_role"]).upper(), int(row["player_id"]))
            return 0

        subject_rows = pool[pool["player_id"].eq(args.player_id)]
        subject = choose_subject(subject_rows, args.player_id, args.min_minutes)
        if args.role and str(subject["macro_role"]).upper() != args.role:
            raise ResolverError(
                f"player found but role mismatch: player_id={args.player_id} is "
                f"{subject['macro_role']}, requested {args.role}"
            )
        peers = peer_candidates(pool, subject, args, roots.features)
        print("Subject")
        print_table(pd.DataFrame([subject]), DISPLAY_COLUMNS)
        print("\nGeneric external comparison candidates (suggestions only; not squad-role peers)")
        peer_columns = DISPLAY_COLUMNS[:-1] + [
            "same_competition",
            "similarity_score",
            "global_benchmark_available",
            "source_file",
        ]
        print_table(peers, peer_columns)
        print_orchestrator_command(str(subject["macro_role"]).upper(), int(subject["player_id"]), peers)
        return 0
    except ResolverError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
