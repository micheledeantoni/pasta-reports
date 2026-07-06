/* ═══════════════════════════════════════════════════════════════════
   Man In Pasta — pasta-quiz.js
   Source: assets/data/player_index.json (all live non-GK reports)
   Random question generation via difficulty buckets each session.
   ═══════════════════════════════════════════════════════════════════ */

const DEBUG = new URLSearchParams(window.location.search).get('debug') === '1';
const log   = (...a) => DEBUG && console.log('[Man In Pasta]', ...a);

/* ── Active index path ───────────────────────────────────────────── */
const REPORT_INDEX_URL = 'assets/data/player_index.json';

/* ── Metric direction ────────────────────────────────────────────── */
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

const CROSS_ROLE_SAFE = new Set([
  'Pass completion',
  'Progressive pass share',
  'Dribbling riusciti',
  'Tackle success rate',
  'Aerial attempts per90',
  'Receivals per90',
  'Receival attempts per90',
  'Progressive carries per90',
  'Progressive carry attempts per90',
  'Passes ending box per90',
  'Shot attempts per90',
  'xG per90',
  'xA per90',
  'Expected assists per90',
]);

/* ── Italian label map ───────────────────────────────────────────── */
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

/* ── Format helpers ──────────────────────────────────────────────── */
function formatValue(v, fmt) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  if (fmt === 'percent')       return `${(v * 100).toFixed(1)}%`;
  if (fmt === 'percent_0_100') return `${v.toFixed(1)}%`;
  if (fmt === 'meters')        return `${v.toFixed(1)} m`;
  if (fmt === 'one_decimal')   return v.toFixed(1);
  if (Number.isInteger(v))     return v.toString();
  return v.toFixed(2);
}

/* ── Direction helper (raw values) ──────────────────────────────── */
function isBetterValue(candidateRaw, otherRaw, metricKey) {
  return LOWER_IS_BETTER.has(metricKey)
    ? candidateRaw <= otherRaw
    : candidateRaw >= otherRaw;
}

/* ── Normalize to 0–100 (for difficulty only) ────────────────────── */
function normalize(v, min, max) {
  if (max === min) return 50;
  return Math.max(0, Math.min(100, ((v - min) / (max - min)) * 100));
}

/* ── Shuffle array in-place (Fisher-Yates) ───────────────────────── */
function shuffle(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

/* ── Badges ──────────────────────────────────────────────────────── */
const BADGES = [
  { min: 9,  title: "Michelin Star PASTA chef",  desc: "Impeccabile. Sai leggere i dati come un executive scout."           },
  { min: 7,  title: "Mi dai la ricetta?",          desc: "Ottimo palato analitico. Quasi perfetto, ma lascia spazio al bis."  },
  { min: 5,  title: "C'avevo questo in frigo",     desc: "Buono, ma non prendo il bis."                                       },
  { min: 3,  title: "Pasta bianca",                desc: "Fai uno sforzo, che abbiamo ospiti dai."                            },
  { min: 0,  title: "PASTA col Ketchup",           desc: "I dati sono un linguaggio: ricomincia dall'alfabeto."               },
];

function getBadge(score) {
  return BADGES.find(b => score >= b.min);
}

const IMAGE_MANIFEST_URL = 'data/quiz/quiz-image-manifest.json';

/* ── State ───────────────────────────────────────────────────────── */
let playerPool    = [];
let questions     = [];
let currentQ      = 0;
let score         = 0;
let timerInterval  = null;
let advanceTimeout = null;
let timeLeft      = 10;
let answered      = false;
let imageManifest  = null;

/* ── DOM ─────────────────────────────────────────────────────────── */
const $ = id => document.getElementById(id);

/* ── Boot ────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  showScreen('pq-hero');
  $('pq-start-btn').addEventListener('click',  startQuiz);
  $('pq-replay-btn').addEventListener('click', startQuiz);
  $('pq-share-btn').addEventListener('click',  shareResult);
  // Pre-load while user reads hero
  loadActiveQuizPool().catch(e => log('Pre-load error:', e.message));
  loadImageManifest().catch(e => log('Manifest error:', e.message));
});

function showScreen(id) {
  document.querySelectorAll('.pq-screen').forEach(s => s.classList.remove('active'));
  const el = $(id);
  if (el) el.classList.add('active');
}

/* ── Image manifest ──────────────────────────────────────────────── */
async function loadImageManifest() {
  const resp = await fetch(IMAGE_MANIFEST_URL);
  if (!resp.ok) { log('Manifest not found:', IMAGE_MANIFEST_URL); return; }
  imageManifest = await resp.json();

  if (DEBUG) {
    console.log('[Man In Pasta] Image manifest loaded:', imageManifest);
    console.log('[Man In Pasta] Cover image:', imageManifest.cover);
    console.table(imageManifest.categories);
  }

  // Apply cover image to hero
  const coverImg = $('mip-cover-img');
  if (coverImg && imageManifest.cover) {
    coverImg.src = imageManifest.cover;
    coverImg.onload  = () => { coverImg.style.display = 'block'; };
    coverImg.onerror = () => { console.warn('[Man In Pasta] Missing cover image:', imageManifest.cover); };
  }
}

function applyResultBanner(score) {
  const banner = $('mip-result-banner');
  if (!banner) return;
  if (!imageManifest?.categories) { banner.style.display = 'none'; return; }

  const cat = imageManifest.categories.find(c => score >= c.min && score <= c.max);
  if (!cat?.image) { banner.style.display = 'none'; return; }

  banner.alt    = cat.title;
  banner.src    = cat.image;
  banner.onload  = () => { banner.style.display = 'block'; };
  banner.onerror = () => {
    console.warn('[Man In Pasta] Missing result image:', cat.image);
    banner.style.display = 'none';
  };
}

/* ══════════════════════════════════════════════════════════════════
   QUIZ START
   ══════════════════════════════════════════════════════════════════ */
async function startQuiz() {
  clearTimeout(advanceTimeout);
  clearInterval(timerInterval);
  score = 0; currentQ = 0; answered = false;
  showScreen('pq-loading');

  try {
    if (playerPool.length === 0) await loadActiveQuizPool();
    questions = buildQuestions();   // fresh random selection every time
    if (questions.length < 5) {
      showError(`Non ci sono abbastanza domande generabili (${questions.length}). Controlla i payload.`);
      return;
    }
    renderQuestion();
    showScreen('pq-question');
  } catch (e) {
    console.error(e);
    showError('Errore nel caricamento. Apri la pagina tramite server locale (python3 -m http.server 8001).');
  }
}

/* ══════════════════════════════════════════════════════════════════
   DATA LOADING
   ══════════════════════════════════════════════════════════════════ */
async function loadActiveQuizPool() {
  if (playerPool.length > 0) { log('Pool already loaded:', playerPool.length); return; }

  log('Active report index:', REPORT_INDEX_URL);

  const resp = await fetch(REPORT_INDEX_URL);
  if (!resp.ok) throw new Error(`Index HTTP ${resp.status}`);
  const rawIndex = await resp.json();

  // Filter: live, non-GK, deduplicate by playerId+role
  const seenReports = new Set();
  const activeReports = [];
  for (const entry of rawIndex) {
    if (entry.macro_role === 'GK') continue;
    if (entry.report_status && entry.report_status !== 'live') continue;
    const key = `${entry.player_id}__${entry.macro_role}`;
    if (seenReports.has(key)) continue;
    seenReports.add(key);
    activeReports.push(entry);
  }

  log('Active reports found:', activeReports.length);
  if (DEBUG) {
    console.table(activeReports.map(r => ({
      slug:    r.slug || r.report_file,
      player:  r.player_name,
      role:    r.macro_role,
      payload: r.payload_file,
    })));
  }

  const results = await Promise.allSettled(
    activeReports.map(entry => loadPayloadPlayers(entry))
  );

  let loaded = 0, failed = 0;
  const tempPool = {};

  for (const result of results) {
    if (result.status === 'rejected') { failed++; log('Payload failed:', result.reason); continue; }
    if (!result.value) { failed++; continue; }
    loaded++;
    for (const player of result.value) {
      const key = player.id ? String(player.id) : `${player.name}__${player.macroRole}`;
      if (!tempPool[key]) {
        tempPool[key] = player;
      } else {
        // Merge sourceTypes
        player.sourceTypes.forEach(t => {
          if (!tempPool[key].sourceTypes.includes(t)) tempPool[key].sourceTypes.push(t);
        });
        player.sourceReports.forEach(r => {
          if (!tempPool[key].sourceReports.includes(r)) tempPool[key].sourceReports.push(r);
        });
      }
    }
  }

  playerPool = Object.values(tempPool);

  // Debug breakdowns
  if (DEBUG) {
    const byType = {}, byRole = {};
    for (const p of playerPool) {
      const t = p.sourceTypes[0];
      byType[t] = (byType[t] || 0) + 1;
      byRole[p.macroRole] = (byRole[p.macroRole] || 0) + 1;
    }
    log('Players in quiz pool:', playerPool.length);
    log('Payloads: loaded=' + loaded + ' failed=' + failed);
    console.table(Object.entries(byType).map(([sourceType, count]) => ({ sourceType, count })));
    console.table(Object.entries(byRole).map(([role, count]) => ({ role, count })));
  }
}

async function loadPayloadPlayers(entry) {
  const url = entry.payload_file;
  const resp = await fetch(url);
  if (!resp.ok) { log(`HTTP ${resp.status} for ${url}`); return null; }
  const payload = await resp.json();

  const subjId  = String(payload.SUBJECT_ID || '');
  const pm      = payload.PLAYER_META || {};
  const allMt   = payload.METRICS || {};
  const ranges  = payload.METRIC_RANGES || {};
  const formats = payload.METRIC_FORMATS || {};
  const role    = payload.ROLE_META?.role || entry.macro_role;

  // Build sourceType map
  const srcMap = {};
  if (subjId) srcMap[subjId] = 'subject';
  for (const g of (payload.COMPARISON_GROUPS || [])) {
    const t = g.key === 'target' ? 'comparison' : 'source_team_peer';
    for (const id of (g.ids || [])) {
      const s = String(id);
      if (!srcMap[s]) srcMap[s] = t;
    }
  }

  const players = [];
  const skipLog = {};

  for (const [pid, pdata] of Object.entries(pm)) {
    const rawMetrics = allMt[pid];
    if (!rawMetrics || !Object.keys(rawMetrics).length) continue;

    const metrics = {};

    for (const [key, rawVal] of Object.entries(rawMetrics)) {
      if (EXCLUDED_METRICS.has(key)) { skipLog[key] = 'excluded'; continue; }
      if (typeof rawVal !== 'number' || isNaN(rawVal) || rawVal === null) { skipLog[key] = 'non-numeric'; continue; }
      const range = ranges[key];
      if (!range) { skipLog[key] = 'no range'; continue; }

      const raw100  = normalize(rawVal, range.min, range.max);
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
      id:           parseInt(pid, 10) || null,
      name:         pdata.name,
      macroRole:    pdata.macroRole || role,
      sourceTypes:  [srcMap[pid] || 'context'],
      sourceReports:[url],
      metrics,
    });
  }

  if (DEBUG && subjId) log(`${url}: ${players.length} players | skip sample:`, skipLog);
  return players;
}

/* ══════════════════════════════════════════════════════════════════
   QUESTION GENERATION — random bucket selection each call
   ══════════════════════════════════════════════════════════════════ */
function buildQuestions() {
  // 1. Generate ALL valid candidate questions
  const candidates = [];
  const n = playerPool.length;
  let skipped = { crossRole: 0, tooSmall: 0 };

  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const pA = playerPool[i];
      const pB = playerPool[j];
      const sameRole = pA.macroRole === pB.macroRole;

      for (const key of Object.keys(pA.metrics)) {
        if (!(key in pB.metrics)) continue;
        if (!sameRole && !CROSS_ROLE_SAFE.has(key)) { skipped.crossRole++; continue; }

        const mA = pA.metrics[key];
        const mB = pB.metrics[key];
        const diff = Math.abs(mA.diffScore - mB.diffScore);

        if (diff < 2) { skipped.tooSmall++; continue; }

        candidates.push({
          playerA:         pA,
          playerB:         pB,
          metricKey:       key,
          label:           mA.label,
          format:          mA.format,
          difficultyScore: diff,
          winner:          isBetterValue(mA.value, mB.value, key) ? 'A' : 'B',
        });
      }
    }
  }

  log(`Candidates: ${candidates.length} | skipped crossRole=${skipped.crossRole} tooSmall=${skipped.tooSmall}`);

  // 2. Split into difficulty buckets
  const easy   = candidates.filter(q => q.difficultyScore >= 25);
  const medium = candidates.filter(q => q.difficultyScore >= 10 && q.difficultyScore < 25);
  const hard   = candidates.filter(q => q.difficultyScore >= 3  && q.difficultyScore < 10);

  log(`Buckets — easy:${easy.length} medium:${medium.length} hard:${hard.length}`);

  // 3. Pick randomly from buckets (3 easy, 4 medium, 3 hard)
  const plan = [
    { bucket: easy,   count: 3, label: 'easy'   },
    { bucket: medium, count: 4, label: 'medium'  },
    { bucket: hard,   count: 3, label: 'hard'    },
  ];

  const selected = [];
  const usedPairKeys   = new Set();
  const metricUsage    = {};
  const playerUsage    = {};

  for (const { bucket, count, label } of plan) {
    let pool = shuffle([...bucket]);
    let needed = count;

    // Fallback: if bucket too small, steal from nearest bucket
    if (pool.length < needed) {
      const fallback = shuffle([...candidates]).filter(q => !selected.includes(q));
      pool = shuffle([...pool, ...fallback]);
    }

    for (const q of pool) {
      if (needed <= 0) break;

      const pairKey = [q.playerA.id ?? q.playerA.name, q.playerB.id ?? q.playerB.name].sort().join('|') + ':' + q.metricKey;
      if (usedPairKeys.has(pairKey)) continue;

      // Soft limits: avoid same metric >2 times, same player >3 times
      if ((metricUsage[q.metricKey] || 0) >= 2) continue;
      const pAKey = String(q.playerA.id ?? q.playerA.name);
      const pBKey = String(q.playerB.id ?? q.playerB.name);
      if ((playerUsage[pAKey] || 0) >= 3 || (playerUsage[pBKey] || 0) >= 3) continue;

      usedPairKeys.add(pairKey);
      metricUsage[q.metricKey]  = (metricUsage[q.metricKey]  || 0) + 1;
      playerUsage[pAKey]        = (playerUsage[pAKey]        || 0) + 1;
      playerUsage[pBKey]        = (playerUsage[pBKey]        || 0) + 1;
      q.difficulty = label;
      selected.push(q);
      needed--;
    }
  }

  // 4. Randomly flip A/B presentation (winner label follows)
  for (const q of selected) {
    if (Math.random() < 0.5) {
      [q.playerA, q.playerB] = [q.playerB, q.playerA];
      q.winner = q.winner === 'A' ? 'B' : 'A';
    }
  }

  // 5. Debug table
  if (DEBUG) {
    console.table(selected.map((q, i) => ({
      question:        i + 1,
      metric:          q.label,
      playerA:         q.playerA.name,
      playerB:         q.playerB.name,
      difficultyScore: q.difficultyScore.toFixed(1),
      difficultyLabel: q.difficulty,
      winner:          q.winner,
    })));

    // Winner audit
    const audit = auditWinners(selected);
    log('Winner audit:', audit);
  }

  return selected;
}

function auditWinners(qs) {
  const results = qs.map((q, i) => {
    const mA = q.playerA.metrics[q.metricKey];
    const mB = q.playerB.metrics[q.metricKey];
    const expected = isBetterValue(mA.value, mB.value, q.metricKey) ? 'A' : 'B';
    return { q: i + 1, ok: expected === q.winner, winner: q.winner, expected };
  });
  const allOk = results.every(r => r.ok);
  return { allOk, total: results.length, passed: results.filter(r => r.ok).length, details: results };
}

/* ══════════════════════════════════════════════════════════════════
   RENDERING
   ══════════════════════════════════════════════════════════════════ */
function renderQuestion() {
  const q = questions[currentQ];
  answered = false;

  $('pq-progress-fill').style.width = `${(currentQ / questions.length) * 100}%`;
  $('pq-question-counter').textContent = `Domanda ${currentQ + 1} / ${questions.length}`;

  const badge = $('pq-difficulty-badge');
  badge.className = 'pq-difficulty-badge';
  const diffMap = { easy: ['Facile', 'pq-diff-easy'], medium: ['Media', 'pq-diff-medium'], hard: ['Difficile', 'pq-diff-hard'] };
  const [lbl, cls] = diffMap[q.difficulty] || diffMap.medium;
  badge.classList.add(cls);
  badge.textContent = lbl;

  $('pq-metric-name').textContent = q.label;

  renderCard('A', q.playerA);
  renderCard('B', q.playerB);

  $('pq-feedback').className = 'pq-feedback';

  startTimer();
}

function renderCard(letter, player) {
  const card = $(`pq-card-${letter}`);
  card.className = 'pq-player-card';
  card.querySelector('.pq-card-name').textContent = player.name;
  card.querySelector('.pq-card-role').textContent = player.macroRole;
  card.onclick = () => handleAnswer(letter);
}

/* ── Timer ───────────────────────────────────────────────────────── */
function startTimer() {
  clearInterval(timerInterval);
  timeLeft = 10;
  updateTimerUI();
  timerInterval = setInterval(() => {
    timeLeft--;
    updateTimerUI();
    if (timeLeft <= 0) { clearInterval(timerInterval); handleTimeout(); }
  }, 1000);
}

function updateTimerUI() {
  $('pq-timer-label').textContent = timeLeft;
  const fill = $('pq-timer-fill');
  fill.style.width = `${(timeLeft / 10) * 100}%`;
  fill.className = 'pq-timer-fill';
  if (timeLeft <= 3)      fill.classList.add('danger');
  else if (timeLeft <= 6) fill.classList.add('warning');
}

/* ── Answer ──────────────────────────────────────────────────────── */
function handleAnswer(letter) {
  if (answered) return;
  answered = true;
  clearInterval(timerInterval);

  const correct = letter === questions[currentQ].winner;
  if (correct) score++;

  $(`pq-card-${letter}`).classList.add(correct ? 'selected-correct' : 'selected-wrong');
  if (!correct) markCorrectCard();
  disableCards();
  showFeedback(correct ? 'correct' : 'wrong');
  scheduleNext();
}

function handleTimeout() {
  if (answered) return;
  answered = true;
  disableCards();
  markCorrectCard();
  showFeedback('timeout');
  scheduleNext();
}

function markCorrectCard() {
  $(`pq-card-${questions[currentQ].winner}`).classList.add('correct-answer');
}

function disableCards() {
  ['A', 'B'].forEach(l => { const c = $(`pq-card-${l}`); c.classList.add('disabled'); c.onclick = null; });
}

function scheduleNext() {
  advanceTimeout = setTimeout(() => {
    currentQ++;
    if (currentQ >= questions.length) showResult();
    else renderQuestion();
  }, 3200);
}

/* ── Feedback ────────────────────────────────────────────────────── */
function showFeedback(verdict) {
  const q   = questions[currentQ];
  const mA  = q.playerA.metrics[q.metricKey];
  const mB  = q.playerB.metrics[q.metricKey];
  const fmt = q.format;

  const verdictEl = $('pq-feedback-verdict');
  if (verdict === 'correct')
    verdictEl.innerHTML = '<span class="pq-verdict-correct">✓ Corretto!</span>';
  else if (verdict === 'wrong')
    verdictEl.innerHTML = '<span class="pq-verdict-wrong">✗ Sbagliato</span>';
  else
    verdictEl.innerHTML = '<span class="pq-verdict-timeout">⏱ Tempo scaduto</span>';

  const winnerIsA = q.winner === 'A';
  $('pq-fb-name-a').textContent = q.playerA.name;
  $('pq-fb-val-a').textContent  = formatValue(mA?.value, fmt);
  $('pq-fb-name-b').textContent = q.playerB.name;
  $('pq-fb-val-b').textContent  = formatValue(mB?.value, fmt);
  $('pq-fb-row-a').className    = 'pq-fb-val' + (winnerIsA  ? ' winner' : '');
  $('pq-fb-row-b').className    = 'pq-fb-val' + (!winnerIsA ? ' winner' : '');

  const winnerName = winnerIsA ? q.playerA.name : q.playerB.name;
  const diff = Math.abs((mA?.diffScore || 0) - (mB?.diffScore || 0));
  let phrase;
  if (diff >= 40)      phrase = `${winnerName} domina nettamente questa metrica.`;
  else if (diff >= 20) phrase = `${winnerName} è chiaramente superiore in questa metrica.`;
  else if (diff >= 8)  phrase = `${winnerName} ha un vantaggio misurabile, ma non enorme.`;
  else                 phrase = 'Differenza minima: serviva occhio clinico.';
  if (LOWER_IS_BETTER.has(q.metricKey)) phrase += ' (↓ valore più basso = meglio)';

  $('pq-feedback-explanation').textContent = phrase;
  $('pq-feedback').classList.add('show');
}

/* ── Result ──────────────────────────────────────────────────────── */
function showResult() {
  $('pq-score-number').textContent  = score;
  $('pq-score-total-label').textContent = `/ ${questions.length}`;

  const badge = getBadge(score);
  $('pq-badge-name').textContent   = `"${badge.title}"`;
  $('pq-badge-phrase').textContent = `${score}/${questions.length} — ${badge.desc}`;

  window._quizBadge = badge.title;
  window._quizScore = score;
  window._quizTotal = questions.length;

  applyResultBanner(score);
  showScreen('pq-result');
}

/* ── Share ───────────────────────────────────────────────────────── */
const QUIZ_URL = 'https://pasta-reports.com/quiz.html';

function shareResult() {
  const cat = imageManifest?.categories?.find(
    c => window._quizScore >= c.min && window._quizScore <= c.max
  );
  const shareUrl = QUIZ_URL;
  const text =
    `Ho fatto ${window._quizScore}/${window._quizTotal} a Man In Pasta` +
    ` e ho ottenuto il badge "${window._quizBadge}" 🍝` +
    `\nProva a battermi!\n${shareUrl}`;
  window.open(
    `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}`,
    '_blank', 'noopener,noreferrer'
  );
}

/* ── Error display ───────────────────────────────────────────────── */
function showError(msg) {
  $('pq-loading').innerHTML = `<div class="pq-error-box">${msg}</div>`;
  showScreen('pq-loading');
}
