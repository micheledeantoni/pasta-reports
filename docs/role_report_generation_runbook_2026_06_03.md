# Role Report Generation Runbook

Guida operativa finale per generare o rigenerare una pagina player report ruolo nel sito PASTA.

Esempi reali usati per validare il flusso:

- Oumar Solet
- Marco Palestra
- Aleksandar Stankovic, con context corretto sui centrocampisti Club Brugge
- caso troubleshooting Andy Diouf senza heatmap nel report Palestra

## Workflow raccomandato

Il flusso consigliato ora parte dal resolver e passa dall'orchestrator
conservativo. Questo riduce il lavoro manuale di ricerca ID senza scegliere
automaticamente i comparatori.

Da `/Users/michele/Documents/Data_scouting_app`:

1. Trovare il giocatore analizzato.

```bash
make find-player QUERY="paz" ROLE=MID
```

2. Scegliere manualmente il `player_id` corretto dai candidati, poi trovare i
   peer del club sorgente: stessa squadra, stesso ruolo, stessa competizione e
   stessa stagione del giocatore analizzato. Questi alimentano il contesto
   sorgente, non il confronto principale.

```bash
make find-squad-role-peers PLAYER_ID=448659 ROLE=MID
```

3. Opzionalmente, trovare la squadra target per preparare note editoriali.

```bash
make find-team TEAM="Inter"
```

4. Trovare i pari ruolo gia' presenti nella squadra target. Per pagine scouting
   Inter, questi sono il gruppo principale: radar, barre e prima sezione di
   confronto.

```bash
make find-target-role-peers TEAM="Inter" ROLE=MID
```

5. Scegliere manualmente `PEERS` dalla lista target-team same-role, e
   `SOURCE_TEAM_PEERS` dalla lista source-team same-role, poi avviare
   l'export/preparazione.

```bash
make role-report ROLE=MID PLAYER_ID=448659 PEERS=444,555,666 SOURCE_TEAM_PEERS=111,222,333 SOURCE_TEAM_PEER_LABEL="Como MID" TARGET_TEAM="Inter" NOTE="Nico Paz evaluated as an internal creativity fit against Inter midfield peers."
```

Sintassi Make importante: non mettere spazi attorno a `=` e non inserire spazi
dentro le liste separate da virgola. Usare `PEERS=425115,424834`, non
`PEERS= 425115, 424834`. Lo stesso vale per `SOURCE_TEAM_PEERS`.

6. Creare o aggiornare la pagina HTML5UP live.

```bash
make player-page ROLE=MID PLAYER_ID=448659 PLAYER_NAME="Nico Paz" SLUG=nico-paz PEERS=444,555,666 COMPARISON_LABEL="Inter MID" SOURCE_TEAM_PEERS=111,222,333 SOURCE_TEAM_PEER_LABEL="Como MID" TEAM="Como" COMPETITION="ITA-Serie A" SEASON=2526 TARGET_TEAM="Inter"
```

`make role-report` prepara l'export e salva metadati editoriali di workflow.
`make player-page` crea lo snapshot inline, scrive
`data/report_legacy_payloads/<slug>.legacy_role_payload.json`, aggiorna
`assets/data/player_index.json` e lancia `generate_pages.py --slug <slug>`.

### Mappa sezioni pagina role report

`oumar-solet.html` e' il modello golden per le pagine ruolo generate.
La pagina ha queste sezioni, in ordine:

| Sezione pagina | Fonte | Campo / payload | Significato |
|---|---|---|---|
| Banner | `player_index.json` + payload minuti | `player_name`, `source_club`, `target_team`, `macro_role`, `competition`, `season`, `PLAYER_META[SUBJECT_ID].mins` | Identita' report e direzione editoriale source → target. |
| Lettura del profilo | `player_index.json`, fallback payload | `narrative`, fallback `PROFILE_READING.paragraphs` | Lettura sintetica del profilo e fit editoriale. |
| Profilo sintetico radar | payload | `RADAR_AXES`, `RADAR_DATA`, `COMPARISON_GROUPS` | Assi stilistici normalizzati e selettore confronto. |
| Confronto individuale | `player_index.json` + payload | `note_confronto`, `TARGET_COMPARISON_BARS` | Barre tecniche contro il gruppo passato come `--comparison-ids`. |
| Impronta spaziale | `player_index.json` + payload | `note_heatmap`, `HEATMAP_DATA` | Lettura delle quattro mappe; per `DEF` il quarto pannello e' `Azioni difensive`. |
| Contesto club attuale | `player_index.json` + payload | `note_context`, `source_team_note`, `SOURCE_TEAM_COMPARISON_BARS` | Interpretazione nel club sorgente e, se presente, secondo gruppo contestuale. |
| Similarita' | `player_index.json` + payload | `note_similarity`, `SIMILARITY_DATA` | Lettura dei profili simili calcolati dall'exporter. |

Campi editoriali supportati in `assets/data/player_index.json`:

```json
{
  "narrative": "",
  "source_team_note": "",
  "note_confronto": "",
  "note_heatmap": "",
  "note_context": "",
  "note_similarity": ""
}
```

Per il workflow corretto attuale, `PEERS` / `--comparison-ids` significa
pari ruolo della squadra target. Questo e' il modello usato da
`oumar-solet.html`: Inter DEF alimenta radar, barre principali e similarita'.
`SOURCE_TEAM_PEERS` / `--context-ids` significa pari ruolo del club sorgente e
alimenta la sezione "Contesto club attuale".

7. Validare lo stato HTML5UP.

```bash
make role-report-validate ROLE=MID
```

Equivalenti Python diretti:

```bash
python scripts/resolve_role_report_players.py --query "paz" --role MID --season 2025-2026
python scripts/resolve_role_report_players.py --player-id 448659 --list-squad-role-peers --role MID --season 2025-2026 --min-minutes 300
python scripts/resolve_role_report_players.py --query-team "Inter" --season 2025-2026
python scripts/resolve_role_report_players.py --target-team "Inter" --list-target-role-peers --role MID --season 2025-2026 --min-minutes 300
python scripts/orchestrate_role_report.py --role MID --player-id 448659 --main-comparison-peer-ids 444,555,666 --source-team-peer-ids 111,222,333 --source-team-peer-label "Como MID" --target-team "Inter" --editorial-note "Nico Paz evaluated as an internal creativity fit against Inter midfield peers." --mode export
python scripts/orchestrate_role_report.py --role MID --player-id 448659 --main-comparison-peer-ids 444,555,666 --source-team-peer-ids 111,222,333 --source-team-peer-label "Como MID" --target-team "Inter" --editorial-note "Nico Paz evaluated as an internal creativity fit against Inter midfield peers." --mode note-only
python scripts/create_player_page_from_export.py --role MID --player-id 448659 --player-name "Nico Paz" --slug nico-paz --main-comparison-peer-ids 444,555,666 --comparison-label "Inter MID" --source-team-peer-ids 111,222,333 --source-team-peer-label "Como MID" --team-name "Como" --source-club "Como" --competition "ITA-Serie A" --season 2526 --target-team "Inter" --visibility hidden
python scripts/orchestrate_role_report.py --role MID --mode validate-only
```

Nota importante: PEERS in the export command means target-team same-role peers
for the main comparison/radar group. SOURCE_TEAM_PEERS means current/source-team
same-role peers for source context. Source-team peers are not mapped to
`--comparison-ids`.

Esempio DEF Leo Ostigard:

```bash
make find-squad-role-peers PLAYER_ID=369971 ROLE=DEF
make find-target-role-peers TEAM="Inter" ROLE=DEF
make role-report ROLE=DEF PLAYER_ID=369971 PEERS=297390,54968,82399 SOURCE_TEAM_PEERS=425115,424834,494398 SOURCE_TEAM_PEER_LABEL="Genoa DEF" TARGET_TEAM="Inter"
make player-page ROLE=DEF PLAYER_ID=369971 PLAYER_NAME="Leo Østigård" SLUG=leo-ostigard PEERS=297390,54968,82399 COMPARISON_LABEL="Inter DEF" SOURCE_TEAM_PEERS=425115,424834,494398 SOURCE_TEAM_PEER_LABEL="Genoa DEF" TEAM="Genoa" COMPETITION="ITA-Serie A" SEASON=2526 TARGET_TEAM="Inter"
```

GUI locale opzionale:

```bash
make report-builder
```

Poi aprire `http://127.0.0.1:8011/`. La GUI espone due selettori separati:
main/radar peers, passati all'exporter come `--comparison-ids`, e source-context
peers, passati come `--context-ids`.

Per cercare un giocatore senza vincolare subito il ruolo:

```bash
make find-player-all QUERY="ostigard"
```

### Hybrid roles / role override

Usare `ROLE` come report/analysis role: e' il ruolo del contesto target, quello
usato per scegliere i target-team peers, costruire radar/confronti e chiamare
l'exporter SoccerDB con `--role`.

Usare `SOURCE_ROLE` solo quando il ruolo rilevato nel club sorgente e' diverso
dal ruolo di valutazione nel club target. Esempio: un esterno/wing-back rilevato
come `DEF` nel club sorgente ma valutato come `MID` nel contesto Napoli.

Regole:

- non c'e' remapping automatico: l'override va scelto esplicitamente;
- se `SOURCE_ROLE != ROLE`, serve `ROLE_OVERRIDE_REASON`;
- i main/radar peers devono essere del target team nel `ROLE` di report;
- i source-context peers possono essere scelti dal `SOURCE_ROLE`;
- se i ruoli divergono, i source-context peers restano metadati editoriali e
  non vengono passati all'exporter come `--context-ids`;
- non cambiare backend analytics, metriche, radar, PCA, similarity o heatmap.

Esempio DEF → MID:

```bash
make player-page ROLE=MID SOURCE_ROLE=DEF ROLE_OVERRIDE_REASON="Player is evaluated as a wing-back / wide midfielder in the target-team context." PLAYER_ID=123 PLAYER_NAME="Player Name" SLUG=player-name PEERS=336915,111892,349561 COMPARISON_LABEL="Napoli MID" SOURCE_TEAM_PEERS=111,222 SOURCE_TEAM_PEER_LABEL="Source DEF" TEAM="Union Saint-Gilloise" COMPETITION="BEL-Jupiler Pro League" SEASON=2526 TARGET_TEAM="Napoli"
```

Nella GUI, la stessa regola vive nella sezione `Role interpretation`: scegliere
detected/source role, report/analysis role, abilitare `Allow cross-role report`
e compilare il motivo.

L'orchestrator scrive un manifest in:

```text
outputs/report_generation_runs/{timestamp}_{role}/run_manifest.json
```

Le sezioni sotto restano come riferimento manuale e troubleshooting, soprattutto
quando bisogna rigenerare artifact SoccerDB, aggiornare `player_index.json`,
produrre brief editoriali, pagine HTML o card.

## 1. Repos e responsabilita

| Repo | Path | Responsabilita |
|---|---|---|
| SoccerDB | `/Users/michele/Documents/SoccerDB` | Genera metriche, radar, barre, heatmap, similarity e payload dati. |
| Frontend PASTA | `/Users/michele/Documents/Data_scouting_app/html5up-forty` | Conserva `player_index`, payload JSON, template HTML, pagina finale e card social. |

Il frontend non calcola i dati del report. Il frontend legge:

```text
assets/data/player_index.json
data/report_legacy_payloads/<slug>.legacy_role_payload.json
assets/templates/player-report-template.html
```

e genera:

```text
<slug>.html
images/cards/<slug>.png
images/cards/<slug>-social.png
```

## 2. Scegliere soggetto e gruppi

Per ogni report ruolo servono:

| Campo | Esempio Palestra |
|---|---|
| role | `DEF` |
| player id | `481154` |
| player name | `Marco Palestra` |
| comparison ids | `255929,322153,388567,415415` |
| comparison label | `Inter FB/DEF` |
| context ids | `424534,371396,532542` |
| context label | `Cagliari FB` |

Esempio Palestra:

```text
Target Inter FB/DEF:
255929 Federico Dimarco
322153 Denzel Dumfries
388567 Luis Henrique
415415 Andy Diouf

Context Cagliari FB:
424534 Adam Obert
371396 Gabriele Zappa
532542 Riyad Idrissi
```

Esempio Stankovic (`MID`):

```text
Subject:
459075 Aleksandar Stankovic

Target Inter MID references:
148684 Nicolo Barella
118169 Piotr Zielinski
110373 Hakan Calhanoglu
439534 Petar Sucic
28421 Henrikh Mkhitaryan

Context Club Brugge MID room:
243567 Hans Vanaken
425338 Raphael Onyedika
335698 Hugo Vetlesen
```

Regola pratica: `comparison-ids` e' la stanza del club target, mentre
`context-ids` deve descrivere il contesto di provenienza o il gruppo interno
piu' utile per leggere il giocatore. Per Stankovic, quindi, il context non deve
essere un campione esterno generico: devono essere gli altri centrocampisti del
Club Brugge.

## 3. Preparare o aggiornare gli artifact SoccerDB

Prima di esportare, se i dati sono stati aggiornati o un giocatore manca nelle heatmap/similarity, rigenerare gli artifact del ruolo.

Per un report `DEF`:

```bash
cd /Users/michele/Documents/SoccerDB

python3 scripts/build_def_heatmap_view_v1.py
python3 scripts/build_def_heatmap_view_v2.py
```

Per altri ruoli usare gli script equivalenti quando presenti:

```bash
python3 scripts/build_mid_heatmap_view_v2.py
python3 scripts/build_att_heatmap_view_v2.py
```

Non abbassare soglie o falsare dati nel frontend: se un giocatore deve stare nel confronto spaziale, deve avere una mappa valida nel payload.

## 4. Esportare il payload inline da SoccerDB

L'exporter SoccerDB aggiorna un file HTML con blocco `DATA:START` / `DATA:END`.
Per i role report `MID`, `DEF` e `ATT`, l'exporter emette anche
`RADAR_AXIS_RANGES` con strategia `p05_p95`, cosi' radar pagina e social card
non tornano compressi sulla scala fissa `0-100`.

Se il file di output non esiste, creare prima uno snapshot-seed copiando un report inline compatibile:

```bash
cd /Users/michele/Documents/Data_scouting_app/html5up-forty

cp archive/frontend_payload_fallback_snapshots/solet.with_inline_payload_2026_05_21.html \
   archive/frontend_payload_fallback_snapshots/marco-palestra.with_inline_payload_2026_06_03.html
```

Poi lanciare l'export da SoccerDB:

```bash
cd /Users/michele/Documents/SoccerDB

python3 scripts/exports/export_role_report_data.py \
  --role DEF \
  --player-id 481154 \
  --player-name "Marco Palestra" \
  --comparison-ids 255929,322153,388567,415415 \
  --comparison-label "Inter FB/DEF" \
  --context-ids 424534,371396,532542 \
  --context-label "Cagliari FB" \
  --colors "#4ade80,#fb923c,#60a5fa,#f472b6,#a78bfa,#34d399,#fbbf24,#e879f9,#67e8f9" \
  --output /Users/michele/Documents/Data_scouting_app/html5up-forty/archive/frontend_payload_fallback_snapshots/marco-palestra.with_inline_payload_2026_06_03.html
```

Output atteso:

```text
[OK] File aggiornato: .../archive/frontend_payload_fallback_snapshots/<slug>.with_inline_payload_YYYY_MM_DD.html
```

## 5. Convertire l'inline payload in JSON esterno

La pagina live carica il JSON esterno da:

```text
data/report_legacy_payloads/<slug>.legacy_role_payload.json
```

Per convertire lo snapshot inline:

```bash
cd /Users/michele/Documents/Data_scouting_app/html5up-forty

python3 - <<'PY'
import json
import re
from pathlib import Path

slug = "marco-palestra"
src = Path(f"archive/frontend_payload_fallback_snapshots/{slug}.with_inline_payload_2026_06_03.html")
dst = Path(f"data/report_legacy_payloads/{slug}.legacy_role_payload.json")

text = src.read_text(encoding="utf-8")
block = text.split("// DATA:START", 1)[1].split("// DATA:END", 1)[0]

keys = [
    "ROLE_META",
    "PAGE_META",
    "SUBJECT_ID",
    "PLAYER_META",
    "PROFILE_READING",
    "COMPARISON_GROUPS",
    "RADAR_AXES",
    "RADAR_DATA",
    "RADAR_AXIS_RANGES",
    "METRIC_GROUPS",
    "METRIC_FORMATS",
    "METRIC_RANGES",
    "METRICS",
    "TARGET_COMPARISON_BARS",
    "SOURCE_TEAM_COMPARISON_BARS",
    "HEATMAP_DATA",
    "SIMILARITY_DATA",
    "FOOTNOTES",
]

payload = {}
for key in keys:
    match = re.search(rf"^const {key} = (.*);$", block, flags=re.M)
    if not match:
        if key == "RADAR_AXIS_RANGES":
            continue
        raise SystemExit(f"Missing {key}")
    payload[key] = json.loads(match.group(1))

# Required by sr-report-loader.js. Keep the exported values if present; only
# fallback to an empty object if the exporter truly did not emit METRICS.
payload.setdefault("METRICS", {})
if "RADAR_AXIS_RANGES" in payload:
    payload.setdefault("payloadMeta", {})
    payload["payloadMeta"]["radarAxisRangesStrategy"] = "p05_p95"
    payload["payloadMeta"]["radarAxisRangesSource"] = "scripts/exports/export_role_report_data.py"

dst.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"written {dst}")
PY
```

## 6. Aggiornare `player_index.json`

Aprire:

```text
/Users/michele/Documents/Data_scouting_app/html5up-forty/assets/data/player_index.json
```

La entry minima deve contenere:

```json
{
  "player_id": "481154",
  "player_name": "Marco Palestra",
  "slug": "marco-palestra",
  "team_name": "Cagliari",
  "source_club": "Cagliari",
  "competition": "ITA-Serie A",
  "season": "2526",
  "macro_role": "DEF",
  "target_team": "Inter",
  "report_file": "marco-palestra.html",
  "report_status": "live",
  "visibility": "hidden",
  "payload_file": "data/report_legacy_payloads/marco-palestra.legacy_role_payload.json",
  "payload_source": "soccerdb",
  "narrative": "",
  "source_team_note": "",
  "note_confronto": "",
  "note_heatmap": "",
  "note_context": "",
  "note_similarity": ""
}
```

I campi editoriali supportano Markdown leggero (`**bold**`, `*italic*`, liste). Se sono vuoti, la pagina mostra comunque il payload tecnico, ma le sezioni narrative restano vuote o fallback.

Prima della pagina finale, generare sempre il brief editoriale e popolare le note.

## 7. Generare il brief editoriale

Il payload tecnico contiene radar, barre, heatmap e similarity. Le note
editoriali non vanno nel payload: vivono in `assets/data/player_index.json`.

Assicurarsi prima che `team_name` e `source_club` siano corretti nella entry del
giocatore. Per Stankovic:

```json
"team_name": "Club Brugge",
"source_club": "Club Brugge"
```

Poi generare il brief:

```bash
cd /Users/michele/Documents/Data_scouting_app/html5up-forty

python3 generate_editorial_brief.py --slug aleksandar-stankovic
```

Output:

```text
data/editorial/aleksandar-stankovic.brief.md
```

Aprire il brief, usare il blocco `PROMPT PER L'AI`, e copiare il JSON prodotto
dentro la entry del giocatore in `assets/data/player_index.json`:

```json
"narrative": "...",
"note_confronto": "...",
"note_heatmap": "...",
"note_context": "...",
"note_similarity": "..."
```

Controllo importante per la `note_heatmap`: il quarto riquadro e' role-aware.

| Ruolo | Titolo quarto riquadro | Payload letto dal runtime | Focus editoriale |
|---|---|---|---|
| `DEF` | `Azioni difensive` | `HEATMAP_DATA[*].def` | work-rate difensivo e altezza della difesa attiva |
| `MID` / altri role report standard | `Progressione via passaggio` | `HEATMAP_DATA[*].prog` | progressione tramite passaggio, non azioni difensive |
| `ATT` con spatial v2 | mappa offensiva/carry dedicata | blocchi ATT v2 | shot map, direzioni e ricezioni offensive |

Per Stankovic (`MID`), la nota heatmap deve quindi parlare del quarto pannello
come `Progressione via passaggio`. La riga sul work-rate difensivo puo' essere
usata come supporto interpretativo, ma non deve diventare la descrizione della
quarta heatmap.

## 8. Generare la pagina HTML

```bash
cd /Users/michele/Documents/Data_scouting_app/html5up-forty

python3 generate_pages.py --slug marco-palestra
```

Output atteso:

```text
Generating 1 page(s)...
  ✓  Marco Palestra                  ->  marco-palestra.html
Done.
```

Ogni volta che si cambia uno dei campi editoriali, rigenerare la pagina HTML.

## 9. Generare le card

Homepage tile:

```bash
python3 assets/cards/generate_cards.py --slug marco-palestra --version a
```

Social card con radar:

```bash
python3 assets/cards/generate_cards.py --slug marco-palestra --version b
```

Entrambe:

```bash
python3 assets/cards/generate_cards.py --slug marco-palestra --version all
```

Output:

```text
images/cards/marco-palestra.png
images/cards/marco-palestra-social.png
```

Il template social adatta dinamicamente il font del cognome per evitare tagli su nomi lunghi.

## 10. Controllare localmente

Avviare server dal frontend:

```bash
cd /Users/michele/Documents/Data_scouting_app/html5up-forty
python3 -m http.server 8000
```

Aprire:

```text
http://localhost:8000/marco-palestra.html
```

Check browser attesi:

- hero con immagine giocatore;
- minuti letti da `PLAYER_META[SUBJECT_ID].mins`;
- narrativa leggibile;
- radar con label non tagliate;
- barre target e context presenti;
- heatmap con selettore giocatori;
- similarity presente;
- note editoriali integrate.

Check payload nel browser:

```js
window.SR_PAYLOAD_LOAD_STATUS
```

Atteso:

```js
{
  mode: "external",
  url: "data/report_legacy_payloads/marco-palestra.legacy_role_payload.json",
  ok: true,
  error: null
}
```

## 11. Troubleshooting: comparatore senza heatmap

Caso reale: Andy Diouf nel report Palestra.

Sintomo:

- Diouf appare nel radar/barre;
- Diouf non disegna nessuno dei quattro quadri heatmap;
- nel JSON iniziale `HEATMAP_DATA[415415]` esisteva, ma `ip`, `carry`, `pass`, `def` erano null.

Diagnosi corretta:

```bash
cd /Users/michele/Documents/SoccerDB

python3 - <<'PY'
import pandas as pd
from pathlib import Path

DATA = Path("data/features")
pid = 415415

for fname in [
    "scouting_view_metrics_v1_def.parquet",
    "def_heatmap_view_v1.parquet",
    "def_heatmap_view_v2.parquet",
    "player_spatial_phase_grid_v1_ITA-Serie_A_2526.parquet",
]:
    df = pd.read_parquet(DATA / fname)
    rows = df[df["player_id"].eq(pid)] if "player_id" in df.columns else pd.DataFrame()
    print(fname, "rows:", len(rows))
    if not rows.empty and "heatmap_block" in rows.columns:
        print(rows.groupby("heatmap_block")["count"].sum())
    elif not rows.empty and "spatial_phase" in rows.columns:
        print(rows[["player_id", "spatial_phase", "minutes_played", "phase_event_count"]])
    elif not rows.empty:
        cols = [c for c in ["player_id", "player_name", "minutes_played", "dominant_position", "reliability_flag"] if c in rows.columns]
        print(rows[cols].drop_duplicates())
PY
```

Interpretazione:

- se il giocatore e' presente nelle metriche ma assente in `def_heatmap_view_v2`, il report sta usando un artifact spaziale stale;
- se e' presente anche in `player_spatial_phase_grid_v1_*`, i dati spaziali grezzi ci sono;
- se supera i minimi eventi ma non appare in v1/v2, rigenerare gli artifact heatmap del ruolo.

Fix usato per Diouf:

```bash
cd /Users/michele/Documents/SoccerDB

python3 scripts/build_def_heatmap_view_v1.py
python3 scripts/build_def_heatmap_view_v2.py
```

Poi riesportare il payload e rigenerare pagina/card.

Verifica finale Diouf:

```text
HEATMAP_DATA[415415].ip    -> presente
HEATMAP_DATA[415415].carry -> presente
HEATMAP_DATA[415415].pass  -> presente
HEATMAP_DATA[415415].def   -> presente
HEATMAP_DATA[415415].prog  -> null per DEF, perche' la quarta mappa e' azioni difensive
```

Nel caso Palestra, dopo rebuild:

```text
ipN: 644
carryN: 124
passN: 234
defN: 49
```

## 12. Troubleshooting: loader non carica il payload

Sintomo:

```js
window.SR_PAYLOAD_LOAD_STATUS
// { ok: false, error: "Missing required keys in payload: METRICS" }
```

Fix:

```bash
cd /Users/michele/Documents/Data_scouting_app/html5up-forty

python3 - <<'PY'
import json
from pathlib import Path

p = Path("data/report_legacy_payloads/marco-palestra.legacy_role_payload.json")
payload = json.loads(p.read_text(encoding="utf-8"))
payload.setdefault("METRICS", {})
p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
PY
```

Poi ricaricare la pagina via localhost.

## 13. Troubleshooting: quarta heatmap per ruolo

La quarta heatmap cambia in base al ruolo. Per i report `DEF` non e'
progressione via passaggio. E':

```text
Azioni difensive
```

Per i report `MID` e per gli altri role report standard non-DEF, invece, e':

```text
Progressione via passaggio
```

Il template usa:

```text
{{HEATMAP_FOURTH_TITLE}}
```

e `generate_pages.py` imposta automaticamente:

```python
HEATMAP_FOURTH_TITLES = {
    "DEF": "Azioni difensive",
}
```

Nel payload DEF la mappa visualizzata nel quarto riquadro viene da:

```text
HEATMAP_DATA[*].def
```

non da:

```text
HEATMAP_DATA[*].prog
```

Nel payload MID/non-DEF standard la mappa visualizzata nel quarto riquadro viene
invece da:

```text
HEATMAP_DATA[*].prog
```

Questo punto va controllato anche nel brief editoriale: non far descrivere una
heatmap MID come se fosse il pannello `Azioni difensive`.

## 14. Checklist finale

Prima di considerare chiuso un report:

- `data/report_legacy_payloads/<slug>.legacy_role_payload.json` esiste;
- `METRICS` e' presente nel JSON, anche come `{}`;
- `RADAR_AXIS_RANGES` e' presente per role report `MID`, `DEF`, `ATT`;
- `assets/data/player_index.json` punta al payload corretto;
- `python3 generate_pages.py --slug <slug>` passa;
- `python3 assets/cards/generate_cards.py --slug <slug> --version all` passa;
- `window.SR_PAYLOAD_LOAD_STATUS.ok === true`;
- tutti i giocatori target importanti hanno heatmap se devono essere confrontati spazialmente;
- i giocatori senza heatmap non vanno nascosti come fix definitivo: va indagato SoccerDB;
- per `DEF`, la quarta heatmap e' `Azioni difensive`;
- per `MID` e non-DEF standard, la quarta heatmap e' `Progressione via passaggio`;
- `generate_editorial_brief.py --slug <slug>` e' stato eseguito dopo il payload definitivo;
- `narrative`, `note_confronto`, `note_heatmap`, `note_context`, `note_similarity` sono stati copiati in `player_index.json`;
- social card non taglia nome/cognome;
- note editoriali e narrative sono leggibili.

## 15. Portieri: flusso GK separato

I portieri non vanno trattati come report ruolo standard anche se
`export_role_report_data.py` accetta `--role GK`.

Il frontend GK usa schema, DOM e runtime dedicati:

```text
data/report_legacy_payloads/<slug>.legacy_gk_payload.json
GK_PAGE_V1_PLAYERS
GK_PAGE_V1_TEAM_COMPARISONS
GK_PAGE_V1_SUMMARY
assets/js/sr-gk-report-loader.js
assets/js/sr-gk-runtime.js
```

Il layout editoriale GK e' piu' corto dei report ruolo standard: lettura
generale, radar, barre vs portieri Inter e visualizzazioni/heatmap GK. Non
mostrare sezioni di contesto club, similarity o metodologia/provenienza come
card finale se non c'e' una fonte editoriale specifica da commentare.

Il template ruolo standard usa invece:

```text
ROLE_META / PLAYER_META / RADAR_DATA / HEATMAP_DATA
assets/js/sr-report-loader.js
assets/js/sr-role-runtime.js
```

Sintomo di pagina GK generata col template sbagliato:

```js
window.SR_GK_PAYLOAD_LOAD_STATUS
// undefined
```

e nell'HTML si vede:

```html
window.SR_EXTERNAL_PAYLOAD_URL = "...legacy_gk_payload.json";
<script src="assets/js/sr-report-loader.js"></script>
<script src="assets/js/sr-role-runtime.js"></script>
```

Fix:

```bash
cd /Users/michele/Documents/Data_scouting_app/html5up-forty
python3 generate_pages.py --slug <slug>
```

Poi verificare che l'HTML generato contenga:

```html
window.SR_GK_EXTERNAL_PAYLOAD_URL = "...legacy_gk_payload.json";
<script src="assets/js/sr-gk-report-loader.js"></script>
<script src="assets/js/sr-gk-runtime.js"></script>
```

Per generare il payload GK stabile:

```bash
cd /Users/michele/Documents/SoccerDB
python3 scripts/exports/build_gk_page_v1_payloads.py <target_id> 35758 321236
```

Per Ivan Provedel:

```bash
python3 scripts/exports/build_gk_page_v1_payloads.py 118667 35758 321236
```

Nota importante: `export_gk_report_data.py` e' legacy per injection inline e puo'
fallire se `gk_report.html` non contiene piu' marker `DATA:START` / `DATA:END`.
Nel sito attuale usare payload JSON esterno e loader GK.

---

## Manual role override / role projection

### When to use

When a player is classified in one role by SoccerDB (e.g. MID) but you want to
evaluate them against a different role group in the target team (e.g. DEF for a
wing-back / fullback profile at Napoli).

### What it does

This is **not** copying MID percentiles into DEF. The override system:

1. Reads the player's raw event data (tackles, passes, carries, etc.) from the
   position-agnostic source files.
2. Runs the exact same DEF metric computation pipeline on that player's data.
3. Appends the resulting row to the DEF cohort.
4. Recomputes z-scores and percentiles for the **entire** DEF cohort with the
   override player included, so percentiles are honest DEF-cohort rankings.
5. Rebuilds volume and action-mix similarity against the DEF cohort.
6. Writes all outputs as `_with_overrides` variants — canonical parquet files
   are never modified.

### Block availability

| Block | Status |
|-------|--------|
| Radar | Available |
| Metric bars | Available |
| Heatmap | Available — rebuilt from position-agnostic spatial/event data |
| Volume similarity | Available |
| Action mix similarity | Available |
| Territorial similarity | Available — rebuilt from spatial grid features |
| PCA | Not rebuilt — not used in report rendering |

### How to use (GUI)

1. Select a player (e.g. search for a MID player).
2. Set **Report/analysis role** to the target role (e.g. DEF).
3. Enable **Allow cross-role report**.
4. Fill in the **Role override reason**.
5. The override panel appears:
   - Click **Create / update manual role override** to register the override.
   - Click **Rebuild override artifacts** to run the SoccerDB pipeline.
   - Wait for the build to complete (30–60 seconds).
6. The panel shows block availability after rebuild.
7. Proceed with peer selection and page generation as normal.
8. The `--use-manual-role-overrides` flag is passed automatically.

### How to use (CLI)

```bash
# 1. Add entry to override registry
# Edit: SoccerDB/config/manual_role_overrides.csv

# 2. Build override artifacts
cd /Users/michele/Documents/SoccerDB
.venv/bin/python scripts/build_manual_role_override_artifacts.py

# 3. Generate page with override
cd /Users/michele/Documents/Data_scouting_app/html5up-forty
python scripts/create_player_page_from_export.py \
  --role DEF --source-role MID \
  --player-id 355377 --player-name "Dennis Eckert Ayensa" \
  --slug dennis-eckert-ayensa \
  --main-comparison-peer-ids "361252,399358" \
  --comparison-label "Napoli DEF" \
  --team-name "Union Saint-Gilloise" \
  --competition "BEL-Jupiler Pro League" \
  --season 2526 \
  --target-team Napoli \
  --role-override-reason "Wing-back/fullback profile in Napoli context" \
  --use-manual-role-overrides
```

### Provenance

Override pages carry provenance in the payload's `PAGE_META`:

```json
{
  "is_manual_role_override": true,
  "source_role": "MID",
  "role_override_reason": "Evaluated as wing-back/fullback profile in Napoli context"
}
```

The player_index.json entry includes `source_role`, `report_role`, and
`role_override_reason` fields, plus a note_context prepend explaining the
role projection.
