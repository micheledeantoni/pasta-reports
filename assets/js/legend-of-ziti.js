/* ═══════════════════════════════════════════════════════════════════
   Legend of Ziti — legend-of-ziti.js
   Standalone game. Uses same player_index.json + payload system as
   Man In Pasta but does NOT share code with pasta-quiz.js.
   ═══════════════════════════════════════════════════════════════════ */

const DEBUG = new URLSearchParams(window.location.search).get('debug') === '1';
const log   = (...a) => DEBUG && console.log('[Legend of Ziti]', ...a);

/* ── Data paths ──────────────────────────────────────────────────── */
const REPORT_INDEX_URL    = 'assets/data/player_index.json';
const IMAGE_MANIFEST_URL  = 'data/quiz/legend-of-ziti-image-manifest.json';

/* ── Game constants ──────────────────────────────────────────────── */
const TOTAL_QUESTIONS   = 8;
const QUESTION_TIMER    = 20;
const BASE_PTS          = 100;
const TRIFORC_PTS       = 60;
const BONUS_FAST        = 20;   // elapsed < 7s
const BONUS_MED         = 10;   // elapsed < 12s
const MAX_SCORE         = TOTAL_QUESTIONS * (BASE_PTS + BONUS_FAST); // 960
const NUM_TRIALS        = 18;   // random candidates per target player

/* ── Metric lists ────────────────────────────────────────────────── */
const LOWER_IS_BETTER = new Set([
  'Avg shot distance',
  'Median time to engage',
]);

const EXCLUDED_METRICS = new Set([
  'Altezza media dei dribbling',
  'Average pass distance',
  'Defensive action mean x',
  'Mean x action location',
  'Interception to tackle ratio',
  'Defensive actions share team',
  'Pass share team',
  'Direct engagements /90',
  'Engagements under 2s',
  'Average progressive carry distance',
]);

const LABEL_IT = {
  'Aerial attempts per90':           'Duelli aerei per90',
  'Aerial win rate':                 'Duelli aerei vinti %',
  'Box shot share':                  'Quota tiri in area',
  'Conversion rate':                 'Conversione tiri',
  'Cross attempts per90':            'Cross tentati per90',
  'Defensive actions padj':          'Azioni difensive pAdj',
  'Dribbling riusciti':              'Successo dribbling %',
  'Expected assists per90':          'xA per90',
  'Final third receival share':      'Quota ricezioni terzo finale',
  'Final-third receival share':      'Quota ricezioni terzo finale',
  'Goals per90':                     'Gol per90',
  'Interceptions padj':              'Intercetti pAdj',
  'Interceptions per90':             'Intercetti per90',
  'NPxG per90':                      'NPxG per90',
  'Offensive aerial attempts per90': 'Duelli aerei offensivi per90',
  'Pass completion':                 'Completamento passaggi %',
  'Passes ending box per90':         'Passaggi in area per90',
  'Passes ending final third per90': 'Passaggi nel terzo finale per90',
  'Passes into final third per90':   "Passaggi nell'ultimo terzo per90",
  'Passes into penalty area per90':  'Passaggi in area di rigore per90',
  'Progressive carries per90':       'Conduzioni progressive per90',
  'Progressive carry attempts per90':'Conduzioni progressive per90',
  'Progressive pass share':          'Quota passaggi progressivi',
  'Progressive passes per90':        'Passaggi progressivi per90',
  'Receival attempts per90':         'Ricezioni tentate per90',
  'Receivals per90':                 'Ricezioni per90',
  'SCA per90':                       'Azioni pre-tiro per90',
  'Shot attempts per90':             'Tiri per90',
  'Shot quality':                    'Qualità del tiro',
  'Shot-creating actions per90':     'Azioni che generano tiro per90',
  'Shots on target %':               'Tiri nello specchio %',
  'Success rate ending box':         'Successo ingressi area',
  'Tackle attempts padj':            'Contrasti tentati pAdj',
  'Tackle success rate':             'Successo nei contrasti %',
  'Tackles padj':                    'Contrasti pAdj',
  'Tackles per90':                   'Contrasti per90',
  'Take-on success rate':            'Successo 1v1 %',
  'Take-ons per90':                  '1v1 tentati per90',
  'xA per90':                        'xA per90',
  'xG per90':                        'xG per90',
  'xG per shot':                     'xG per tiro',
  'Avg shot distance':               'Distanza media tiro (↓ meglio)',
  'Median time to engage':           'Tempo mediano di intervento (↓ meglio)',
};

/* ── Badges ──────────────────────────────────────────────────────── */
const BADGES = [
  { min: 850, title: 'Triforc Suprema',   desc: 'Tre punte, zero dubbi. Sei la leggenda che cercavamo.' },
  { min: 700, title: 'Triforc Affilata',  desc: 'Hai tagliato via quasi tutte le false piste.' },
  { min: 500, title: 'Triforc in Viaggio',desc: 'La quest procede bene, ma la leggenda è ancora lontana.' },
  { min: 300, title: 'Triforc Piegata',   desc: 'Qualche scelta buona c\'è, ma la mappa va letta meglio.' },
  { min: 0,   title: 'Riparti dal Villaggio',  desc: 'La leggenda può aspettare. Torna quando sei pronto.' },
];

function getBadge(pts) {
  return BADGES.find(b => pts >= b.min) || BADGES[BADGES.length - 1];
}

/* ── Helpers ─────────────────────────────────────────────────────── */
function normalize(v, min, max) {
  if (max === min) return 50;
  return Math.max(0, Math.min(100, ((v - min) / (max - min)) * 100));
}

function shuffle(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

function formatValue(v, fmt) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  if (fmt === 'percent')       return `${(v * 100).toFixed(1)}%`;
  if (fmt === 'percent_0_100') return `${v.toFixed(1)}%`;
  if (fmt === 'meters')        return `${v.toFixed(1)} m`;
  if (fmt === 'one_decimal')   return v.toFixed(1);
  if (Number.isInteger(v))     return v.toString();
  return v.toFixed(2);
}

/* ── Game-friendly metric labels (used only in clue text) ────────── */
const GAME_METRIC_LABELS = {
  'Aerial attempts per90':           'duelli aerei',
  'Aerial win rate':                 'duelli aerei vinti',
  'Box shot share':                  'tiri in area sul totale',
  'Conversion rate':                 'conversione dei tiri',
  'Cross attempts per90':            'cross tentati',
  'Defensive actions padj':          'azioni difensive',
  'Dribbling riusciti':              'dribbling riusciti',
  'Expected assists per90':          'assist attesi (xA)',
  'Final third receival share':      'ricezioni nel terzo finale',
  'Final-third receival share':      'ricezioni nel terzo finale',
  'Goals per90':                     'gol segnati',
  'Interceptions padj':              'intercetti',
  'Interceptions per90':             'intercetti',
  'NPxG per90':                      'gol attesi senza rigori',
  'Offensive aerial attempts per90': 'duelli aerei offensivi',
  'Pass completion':                 'precisione nei passaggi',
  'Passes ending box per90':         'passaggi che arrivano in area',
  'Passes ending final third per90': 'passaggi nel terzo finale',
  'Passes into final third per90':   "passaggi verso l'ultimo terzo",
  'Passes into penalty area per90':  'passaggi in area di rigore',
  'Progressive carries per90':       'conduzioni progressive',
  'Progressive carry attempts per90':'conduzioni progressive tentate',
  'Progressive pass share':          'quota passaggi progressivi',
  'Progressive passes per90':        'passaggi progressivi',
  'Receival attempts per90':         'ricezioni tentate',
  'Receivals per90':                 'ricezioni completate',
  'SCA per90':                       'azioni che portano al tiro',
  'Shot attempts per90':             'tiri tentati',
  'Shot quality':                    'qualità media del tiro',
  'Shot-creating actions per90':     'azioni che generano tiro',
  'Shots on target %':               'tiri nello specchio',
  'Success rate ending box':         'ingressi riusciti in area',
  'Tackle attempts padj':            'contrasti tentati',
  'Tackle success rate':             'contrasti riusciti',
  'Tackles padj':                    'contrasti vinti',
  'Tackles per90':                   'contrasti per90',
  'Take-on success rate':            'dribbling 1v1 riusciti',
  'Take-ons per90':                  'dribbling 1v1 tentati',
  'xA per90':                        'assist attesi',
  'xG per90':                        'gol attesi (xG)',
  'xG per shot':                     'qualità del tiro (xG/tiro)',
  'Avg shot distance':               'distanza media dal tiro',
  'Median time to engage':           'tempo di intervento',
};

/* ── Minimum normalised spread to use a metric as a clue ─────────── */
const MIN_CLUE_SPREAD = 8; // diffScore units out of 100

/* ── Ranking & clue text ─────────────────────────────────────────── */
// Rank by raw numeric value: rank 1 = highest value among the three.
function computeRank(targetVal, allVals) {
  const higher = allVals.filter(v => v > targetVal).length;
  return higher + 1;  // 1 = highest, 3 = lowest
}

// Friendly lowercase label for embedding in a sentence.
function clueLabel(metricKey) {
  return GAME_METRIC_LABELS[metricKey]
    || (LABEL_IT[metricKey] || metricKey).replace(' (↓ meglio)', '').toLowerCase();
}

const _FIRST_TPL  = [
  'È quello con più {L}',
  'Primeggia per {L}',
  'Guida il trio per {L}',
];
const _LAST_TPL   = [
  'È quello con meno {L}',
  'Ha il valore più basso per {L}',
  'Resta sotto gli altri per {L}',
];
const _MIDDLE_TPL = [
  'È secondo per {L}',
  'Sta nel mezzo per {L}',
  'Non è primo né ultimo per {L}',
];

function buildClueText(metricKey, rank, idx) {
  const L   = clueLabel(metricKey);
  const tpl = rank === 1 ? _FIRST_TPL : rank === 3 ? _LAST_TPL : _MIDDLE_TPL;
  return tpl[idx % tpl.length].replace('{L}', L);
}

const $ = id => document.getElementById(id);

/* ── State ───────────────────────────────────────────────────────── */
let playerPool      = [];
let questions       = [];
let currentQ        = 0;
let score           = 0;
let timerInterval   = null;
let advanceTimeout  = null;
let timeLeft        = QUESTION_TIMER;
let answered        = false;
let triforcUsed      = false;
let eliminatedSlot   = null;  // 0|1|2 index of eliminated option
let lzImageManifest  = null;

/* ══════════════════════════════════════════════════════════════════
   BOOT
   ══════════════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  showScreen('lz-hero');
  $('lz-start-btn').addEventListener('click',       startGame);
  $('lz-replay-btn').addEventListener('click',      startGame);
  $('lz-share-btn').addEventListener('click',       shareResult);
  $('lz-triforc-btn').addEventListener('click', useTriforc);
  loadPlayerPool().catch(e => log('Pre-load error:', e.message));
  loadImageManifest().catch(e => log('Manifest error:', e.message));
});

function showScreen(id) {
  document.querySelectorAll('.lz-screen').forEach(s => s.classList.remove('active'));
  const el = $(id);
  if (el) el.classList.add('active');
}

/* ══════════════════════════════════════════════════════════════════
   IMAGE MANIFEST
   ══════════════════════════════════════════════════════════════════ */
async function loadImageManifest() {
  const resp = await fetch(IMAGE_MANIFEST_URL);
  if (!resp.ok) { log('Manifest not found:', IMAGE_MANIFEST_URL); return; }
  lzImageManifest = await resp.json();

  if (DEBUG) {
    console.log('[Legend of Ziti] Image manifest loaded:', lzImageManifest);
    console.log('[Legend of Ziti] Cover image:', lzImageManifest.cover);
    console.log('[Legend of Ziti] Triforc icon:', lzImageManifest.icon);
    console.table(lzImageManifest.categories);
  }

  // Cover in hero
  const coverImg = $('lz-cover-img');
  if (coverImg && lzImageManifest.cover) {
    coverImg.src    = lzImageManifest.cover;
    coverImg.onload  = () => { coverImg.style.display = 'block'; };
    coverImg.onerror = () => { console.warn('[Legend of Ziti] Missing image:', lzImageManifest.cover); };
  }

  // Icon in Triforc button
  if (lzImageManifest.icon) {
    const btn = $('lz-triforc-btn');
    if (btn) {
      btn.innerHTML =
        `<img class="lz-triforc-icon" src="${lzImageManifest.icon}" alt="" aria-hidden="true" />`+
        `<span class="lz-tf-label">Usa la Triforc</span>`;
      btn.querySelector('img').onerror = () => {
        console.warn('[Legend of Ziti] Missing image:', lzImageManifest.icon);
        btn.innerHTML = '<span class="lz-tf-label">🍴 Usa la Triforc</span>';
      };
    }
  }
}

function applyResultBanner(pts) {
  const banner = $('lz-result-banner');
  if (!banner) return;
  if (!lzImageManifest?.categories) { banner.style.display = 'none'; return; }

  const cat = lzImageManifest.categories.find(c => pts >= c.min && pts <= c.max);
  if (!cat?.image) { banner.style.display = 'none'; return; }

  banner.alt    = cat.title;
  banner.src    = cat.image;
  banner.onload  = () => { banner.style.display = 'block'; };
  banner.onerror = () => {
    console.warn('[Legend of Ziti] Missing image:', cat.image);
    banner.style.display = 'none';
  };
}

// Update only the text span inside the Triforc button (preserves icon img).
function _setTriforcLabel(text) {
  const btn = $('lz-triforc-btn');
  if (!btn) return;
  const span = btn.querySelector('.lz-tf-label');
  if (span) span.textContent = text;
  else btn.textContent = text;
}

/* ══════════════════════════════════════════════════════════════════
   GAME START
   ══════════════════════════════════════════════════════════════════ */
async function startGame() {
  clearTimeout(advanceTimeout);
  clearInterval(timerInterval);
  score = 0; currentQ = 0; answered = false;
  showScreen('lz-loading');

  try {
    if (playerPool.length === 0) await loadPlayerPool();
    questions = buildQuestions();
    if (questions.length < TOTAL_QUESTIONS) {
      showError(`Non è stato possibile generare ${TOTAL_QUESTIONS} domande (trovate: ${questions.length}). Controlla i payload.`);
      return;
    }
    renderQuestion();
    showScreen('lz-question');
  } catch (e) {
    console.error(e);
    showError('Errore nel caricamento. Apri la pagina tramite server locale (python3 -m http.server 8001).');
  }
}

/* ══════════════════════════════════════════════════════════════════
   DATA LOADING  (mirrors pasta-quiz.js but self-contained)
   ══════════════════════════════════════════════════════════════════ */
async function loadPlayerPool() {
  if (playerPool.length > 0) { log('Pool already loaded:', playerPool.length); return; }

  log('Index:', REPORT_INDEX_URL);
  const resp = await fetch(REPORT_INDEX_URL);
  if (!resp.ok) throw new Error(`Index HTTP ${resp.status}`);
  const rawIndex = await resp.json();

  const seen = new Set();
  const active = [];
  for (const entry of rawIndex) {
    if (entry.macro_role === 'GK') continue;
    if (entry.report_status && entry.report_status !== 'live') continue;
    const key = `${entry.player_id}__${entry.macro_role}`;
    if (seen.has(key)) continue;
    seen.add(key);
    active.push(entry);
  }

  log('Active reports:', active.length);
  if (DEBUG) console.table(active.map(r => ({ name: r.player_name, role: r.macro_role, payload: r.payload_file })));

  const results = await Promise.allSettled(active.map(e => loadPayload(e)));

  const tempPool = {};
  let loaded = 0, failed = 0;

  for (const result of results) {
    if (result.status === 'rejected') { failed++; continue; }
    if (!result.value) { failed++; continue; }
    loaded++;
    for (const player of result.value) {
      const key = player.id ? String(player.id) : `${player.name}__${player.macroRole}`;
      if (!tempPool[key]) {
        tempPool[key] = player;
      } else {
        player.sourceTypes.forEach(t => { if (!tempPool[key].sourceTypes.includes(t)) tempPool[key].sourceTypes.push(t); });
      }
    }
  }

  playerPool = Object.values(tempPool);

  if (DEBUG) {
    const byRole = {};
    const bySrc  = {};
    for (const p of playerPool) {
      byRole[p.macroRole] = (byRole[p.macroRole] || 0) + 1;
      const t = p.sourceTypes[0];
      bySrc[t] = (bySrc[t] || 0) + 1;
    }
    log(`Player pool size: ${playerPool.length} | payloads: loaded=${loaded} failed=${failed}`);
    console.table(Object.entries(byRole).map(([role, count]) => ({ role, count })));
    console.table(Object.entries(bySrc).map(([sourceType, count]) => ({ sourceType, count })));
  }
}

async function loadPayload(entry) {
  const url  = entry.payload_file;
  const resp = await fetch(url);
  if (!resp.ok) { log(`HTTP ${resp.status} → ${url}`); return null; }
  const payload = await resp.json();

  const subjId  = String(payload.SUBJECT_ID || '');
  const pm      = payload.PLAYER_META   || {};
  const allMt   = payload.METRICS       || {};
  const ranges  = payload.METRIC_RANGES || {};
  const formats = payload.METRIC_FORMATS|| {};
  const role    = payload.ROLE_META?.role || entry.macro_role;

  const srcMap = {};
  if (subjId) srcMap[subjId] = 'subject';
  for (const g of (payload.COMPARISON_GROUPS || [])) {
    const t = g.key === 'target' ? 'comparison' : 'source_team_peer';
    for (const id of (g.ids || [])) { const s = String(id); if (!srcMap[s]) srcMap[s] = t; }
  }

  const players = [];
  for (const [pid, pdata] of Object.entries(pm)) {
    const rawMetrics = allMt[pid];
    if (!rawMetrics || !Object.keys(rawMetrics).length) continue;
    const metrics = {};

    for (const [key, rawVal] of Object.entries(rawMetrics)) {
      if (EXCLUDED_METRICS.has(key)) continue;
      if (typeof rawVal !== 'number' || isNaN(rawVal)) continue;
      const range = ranges[key];
      if (!range) continue;

      const raw100    = normalize(rawVal, range.min, range.max);
      const diffScore = LOWER_IS_BETTER.has(key) ? (100 - raw100) : raw100;

      metrics[key] = {
        key,
        label:     LABEL_IT[key] || key,
        value:     rawVal,
        diffScore,
        format:    formats[key] || null,
      };
    }
    if (!Object.keys(metrics).length) continue;

    players.push({
      id:          parseInt(pid, 10) || null,
      name:        pdata.name,
      macroRole:   pdata.macroRole || role,
      sourceTypes: [srcMap[pid] || 'context'],
      metrics,
    });
  }
  return players;
}

/* ══════════════════════════════════════════════════════════════════
   QUESTION GENERATION
   Q1-Q2 easy | Q3-Q5 medium | Q6-Q8 hard
   Difficulty = mean(|target.diffScore - distractor.diffScore|) across
   4 chosen metrics and 2 distractors.  Large value → easy.
   ══════════════════════════════════════════════════════════════════ */
function buildQuestions() {
  const candidates = [];
  let _discardedSpread = 0;

  for (const target of playerPool) {
    // Prefer same-role distractors
    const sameRole = playerPool.filter(p => p !== target && p.macroRole === target.macroRole);
    const eligible  = sameRole.length >= 2 ? sameRole : playerPool.filter(p => p !== target);
    if (eligible.length < 2) continue;

    for (let t = 0; t < NUM_TRIALS; t++) {
      const pool = shuffle([...eligible]);
      const d1   = pool[0];
      const d2   = pool[1];

      // Shared metrics across all three players
      const shared = Object.keys(target.metrics).filter(
        k => k in d1.metrics && k in d2.metrics
      );
      if (shared.length < 4) continue;

      // Filter out metrics whose normalised spread is too small to be a useful clue.
      const distinctiveShared = shared.filter(mk => {
        const scores = [target, d1, d2].map(p => p.metrics[mk].diffScore);
        return Math.max(...scores) - Math.min(...scores) >= MIN_CLUE_SPREAD;
      });
      if (distinctiveShared.length < 4) { _discardedSpread += (shared.length - distinctiveShared.length); continue; }
      _discardedSpread += (shared.length - distinctiveShared.length);

      // Pick 4 random metrics that passed the spread filter
      const metrics4 = shuffle([...distinctiveShared]).slice(0, 4);

      // Difficulty: mean weighted distance.
      // rank weight: 1st/3rd = more distinctive (1.0), 2nd = less (0.5).
      let totalDiff = 0;
      const clueData = [];
      for (const mk of metrics4) {
        const tVal  = target.metrics[mk].value;
        const d1Val = d1.metrics[mk].value;
        const d2Val = d2.metrics[mk].value;
        const rank  = computeRank(tVal, [tVal, d1Val, d2Val]);
        const diff  = (Math.abs(target.metrics[mk].diffScore - d1.metrics[mk].diffScore) +
                       Math.abs(target.metrics[mk].diffScore - d2.metrics[mk].diffScore)) / 2;
        const rankWeight = (rank === 1 || rank === 3) ? 1.0 : 0.5;
        totalDiff += diff * rankWeight;
        clueData.push({ mk, rank, diff, tVal, d1Val, d2Val });
      }
      const difficulty = totalDiff / metrics4.length;

      candidates.push({ target, d1, d2, metrics4, difficulty, clueData });
    }
  }

  log(`Candidates generated: ${candidates.length}`);
  log(`Metrics discarded (spread < ${MIN_CLUE_SPREAD}): ${_discardedSpread}`);

  const easy   = candidates.filter(c => c.difficulty >= 30);
  const medium = candidates.filter(c => c.difficulty >= 15 && c.difficulty < 30);
  const hard   = candidates.filter(c => c.difficulty >= 5  && c.difficulty < 15);

  log(`Buckets — easy:${easy.length} medium:${medium.length} hard:${hard.length}`);

  // 2 easy, 3 medium, 3 hard
  const plan = [
    { bucket: easy,   count: 2, label: 'easy'   },
    { bucket: medium, count: 3, label: 'medium'  },
    { bucket: hard,   count: 3, label: 'hard'    },
  ];

  const selected  = [];
  const usedTargets = new Set();
  const metricUsage = {};

  for (const { bucket, count, label } of plan) {
    let pool   = shuffle([...bucket]);
    let needed = count;

    // Fallback if bucket too small
    if (pool.length < needed) {
      const extra = shuffle([...candidates]).filter(c => !selected.some(s => s === c));
      pool = shuffle([...pool, ...extra]);
    }

    for (const c of pool) {
      if (needed <= 0) break;
      const targetKey = String(c.target.id ?? c.target.name);
      if (usedTargets.has(targetKey)) continue;
      if (c.metrics4.some(mk => (metricUsage[mk] || 0) >= 2)) continue;

      usedTargets.add(targetKey);
      c.metrics4.forEach(mk => { metricUsage[mk] = (metricUsage[mk] || 0) + 1; });
      c.difficultyLabel = label;

      // Assign random presentation slots [A, B, C]
      const options = shuffle([
        { player: c.target, correct: true  },
        { player: c.d1,     correct: false },
        { player: c.d2,     correct: false },
      ]);
      c.options      = options;
      c.correctIndex = options.findIndex(o => o.correct);

      // Build text clues from pre-computed rank data
      c.clues = c.clueData.map((cd, idx) => ({
        key:         cd.mk,
        text:        buildClueText(cd.mk, cd.rank, idx),
        rank:        cd.rank,
        targetValue: cd.tVal,
        d1Value:     cd.d1Val,
        d2Value:     cd.d2Val,
        format:      c.target.metrics[cd.mk].format,
        labelClean:  (LABEL_IT[cd.mk] || cd.mk).replace(' (↓ meglio)', ''),
      }));

      selected.push(c);
      needed--;
    }
  }

  if (DEBUG) {
    console.table(selected.map((q, i) => ({
      '#':        i + 1,
      target:     q.target.name,
      role:       q.target.macroRole,
      d1:         q.d1.name,
      d2:         q.d2.name,
      difficulty: q.difficulty.toFixed(1),
      label:      q.difficultyLabel,
      correctSlot:['A','B','C'][q.correctIndex],
      clues:      q.clues.map(c => `[r${c.rank}] ${c.text}`).join(' | '),
    })));

    // Per-question clue audit: verify rank matches raw values
    for (const [i, q] of selected.entries()) {
      console.group(`Q${i + 1} — target: ${q.target.name} (${['A','B','C'][q.correctIndex]})`);
      for (const clue of q.clues) {
        const rows = [
          { player: q.target.name, value: clue.targetValue, isTarget: true },
          { player: q.d1.name,     value: clue.d1Value,     isTarget: false },
          { player: q.d2.name,     value: clue.d2Value,     isTarget: false },
        ].sort((a, b) => b.value - a.value);
        const computedRank = rows.findIndex(r => r.isTarget) + 1;
        const ok = computedRank === clue.rank ? '✓' : '✗ MISMATCH';
        console.log(`${ok} rank=${clue.rank} "${clue.text}"`);
        console.table(rows.map(r => ({
          player: r.player,
          value:  formatValue(r.value, clue.format),
          raw:    r.value,
          target: r.isTarget ? '← target' : '',
        })));
      }
      console.groupEnd();
    }
  }

  return selected;
}

/* ══════════════════════════════════════════════════════════════════
   RENDERING
   ══════════════════════════════════════════════════════════════════ */
function renderQuestion() {
  const q = questions[currentQ];
  answered        = false;
  triforcUsed = false;
  eliminatedSlot   = null;

  // Progress
  $('lz-progress-fill').style.width = `${(currentQ / questions.length) * 100}%`;
  $('lz-question-counter').textContent = `Domanda ${currentQ + 1} / ${questions.length}`;
  $('lz-score-running').textContent    = `${score} pt`;

  // Difficulty badge
  const badge = $('lz-difficulty-badge');
  badge.className = 'lz-difficulty-badge';
  const diffMap = {
    easy:   ['Facile',    'lz-diff-easy'],
    medium: ['Media',     'lz-diff-medium'],
    hard:   ['Difficile', 'lz-diff-hard'],
  };
  const [lbl, cls] = diffMap[q.difficultyLabel] || diffMap.medium;
  badge.classList.add(cls);
  badge.textContent = lbl;

  // Clue list — comparative text clues, no raw values
  const clueGrid = $('lz-clue-grid');
  clueGrid.innerHTML = '';
  for (const clue of q.clues) {
    const li = document.createElement('li');
    li.className = 'lz-clue-item';
    li.textContent = clue.text;
    clueGrid.appendChild(li);
  }

  // Triforc button
  const tfBtn = $('lz-triforc-btn');
  tfBtn.disabled = false;
  tfBtn.classList.remove('used');
  _setTriforcLabel('Usa la Triforc');

  // Player cards
  ['A', 'B', 'C'].forEach((letter, idx) => {
    const card   = $(`lz-card-${letter}`);
    const player = q.options[idx].player;
    card.className = 'lz-player-card';
    card.querySelector('.lz-card-name').textContent = player.name;
    card.querySelector('.lz-card-role').textContent = player.macroRole;
    card.onclick = () => handleAnswer(idx);
    card.style.display = '';
  });

  // Feedback hidden
  $('lz-feedback').className = 'lz-feedback';

  startTimer();
}

/* ── Timer ───────────────────────────────────────────────────────── */
let _questionStartTime = 0;

function startTimer() {
  clearInterval(timerInterval);
  timeLeft = QUESTION_TIMER;
  _questionStartTime = Date.now();
  updateTimerUI();
  timerInterval = setInterval(() => {
    timeLeft--;
    updateTimerUI();
    if (timeLeft <= 0) { clearInterval(timerInterval); handleTimeout(); }
  }, 1000);
}

function updateTimerUI() {
  $('lz-timer-label').textContent = timeLeft;
  const fill = $('lz-timer-fill');
  fill.style.width = `${(timeLeft / QUESTION_TIMER) * 100}%`;
  fill.className = 'lz-timer-fill';
  if (timeLeft <= 5)       fill.classList.add('danger');
  else if (timeLeft <= 10) fill.classList.add('warning');
}

/* ── Triforc ─────────────────────────────────────────────────────── */
function useTriforc() {
  if (answered || triforcUsed) return;
  const q = questions[currentQ];
  triforcUsed = true;

  // Find a wrong option to eliminate (not already eliminated)
  const wrongIndices = [0, 1, 2].filter(i => !q.options[i].correct);
  eliminatedSlot = wrongIndices[Math.floor(Math.random() * wrongIndices.length)];

  const letter = ['A', 'B', 'C'][eliminatedSlot];
  const card   = $(`lz-card-${letter}`);
  card.classList.add('eliminated');
  card.onclick = null;

  const tfBtn = $('lz-triforc-btn');
  tfBtn.disabled = true;
  tfBtn.classList.add('used');
  _setTriforcLabel('Usata');
}

/* ── Answer ──────────────────────────────────────────────────────── */
function handleAnswer(idx) {
  if (answered) return;
  if (idx === eliminatedSlot) return;
  answered = true;
  clearInterval(timerInterval);

  const q       = questions[currentQ];
  const correct = q.options[idx].correct;
  const elapsed = (Date.now() - _questionStartTime) / 1000;
  let pts = 0;

  if (correct) {
    if (triforcUsed) {
      pts = TRIFORC_PTS;
    } else {
      pts = BASE_PTS;
      if (elapsed < 7)       pts += BONUS_FAST;
      else if (elapsed < 12) pts += BONUS_MED;
    }
  }
  score += pts;

  const letter = ['A', 'B', 'C'][idx];
  $(`lz-card-${letter}`).classList.add(correct ? 'selected-correct' : 'selected-wrong');
  if (!correct) markCorrect(q);
  disableCards();
  showFeedback(correct ? 'correct' : 'wrong', pts, q);
  scheduleNext();
}

function handleTimeout() {
  if (answered) return;
  answered = true;
  disableCards();
  markCorrect(questions[currentQ]);
  showFeedback('timeout', 0, questions[currentQ]);
  scheduleNext();
}

function markCorrect(q) {
  const letter = ['A', 'B', 'C'][q.correctIndex];
  $(`lz-card-${letter}`).classList.add('correct-answer');
}

function disableCards() {
  ['A', 'B', 'C'].forEach(l => {
    const c = $(`lz-card-${l}`);
    c.classList.add('disabled');
    c.onclick = null;
  });
}

function scheduleNext() {
  advanceTimeout = setTimeout(() => {
    currentQ++;
    if (currentQ >= questions.length) showResult();
    else renderQuestion();
  }, 3000);
}

/* ── Feedback ────────────────────────────────────────────────────── */
function showFeedback(verdict, pts, q) {
  const verdictEl = $('lz-feedback-verdict');
  if (verdict === 'correct')
    verdictEl.innerHTML = '<span class="lz-verdict-correct">✓ Corretto!</span>';
  else if (verdict === 'wrong')
    verdictEl.innerHTML = '<span class="lz-verdict-wrong">✗ Sbagliato</span>';
  else
    verdictEl.innerHTML = '<span class="lz-verdict-timeout">⏱ Tempo scaduto</span>';

  const ptsEl = $('lz-pts-earned');
  if (pts > 0) {
    ptsEl.textContent = `+${pts} pt`;
    ptsEl.style.display = '';
  } else {
    ptsEl.style.display = 'none';
  }

  const targetName = q.target.name;
  const intro = verdict === 'correct'
    ? `Era <strong>${targetName}</strong>.`
    : `Era <strong>${targetName}</strong>. Ecco i valori per capire perché.`;
  const fbText = $('lz-feedback-text');
  fbText.innerHTML = intro;

  // Comparison mini-table: for each clue, show all 3 players' values sorted highest→lowest
  const compEl = document.createElement('div');
  compEl.className = 'lz-comp-table';
  for (const clue of q.clues) {
    const rows = [
      { name: q.target.name, val: clue.targetValue, target: true },
      { name: q.d1.name,     val: clue.d1Value,     target: false },
      { name: q.d2.name,     val: clue.d2Value,     target: false },
    ].sort((a, b) => b.val - a.val);

    const rowsHtml = rows.map(r =>
      `<div class="lz-comp-row${r.target ? ' lz-comp-target' : ''}">
        <span class="lz-comp-name">${r.name}</span>
        <span class="lz-comp-val">${formatValue(r.val, clue.format)}</span>
      </div>`
    ).join('');

    compEl.innerHTML +=
      `<div class="lz-comp-metric">
        <div class="lz-comp-metric-label">${clue.labelClean}</div>
        ${rowsHtml}
      </div>`;
  }
  fbText.appendChild(compEl);

  $('lz-feedback').classList.add('show');
}

/* ══════════════════════════════════════════════════════════════════
   RESULT
   ══════════════════════════════════════════════════════════════════ */
function showResult() {
  $('lz-score-number').textContent = score;
  $('lz-score-max').textContent    = `/ ${MAX_SCORE}`;

  const badge = getBadge(score);
  $('lz-badge-name').textContent   = `"${badge.title}"`;
  $('lz-badge-phrase').textContent = `${score}/${MAX_SCORE} — ${badge.desc}`;

  window._lzBadge = badge.title;
  window._lzScore = score;

  applyResultBanner(score);
  showScreen('lz-result');
}

/* ── Share ───────────────────────────────────────────────────────── */
const GAME_URL = 'https://pasta-reports.com/legend-of-ziti.html';

function shareResult() {
  const cat = lzImageManifest?.categories?.find(
    c => window._lzScore >= c.min && window._lzScore <= c.max
  );
  const shareUrl = GAME_URL;

  const text =
    `Ho fatto ${window._lzScore} punti a Legend of Ziti e ho ottenuto il badge "${window._lzBadge}".` +
    ` Quattro dati. Tre giocatori. Una leggenda da riconoscere.\n${shareUrl}`;
  window.open(
    `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}`,
    '_blank', 'noopener,noreferrer'
  );
}

/* ── Error ───────────────────────────────────────────────────────── */
function showError(msg) {
  $('lz-loading').innerHTML = `<div class="lz-error-box">${msg}</div>`;
  showScreen('lz-loading');
}
