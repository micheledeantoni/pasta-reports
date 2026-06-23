#!/usr/bin/env python3
"""Conservative role-report orchestration wrapper.

This first version coordinates existing export and HTML5UP validation commands.
It does not rebuild analytics or alter metric/radar/PCA/similarity logic.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROLE_CHOICES = ("GK", "DEF", "MID", "ATT")
MODE_CHOICES = ("validate-only", "export", "note-only")
DEFAULT_SOCCERDB_ROOT = Path("/Users/michele/Documents/SoccerDB")
EDITORIAL_METADATA_NOTICE = (
    "Target-team peers are recorded as editorial workflow metadata only. "
    "They are not passed to the exporter and do not modify the report payload."
)


class OrchestratorError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the conservative role-report workflow.")
    parser.add_argument("--mode", choices=MODE_CHOICES, default="export")
    parser.add_argument("--role", choices=ROLE_CHOICES, required=True)
    parser.add_argument("--player-id", type=int)
    parser.add_argument("--comparison-player-ids", default="")
    parser.add_argument("--target-team")
    parser.add_argument("--target-team-id", type=int)
    parser.add_argument("--target-role-peer-ids", default="")
    parser.add_argument("--editorial-note", default="")
    parser.add_argument("--editorial-notes-file", type=Path)
    parser.add_argument("--season")
    parser.add_argument("--html5up-root", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-validation", action="store_true")
    return parser.parse_args()


def detect_workspace_root() -> Path:
    candidates = [Path.cwd(), *Path.cwd().parents, Path(__file__).resolve().parents[2]]
    for base in candidates:
        if (base / "html5up-forty").is_dir():
            return base.resolve()
    return Path(__file__).resolve().parents[1]


def load_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.exists():
        raise OrchestratorError(f"config file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OrchestratorError(f"config file is not valid JSON: {path}: {exc}") from exc


def role_config(config: dict[str, Any], role: str) -> dict[str, Any]:
    merged = dict(config.get("defaults", {}))
    roles = config.get("roles", {})
    if isinstance(roles, dict):
        merged.update(roles.get(role, {}))
    return merged


def python_for(root: Path) -> str:
    venv_python = root / ".venv" / "bin" / "python"
    return str(venv_python if venv_python.exists() else Path(sys.executable))


def command_text(command: list[str]) -> str:
    return " ".join(command)


def make_export_command(
    args: argparse.Namespace,
    config: dict[str, Any],
    workspace_root: Path,
) -> tuple[list[str], Path]:
    soccerdb_root = Path(config.get("soccerdb_root") or DEFAULT_SOCCERDB_ROOT).expanduser().resolve()
    exporter = Path(config.get("exporter") or soccerdb_root / "scripts" / "exports" / "export_role_report_data.py")
    if not exporter.exists():
        raise OrchestratorError(f"role export command not found: {exporter}")
    command = [
        python_for(soccerdb_root),
        str(exporter),
        "--role",
        args.role,
        "--player-id",
        str(args.player_id),
    ]
    if args.comparison_player_ids:
        command.extend(["--comparison-ids", args.comparison_player_ids])
    else:
        command.extend(["--comparison-ids", ""])

    optional_map = {
        "player_name": "--player-name",
        "comparison_label": "--comparison-label",
        "context_ids": "--context-ids",
        "context_label": "--context-label",
        "colors": "--colors",
        "top_n_sim": "--top-n-sim",
    }
    for key, flag in optional_map.items():
        value = config.get(key)
        if value not in (None, ""):
            command.extend([flag, str(value)])

    output = config.get("output")
    if output:
        output_path = Path(str(output).format(role=args.role, player_id=args.player_id, season=args.season or ""))
        if not output_path.is_absolute():
            output_path = workspace_root / output_path
        command.extend(["--output", str(output_path)])
    if args.dry_run:
        command.append("--dry-run")
    return command, soccerdb_root


def make_validation_command(config: dict[str, Any]) -> list[str]:
    validation = config.get("validation_command") or [
        "python3",
        "scripts/proofs/validate_role_pages_external_only_state.py",
    ]
    if isinstance(validation, str):
        return validation.split()
    if not isinstance(validation, list) or not validation:
        raise OrchestratorError("validation_command config must be a non-empty string or list")
    return [str(part) for part in validation]


def run_step(command: list[str], cwd: Path, dry_run: bool) -> dict[str, Any]:
    print(f"  cwd: {cwd}")
    print(f"  cmd: {command_text(command)}")
    if dry_run:
        print("  dry-run: command not executed")
        return {"command": command, "cwd": str(cwd), "skipped": True, "returncode": None}
    result = subprocess.run(command, cwd=cwd, text=True)
    if result.returncode != 0:
        raise OrchestratorError(f"command failed with exit code {result.returncode}: {command_text(command)}")
    return {"command": command, "cwd": str(cwd), "skipped": False, "returncode": result.returncode}


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nManifest: {path}")


def read_editorial_notes_file(path: Path | None) -> str:
    if path is None:
        return ""
    if not path.exists():
        raise OrchestratorError(f"editorial notes file not found: {path}")
    return path.read_text(encoding="utf-8")


def write_editorial_notes(
    path: Path,
    *,
    args: argparse.Namespace,
    export_command: list[str] | None,
    validation_command: list[str] | None,
    editorial_file_text: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Role Report Editorial Notes",
        "",
        f"- Role: `{args.role}`",
        f"- Analyzed player ID: `{args.player_id if args.player_id is not None else ''}`",
        f"- Comparison player IDs: `{args.comparison_player_ids}`",
        f"- Target team: `{args.target_team or ''}`",
        f"- Target team ID: `{args.target_team_id if args.target_team_id is not None else ''}`",
        f"- Target role peer IDs: `{args.target_role_peer_ids}`",
        "",
        "## Editorial Metadata Notice",
        "",
        EDITORIAL_METADATA_NOTICE,
        "",
        "## Editorial Note",
        "",
        args.editorial_note or "",
        "",
        "## Editorial Notes File",
        "",
        f"- Path: `{str(args.editorial_notes_file) if args.editorial_notes_file else ''}`",
        "",
        "## Editorial Notes File Content",
        "",
    ]
    if editorial_file_text:
        lines.extend(["```markdown", editorial_file_text.rstrip(), "```", ""])
    else:
        lines.append("")
    lines.extend(
        [
            "## Generated Export Command",
            "",
            f"`{command_text(export_command) if export_command else ''}`",
            "",
            "## Validation Command",
            "",
            f"`{command_text(validation_command) if validation_command else ''}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Editorial notes: {path}")


def main() -> int:
    args = parse_args()
    workspace_root = detect_workspace_root()
    config: dict[str, Any] = {}
    commands_planned: list[dict[str, Any]] = []
    commands_executed: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    manifest_path = (
        workspace_root
        / "outputs"
        / "report_generation_runs"
        / f"{timestamp}_{args.role}"
        / "run_manifest.json"
    )
    editorial_notes_path = manifest_path.parent / "editorial_notes.md"

    try:
        raw_config = load_config(args.config)
        config = role_config(raw_config, args.role)
        editorial_file_text = read_editorial_notes_file(args.editorial_notes_file)
        html5up_root = (
            args.html5up_root
            or Path(config.get("html5up_root") or workspace_root / "html5up-forty")
        ).expanduser().resolve()
        if not html5up_root.exists():
            raise OrchestratorError(f"html5up root not found: {html5up_root}")

        print(f"[1/4] Workspace root: {workspace_root}")
        print(f"[2/4] HTML5UP root: {html5up_root}")

        validation_command: list[str] | None = None
        export_command: list[str] | None = None

        if args.mode == "export":
            if args.player_id is None:
                raise OrchestratorError(
                    "missing --player-id. Run the resolver first, for example: "
                    f'python scripts/resolve_role_report_players.py --query "paz" --role {args.role}'
                    + (f" --season {args.season}" if args.season else "")
                )
            if not args.comparison_player_ids:
                print(
                    "[info] --comparison-player-ids not provided; continuing because the existing exporter "
                    "supports an empty comparison group."
                )
            export_command, export_cwd = make_export_command(args, config, workspace_root)
            commands_planned.append({"name": "export", "command": export_command, "cwd": str(export_cwd)})
            print("[3/4] Export role payload")
            commands_executed.append(run_step(export_command, export_cwd, args.dry_run))
        elif args.mode == "note-only":
            print("[3/4] Export skipped for note-only mode")
        else:
            print("[3/4] Export skipped for validate-only mode")

        if args.target_team or args.target_team_id is not None or args.target_role_peer_ids:
            warnings.append(EDITORIAL_METADATA_NOTICE)
            print(f"[info] {EDITORIAL_METADATA_NOTICE}")

        if args.mode == "note-only":
            print("[4/4] Validation skipped for note-only mode")
        elif args.skip_validation:
            print("[4/4] Validation skipped by --skip-validation")
        else:
            validation_command = make_validation_command(config)
            commands_planned.append(
                {"name": "validation", "command": validation_command, "cwd": str(html5up_root)}
            )
            print("[4/4] HTML5UP validation")
            commands_executed.append(run_step(validation_command, html5up_root, args.dry_run))

        write_editorial_notes(
            editorial_notes_path,
            args=args,
            export_command=export_command,
            validation_command=validation_command,
            editorial_file_text=editorial_file_text,
        )

        manifest = {
            "role": args.role,
            "player_id": args.player_id,
            "comparison_player_ids": args.comparison_player_ids,
            "target_team": args.target_team,
            "target_team_id": args.target_team_id,
            "target_role_peer_ids": args.target_role_peer_ids,
            "editorial_note": args.editorial_note,
            "editorial_notes_file": str(args.editorial_notes_file) if args.editorial_notes_file else "",
            "editorial_notes_output": str(editorial_notes_path),
            "season": args.season,
            "mode": args.mode,
            "html5up_root": str(html5up_root),
            "commands_planned": commands_planned,
            "commands_executed": commands_executed,
            "validation_command": validation_command,
            "status": "dry-run" if args.dry_run else "success",
            "errors": errors,
            "warnings": warnings,
        }
        write_manifest(manifest_path, manifest)
        return 0
    except OrchestratorError as exc:
        errors.append(str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        manifest = {
            "role": args.role,
            "player_id": args.player_id,
            "comparison_player_ids": args.comparison_player_ids,
            "target_team": args.target_team,
            "target_team_id": args.target_team_id,
            "target_role_peer_ids": args.target_role_peer_ids,
            "editorial_note": args.editorial_note,
            "editorial_notes_file": str(args.editorial_notes_file) if args.editorial_notes_file else "",
            "editorial_notes_output": str(editorial_notes_path),
            "season": args.season,
            "mode": args.mode,
            "html5up_root": str(args.html5up_root or ""),
            "commands_planned": commands_planned,
            "commands_executed": commands_executed,
            "validation_command": None,
            "status": "failed",
            "errors": errors,
            "warnings": warnings,
        }
        write_manifest(manifest_path, manifest)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
