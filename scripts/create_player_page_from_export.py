#!/usr/bin/env python3
"""Create one HTML5UP player page from a SoccerDB role-report export.

This helper wraps the existing manual workflow:
1. export an inline SoccerDB role payload into an archive snapshot;
2. extract the legacy runtime globals into data/report_legacy_payloads;
3. add or update the player entry in assets/data/player_index.json;
4. run generate_pages.py for the selected slug.

It does not change analytics logic, payload shape, or frontend rendering.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOCCERDB_ROOT = Path("/Users/michele/Documents/SoccerDB")
ROLE_CHOICES = ("GK", "DEF", "MID", "ATT")
VISIBILITY_CHOICES = ("hidden", "public")

RUNTIME_GLOBALS = [
    "ROLE_META",
    "PAGE_META",
    "SUBJECT_ID",
    "PLAYER_META",
    "PROFILE_READING",
    "COMPARISON_GROUPS",
    "RADAR_AXES",
    "RADAR_DATA",
    "METRIC_FORMATS",
    "METRIC_RANGES",
    "METRICS",
    "TARGET_COMPARISON_BARS",
    "SOURCE_TEAM_COMPARISON_BARS",
    "HEATMAP_DATA",
    "SIMILARITY_DATA",
    "FOOTNOTES",
    "RADAR_AXIS_RANGES",
]


class PageCreationError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an HTML5UP player page from a SoccerDB role export.")
    parser.add_argument("--role", choices=ROLE_CHOICES, required=True)
    parser.add_argument("--source-role", choices=ROLE_CHOICES)
    parser.add_argument("--role-override-reason", default="")
    parser.add_argument(
        "--source-context-editorial-only",
        action="store_true",
        help="Record source-context peer IDs in metadata, but do not pass them as exporter --context-ids.",
    )
    parser.add_argument("--player-id", required=True)
    parser.add_argument("--player-name", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--comparison-ids", dest="main_comparison_peer_ids", help="Deprecated alias for --main-comparison-peer-ids.")
    parser.add_argument("--main-comparison-peer-ids", dest="main_comparison_peer_ids")
    parser.add_argument("--target-team-peer-ids", dest="main_comparison_peer_ids", help="Alias for target-team same-role peers used by exporter/radar.")
    parser.add_argument("--comparison-label", required=True)
    parser.add_argument("--source-team-peer-ids", default="")
    parser.add_argument("--source-team-peer-label", default="")
    parser.add_argument("--team-name", required=True)
    parser.add_argument("--source-club")
    parser.add_argument("--competition", required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--target-team", required=True)
    parser.add_argument("--target-role-peer-ids", dest="target_role_peer_ids", default="", help="Deprecated metadata alias; use --target-team-peer-ids for main/radar peers.")
    parser.add_argument("--visibility", choices=VISIBILITY_CHOICES, default="hidden")
    parser.add_argument("--report-status", choices=["live", "draft"], default="live")
    parser.add_argument("--note", default="", help="Backward-compatible alias for --narrative.")
    parser.add_argument("--narrative", default="")
    parser.add_argument("--source-team-note", default="")
    parser.add_argument("--note-confronto", default="")
    parser.add_argument("--note-heatmap", default="")
    parser.add_argument("--note-context", default="")
    parser.add_argument("--note-similarity", default="")
    parser.add_argument("--editorial-json", type=Path)
    parser.add_argument("--print-llm-prompt", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--soccerdb-root", type=Path, default=SOCCERDB_ROOT)
    args = parser.parse_args()
    args.source_role = args.source_role or args.role
    if not args.main_comparison_peer_ids:
        parser.error("--main-comparison-peer-ids / --target-team-peer-ids is required.")
    if args.source_role != args.role and not args.role_override_reason.strip():
        parser.error("--role-override-reason is required when --source-role differs from --role.")
    if args.source_role != args.role:
        args.source_context_editorial_only = True
    return args


def python_for(root: Path) -> str:
    venv_python = root / ".venv" / "bin" / "python"
    return str(venv_python if venv_python.exists() else Path(sys.executable))


def command_text(command: list[str]) -> str:
    return " ".join(command)


def load_extractor():
    sys.path.insert(0, str(ROOT / "scripts"))
    from frontend_contract.js_const_extractor import extract_globals  # noqa: PLC0415

    return extract_globals


def normalize_season(season: str) -> str:
    value = season.strip()
    if len(value) == 9 and value[:4].isdigit() and value[5:].isdigit():
        return value[2:4] + value[7:9]
    return value


def load_editorial_fields(args: argparse.Namespace) -> tuple[dict[str, str], dict[str, Any]]:
    supported = {
        "narrative",
        "source_team_note",
        "note_confronto",
        "note_heatmap",
        "note_context",
        "note_similarity",
    }
    values = {
        "narrative": args.narrative or args.note,
        "source_team_note": args.source_team_note,
        "note_confronto": args.note_confronto,
        "note_heatmap": args.note_heatmap,
        "note_context": args.note_context,
        "note_similarity": args.note_similarity,
    }
    unsupported: dict[str, Any] = {}
    if args.editorial_json:
        if not args.editorial_json.exists():
            raise PageCreationError(f"editorial JSON file not found: {args.editorial_json}")
        data = json.loads(args.editorial_json.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise PageCreationError("editorial JSON must contain an object")
        for key, value in data.items():
            if key in supported:
                values[key] = "" if value is None else str(value)
            else:
                unsupported[key] = value
    return values, unsupported


def llm_prompt(args: argparse.Namespace) -> str:
    return f"""Generate Italian editorial copy for a PASTA role report using exactly this JSON schema.

Return only JSON with these exact keys:
{{
  "narrative": "",
  "source_team_note": "",
  "note_confronto": "",
  "note_heatmap": "",
  "note_context": "",
  "note_similarity": ""
}}

Context:
- Player: {args.player_name} ({args.player_id})
- Source/detected role: {args.source_role}
- Report/analysis role: {args.role}
- Role override reason: {args.role_override_reason or "(none; source role and report role match)"}
- Source team: {args.team_name}
- Main/radar comparison peers: {args.comparison_label} = {args.main_comparison_peer_ids}
- Target team: {args.target_team}
- Source-team context peers: {args.source_team_peer_label or args.team_name + " " + args.source_role} = {args.source_team_peer_ids or "(none provided)"}
- Source-context peers exported as context IDs: {"no; stored as editorial metadata only because source_role differs from report_role" if args.source_context_editorial_only else "yes, when provided"}
- Competition: {args.competition}
- Season: {normalize_season(args.season)}

Semantic rules:
- The report is built in the report/analysis role.
- The source role may differ from the report role; do not describe this as a data error.
- Explain the tactical conversion clearly with language such as "in the source team he is used as..." and "in the target context he is evaluated as...".
- The radar/main comparison is against target-team same-role peers in the report role.
- Source-team peers are source-context peers only; do not describe the radar as a source-team comparison.
- Explain what {args.player_name} brings/adds/changes compared with {args.target_team} {args.role} peers.
- Use source-team context only to explain how his profile emerged in his source team.
- Avoid better/worse language. Prefer brings, adds, changes, fits, differs from.

Field meanings:
- narrative: high-level fit/profile reading, including target-team fit.
- source_team_note: optional short helper line for the source-team context card.
- note_confronto: explain the technical/export comparison against target-team peers.
- note_heatmap: explain spatial panels; for DEF the fourth panel is defensive actions.
- note_context: explain how the player stands out inside the source-team role group.
- note_similarity: explain similarity using the exported target-team comparison set.
"""


def print_review(args: argparse.Namespace, editorial_fields: dict[str, str], unsupported: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    print("[review] Page generation semantics")
    print(f"  analyzed player: {args.player_name} ({args.player_id})")
    print(f"  source role:       {args.source_role} · {args.team_name} · {args.competition} · {normalize_season(args.season)}")
    print(f"  report role:       {args.role}")
    if args.source_role != args.role:
        print(f"  role override:     {args.role_override_reason}")
        warnings.append(
            f"cross-role report: source_role={args.source_role}, report_role={args.role}. "
            f"Reason: {args.role_override_reason}"
        )
    print(f"  main/radar peers:  {args.comparison_label} = {args.main_comparison_peer_ids}")
    print(f"  source context:    {args.source_team_peer_label or args.team_name + ' ' + args.source_role} = {args.source_team_peer_ids or '(none)'}")
    if args.target_role_peer_ids:
        print(f"  deprecated target-role-peer-ids metadata: {args.target_role_peer_ids}")
    if args.source_context_editorial_only:
        print("  exporter mapping:  main/radar peers -> --comparison-ids; source context peers -> editorial metadata only")
    else:
        print("  exporter mapping:  main/radar peers -> --comparison-ids; source context peers -> --context-ids")
    if args.target_team and args.target_team.lower() not in args.comparison_label.lower():
        warning = (
            "comparison label does not include the target team name; for Inter scouting pages "
            "the golden Solet pattern expects target-team peers as the main/radar group."
        )
        warnings.append(warning)
        print(f"  warning: {warning}")
    missing = [key for key, value in editorial_fields.items() if not value]
    if missing:
        print(f"  empty editorial fields: {', '.join(missing)}")
    if unsupported:
        print(f"  unsupported editorial JSON keys stored in manifest only: {', '.join(sorted(unsupported))}")
    return warnings


def backup_file(path: Path, timestamp: str, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{path.name}.bak_{timestamp}"
    shutil.copy2(path, backup)
    return backup


def write_snapshot_seed(path: Path) -> None:
    path.write_text(
        "<!doctype html>\n"
        "<html><head><meta charset=\"utf-8\"><title>Role payload snapshot</title></head>\n"
        "<body><script>\n"
        "// DATA:START\n"
        "// DATA:END\n"
        "</script></body></html>\n",
        encoding="utf-8",
    )


def missing_payload_players(
    payload: dict[str, Any],
    *,
    raw_ids: str,
) -> list[str]:
    player_meta = payload.get("PLAYER_META", {})
    missing = []
    for raw in [part.strip() for part in raw_ids.split(",") if part.strip()]:
        meta = player_meta.get(raw)
        if (
            not isinstance(meta, dict)
            or not meta.get("name")
            or meta.get("name") == f"Player {raw}"
            or meta.get("mins") in (None, 0, "0")
        ):
            missing.append(raw)
    return missing


def run_command(command: list[str], cwd: Path, dry_run: bool) -> dict[str, Any]:
    print(f"  cwd: {cwd}")
    print(f"  cmd: {command_text(command)}")
    if dry_run:
        print("  dry-run: command not executed")
        return {"command": command, "cwd": str(cwd), "skipped": True, "returncode": None}
    result = subprocess.run(command, cwd=cwd, text=True)
    if result.returncode != 0:
        raise PageCreationError(f"command failed with exit code {result.returncode}: {command_text(command)}")
    return {"command": command, "cwd": str(cwd), "skipped": False, "returncode": result.returncode}


def extract_payload(snapshot_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    extract_globals = load_extractor()
    values, diagnostics = extract_globals(snapshot_path, RUNTIME_GLOBALS, root=ROOT)
    required = [name for name in RUNTIME_GLOBALS if name != "RADAR_AXIS_RANGES"]
    missing_required = [name for name in required if name not in values]
    if missing_required:
        raise PageCreationError(f"snapshot is missing required payload globals: {missing_required}")
    payload = {name: values[name] for name in RUNTIME_GLOBALS if name in values}
    payload["payloadMeta"] = {
        "payloadType": "legacy_role_payload",
        "sourcePage": f"{snapshot_path.name.replace('.with_inline_payload_', '.html#')}",
        "archiveSource": str(snapshot_path.relative_to(ROOT)),
        "loadedByProductionRuntime": True,
        "fallbackInlineAvailable": False,
        "extractedGlobals": diagnostics["extracted"],
        "missingGlobals": diagnostics["missing"],
        "blockedGlobals": diagnostics["blocked"],
    }
    return payload, diagnostics


def load_player_index(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise PageCreationError(f"player index not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise PageCreationError("assets/data/player_index.json must be a list")
    return data


def upsert_player_entry(players: list[dict[str, Any]], entry: dict[str, Any]) -> str:
    for idx, player in enumerate(players):
        if player.get("slug") == entry["slug"]:
            merged = dict(player)
            merged.update(entry)
            players[idx] = merged
            return "updated"
    players.append(entry)
    return "added"


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Manifest: {path}")


def main() -> int:
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_dir = ROOT / "outputs" / "page_generation_runs" / f"{timestamp}_{args.slug}"
    manifest_path = run_dir / "run_manifest.json"
    commands_planned: list[dict[str, Any]] = []
    commands_executed: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    backups: list[str] = []
    editorial_fields: dict[str, str] = {}
    unsupported_editorial: dict[str, Any] = {}

    snapshot_path = ROOT / "archive" / "frontend_payload_fallback_snapshots" / f"{args.slug}.with_inline_payload_{timestamp}.html"
    payload_path = ROOT / "data" / "report_legacy_payloads" / f"{args.slug}.legacy_role_payload.json"
    index_path = ROOT / "assets" / "data" / "player_index.json"
    html_path = ROOT / f"{args.slug}.html"
    backup_dir = run_dir / "backups"

    try:
        editorial_fields, unsupported_editorial = load_editorial_fields(args)
        warnings.extend(print_review(args, editorial_fields, unsupported_editorial))
        if args.print_llm_prompt:
            print("\n[llm-prompt]\n" + llm_prompt(args))

        soccerdb_root = args.soccerdb_root.expanduser().resolve()
        exporter = soccerdb_root / "scripts" / "exports" / "export_role_report_data.py"
        if not exporter.exists():
            raise PageCreationError(f"SoccerDB exporter not found: {exporter}")

        conflicts = [path for path in (payload_path, html_path) if path.exists()]
        if conflicts and not args.overwrite:
            names = ", ".join(str(path.relative_to(ROOT)) for path in conflicts)
            raise PageCreationError(f"refusing to overwrite existing file(s): {names}. Re-run with --overwrite.")

        export_command = [
            python_for(soccerdb_root),
            str(exporter),
            "--role",
            args.role,
            "--player-id",
            str(args.player_id),
            "--player-name",
            args.player_name,
            "--comparison-ids",
            args.main_comparison_peer_ids,
            "--comparison-label",
            args.comparison_label,
            "--output",
            str(snapshot_path),
        ]
        if args.source_team_peer_ids and not args.source_context_editorial_only:
            export_command.extend(
                [
                    "--context-ids",
                    args.source_team_peer_ids,
                    "--context-label",
                    args.source_team_peer_label or f"{args.team_name} {args.source_role}",
                ]
            )
        generate_command = [sys.executable, "generate_pages.py", "--slug", args.slug]
        commands_planned.append({"name": "soccerdb_export", "command": export_command, "cwd": str(soccerdb_root)})
        commands_planned.append({"name": "generate_page", "command": generate_command, "cwd": str(ROOT)})

        print("[1/5] Plan SoccerDB export")
        print(f"  snapshot: {snapshot_path}")
        print(f"  payload:  {payload_path}")
        print(f"  html:     {html_path}")

        if args.dry_run:
            print("[2/5] Dry-run: no files written")
        else:
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            payload_path.parent.mkdir(parents=True, exist_ok=True)
            if payload_path.exists():
                backups.append(str(backup_file(payload_path, timestamp, backup_dir)))
            if html_path.exists():
                backups.append(str(backup_file(html_path, timestamp, backup_dir)))
            if index_path.exists():
                backups.append(str(backup_file(index_path, timestamp, backup_dir)))

            print("[2/5] Export inline snapshot")
            write_snapshot_seed(snapshot_path)
            commands_executed.append(run_command(export_command, soccerdb_root, False))

            print("[3/5] Extract legacy payload JSON")
            payload, diagnostics = extract_payload(snapshot_path)
            missing_main = missing_payload_players(payload, raw_ids=args.main_comparison_peer_ids)
            if missing_main:
                raise PageCreationError(
                    "selected main comparison peer(s) cannot be resolved in "
                    f"{args.role} metrics: {','.join(missing_main)}. "
                    "Search replacement before generating."
                )
            missing_source = [] if args.source_context_editorial_only else missing_payload_players(payload, raw_ids=args.source_team_peer_ids)
            for warning in [
                f"source-context peer IDs missing from payload PLAYER_META: {','.join(missing_source)}"
            ] if missing_source else []:
                warnings.append(warning)
                print(f"  warning: {warning}")
            payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if diagnostics["missing"]:
                warnings.append(f"optional/missing globals: {diagnostics['missing']}")
                print(f"  warning: optional/missing globals: {diagnostics['missing']}")
            print(f"  wrote: {payload_path}")

            print("[4/5] Update player_index.json")
            players = load_player_index(index_path)
            entry = {
                "player_id": str(args.player_id),
                "player_name": args.player_name,
                "slug": args.slug,
                "team_name": args.team_name,
                "source_club": args.source_club or args.team_name,
                "competition": args.competition,
                "season": normalize_season(args.season),
                "macro_role": args.role,
                "source_role": args.source_role,
                "report_role": args.role,
                "role_override_reason": args.role_override_reason,
                "target_team": args.target_team,
                "target_team_peer_ids": args.main_comparison_peer_ids,
                "source_team_peer_ids": args.source_team_peer_ids,
                "source_team_peer_label": args.source_team_peer_label or f"{args.team_name} {args.source_role}",
                "target_role_peer_ids": args.target_role_peer_ids,
                "report_file": f"{args.slug}.html",
                "report_status": args.report_status,
                "visibility": args.visibility,
                "payload_file": str(payload_path.relative_to(ROOT)),
                "payload_source": "soccerdb",
                "narrative": editorial_fields["narrative"],
                "source_team_note": editorial_fields["source_team_note"],
                "note_confronto": editorial_fields["note_confronto"],
                "note_heatmap": editorial_fields["note_heatmap"],
                "note_context": (
                    f"Role override: in the source team the player is recorded as {args.source_role}; "
                    f"in this report he is evaluated as {args.role}. {args.role_override_reason}\n\n"
                    + editorial_fields["note_context"]
                    if args.source_role != args.role and args.role_override_reason
                    else editorial_fields["note_context"]
                ),
                "note_similarity": editorial_fields["note_similarity"],
            }
            action = upsert_player_entry(players, entry)
            index_path.write_text(json.dumps(players, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"  {action}: {args.slug}")

            print("[5/5] Generate HTML page")
            commands_executed.append(run_command(generate_command, ROOT, False))
            if not html_path.exists():
                raise PageCreationError(f"generated HTML page not found: {html_path}")
            print(f"  verified: {html_path}")

        manifest = {
            "status": "dry-run" if args.dry_run else "success",
            "role": args.role,
            "source_role": args.source_role,
            "report_role": args.role,
            "role_override_reason": args.role_override_reason,
            "player_id": str(args.player_id),
            "player_name": args.player_name,
            "slug": args.slug,
            "main_comparison_peer_ids": args.main_comparison_peer_ids,
            "target_team_peer_ids": args.main_comparison_peer_ids,
            "source_team_peer_ids": args.source_team_peer_ids,
            "comparison_label": args.comparison_label,
            "team_name": args.team_name,
            "source_club": args.source_club or args.team_name,
            "competition": args.competition,
            "season": normalize_season(args.season),
            "target_team": args.target_team,
            "source_team_peer_label": args.source_team_peer_label or f"{args.team_name} {args.source_role}",
            "source_context_exported": bool(args.source_team_peer_ids and not args.source_context_editorial_only),
            "source_context_editorial_only": args.source_context_editorial_only,
            "target_role_peer_ids": args.target_role_peer_ids,
            "visibility": args.visibility,
            "report_status": args.report_status,
            "editorial_fields": editorial_fields,
            "unsupported_editorial_fields": unsupported_editorial,
            "snapshot_path": str(snapshot_path),
            "payload_path": str(payload_path),
            "player_index_path": str(index_path),
            "html_path": str(html_path),
            "commands_planned": commands_planned,
            "commands_executed": commands_executed,
            "backups": backups,
            "warnings": warnings,
            "errors": errors,
        }
        write_manifest(manifest_path, manifest)
        return 0
    except PageCreationError as exc:
        errors.append(str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        manifest = {
            "status": "failed",
            "role": args.role,
            "source_role": args.source_role,
            "report_role": args.role,
            "role_override_reason": args.role_override_reason,
            "player_id": str(args.player_id),
            "player_name": args.player_name,
            "slug": args.slug,
            "main_comparison_peer_ids": args.main_comparison_peer_ids,
            "target_team_peer_ids": args.main_comparison_peer_ids,
            "source_team_peer_ids": args.source_team_peer_ids,
            "comparison_label": args.comparison_label,
            "team_name": args.team_name,
            "source_club": args.source_club or args.team_name,
            "competition": args.competition,
            "season": normalize_season(args.season),
            "target_team": args.target_team,
            "source_team_peer_label": args.source_team_peer_label or f"{args.team_name} {args.source_role}",
            "source_context_exported": bool(args.source_team_peer_ids and not args.source_context_editorial_only),
            "source_context_editorial_only": args.source_context_editorial_only,
            "target_role_peer_ids": args.target_role_peer_ids,
            "visibility": args.visibility,
            "report_status": args.report_status,
            "unsupported_editorial_fields": unsupported_editorial,
            "snapshot_path": str(snapshot_path),
            "payload_path": str(payload_path),
            "player_index_path": str(index_path),
            "html_path": str(html_path),
            "commands_planned": commands_planned,
            "commands_executed": commands_executed,
            "backups": backups,
            "warnings": warnings,
            "errors": errors,
        }
        write_manifest(manifest_path, manifest)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
