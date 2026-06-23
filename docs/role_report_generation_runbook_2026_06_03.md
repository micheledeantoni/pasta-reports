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

```bash
make find-player QUERY="paz" ROLE=MID
```

Scegliere manualmente il `player_id` corretto dai candidati, poi cercare pari
ruolo comparabili:

```bash
make find-peers PLAYER_ID=448659 ROLE=MID
```

Scegliere manualmente i peer dalla lista suggerita, poi avviare l'export:

```bash
make role-report ROLE=MID PLAYER_ID=448659 PEERS=111,222,333
```

Validare lo stato HTML5UP:

```bash
make role-report-validate ROLE=MID
```

Equivalenti Python diretti:

```bash
python scripts/resolve_role_report_players.py --query "paz" --role MID --season 2025-2026
python scripts/resolve_role_report_players.py --player-id 448659 --list-peers --role MID --season 2025-2026 --min-minutes 900
python scripts/orchestrate_role_report.py --role MID --player-id 448659 --comparison-player-ids 111,222,333 --mode export
python scripts/orchestrate_role_report.py --role MID --mode validate-only
```

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
