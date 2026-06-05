#!/usr/bin/env python3
"""
Generate an editorial brief for a player report.

Reads player_index.json and the corresponding payload JSON, extracts key
data points for each section, and writes a structured Markdown file that
can be fed directly to an AI to generate the 4 editorial section notes.

Usage:
    python generate_editorial_brief.py --slug curtis-jones
    python generate_editorial_brief.py --slug curtis-jones --open

Output:
    data/editorial/{slug}.brief.md

Workflow:
    1. Run this script  →  data/editorial/{slug}.brief.md
    2. (Optional) add analyst notes in the "> …" fields
    3. Paste the whole file into Claude / ChatGPT
    4. Copy the 4 JSON fields into assets/data/player_index.json
    5. Run: python generate_pages.py --slug {slug}
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent
INDEX      = BASE_DIR / "assets/data/player_index.json"
OUTPUT_DIR = BASE_DIR / "data/editorial"

# ── Metric labels (IT) ────────────────────────────────────────────────────────
METRIC_LABELS_IT = {
    "Pass completion":                    "Completamento passaggi",
    "Pass share team":                    "Quota passaggi squadra",
    "Receival attempts per90":            "Ricezioni tentate p90",
    "Average pass distance":              "Distanza media passaggio",
    "Progressive pass share":             "Quota pass. progressivi",
    "Passes ending final third per90":    "Pass. nel terzo finale p90",
    "Passes ending box per90":            "Pass. in area p90",
    "Progressive carry attempts per90":   "Conduzioni progressive p90",
    "Take-on attempts per90":             "Dribbling tentati p90",
    "Average progressive carry distance": "Dist. media cond. prog.",
    "Shot-creating actions per90":        "Az. che generano tiro p90",
    "Expected assists per90":             "xA p90",
    "Final third receival share":         "Quota rice. terzo finale",
    "Shot attempts per90":                "Tiri p90",
    "xG per90":                           "xG p90",
    "Avg shot distance":                  "Dist. media tiro",
    "Shot quality":                       "Qualità del tiro",
    "Tackles padj":                       "Contrasti (padj)",
    "Interceptions padj":                 "Intercetti (padj)",
    "Aerial attempts per90":              "Duelli aerei p90",
    "Tackle success rate":                "Successo nei contrasti",
}

ROLE_PLURAL = {
    "MID": "centrocampisti",
    "ATT": "attaccanti",
    "DEF": "difensori",
    "GK":  "portieri",
}

FORMAT_FNS = {
    "percent": lambda v: f"{v:.1%}",
    "meters":  lambda v: f"{v:.1f} m",
    "number":  lambda v: f"{v:.2f}",
}

RADAR_AXIS_ORDER = [
    "technical_security",
    "progression",
    "creation",
    "direct_threat",
    "defensive_contribution",
]

GK_AXIS_LABELS_IT = {
    "shot_stopping": "Parate e rendimento sui tiri",
    "box_control": "Controllo dell'area",
    "sweeper_activity": "Uscite e copertura profondita",
    "distribution": "Distribuzione",
}

GK_METRIC_LABELS_IT = {
    "save_pct": "Save percentage",
    "xgot_faced_minus_goals_conceded_per90": "xGOT - gol concessi p90",
    "goals_conceded_per90": "Gol concessi p90",
    "cross_stop_pct": "Cross stop %",
    "claim_rate_on_crosses": "Claim rate sui cross",
    "def_actions_outside_box_per90": "Azioni fuori area p90",
    "pass_attempts_per90": "Passaggi tentati p90",
    "pass_completion_pct": "Completamento passaggi",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_season(raw: str) -> str:
    s = raw.strip()
    if len(s) == 4 and s.isdigit():
        return f"20{s[:2]}–{s[2:]}"
    return raw


def fmt_val(value, metric_key: str, metric_formats: dict) -> str:
    fmt = metric_formats.get(metric_key, "number")
    fn  = FORMAT_FNS.get(fmt, FORMAT_FNS["number"])
    try:
        return fn(float(value))
    except (TypeError, ValueError):
        return str(value)


def fmt_gk_val(value, metric_key: str) -> str:
    if value is None:
        return "–"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if metric_key.endswith("_pct") or metric_key in {"save_pct", "cross_stop_pct", "claim_rate_on_crosses", "pass_completion_pct"}:
        return f"{v:.1%}"
    if "per90" in metric_key:
        return f"{v:.2f} p90"
    return f"{v:.2f}"


def group_names(player_meta: dict, ids: list) -> list[str]:
    return [player_meta.get(str(pid), {}).get("name", str(pid)) for pid in ids]


def bars_diffs(bar_section: dict, metric_formats: dict) -> list[dict]:
    """Flatten all metrics with (subject − baseline) delta, sorted desc."""
    rows = []
    for group in bar_section.get("groups", []):
        for m in group.get("metrics", []):
            diff = m["subjectScore"] - m["baselineScore"]
            rows.append({
                "label":         m.get("label", METRIC_LABELS_IT.get(m["metric"], m["metric"])),
                "metric":        m["metric"],
                "group":         group["label"],
                "subject_raw":   m["subjectValue"],
                "baseline_raw":  m["baselineValue"],
                "subject_score": m["subjectScore"],
                "baseline_score":m["baselineScore"],
                "diff":          diff,
            })
    rows.sort(key=lambda x: x["diff"], reverse=True)
    return rows


def radar_rows(radar_data: dict, radar_axes: list) -> list[dict]:
    """Return per-axis comparison rows in canonical order."""
    sv   = radar_data["subject"]["values"]
    tv   = radar_data["target"]["values"]
    sov  = radar_data.get("sourceTeam", {}).get("values", [])
    keys = [a["key"] for a in radar_axes]

    def row(i):
        s   = sv[i]  if i < len(sv)  else None
        t   = tv[i]  if i < len(tv)  else None
        so  = sov[i] if i < len(sov) else None
        return {
            "key":    keys[i],
            "label":  radar_axes[i]["label"],
            "subject": s,
            "target":  t,
            "source":  so,
            "diff":    round(s - t, 2) if s is not None and t is not None else None,
        }

    ordered = sorted(
        range(len(radar_axes)),
        key=lambda i: RADAR_AXIS_ORDER.index(keys[i])
                      if keys[i] in RADAR_AXIS_ORDER else 99,
    )
    return [row(i) for i in ordered]


def build_gk_brief(player: dict, payload: dict) -> str:
    players_env = payload["GK_PAGE_V1_PLAYERS"]
    comparisons_env = payload["GK_PAGE_V1_TEAM_COMPARISONS"]
    summary_env = payload["GK_PAGE_V1_SUMMARY"]
    context = players_env.get("report_context", {}) or summary_env.get("report_context", {})

    subject_id = int(context.get("target_player_id") or player.get("player_id"))
    target_team = context.get("comparison_team_name") or player.get("target_team", "Inter")
    source_club = player.get("source_club") or player.get("team_name") or ""
    subject = None
    for item in players_env.get("players", []):
        if int(item.get("header", {}).get("player_id", -1)) == subject_id:
            subject = item
            break
    if subject is None:
        raise KeyError(f"GK subject {subject_id} not found in payload")

    header = subject["header"]
    subject_name = header["player_name"]
    season = fmt_season(str(header.get("season_id", player.get("season", ""))))
    comp = header.get("competition_name") or player.get("competition", "")
    minutes = header.get("minutes")
    sample_status = header.get("sample_status", "")
    narrative = player.get("narrative", "").strip()

    inter_comparison = None
    for item in comparisons_env.get("team_comparisons", []):
        comp_obj = item.get("team_gk_comparison", {})
        if comp_obj.get("team_name") == target_team:
            inter_comparison = comp_obj
            break
    inter_gks = inter_comparison.get("gks", []) if inter_comparison else []
    inter_names = [g.get("player_name", "") for g in inter_gks]

    axes = subject.get("radar", {}).get("axes", [])
    subject_metrics = subject.get("action_split", {})
    visuals = subject.get("visual_blocks", {})
    goal_map = visuals.get("goal_map_save_map", {})
    sweeper = visuals.get("sweeper_actions_map", {})
    distribution = visuals.get("distribution_profile", {})
    buildup = visuals.get("build_up_map", {})

    L = [
        f"# Brief editoriale GK — {subject_name}",
        f"**Ruolo**: Portiere · **Destinazione**: {target_team} · **Stagione**: {season} · **Campionato**: {comp}",
        f"**Club di provenienza**: {source_club} · **Minuti**: {minutes:.0f} · **Sample**: {sample_status}",
        "",
    ]

    if narrative:
        L += ["## Incipit esistente", f"> {narrative}", ""]

    L += [
        "---",
        "## § Lettura generale",
        "Radar GK a 4 assi. Scala 0–100, normalizzata nel contesto competitivo.",
        "",
        "| Asse | Score | z-score | Componenti principali |",
        "|------|------:|--------:|-----------------------|",
    ]
    for axis in axes:
        axis_id = axis.get("axis_id")
        label = GK_AXIS_LABELS_IT.get(axis_id, axis.get("axis_name", axis_id))
        comps = ", ".join(GK_METRIC_LABELS_IT.get(m.get("metric_name"), m.get("metric_name", "")) for m in axis.get("component_metrics", [])[:3])
        L.append(f"| {label} | {axis.get('axis_score_0_100', 0):.1f} | {axis.get('axis_z_score', 0):+.2f} | {comps} |")
    L += ["", "**Note analista** *(facoltativo)*:", "> …", ""]

    L += [
        "---",
        f"## § Barre vs portieri {target_team}",
        f"Confronto visuale con: {', '.join(inter_names)}.",
        "",
        "| Metrica | " + subject_name + " | " + " | ".join(inter_names) + " |",
        "|---------|" + "---:|" * (1 + len(inter_names)),
    ]
    key_metrics = [
        "save_pct",
        "goals_conceded_per90",
        "cross_stop_pct",
        "claim_rate_on_crosses",
        "def_actions_outside_box_per90",
        "pass_attempts_per90",
        "pass_completion_pct",
    ]
    raw_subject = {
        "save_pct": subject_metrics.get("saves", {}).get("percentage_or_share"),
        "goals_conceded_per90": subject_metrics.get("goals_conceded", {}).get("per90"),
        "cross_stop_pct": subject_metrics.get("crosses_stopped", {}).get("percentage_or_share"),
        "claim_rate_on_crosses": subject_metrics.get("claims", {}).get("percentage_or_share"),
        "def_actions_outside_box_per90": subject_metrics.get("defensive_actions_outside_box", {}).get("per90"),
        "pass_attempts_per90": subject_metrics.get("passes_attempted", {}).get("per90"),
    }
    for axis in axes:
        for metric in axis.get("component_metrics", []):
            metric_name = metric.get("metric_name")
            if raw_subject.get(metric_name) is None:
                raw_subject[metric_name] = metric.get("raw_value")
    raw_subject.update(subject.get("visual_blocks", {}).get("distribution_profile", {}).get("season_metrics", {}) or {})
    raw_subject.update(subject.get("header", {}).get("key_raw_metrics", {}) or {})
    # Prefer the team-comparison raw metrics when available.
    target_row = next((g for g in ([{"player_name": subject_name, "key_raw_metrics": {}}] + inter_gks) if g.get("player_name") == subject_name), None)
    if target_row and target_row.get("key_raw_metrics"):
        raw_subject.update(target_row["key_raw_metrics"])
    for metric in key_metrics:
        vals = [fmt_gk_val(raw_subject.get(metric), metric)]
        vals += [fmt_gk_val(g.get("key_raw_metrics", {}).get(metric), metric) for g in inter_gks]
        L.append(f"| {GK_METRIC_LABELS_IT.get(metric, metric)} | " + " | ".join(vals) + " |")
    L += [
        "",
        "**Lettura attesa**: non cercare un vincitore secco. Separare rendimento sui tiri, gestione area, altezza/uscite e uso coi piedi.",
        "",
        "**Note analista** *(facoltativo)*:",
        "> …",
        "",
    ]

    L += [
        "---",
        "## § Visualizzazioni / heatmap portiere",
        "La V1 GK non usa heatmap posizionali generiche: usa mappe specifiche da portiere.",
        "",
    ]
    if goal_map:
        L.append(f"- Goal/save map: {goal_map.get('visual_status', 'n/d')} · tiri nello specchio: {goal_map.get('total_on_target', '–')}")
    if sweeper:
        L.append(
            "- Sweeper / defensive range: "
            f"{sweeper.get('event_count', '–')} eventi, "
            f"{fmt_gk_val(sweeper.get('event_count_per90'), 'event_count_per90')}, "
            f"quota fuori area {fmt_gk_val(sweeper.get('outside_box_share'), 'outside_box_share_pct')}"
        )
    if distribution:
        L.append(f"- Distribuzione: {distribution.get('event_count', '–')} passaggi/eventi; profilo per lunghezza, corsia e profondita.")
    if buildup:
        L.append(f"- Build-up map: {buildup.get('visual_status', 'n/d')} · eventi totali: {buildup.get('total_events', '–')}")
    L += ["", "**Note analista** *(facoltativo — pattern visibili nelle mappe)*:", "> …", ""]

    L += [
        "---",
        "---",
        "## PROMPT PER L'AI",
        "",
        "Sei il redattore di una pubblicazione italiana di scouting calcistico.",
        f"Usa i dati del brief qui sopra per scrivere una narrative iniziale e 2 note editoriali in italiano per il report GK di **{subject_name}**.",
        "",
        "**Regole:**",
        "- Tono: interpretativo, editoriale. Guida il lettore, non elencare dati.",
        "- Lunghezza narrative: 1 paragrafo da 3–4 frasi.",
        "- Lunghezza note: 2–3 frasi compatte per nota.",
        "- Non inventare un contesto squadra o una similarità: qui il report ha solo lettura generale, confronto con i portieri Inter e visualizzazioni GK.",
        "- Audience: direttori sportivi e analisti calcistici.",
        "- Evita frasi come «i dati mostrano» o «il grafico indica».",
        "",
        "**Campi da produrre:**",
        "",
        f"1. **narrative** — Incipit editoriale: che tipo di portiere è {subject_name}, perché è leggibile per {target_team}, e quale cautela serve?",
        "",
        f"2. **note_confronto** — Come si colloca {subject_name} rispetto a {', '.join(inter_names)} nelle barre?",
        "",
        "3. **note_heatmap** — Cosa rivelano goal map, sweeper range, distribuzione e build-up map sul suo uso effettivo?",
        "",
        "**Formato output** (copia-incolla diretto in player_index.json):",
        "```json",
        '"narrative": "...",',
        '"note_confronto": "...",',
        '"note_heatmap": "...",',
        '"note_context": "",',
        '"note_similarity": ""',
        "```",
    ]
    return "\n".join(L)


# ── Core builder ──────────────────────────────────────────────────────────────

def build_brief(player: dict, payload: dict) -> str:
    if "GK_PAGE_V1_PLAYERS" in payload:
        return build_gk_brief(player, payload)

    subject_id   = str(payload["SUBJECT_ID"])
    player_meta  = payload["PLAYER_META"]
    subject_name = player_meta[subject_id]["name"]
    role_label   = payload["ROLE_META"]["label"]
    macro_role   = payload["ROLE_META"]["role"]
    role_plural  = ROLE_PLURAL.get(macro_role, role_label.lower() + "i")
    metric_fmts  = payload["METRIC_FORMATS"]

    cg           = payload["COMPARISON_GROUPS"]
    target_grp   = cg[0]
    source_grp   = cg[1] if len(cg) > 1 else {}
    target_names = group_names(player_meta, target_grp.get("ids", []))
    source_names = group_names(player_meta, source_grp.get("ids", []))

    target_team = player.get("target_team", "Inter")
    source_club = player.get("source_club") or player.get("team_name") or ""
    season      = fmt_season(player.get("season", ""))
    comp        = player.get("competition", "")
    narr        = player.get("narrative", "").strip()
    src_note    = player.get("source_team_note", "").strip()

    radar  = radar_rows(payload["RADAR_DATA"], payload["RADAR_AXES"])
    t_bars = bars_diffs(payload["TARGET_COMPARISON_BARS"],      metric_fmts)
    s_bars = bars_diffs(payload["SOURCE_TEAM_COMPARISON_BARS"], metric_fmts)
    sim    = payload["SIMILARITY_DATA"]
    subj_hm = payload["HEATMAP_DATA"].get(subject_id, {})

    L = []  # lines

    # ── HEADER ────────────────────────────────────────────────────────────────
    L += [
        f"# Brief editoriale — {subject_name}",
        f"**Ruolo**: {role_label} · **Destinazione**: {target_team} · "
        f"**Stagione**: {season} · **Campionato**: {comp}",
        f"**Club di provenienza**: {source_club}",
        "",
    ]

    # ── INCIPIT ESISTENTE ─────────────────────────────────────────────────────
    if narr:
        L += [
            "## Incipit esistente",
            f"> {narr}",
            "",
        ]

    # ── § RADAR ───────────────────────────────────────────────────────────────
    target_preview = ", ".join(target_names[:3]) + ("…" if len(target_names) > 3 else "")
    L += [
        "---",
        "## § Profilo radar",
        f"Scala 0–100 (role-minmax). Riferimento Inter: {target_preview}",
        "",
        f"| Asse | {subject_name.split()[0]} | Inter avg | Δ | {source_club} avg |",
        "|------|------:|----------:|--:|--------------:|",
    ]
    for ax in radar:
        s_str  = f"{ax['subject']:.1f}"  if ax['subject']  is not None else "–"
        t_str  = f"{ax['target']:.1f}"   if ax['target']   is not None else "–"
        so_str = f"{ax['source']:.1f}"   if ax['source']   is not None else "–"
        d_str  = f"{ax['diff']:+.1f}"    if ax['diff']     is not None else "–"
        L.append(f"| {ax['label']} | {s_str} | {t_str} | {d_str} | {so_str} |")

    above = [ax["label"] for ax in radar if ax["diff"] is not None and ax["diff"] >  3]
    below = [ax["label"] for ax in radar if ax["diff"] is not None and ax["diff"] < -3]
    L.append("")
    if above:
        L.append(f"**Sopra media Inter (Δ > +3)**: {', '.join(above)}")
    if below:
        L.append(f"**Sotto media Inter (Δ < −3)**: {', '.join(below)}")
    L += ["", "**Note analista** *(facoltativo)*:", "> …", ""]

    # ── § CONFRONTO INDIVIDUALE ───────────────────────────────────────────────
    L += [
        "---",
        f"## § Confronto individuale vs {target_team}",
        f"Gruppo: {', '.join(target_names)}",
        "",
        f"**Metriche dove {subject_name.split()[0]} supera la baseline (top 5):**",
    ]
    for m in t_bars[:5]:
        sv = fmt_val(m["subject_raw"],  m["metric"], metric_fmts)
        bv = fmt_val(m["baseline_raw"], m["metric"], metric_fmts)
        L.append(
            f"- {m['label']} · {sv} vs {bv}"
            f" · score {m['subject_score']:.0f} vs {m['baseline_score']:.0f}"
            f" · **Δ = +{m['diff']:.1f}**"
        )
    L += ["", f"**Metriche dove {subject_name.split()[0]} è sotto la baseline (bottom 5):**"]
    for m in t_bars[-5:]:
        sv = fmt_val(m["subject_raw"],  m["metric"], metric_fmts)
        bv = fmt_val(m["baseline_raw"], m["metric"], metric_fmts)
        L.append(
            f"- {m['label']} · {sv} vs {bv}"
            f" · score {m['subject_score']:.0f} vs {m['baseline_score']:.0f}"
            f" · **Δ = {m['diff']:.1f}**"
        )
    L += ["", "**Note analista** *(facoltativo)*:", "> …", ""]

    # ── § IMPRONTA SPAZIALE ───────────────────────────────────────────────────
    ip_n   = subj_hm.get("ipN", "?")
    ip_ft  = subj_hm.get("ipFT")
    def_op = subj_hm.get("defOppPct")
    cx, cy = subj_hm.get("ipCx"), subj_hm.get("ipCy")
    prog_n = subj_hm.get("progN")
    carry_n= subj_hm.get("carryProgN")

    L += [
        "---",
        "## § Impronta spaziale",
        f"Tocchi totali nel campione: {ip_n}",
        "",
    ]
    if cx is not None:
        L.append(f"- Centroide posizionale: x={cx:.1f}, y={cy:.1f} "
                 "(x: 0=porta propria → 100=porta avversaria; y: 0=sinistra → 100=destra)")
    if ip_ft is not None:
        L.append(f"- Quota tocchi nel terzo offensivo: {ip_ft:.1%}")
    if def_op is not None:
        L.append(f"- Azioni difensive in metà avversaria: {def_op:.1%}")
    if prog_n is not None:
        L.append(f"- Passaggi progressivi: {prog_n} | Conduzioni progressive: {carry_n}")
    L += ["", "**Note analista** *(facoltativo — pattern visibili nelle 4 mappe)*:", "> …", ""]

    # ── § CONTESTO SOURCE CLUB ────────────────────────────────────────────────
    L += [
        "---",
        f"## § Contesto {source_club}",
        f"Gruppo: {', '.join(source_names)}",
        "",
    ]
    if src_note:
        L += [f"> Nota esistente: {src_note}", ""]
    L.append(f"**Top 5 metriche sopra la media {source_club}:**")
    for m in s_bars[:5]:
        sv = fmt_val(m["subject_raw"],  m["metric"], metric_fmts)
        bv = fmt_val(m["baseline_raw"], m["metric"], metric_fmts)
        L.append(f"- {m['label']} · {sv} vs {bv} · **Δ = +{m['diff']:.1f}**")
    L += ["", f"**Top 5 metriche sotto la media {source_club}:**"]
    for m in s_bars[-5:]:
        sv = fmt_val(m["subject_raw"],  m["metric"], metric_fmts)
        bv = fmt_val(m["baseline_raw"], m["metric"], metric_fmts)
        L.append(f"- {m['label']} · {sv} vs {bv} · **Δ = {m['diff']:.1f}**")
    L += ["", "**Note analista** *(facoltativo)*:", "> …", ""]

    # ── § SIMILARITÀ ─────────────────────────────────────────────────────────
    L += [
        "---",
        f"## § Similarità vs {target_team}",
        "",
    ]
    for space in sim:
        L.append(f"**{space['space']}**")
        L.append(f"_{space.get('description', '')}_")
        for i, m in enumerate(space.get("matches", [])[:5], 1):
            L.append(f"  {i}. {m['name']}  (score {m['score']:.1f})")
        L.append("")
    L += ["**Note analista** *(facoltativo)*:", "> …", ""]

    # ── AI PROMPT ─────────────────────────────────────────────────────────────
    L += [
        "---",
        "---",
        "## PROMPT PER L'AI",
        "",
        f"Sei il redattore di una pubblicazione italiana di scouting calcistico.",
        f"Usa i dati del brief qui sopra per scrivere una narrative iniziale e 4 note editoriali in italiano",
        f"per il report di **{subject_name}**.",
        "",
        "**Regole:**",
        "- Tono: interpretativo, editoriale. Guida il lettore, non elencare dati.",
        "- Lunghezza narrative: 1 paragrafo da 3–4 frasi.",
        "- Lunghezza note: 2–3 frasi compatte per nota.",
        "- Puoi usare Markdown leggero: **grassetto**, *corsivo*, paragrafi brevi.",
        "- Usa i dati come base di ragionamento, non come lista.",
        "- Audience: direttori sportivi e analisti calcistici.",
        "- Evita frasi come «i dati mostrano» o «il grafico indica».",
        "- Riferimenti a nomi di giocatori e squadre sono benvenuti.",
        "",
        "**Campi da produrre:**",
        "",
        f"1. **narrative** — Incipit editoriale del report: che tipo di profilo è {subject_name},",
        f"   perché è interessante per {target_team}, e quale cautela interpretativa serve?",
        "",
        f"2. **note_confronto** — Come si colloca {subject_name} rispetto ai",
        f"   {role_plural} dell'{target_team}? Complementarietà o ridondanza?",
        "",
        f"3. **note_heatmap** — Cosa rivela l'impronta spaziale sullo stile",
        f"   e sul raggio d'azione effettivo del giocatore?",
        "",
        f"4. **note_context** — Cosa dice il confronto con i compagni al {source_club}",
        f"   su chi è davvero {subject_name} fuori dal contesto narrativo?",
        "",
        f"5. **note_similarity** — Chi assomiglia di più a {subject_name} tra i",
        f"   {role_plural} dell'{target_team}? Cosa implica per la rosa?",
        "",
        "**Formato output** (copia-incolla diretto in player_index.json):",
        "```json",
        '"narrative": "...",',
        '"note_confronto": "...",',
        '"note_heatmap": "...",',
        '"note_context": "...",',
        '"note_similarity": "..."',
        "```",
    ]

    return "\n".join(L)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate editorial brief for a player")
    parser.add_argument("--slug", required=True, help="Player slug (e.g. curtis-jones)")
    parser.add_argument("--open", action="store_true",
                        help="Open the output file after generation (macOS)")
    args = parser.parse_args()

    if not INDEX.exists():
        sys.exit(f"Index not found: {INDEX}")

    players = json.loads(INDEX.read_text(encoding="utf-8"))
    matches = [p for p in players if p["slug"] == args.slug]
    if not matches:
        available = [p["slug"] for p in players]
        sys.exit(f"Slug '{args.slug}' not found.\nAvailable: {available}")
    player = matches[0]

    payload_file = player.get("payload_file")
    if not payload_file:
        sys.exit(f"No payload_file set for '{args.slug}'.")
    payload_path = BASE_DIR / payload_file
    if not payload_path.exists():
        sys.exit(f"Payload not found: {payload_path}")

    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    is_gk_payload = "GK_PAGE_V1_PLAYERS" in payload

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"{args.slug}.brief.md"
    brief = build_brief(player, payload)
    output_file.write_text(brief, encoding="utf-8")

    print(f"✓  Brief generato: {output_file}")
    print(f"\nWorkflow:")
    print(f"  1. Apri {output_file}")
    print(f"  2. (Opzionale) aggiungi note analista nei campi '> …'")
    print(f"  3. Incolla il file in Claude o ChatGPT")
    if is_gk_payload:
        print(f"  4. Copia narrative + note_confronto + note_heatmap in assets/data/player_index.json")
    else:
        print(f"  4. Copia narrative + i 4 campi JSON in assets/data/player_index.json")
    print(f"  5. python generate_pages.py --slug {args.slug}")

    if args.open:
        subprocess.run(["open", str(output_file)])


if __name__ == "__main__":
    main()
