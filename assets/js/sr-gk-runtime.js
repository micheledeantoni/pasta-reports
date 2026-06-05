// sr-gk-runtime.js
// GK Page V1 HTML5UP runtime. Data comes from the inline DATA block or external JSON.
// version: mplsoccer-polish-v1 (2026-05-20)
// Sprint 4C: unwrapped IIFE to named function; SR_GK_PAYLOAD_READY wait added at bottom.

function initGkReport() {
    console.info('[GK runtime] version: mplsoccer-polish-v1 (2026-05-20) — build_up_map + backend sweeper normalization active');
    function readGlobal(name, fallback) {
        try {
            return Function('fallback', `return typeof ${name} !== "undefined" ? ${name} : fallback;`)(fallback);
        } catch (_err) {
            return fallback;
        }
    }

    const payloadEnvelope = readGlobal('GK_PAGE_V1_PLAYERS', { players: [] });
    const comparisonEnvelope = readGlobal('GK_PAGE_V1_TEAM_COMPARISONS', { team_comparisons: [] });
    const summaryEnvelope = readGlobal('GK_PAGE_V1_SUMMARY', {});
    const players = Array.isArray(payloadEnvelope) ? payloadEnvelope : (payloadEnvelope.players || []);
    const teamComparisons = Array.isArray(comparisonEnvelope) ? comparisonEnvelope : (comparisonEnvelope.team_comparisons || []);
    const reportContext = payloadEnvelope.report_context || summaryEnvelope.report_context || {
        report_type: 'gk_target_vs_team_room',
        target_player_name: 'Guglielmo Vicario',
        comparison_team_name: 'Inter',
        comparison_players: ['Yann Sommer', 'Josep Martínez'],
        primary_comparison_player: 'Yann Sommer',
        forced_backup_player: 'Josep Martínez',
    };

    const AXES = ['shot_stopping', 'box_control', 'sweeper_activity', 'distribution'];
    const AXIS_LABELS = {
        shot_stopping: 'Parate e rendimento sui tiri',
        box_control: 'Controllo dell’area',
        sweeper_activity: 'Uscite e copertura profondità',
        distribution: 'Distribuzione',
    };
    const AXIS_GUIDE = {
        shot_stopping: 'capacità statistica di incidere sui tiri nello specchio e sui gol concessi.',
        box_control: 'presenza su cross, prese, uscite alte e gestione dello spazio vicino alla porta.',
        sweeper_activity: 'tendenza a difendere lo spazio fuori dall’area e ad agire da portiere-libero.',
        distribution: 'coinvolgimento e sicurezza nel gioco con i piedi.',
    };
    const SAMPLE_LABELS = {
        starter_sample: 'Campione da titolare',
        backup_sample: 'Campione da secondo portiere',
        forced_low_sample: 'Campione ridotto, incluso per confronto interno',
        unreliable_sample: 'Campione poco affidabile',
    };
    const GOAL_ZONE_ROWS = [
        ['top_left', 'top_center', 'top_right'],
        ['middle_left', 'middle_center', 'middle_right'],
        ['bottom_left', 'bottom_center', 'bottom_right'],
    ];
    function cssVar(name, fallback) {
        const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return value || fallback;
    }
    const COLORS = {
        target: cssVar('--sr-radar-subject-border', '#c47434'),
        comparison: cssVar('--sr-radar-comparison-border', '#94c4e6'),
        alternate: cssVar('--ei2-accent', '#831843'),
    };
    let selectedComparisonName = reportContext.primary_comparison_player || 'Yann Sommer';
    let visualPlayerId = null;
    let radarChart = null;
    let radarEnhanced = false;

    function $(id) { return document.getElementById(id); }
    function esc(value) {
        return String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
    }
    function titleCase(value) {
        return String(value || '').replace(/_/g, ' ').replace(/\b\w/g, ch => ch.toUpperCase());
    }
    function fmt(value, digits = 2) {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
        const n = Number(value);
        if (Number.isInteger(n) || Math.abs(n) >= 100) return n.toLocaleString('it-IT');
        return n.toFixed(digits);
    }
    function pct(value) {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
        return `${(Number(value) * 100).toFixed(0)}%`;
    }
    function statusClass(status) {
        if (status === 'starter_sample') return 'sr-gk-ok';
        if (status === 'backup_sample') return 'sr-gk-info';
        if (status === 'forced_low_sample') return 'sr-gk-warn';
        if (status === 'unreliable_sample') return 'sr-gk-alert';
        return 'sr-gk-muted';
    }
    function sampleLabel(status) { return SAMPLE_LABELS[status] || titleCase(status || 'campione non disponibile'); }
    function sampleWarningText(payload) {
        const h = payload.header || {};
        if (h.sample_status === 'starter_sample') return 'Campione da titolare: minuti sufficienti per una lettura GK ordinaria.';
        if (h.sample_status === 'backup_sample') return 'Campione da secondo portiere: minuti sufficienti, ma ruolo e contesto restano da leggere con cautela.';
        if (h.sample_status === 'forced_low_sample') return 'Campione ridotto: incluso solo per il confronto interno con la stanza portieri Inter, senza modificare i benchmark ufficiali.';
        if (h.sample_status === 'unreliable_sample') return 'Campione poco affidabile: i valori vanno letti come indicativi.';
        return h.sample_warning_text || 'Campione disponibile per la lettura GK V1.';
    }
    function visualReady(block) { return ['available', 'ready'].includes(block?.visual_status); }
    function visualPartial(block) { return String(block?.visual_status || '').includes('partial') || String(block?.visual_status || '').includes('summary_only'); }
    function findPlayerByName(name) {
        return players.find(p => String(p.header?.player_name || '').toLowerCase() === String(name || '').toLowerCase());
    }
    function findPlayerById(id) {
        return players.find(p => String(p.header?.player_id) === String(id));
    }
    function targetPayload() {
        return findPlayerByName(reportContext.target_player_name) || findPlayerById(reportContext.target_player_id) || players[0];
    }
    function comparisonPayloads() {
        return (reportContext.comparison_players || []).map(findPlayerByName).filter(Boolean);
    }
    function selectedComparisonPayload() {
        return findPlayerByName(selectedComparisonName) || comparisonPayloads()[0] || targetPayload();
    }
    function visualPayload() {
        return findPlayerById(visualPlayerId) || targetPayload();
    }
    function findInterRoomComparison() {
        return teamComparisons.find(item => {
            const c = item.team_gk_comparison || item;
            const gks = c.gks || [];
            const names = new Set(gks.map(gk => gk.player_name));
            return String(c.team_name) === String(reportContext.comparison_team_name || 'Inter')
                && names.has(reportContext.primary_comparison_player || 'Yann Sommer')
                && names.has(reportContext.forced_backup_player || 'Josep Martínez');
        });
    }
    function axisScores(payload) {
        const axes = payload.radar?.axes || [];
        return Object.fromEntries(AXES.map(id => [id, axes.find(axis => axis.axis_id === id)?.axis_score_0_100]));
    }
    function actionMetric(payload, key) {
        return payload?.action_split?.[key] || null;
    }
    function metricNumber(row, preference = 'raw') {
        if (!row) return null;
        if (preference === 'share' && row.percentage_or_share !== null && row.percentage_or_share !== undefined) return Number(row.percentage_or_share);
        if (preference === 'per90' && row.per90 !== null && row.per90 !== undefined) return Number(row.per90);
        if (row.raw_total !== null && row.raw_total !== undefined) return Number(row.raw_total);
        if (row.per90 !== null && row.per90 !== undefined) return Number(row.per90);
        if (row.percentage_or_share !== null && row.percentage_or_share !== undefined) return Number(row.percentage_or_share);
        return null;
    }
    function metricDisplay(row, preference = 'raw') {
        if (!row) return '—';
        if (preference === 'share' && row.percentage_or_share !== null && row.percentage_or_share !== undefined) return pct(row.percentage_or_share);
        if (preference === 'per90' && row.per90 !== null && row.per90 !== undefined) return `${fmt(row.per90)} p90`;
        if (row.raw_total !== null && row.raw_total !== undefined) return fmt(row.raw_total, 0);
        if (row.per90 !== null && row.per90 !== undefined) return `${fmt(row.per90)} p90`;
        if (row.percentage_or_share !== null && row.percentage_or_share !== undefined) return pct(row.percentage_or_share);
        return '—';
    }
    function savePct(payload) {
        const saves = metricNumber(actionMetric(payload, 'saves'));
        const sot = metricNumber(actionMetric(payload, 'shots_on_target_faced'));
        if (!saves && saves !== 0 || !sot) return null;
        return saves / sot;
    }
    function distMetric(payload, key) {
        return payload?.visual_blocks?.distribution_profile?.season_metrics?.[key];
    }

    function renderHeader() {
        const payload = targetPayload();
        const h = payload.header || {};
        const el = $('gkHeader');
        if (!el) return;
        const targetSavePct = savePct(payload);
        const passCompletion = distMetric(payload, 'pass_completion_pct');
        el.innerHTML = `
            <div class="sr-header-top">
                <div class="sr-header-left">
                    <div class="sr-player-photo"><div class="sr-photo-placeholder">${esc((h.player_name || 'G').slice(0, 1))}</div></div>
                    <div>
                        <h2 class="sr-player-name">${esc(h.player_name || reportContext.target_player_name)}</h2>
                        <span class="sr-clubs-line">Valutazione per Inter</span>
                        <div class="sr-club-flow" aria-label="Percorso valutazione club">
                            <div class="sr-club-node"><div class="sr-club-logo tottenham">TOT</div><span>${esc(h.team_name || 'Tottenham')}</span></div>
                            <span class="sr-club-arrow">→</span>
                            <div class="sr-club-node"><div class="sr-club-logo inter">INT</div><span>Inter</span></div>
                        </div>
                    </div>
                </div>
                <span class="sr-role-pill">Portiere</span>
            </div>
            <div class="sr-meta-row">
                <span class="sr-meta-chip">${esc(h.competition_name || 'Competizione n.d.')}</span>
                <span class="sr-meta-chip">Stagione ${esc(h.season_id || '—')}</span>
                <span class="sr-meta-chip">${fmt(h.minutes, 0)} minuti</span>
                <span class="sr-meta-chip">${esc(sampleLabel(h.sample_status))}</span>
            </div>
            <div class="sr-badges">
                <div class="sr-badge"><span class="sr-badge-k">Save pct</span><span class="sr-badge-v">${pct(targetSavePct)}</span></div>
                <div class="sr-badge"><span class="sr-badge-k">Pass completion</span><span class="sr-badge-v">${pct(passCompletion)}</span></div>
                <div class="sr-badge"><span class="sr-badge-k">Benchmark</span><span class="sr-badge-v">${h.official_benchmark_eligible ? 'Ufficiale' : 'Solo display'}</span></div>
            </div>
        `;
        const warn = $('gkSampleWarning');
        if (warn) {
            warn.innerHTML = h.sample_status === 'starter_sample'
                ? ''
                : `<div class="sr-gk-sample ${statusClass(h.sample_status)}"><strong>${esc(sampleLabel(h.sample_status))}</strong><span>${esc(sampleWarningText(payload))}</span></div>`;
        }
    }

    function setupRadarSelector() {
        const select = $('gkRadarTargetSelect');
        if (!select) return;
        const options = comparisonPayloads();
        select.innerHTML = options.map(p => `<option value="${esc(p.header?.player_name)}">${esc(p.header?.player_name)}</option>`).join('');
        if (!options.some(p => p.header?.player_name === selectedComparisonName)) selectedComparisonName = options[0]?.header?.player_name || selectedComparisonName;
        select.value = selectedComparisonName;
        select.addEventListener('change', () => {
            selectedComparisonName = select.value;
            renderRadar();
        });
    }

    function enhanceRadarMobile() {
        if (radarEnhanced) return;
        const section = $('gkRadarSection');
        const wrap = section?.querySelector('.sr-radar-wrap-full');
        if (!section || !wrap) return;
        let summary = $('gkRadarMobileSummary');
        if (!summary) {
            summary = document.createElement('div');
            summary.id = 'gkRadarMobileSummary';
            summary.className = 'sr-gk-radar-summary';
            wrap.parentNode.insertBefore(summary, wrap);
        }
        if (!section.querySelector('.sr-gk-radar-details')) {
            const details = document.createElement('details');
            details.className = 'sr-gk-radar-details';
            details.id = 'gkRadarDetails';
            details.open = !window.matchMedia('(max-width: 768px)').matches;
            const summaryEl = document.createElement('summary');
            summaryEl.className = 'sr-axis-accordion-summary';
            summaryEl.textContent = 'Radar completo';
            details.appendChild(summaryEl);
            wrap.parentNode.insertBefore(details, wrap);
            details.appendChild(wrap);
            const context = section.querySelector('.sr-radar-context-note');
            const axis = section.querySelector('.sr-axis-accordion');
            if (context) details.appendChild(context);
            if (axis) details.appendChild(axis);
            details.addEventListener('toggle', () => {
                if (details.open && radarChart) {
                    window.requestAnimationFrame(() => radarChart.resize());
                }
            });
        }
        radarEnhanced = true;
    }

    function renderRadarLegend(target, comparison) {
        const el = $('gkRadarLegend');
        if (!el) return;
        el.innerHTML = `
            <span class="sr-rcl-item"><span class="sr-rcl-line sr-rcl-line--subject"></span>${esc(target.header?.player_name || 'Vicario')}</span>
            <span class="sr-rcl-item"><span class="sr-rcl-line sr-rcl-line--comp"></span>${esc(comparison.header?.player_name || 'Confronto')}</span>
        `;
    }

    function renderAxisGuide(target) {
        const guide = $('gkRadarAxisGuide');
        if (!guide) return;
        const targetAxes = target.radar?.axes || [];
        guide.innerHTML = AXES.map(axisId => {
            const axis = targetAxes.find(item => item.axis_id === axisId) || {};
            const metrics = (axis.component_metrics || []).map(item => item.metric_name).join(', ');
            return `<li class="sr-axis-card"><strong>${esc(AXIS_LABELS[axisId])}</strong><span>${esc(AXIS_GUIDE[axisId])}</span>${metrics ? `<span>${esc(metrics)}</span>` : ''}</li>`;
        }).join('');
    }

    function renderRadarSummary(target, comparison) {
        const el = $('gkRadarMobileSummary');
        if (!el) return;
        const targetScores = axisScores(target);
        const comparisonScores = axisScores(comparison);
        el.innerHTML = AXES.map(axisId => {
            const targetValue = Number(targetScores[axisId]) || 0;
            const comparisonValue = Number(comparisonScores[axisId]) || 0;
            const delta = targetValue - comparisonValue;
            const deltaText = delta >= 0 ? `+${fmt(delta, 0)}` : fmt(delta, 0);
            return `<div class="sr-gk-radar-axis">
                <div class="sr-gk-radar-axis-head">
                    <span>${esc(AXIS_LABELS[axisId])}</span>
                    <strong>${fmt(targetValue, 0)}</strong>
                </div>
                <div class="sr-gk-radar-track" aria-hidden="true">
                    <i class="sr-gk-radar-fill" style="width:${Math.max(0, Math.min(100, targetValue))}%; background:${COLORS.target};"></i>
                    <b class="sr-gk-radar-marker" style="left:${Math.max(0, Math.min(100, comparisonValue))}%; border-color:${COLORS.comparison};"></b>
                </div>
                <div class="sr-gk-radar-axis-foot">
                    <span>${esc(target.header?.player_name || 'Target')}</span>
                    <span>${esc(comparison.header?.player_name || 'Confronto')} ${fmt(comparisonValue, 0)} · diff ${deltaText}</span>
                </div>
            </div>`;
        }).join('');
    }

    function renderRadar() {
        enhanceRadarMobile();
        const target = targetPayload();
        const comparison = selectedComparisonPayload();
        renderRadarLegend(target, comparison);
        renderAxisGuide(target);
        renderRadarSummary(target, comparison);
        const canvas = $('gkRadarChart');
        if (!canvas || typeof Chart === 'undefined') return;
        if (radarChart) radarChart.destroy();
        const targetScores = axisScores(target);
        const comparisonScores = axisScores(comparison);
        radarChart = new Chart(canvas.getContext('2d'), {
            type: 'radar',
            data: {
                labels: AXES.map(axis => AXIS_LABELS[axis]),
                datasets: [
                    {
                        label: target.header?.player_name || 'Vicario',
                        data: AXES.map(axis => Number(targetScores[axis]) || 0),
                        borderColor: COLORS.target,
                        backgroundColor: 'rgba(74,222,128,.18)',
                        pointBackgroundColor: COLORS.target,
                        pointBorderColor: COLORS.target,
                        borderWidth: 3,
                        pointRadius: 4,
                    },
                    {
                        label: comparison.header?.player_name || 'Confronto',
                        data: AXES.map(axis => Number(comparisonScores[axis]) || 0),
                        borderColor: COLORS.comparison,
                        backgroundColor: 'rgba(251,146,60,.12)',
                        pointBackgroundColor: COLORS.comparison,
                        pointBorderColor: COLORS.comparison,
                        borderWidth: 2,
                        pointRadius: 3,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: { r: { min: 0, max: 100, ticks: { display: false, stepSize: 25 }, grid: { color: 'rgba(255,255,255,.055)' }, angleLines: { color: 'rgba(255,255,255,.06)' }, pointLabels: { color: 'rgba(255,255,255,.72)', font: { size: 12, weight: '600' } } } },
                plugins: { legend: { display: false } },
            },
        });
    }

    // ---- BARS: 3 players (Vicario, Sommer, Martínez) ----

    function minutesOf(payload) {
        const m = Number(payload?.header?.minutes);
        return Number.isFinite(m) && m > 0 ? m : null;
    }
    function per90FromTotal(payload, key) {
        const row = actionMetric(payload, key);
        if (!row) return null;
        if (row.per90 !== null && row.per90 !== undefined && Number.isFinite(Number(row.per90))) return Number(row.per90);
        const total = row.raw_total;
        const minutes = minutesOf(payload);
        if (total !== null && total !== undefined && minutes) return Number(total) / minutes * 90;
        return null;
    }
    function shareValue(payload, key) {
        const row = actionMetric(payload, key);
        if (!row) return null;
        if (row.percentage_or_share !== null && row.percentage_or_share !== undefined && Number.isFinite(Number(row.percentage_or_share))) return Number(row.percentage_or_share);
        return null;
    }
    function rawTotal(payload, key) {
        const row = actionMetric(payload, key);
        if (!row || row.raw_total === null || row.raw_total === undefined || !Number.isFinite(Number(row.raw_total))) return null;
        return Number(row.raw_total);
    }
    function crossStopPct(payload) {
        const stopped = rawTotal(payload, 'crosses_stopped');
        const faced = rawTotal(payload, 'crosses_faced');
        if (stopped === null || !faced) return shareValue(payload, 'crosses_stopped');
        return stopped / faced;
    }
    function normMetric(payload, key, mode = 'per90') {
        if (mode === 'share') return shareValue(payload, key);
        if (mode === 'raw') return rawTotal(payload, key);
        return per90FromTotal(payload, key);
    }
    function buildMetricGroups(target, comp1, comp2) {
        const trio = [target, comp1, comp2];
        function row(label, values, opts = {}) {
            const clean = values.map(v => (v === null || v === undefined || Number.isNaN(Number(v))) ? null : Number(v));
            const valid = clean.filter(v => v !== null);
            if (!valid.length) return null;
            const max = Math.max(...valid.map(v => Math.abs(v)), 1);
            return { label, values: clean, max, fmt: opts.fmt || ((v) => fmt(v)), lowerBetter: Boolean(opts.lowerBetter), note: opts.note || '', rawTips: opts.rawTips || [] };
        }
        return [
            {
                label: 'Parate e rendimento sui tiri',
                metrics: [
                    row('Parate p90', trio.map(p => per90FromTotal(p, 'saves')), { fmt: v => `${fmt(v)} p90`, rawTips: trio.map(p => rawTotal(p, 'saves')) }),
                    row('Gol concessi p90', trio.map(p => per90FromTotal(p, 'goals_conceded')), { fmt: v => `${fmt(v)} p90`, lowerBetter: true, note: 'valore più basso preferibile', rawTips: trio.map(p => rawTotal(p, 'goals_conceded')) }),
                    row('Tiri in porta affrontati p90', trio.map(p => per90FromTotal(p, 'shots_on_target_faced')), { fmt: v => `${fmt(v)} p90`, rawTips: trio.map(p => rawTotal(p, 'shots_on_target_faced')) }),
                    row('Save percentage', trio.map(p => savePct(p)), { fmt: v => pct(v) }),
                ].filter(Boolean),
            },
            {
                label: 'Controllo dell’area',
                metrics: [
                    row('Prese / claims p90', trio.map(p => per90FromTotal(p, 'claims')), { fmt: v => `${fmt(v)} p90`, rawTips: trio.map(p => rawTotal(p, 'claims')) }),
                    row('Punches p90', trio.map(p => per90FromTotal(p, 'punches')), { fmt: v => `${fmt(v)} p90`, rawTips: trio.map(p => rawTotal(p, 'punches')) }),
                    row('Cross affrontati p90', trio.map(p => per90FromTotal(p, 'crosses_faced')), { fmt: v => `${fmt(v)} p90`, rawTips: trio.map(p => rawTotal(p, 'crosses_faced')) }),
                    row('Cross fermati p90', trio.map(p => per90FromTotal(p, 'crosses_stopped')), { fmt: v => `${fmt(v)} p90`, rawTips: trio.map(p => rawTotal(p, 'crosses_stopped')) }),
                    row('Cross stop %', trio.map(p => crossStopPct(p)), { fmt: v => pct(v) }),
                ].filter(Boolean),
            },
            {
                label: 'Uscite e copertura profondità',
                metrics: [
                    row('Azioni fuori area p90', trio.map(p => per90FromTotal(p, 'defensive_actions_outside_box')), { fmt: v => `${fmt(v)} p90`, rawTips: trio.map(p => rawTotal(p, 'defensive_actions_outside_box')) }),
                    row('Quota fuori area', trio.map(p => shareValue(p, 'defensive_actions_outside_box')), { fmt: v => pct(v) }),
                    row('Distanza media azione', trio.map(p => p?.visual_blocks?.sweeper_actions_map?.average_action_distance_from_goal), { fmt: v => fmt(v) }),
                ].filter(Boolean),
            },
            {
                label: 'Distribuzione',
                metrics: [
                    row('Passaggi tentati p90', trio.map(p => per90FromTotal(p, 'passes_attempted')), { fmt: v => `${fmt(v)} p90`, rawTips: trio.map(p => rawTotal(p, 'passes_attempted')) }),
                    row('Passaggi corti share', trio.map(p => shareValue(p, 'short_passes') ?? distMetric(p, 'short_pass_share')), { fmt: v => pct(v) }),
                    row('Passaggi lunghi share', trio.map(p => shareValue(p, 'long_passes') ?? distMetric(p, 'long_pass_share')), { fmt: v => pct(v) }),
                    row('Passaggi progressivi p90', trio.map(p => per90FromTotal(p, 'progressive_passes') ?? distMetric(p, 'progressive_passes_per90')), { fmt: v => `${fmt(v)} p90`, rawTips: trio.map(p => rawTotal(p, 'progressive_passes')) }),
                    row('Completamento passaggi', trio.map(p => distMetric(p, 'pass_completion_pct')), { fmt: v => pct(v) }),
                ].filter(Boolean),
            },
        ].filter(group => group.metrics.length);
    }

    function renderBarsLegend(target, comp1, comp2) {
        const el = $('gkBarsLegend');
        if (!el) return;
        let html = `<span class="sr-player-tag"><span class="sr-ptag-dot" style="background:${COLORS.target}"></span>${esc(target?.header?.player_name || 'Vicario')}</span>`;
        if (comp1) html += `<span class="sr-player-tag"><span class="sr-ptag-dot" style="background:${COLORS.comparison}"></span>${esc(comp1.header?.player_name || 'Sommer')}</span>`;
        if (comp2) html += `<span class="sr-player-tag"><span class="sr-ptag-dot" style="background:${COLORS.alternate}"></span>${esc(comp2.header?.player_name || 'Martínez')}</span>`;
        el.innerHTML = html;
    }

    function renderBars() {
        const el = $('gkBars');
        if (!el) return;
        const target = targetPayload();
        const comps = comparisonPayloads();
        const comp1 = comps[0];
        const comp2 = comps[1];
        const trio = [target, comp1, comp2].filter(Boolean);
        const names = trio.map(p => p?.header?.player_name || 'GK');
        renderBarsLegend(target, comp1, comp2);
        const groups = buildMetricGroups(target, comp1, comp2);
        let warning = '<p class="sr-radar-context-note">Valori principali normalizzati per90, percentuali, rate o share. I conteggi grezzi restano solo nei tooltip quando disponibili.</p>';
        if (comp2?.header?.sample_status === 'forced_low_sample') {
            warning += `<div class="sr-gk-sample ${statusClass(comp2.header.sample_status)}"><strong>${esc(sampleLabel(comp2.header.sample_status))}</strong><span>Martínez è incluso solo come confronto interno della stanza portieri Inter; non entra nei benchmark ufficiali.</span></div>`;
        }
        el.innerHTML = `${warning}${groups.map(group => `
            <div class="sr-dot-group">
                <div class="sr-dot-group-title">${esc(group.label)}</div>
                ${group.metrics.map(metric => {
                    const widths = metric.values.map(v => v == null ? 0 : Math.max(3, Math.min(100, Math.abs(Number(v)) / metric.max * 100)));
                    const colors = [COLORS.target, COLORS.comparison, COLORS.alternate];
                    const tracks = trio.map((payload, idx) => {
                        const raw = metric.rawTips?.[idx];
                        const rawTip = raw !== null && raw !== undefined ? ` · raw ${fmt(raw, 0)}` : '';
                        const cls = idx === 0 ? ' main' : '';
                        return `<div class="sr-bar-track${cls}"><div class="sr-bar-fill" style="width:${widths[idx]}%; background:${colors[idx]};" data-tip="${esc(names[idx])} · ${esc(metric.fmt(metric.values[idx]))}${esc(rawTip)}"></div></div>`;
                    }).join('');
                    const valueText = metric.values.map((v, idx) => `${names[idx].split(' ').slice(-1)[0]} ${metric.fmt(v)}`).join(' · ');
                    const metricId = `gk-${group.label}-${metric.label}`.toLowerCase().replace(/[^a-z0-9]+/g, '-');
                    const mobileRows = trio.map((payload, idx) => {
                        const raw = metric.rawTips?.[idx];
                        const rawText = raw !== null && raw !== undefined ? `<span>Raw ${esc(fmt(raw, 0))}</span>` : '';
                        return `<div class="sr-gk-metric-player">
                            <span><i style="background:${colors[idx]}"></i>${esc(names[idx])}</span>
                            <strong>${esc(metric.fmt(metric.values[idx]))}</strong>
                            ${rawText}
                        </div>`;
                    }).join('');
                    return `<div class="sr-dot-row sr-dot-row-3 sr-gk-bars-desktop">
                        <div class="sr-dot-label">${esc(metric.label)}${metric.note ? `<span class="sr-bar-note">${esc(metric.note)}</span>` : ''}</div>
                        <div class="sr-bar-group">${tracks}</div>
                        <div class="sr-dot-val sr-dot-val-3">${esc(valueText)}</div>
                    </div>
                    <details class="sr-gk-metric-detail" id="${esc(metricId)}">
                        <summary>
                            <span class="sr-gk-metric-summary-label">${esc(metric.label)}${metric.note ? `<small>${esc(metric.note)}</small>` : ''}</span>
                            <span class="sr-gk-metric-summary-value">${esc(names[0].split(' ').slice(-1)[0])} ${esc(metric.fmt(metric.values[0]))}</span>
                        </summary>
                        <div class="sr-gk-metric-players">${mobileRows}</div>
                    </details>`;
                }).join('')}
            </div>`).join('')}`;
    }

    // ---- VISUAL SELECTOR: buttons ----

    function setupVisualSelector() {
        const container = $('gkVisualPlayerBtns');
        if (!container) return;
        const ordered = [targetPayload(), ...comparisonPayloads()].filter(Boolean);
        visualPlayerId = String(targetPayload()?.header?.player_id ?? ordered[0]?.header?.player_id ?? '');
        container.innerHTML = ordered.map(p => {
            const name = p.header?.player_name || '';
            const pid = String(p.header?.player_id ?? '');
            const color = name === reportContext.target_player_name ? COLORS.target
                : name === reportContext.primary_comparison_player ? COLORS.comparison
                : COLORS.alternate;
            const active = pid === visualPlayerId ? ' active' : '';
            return `<button class="sr-heatmap-btn${active}" data-player-id="${esc(pid)}"><span class="sr-heatmap-btn-dot" style="background:${color}"></span>${esc(name)}</button>`;
        }).join('');
        container.querySelectorAll('.sr-heatmap-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                container.querySelectorAll('.sr-heatmap-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                visualPlayerId = btn.dataset.playerId;
                renderVisuals();
            });
        });
    }

    function blockedState(block, label) {
        const missing = (block?.missing_fields || []).join(', ');
        return `<div class="sr-gk-empty"><strong>${esc(label)} ${visualPartial(block) ? 'parziale' : 'non disponibile'}</strong><span>${esc(block?.visual_status || 'blocked')}</span>${missing ? `<p>Campi mancanti: ${esc(missing)}</p>` : '<p>Il grafico non viene disegnato finché il payload non espone i campi necessari.</p>'}</div>`;
    }


    // ---- COMMON GK FIELD HEATMAP GRAMMAR ----

    function clamp(n, min, max) {
        return Math.max(min, Math.min(max, Number(n) || 0));
    }
    function heatRgba(rgb, intensity) {
        const alpha = clamp(intensity, 0.08, 0.76).toFixed(2);
        return `rgba(${rgb},${alpha})`;
    }
    function fieldFrame(inner, ariaLabel, opts = {}) {
        const defensiveOnly = Boolean(opts.defensiveOnly);
        const guides = defensiveOnly
            ? '<line class="pitch-guide" x1="58" y1="8" x2="58" y2="82"/>'
            : '<line class="pitch-guide" x1="48" y1="8" x2="48" y2="82"/><line class="pitch-guide" x1="92" y1="8" x2="92" y2="82"/>';
        return `<svg class="sr-gk-field-map sr-gk-field-map--horizontal" viewBox="0 0 140 90" role="img" aria-label="${esc(ariaLabel)}">
            <rect x="6" y="8" width="128" height="74" rx="3" fill="rgba(8,14,28,.72)" stroke="rgba(255,255,255,.10)" stroke-width=".7"/>
            ${guides}
            <rect class="pitch-line" x="6" y="23" width="30" height="44" rx="1.5"/>
            <rect class="pitch-line" x="6" y="33" width="12" height="24" rx="1"/>
            <rect x="3" y="38" width="3" height="14" fill="rgba(255,255,255,.38)" rx=".8"/>
            <path class="pitch-line" d="M36 34 Q46 45 36 56"/>
            ${inner}
        </svg>`;
    }
    function zoneRect(z, rgb) {
        const intensity = clamp(z.intensity, 0.08, 0.76);
        return `<rect x="${z.x}" y="${z.y}" width="${z.w}" height="${z.h}" rx="2" fill="${heatRgba(rgb, intensity)}" stroke="rgba(255,255,255,.14)" stroke-width=".45"/>
            <text x="${z.x + z.w / 2}" y="${z.y + z.h * 0.38}" text-anchor="middle" font-size="4.5" fill="rgba(255,255,255,.9)" font-weight="700">${esc(z.label)}</text>
            <text x="${z.x + z.w / 2}" y="${z.y + z.h * 0.64}" text-anchor="middle" font-size="3.8" fill="rgba(255,255,255,.7)">${esc(z.valueText || '—')}</text>
            ${z.subText ? `<text x="${z.x + z.w / 2}" y="${z.y + z.h * 0.82}" text-anchor="middle" font-size="3.2" fill="rgba(255,255,255,.48)">${esc(z.subText)}</text>` : ''}`;
    }
    function fieldLegend(color, label, extra = '') {
        return `<div class="sr-gk-field-legend"><span><i class="sr-gk-field-dot" style="background:${color}"></i>${esc(label)}</span>${extra}</div>`;
    }

    // ---- POSITIONAL HEATMAP GRAMMAR (mplsoccer-inspired, horizontal) ----
    // Zones ARE the pitch: colored rects fill the field area, pitch lines
    // and scatter dots are drawn on top — matching bin_statistic_positional
    // + heatmap_positional + scatter grammar but rotated to horizontal.

    const SVG_VW = 140, SVG_VH = 90;
    const FX0_H = 6, FY0_H = 8, FPW_H = 128, FPH_H = 74;
    const FM_W_H = 105, FM_H_H = 68;
    function fX(m) { return FX0_H + (m / FM_W_H) * FPW_H; }
    function fY(m) { return FY0_H + (m / FM_H_H) * FPH_H; }
    function fXd(m) { return FX0_H + (m / 52.5) * FPW_H; } // defensive half: 0-52.5m fills full width
    function lerp2(a, b, t) { return a + (b - a) * Math.max(0, Math.min(1, t)); }
    function zoneColor(t, scheme) {
        const P = {
            green: [[10,18,32,0.94],[18,58,48,0.88],[40,138,80,0.86],[66,208,116,0.92]],
            blue:  [[10,18,32,0.94],[18,38,96,0.88],[48,98,190,0.86],[86,152,244,0.92]],
        };
        const pal = P[scheme] || P.green;
        const idx = Math.max(0, Math.min(1, t)) * (pal.length - 1);
        const i = Math.min(Math.floor(idx), pal.length - 2);
        const f = idx - i;
        const [r0, g0, b0, a0] = pal[i], [r1, g1, b1, a1] = pal[i + 1];
        return `rgba(${Math.round(lerp2(r0,r1,f))},${Math.round(lerp2(g0,g1,f))},${Math.round(lerp2(b0,b1,f))},${lerp2(a0,a1,f).toFixed(2)})`;
    }
    function qualityColor(compl) {
        // Completion quality tuned for GK distribution: <60 red, 60-85 amber, >85 green.
        // This avoids painting long/far zones as elite when completion is merely moderate.
        if (compl == null) return 'rgba(30,40,60,0.88)';
        const t = Math.max(0, Math.min(1, Number(compl)));
        let r, g, b;
        if (t < 0.6) {
            const f = t / 0.6;
            r = Math.round(lerp2(248, 239, f)); g = Math.round(lerp2(80, 120, f)); b = Math.round(lerp2(80, 42, f));
        } else if (t < 0.85) {
            const f = (t - 0.6) / 0.25;
            r = Math.round(lerp2(239, 251, f)); g = Math.round(lerp2(120, 191, f)); b = Math.round(lerp2(42, 36, f));
        } else {
            const f = (t - 0.85) / 0.15;
            r = Math.round(lerp2(251, 74, f)); g = Math.round(lerp2(191, 222, f)); b = Math.round(lerp2(36, 128, f));
        }
        return `rgba(${r},${g},${b},0.84)`;
    }
    function pitchLines(defensiveOnly) {
        const f0 = FX0_H, f1 = FX0_H + FPW_H;
        let s = `<rect x="${f0}" y="${FY0_H}" width="${FPW_H}" height="${FPH_H}" fill="none" stroke="rgba(255,255,255,.32)" stroke-width=".9"/>`;
        s += `<rect x="${f0}" y="${fY(13.84).toFixed(1)}" width="${(fX(16.5)-f0).toFixed(1)}" height="${(fY(54.16)-fY(13.84)).toFixed(1)}" fill="none" stroke="rgba(255,255,255,.26)" stroke-width=".7"/>`;
        s += `<rect x="${f0}" y="${fY(24.84).toFixed(1)}" width="${(fX(5.5)-f0).toFixed(1)}" height="${(fY(43.16)-fY(24.84)).toFixed(1)}" fill="none" stroke="rgba(255,255,255,.16)" stroke-width=".45"/>`;
        s += `<rect x="${(f0-3).toFixed(1)}" y="${fY(30.34).toFixed(1)}" width="3" height="${(fY(37.66)-fY(30.34)).toFixed(1)}" fill="none" stroke="rgba(255,255,255,.4)" stroke-width=".7"/>`;
        s += `<path d="M${fX(16.5).toFixed(1)} ${fY(26).toFixed(1)} Q${fX(24).toFixed(1)} ${fY(34).toFixed(1)} ${fX(16.5).toFixed(1)} ${fY(42).toFixed(1)}" fill="none" stroke="rgba(255,255,255,.16)" stroke-width=".55"/>`;
        if (!defensiveOnly) {
            s += `<line x1="${fX(52.5).toFixed(1)}" y1="${FY0_H}" x2="${fX(52.5).toFixed(1)}" y2="${FY0_H+FPH_H}" stroke="rgba(255,255,255,.22)" stroke-width=".65"/>`;
            s += `<circle cx="${fX(52.5).toFixed(1)}" cy="${fY(34).toFixed(1)}" r="${((9.15/FM_W_H)*FPW_H).toFixed(1)}" fill="none" stroke="rgba(255,255,255,.18)" stroke-width=".6"/>`;
            s += `<circle cx="${fX(52.5).toFixed(1)}" cy="${fY(34).toFixed(1)}" r="1.2" fill="rgba(255,255,255,.22)"/>`;
            s += `<rect x="${fX(88.5).toFixed(1)}" y="${fY(13.84).toFixed(1)}" width="${(f1-fX(88.5)).toFixed(1)}" height="${(fY(54.16)-fY(13.84)).toFixed(1)}" fill="none" stroke="rgba(255,255,255,.26)" stroke-width=".7"/>`;
            s += `<rect x="${fX(99.5).toFixed(1)}" y="${fY(24.84).toFixed(1)}" width="${(f1-fX(99.5)).toFixed(1)}" height="${(fY(43.16)-fY(24.84)).toFixed(1)}" fill="none" stroke="rgba(255,255,255,.16)" stroke-width=".45"/>`;
            s += `<rect x="${f1.toFixed(1)}" y="${fY(30.34).toFixed(1)}" width="3" height="${(fY(37.66)-fY(30.34)).toFixed(1)}" fill="none" stroke="rgba(255,255,255,.4)" stroke-width=".7"/>`;
            s += `<path d="M${fX(88.5).toFixed(1)} ${fY(26).toFixed(1)} Q${fX(81).toFixed(1)} ${fY(34).toFixed(1)} ${fX(88.5).toFixed(1)} ${fY(42).toFixed(1)}" fill="none" stroke="rgba(255,255,255,.16)" stroke-width=".55"/>`;
        }
        return s;
    }
    // Defensive-half pitch lines where fXd maps 0..52.5m to full SVG width.
    // The outer border's right edge acts as the center-line boundary.
    function pitchLinesDefHalf() {
        const f0 = FX0_H;
        let s = `<rect x="${f0}" y="${FY0_H}" width="${FPW_H}" height="${FPH_H}" fill="none" stroke="rgba(255,255,255,.32)" stroke-width=".9"/>`;
        s += `<rect x="${f0}" y="${fY(13.84).toFixed(1)}" width="${(fXd(16.5)-f0).toFixed(1)}" height="${(fY(54.16)-fY(13.84)).toFixed(1)}" fill="none" stroke="rgba(255,255,255,.26)" stroke-width=".7"/>`;
        s += `<rect x="${f0}" y="${fY(24.84).toFixed(1)}" width="${(fXd(5.5)-f0).toFixed(1)}" height="${(fY(43.16)-fY(24.84)).toFixed(1)}" fill="none" stroke="rgba(255,255,255,.16)" stroke-width=".45"/>`;
        s += `<rect x="${(f0-3).toFixed(1)}" y="${fY(30.34).toFixed(1)}" width="3" height="${(fY(37.66)-fY(30.34)).toFixed(1)}" fill="rgba(255,255,255,.38)" rx=".8"/>`;
        s += `<path d="M${fXd(16.5).toFixed(1)} ${fY(26).toFixed(1)} Q${fXd(24).toFixed(1)} ${fY(34).toFixed(1)} ${fXd(16.5).toFixed(1)} ${fY(42).toFixed(1)}" fill="none" stroke="rgba(255,255,255,.16)" stroke-width=".55"/>`;
        return s;
    }
    // Defensive-half SVG: zones and dots use fXd (0..52.5m fills full width).
    // zones: [{x1m,y1m,x2m,y2m,color,label,sub}]  dots: [{xm,ym,color,r}]
    function pitchDefHalfSvg(zones, dots, ariaLabel) {
        const rects = (zones || []).map(z => {
            const x = fXd(z.x1m), y = fY(z.y1m);
            const w = Math.max(0, fXd(z.x2m) - x), h = Math.max(0, fY(z.y2m) - y);
            const mx = (x + w / 2).toFixed(1), myMid = y + h / 2;
            const mainY = (z.sub ? myMid - 2.4 : myMid).toFixed(1);
            const subY  = (myMid + 3.2).toFixed(1);
            const ts = 'style="paint-order:stroke;stroke:rgba(0,0,0,.72);stroke-width:2px;stroke-linejoin:round;"';
            const ts2 = 'style="paint-order:stroke;stroke:rgba(0,0,0,.6);stroke-width:1.2px;"';
            return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" fill="${z.color}"/>`
                + (z.label ? `<text x="${mx}" y="${mainY}" text-anchor="middle" dominant-baseline="middle" font-size="5.4" fill="rgba(255,255,255,.94)" font-weight="700" ${ts}>${esc(z.label)}</text>` : '')
                + (z.sub ? `<text x="${mx}" y="${subY}" text-anchor="middle" dominant-baseline="middle" font-size="3.5" fill="rgba(255,255,255,.6)" ${ts2}>${esc(z.sub)}</text>` : '');
        }).join('');
        const scatter = (dots || []).map(d => {
            const px = fXd(clamp(d.xm, 0, 52.5)).toFixed(1);
            const py = fY(clamp(d.ym, 0, FM_H_H)).toFixed(1);
            return `<circle cx="${px}" cy="${py}" r="${d.r || 1.2}" fill="${d.color || 'rgba(255,255,255,.55)'}" stroke="rgba(0,0,0,.3)" stroke-width=".25"/>`;
        }).join('');
        return `<svg class="sr-gk-field-map sr-gk-field-map--horizontal" viewBox="0 0 ${SVG_VW} ${SVG_VH}" role="img" aria-label="${esc(ariaLabel)}">
    <rect x="${FX0_H}" y="${FY0_H}" width="${FPW_H}" height="${FPH_H}" fill="rgba(8,14,28,.96)"/>
    ${rects}${pitchLinesDefHalf()}${scatter}</svg>`;
    }
    // zones: [{x1m,y1m,x2m,y2m,color,label,sub}]
    // dots:  [{xm,ym,color,r}] or null
    function pitchHeatmapSvg(zones, dots, ariaLabel, opts) {
        opts = opts || {};
        const rects = (zones || []).map(z => {
            const x = fX(z.x1m), y = fY(z.y1m);
            const w = Math.max(0, fX(z.x2m) - x), h = Math.max(0, fY(z.y2m) - y);
            const mx = (x + w / 2).toFixed(1), myMid = y + h / 2;
            const mainY = (z.sub ? myMid - 2.4 : myMid).toFixed(1);
            const subY  = (myMid + 3.2).toFixed(1);
            const ts = 'style="paint-order:stroke;stroke:rgba(0,0,0,.72);stroke-width:2px;stroke-linejoin:round;"';
            const ts2 = 'style="paint-order:stroke;stroke:rgba(0,0,0,.6);stroke-width:1.2px;"';
            return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" fill="${z.color}"/>`
                + (z.label ? `<text x="${mx}" y="${mainY}" text-anchor="middle" dominant-baseline="middle" font-size="5.4" fill="rgba(255,255,255,.94)" font-weight="700" ${ts}>${esc(z.label)}</text>` : '')
                + (z.sub ? `<text x="${mx}" y="${subY}" text-anchor="middle" dominant-baseline="middle" font-size="3.5" fill="rgba(255,255,255,.6)" ${ts2}>${esc(z.sub)}</text>` : '');
        }).join('');
        const scatter = (dots || []).map(d => {
            const px = fX(clamp(d.xm, 0, FM_W_H)).toFixed(1);
            const py = fY(clamp(d.ym, 0, FM_H_H)).toFixed(1);
            return `<circle cx="${px}" cy="${py}" r="${d.r || 1.2}" fill="${d.color || 'rgba(255,255,255,.55)'}" stroke="rgba(0,0,0,.3)" stroke-width=".25"/>`;
        }).join('');
        return `<svg class="sr-gk-field-map sr-gk-field-map--horizontal" viewBox="0 0 ${SVG_VW} ${SVG_VH}" role="img" aria-label="${esc(ariaLabel)}">
    <rect x="${FX0_H}" y="${FY0_H}" width="${FPW_H}" height="${FPH_H}" fill="rgba(8,14,28,.96)"/>
    ${rects}${pitchLines(Boolean(opts.defensiveOnly))}${scatter}</svg>`;
    }

    // ---- GOAL MAP: SVG porta 3x3 ----

    function renderGoalMap(payload) {
        const el = $('gkGoalMap');
        const block = payload.visual_blocks?.goal_map_save_map;
        if (!el) return;
        if (!visualReady(block)) { el.innerHTML = blockedState(block, 'Goal map'); return; }

        const POST = 5, CB = 5, W = 180, H = 108, CW = W / 3, CH = H / 3;
        const SW = W + POST * 2, SH = H + CB + 10;

        const cells = GOAL_ZONE_ROWS.map((row, ri) => row.map((zid, ci) => {
            const z = block.zones?.[zid] || {};
            const sot = z.shots_on_target_faced ?? null;
            const goals = z.goals_conceded ?? null;
            const saves = z.saves ?? null;
            const sp = z.save_pct != null ? `${(z.save_pct * 100).toFixed(0)}%` : null;
            const danger = (sot > 0 && goals != null) ? goals / sot : 0;
            const fill = danger > 0.4
                ? `rgba(248,113,113,${(0.18 + danger * 0.42).toFixed(2)})`
                : danger > 0.1
                    ? `rgba(251,191,36,${(0.1 + danger * 0.35).toFixed(2)})`
                    : 'rgba(74,222,128,0.07)';
            const cx = POST + ci * CW, cy = CB + ri * CH;
            const mid = cx + CW / 2;
            return `<rect x="${cx.toFixed(1)}" y="${cy.toFixed(1)}" width="${CW.toFixed(1)}" height="${CH.toFixed(1)}" fill="${fill}" stroke="rgba(255,255,255,0.15)" stroke-width="0.6"/>`
                + (sot != null ? `<text x="${mid.toFixed(1)}" y="${(cy + CH * 0.24).toFixed(1)}" text-anchor="middle" font-size="5.5" fill="rgba(255,255,255,.44)">${sot} SOT</text>` : '')
                + (saves != null && goals != null ? `<text x="${mid.toFixed(1)}" y="${(cy + CH * 0.52).toFixed(1)}" text-anchor="middle" font-size="6.2" fill="#b9f7d8" font-weight="600">${saves}↑ ${goals}⚽</text>` : '')
                + (sp ? `<text x="${mid.toFixed(1)}" y="${(cy + CH * 0.8).toFixed(1)}" text-anchor="middle" font-size="7.5" fill="#fde68a" font-weight="700">${sp}</text>` : '');
        }).flat().join(''));

        el.innerHTML = `<div style="background:#080e1c;border:1px solid rgba(255,255,255,.07);border-radius:.75rem;padding:.5rem .5rem .3rem;margin-bottom:.35rem;"><svg viewBox="0 0 ${SW} ${SH}" style="width:100%;max-height:210px;display:block;margin:0 auto;" role="img" aria-label="Goal map a zone">
  <rect x="${POST}" y="${CB}" width="${W}" height="${H}" fill="rgba(8,14,28,.75)" rx="1"/>
  ${cells}
  <line x1="${POST}" y1="${(CB + CH).toFixed(1)}" x2="${POST + W}" y2="${(CB + CH).toFixed(1)}" stroke="rgba(255,255,255,.22)" stroke-width=".7"/>
  <line x1="${POST}" y1="${(CB + CH * 2).toFixed(1)}" x2="${POST + W}" y2="${(CB + CH * 2).toFixed(1)}" stroke="rgba(255,255,255,.22)" stroke-width=".7"/>
  <line x1="${(POST + CW).toFixed(1)}" y1="${CB}" x2="${(POST + CW).toFixed(1)}" y2="${CB + H}" stroke="rgba(255,255,255,.22)" stroke-width=".7"/>
  <line x1="${(POST + CW * 2).toFixed(1)}" y1="${CB}" x2="${(POST + CW * 2).toFixed(1)}" y2="${CB + H}" stroke="rgba(255,255,255,.22)" stroke-width=".7"/>
  <rect x="0" y="${CB}" width="${POST}" height="${H + 6}" fill="#c9cdd4" rx="1"/>
  <rect x="${POST + W}" y="${CB}" width="${POST}" height="${H + 6}" fill="#c9cdd4" rx="1"/>
  <rect x="0" y="0" width="${SW}" height="${CB}" fill="#c9cdd4" rx="1"/>
  <line x1="0" y1="${CB + H + 6}" x2="${SW}" y2="${CB + H + 6}" stroke="#d1d5db" stroke-width="2.5"/>
</svg></div>
<div style="display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.35rem;font-size:.59rem;color:rgba(255,255,255,.36);">
  <span style="display:flex;align-items:center;gap:.22rem;"><span style="width:8px;height:8px;border-radius:2px;background:rgba(74,222,128,.45);display:inline-block;"></span>Alta % parate</span>
  <span style="display:flex;align-items:center;gap:.22rem;"><span style="width:8px;height:8px;border-radius:2px;background:rgba(251,191,36,.5);display:inline-block;"></span>Media</span>
  <span style="display:flex;align-items:center;gap:.22rem;"><span style="width:8px;height:8px;border-radius:2px;background:rgba(248,113,113,.6);display:inline-block;"></span>Bassa % parate</span>
</div>
<p class="sr-pitch-note" style="margin-top:.3rem">${esc(payload.header?.player_name)} · ${fmt(block.total_on_target, 0)} tiri in porta · Zone prototipali.</p>`;
    }

    // ---- SWEEPER MAP: coordinate normalization ----
    // Backend normalizes coordinates when coordinate_normalization_status is
    // "backend_normalized_heuristic". For older payloads without this field,
    // the frontend heuristic (52.5 mirror) applies as fallback.

    function renderSweeperMap(payload) {
        const el = $('gkSweeperMap');
        const block = payload.visual_blocks?.sweeper_actions_map;
        if (!el) return;
        if (!visualReady(block) && !visualPartial(block)) { el.innerHTML = blockedState(block, 'Sweeper map'); return; }

        const backendNormalized = block?.coordinate_normalization_status === 'backend_normalized_heuristic';
        const rawCoords = block.coordinates_sample || [];
        const normalized = rawCoords.map(ev => {
            let x = Number(ev.x), y = Number(ev.y);
            if (!backendNormalized && x > 52.5) { x = 105 - x; y = 68 - y; }
            return { ...ev, x_norm: clamp(x, 0, 52.5), y_norm: clamp(y, 0, 68) };
        }).slice(0, 140);
        const dots = normalized.map(ev => {
            const inBox = ev.x_norm <= 16.5 && ev.y_norm >= 13.84 && ev.y_norm <= 54.16;
            return {
                xm: ev.x_norm,
                ym: ev.y_norm,
                color: inBox ? 'rgba(96,165,250,0.58)' : 'rgba(251,191,36,0.88)',
                r: inBox ? 1.2 : 1.55,
            };
        });
        const normNote = backendNormalized
            ? '<div class="sr-gk-coord-note">Coordinate normalizzate nel backend (euristica). Visualizzazione prototipale.</div>'
            : '<div class="sr-gk-coord-note">Coordinate normalizzate tramite euristica visuale; da consolidare nel backend.</div>';

        el.innerHTML = `${normNote}
${pitchDefHalfSvg([], dots, 'Mappa orizzontale sweeper e copertura profondità GK')}
<div class="sr-gk-field-legend" style="display:flex;gap:.8rem;flex-wrap:wrap;" aria-label="Interventi sweeper / copertura profondità">
  <span><i class="sr-gk-field-dot" style="background:rgba(251,191,36,.9)"></i>Fuori area (sweeper)</span>
  <span><i class="sr-gk-field-dot" style="background:rgba(96,165,250,.7)"></i>In area / area di rigore</span>
</div>
<div class="sr-gk-stat-grid"><span><b>${fmt(block.event_count, 0)}</b> eventi tot.</span><span><b>${fmt(block.event_count_per90)}</b> p90</span><span><b>${fmt(block.outside_box_count, 0)}</b> fuori area</span><span><b>${pct(block.outside_box_share)}</b> quota fuori area</span></div>
<p class="sr-pitch-note" style="margin-top:.35rem;">Dove il portiere esce o copre la profondità. L’area disegnata usa la stessa scala metrica dei punti.</p>`;
    }

    // ---- DISTRIBUTION DESTINATION HEATMAP: full-pitch 3×3 positional ----
    // Zones tile the entire 105×68 field (destination_depth × destination_lanes).
    // Color intensity = estimated share toward that zone; label = completion %.
    // Pitch lines are drawn on top of the colored cells (mplsoccer grammar).

    function renderDistribution(payload) {
        const el = $('gkDistribution');
        const block = payload.visual_blocks?.distribution_profile;
        if (!el) return;
        if (!visualReady(block) && !visualPartial(block)) { el.innerHTML = blockedState(block, 'Distribution profile'); return; }

        const m = block.season_metrics || {};
        const depth = block.destination_depth || {};
        const lanes = block.destination_lanes || {};

        const DEPTHS = [
            { key: 'own_third',    x1: 0,  x2: 35,  shortLabel: 'Bassa' },
            { key: 'middle_third', x1: 35, x2: 70,  shortLabel: 'Media' },
            { key: 'final_third',  x1: 70, x2: 105, shortLabel: 'Alta'  },
        ];
        const LANES = [
            { key: 'left',   y1: 0,     y2: 22.67 },
            { key: 'center', y1: 22.67, y2: 45.33 },
            { key: 'right',  y1: 45.33, y2: 68    },
        ];

        const grid = block.destination_grid || {};
        const hasJointGrid = Object.keys(grid).length > 0;
        const totalAttempts = block.event_count || Object.values(grid).reduce((sum, item) => sum + (Number(item.attempts) || 0), 0) || Object.values(depth).reduce((sum, item) => sum + (Number(item.attempts) || 0), 0) || 1;
        const cells = DEPTHS.flatMap(d => LANES.map(l => {
            const joint = grid[`${d.key}__${l.key}`];
            if (joint) {
                return { d, l, attempts: Number(joint.attempts) || 0, share: Number(joint.share_of_attempts) || 0, compl: joint.completion_pct };
            }
            const ds = Number(depth[d.key]?.share_of_attempts) || 0;
            const ls = Number(lanes[l.key]?.share_of_attempts) || 0;
            const dc = depth[d.key]?.completion_pct, lc = lanes[l.key]?.completion_pct;
            const compl = (dc != null && lc != null) ? (Number(dc) + Number(lc)) / 2 : null;
            const share = ds * ls;
            return { d, l, attempts: Math.round(totalAttempts * share), share, compl };
        }));
        const maxShare = Math.max(...cells.map(c => c.share), 0.001);

        const zoneRects = cells.map(({ d, l, share, compl, attempts }) => ({
            x1m: d.x1, x2m: d.x2, y1m: l.y1, y2m: l.y2,
            color: zoneColor(share / maxShare, 'green'),
            label: attempts > 0 ? `${attempts}` : '—',
            sub: compl != null ? `(${pct(compl)})` : null,
        }));

        const dataSourceLabel = hasJointGrid ? 'Griglia reale profondità × corsia' : 'Fallback da bucket marginali aggregati';
        el.innerHTML = `${pitchHeatmapSvg(zoneRects, null, 'Heatmap orizzontale destinazione distribuzione portiere')}
${fieldLegend('rgba(66,208,116,.88)', 'Numero = passaggi tentati · parentesi = % riuscita · Colore = quota tentativi nella cella', `<span>${dataSourceLabel}</span>`)}
<div class="sr-gk-stat-grid" style="margin-top:.6rem;">
    <span><b>${fmt(m.pass_attempts_per90)}</b> pass p90</span>
    <span><b>${pct(m.pass_completion_pct)}</b> compl.</span>
    <span><b>${pct(m.short_pass_share)}</b> corto share</span>
    <span><b>${pct(m.long_pass_share)}</b> lungo share</span>
</div>
<p class="sr-pitch-note" style="margin-top:.35rem;">Dove terminano i passaggi del portiere. Distribuzione rappresentata per zone aggregate.</p>`;
    }

    // ---- BUILD-UP INVOLVEMENT HEATMAP: positional zones + scatter ----
    // Zones tile the defensive half (build_up_map block); attacking half muted.
    // Scatter dots from sweeper coordinates_sample sit on top of zone colors.
    // Pitch lines are drawn between zones and dots (mplsoccer grammar).

    function renderBuildUpMap(payload) {
        const el = $('gkBuildUpMap');
        if (!el) return;

        const buBlock  = payload.visual_blocks?.build_up_map;
        const distBlock = payload.visual_blocks?.distribution_profile;
        const distMetrics = distBlock?.season_metrics || {};
        const hasBu = visualReady(buBlock) || visualPartial(buBlock);

        if (!hasBu && (!distBlock || (!visualReady(distBlock) && !visualPartial(distBlock)))) {
            el.innerHTML = blockedState(buBlock || distBlock, 'Build-up involvement');
            return;
        }

        const BU_ZONES = [
            { id: 'in_box',        x1:  0,    x2: 16.5, y1: 13.84, y2: 54.16, label: 'Area' },
            { id: 'left_corridor', x1: 16.5,  x2: 52.5, y1:  0,    y2: 22.67, label: 'Sx' },
            { id: 'limite',        x1: 16.5,  x2: 30,   y1: 22.67, y2: 45.33, label: 'Limite' },
            { id: 'deep_center',   x1: 30,    x2: 52.5, y1: 22.67, y2: 45.33, label: 'Centro' },
            { id: 'right_corridor',x1: 16.5,  x2: 52.5, y1: 45.33, y2: 68,    label: 'Dx' },
        ];

        let zoneData = {}, maxP90 = 0.01;
        if (hasBu && buBlock.zones) {
            zoneData = buBlock.zones;
            maxP90 = Math.max(...Object.values(zoneData).map(z => Number(z.event_count_per90) || 0), 0.01);
        } else {
            const passesP90 = distMetric(payload, 'pass_attempts_per90') ?? per90FromTotal(payload, 'passes_attempted') ?? 0;
            const shortShare = distMetric(payload, 'short_pass_share') ?? shareValue(payload, 'short_passes') ?? 0;
            const lns = distBlock?.destination_lanes || {};
            zoneData = {
                in_box:        { event_count_per90: passesP90 * shortShare, event_count: null },
                left_corridor: { event_count_per90: passesP90 * (lns.left?.share_of_attempts ?? 0), event_count: null },
                right_corridor:{ event_count_per90: passesP90 * (lns.right?.share_of_attempts ?? 0), event_count: null },
                limite:        { event_count_per90: distMetric(payload,'progressive_passes_per90') ?? per90FromTotal(payload,'progressive_passes') ?? 0, event_count: null },
                deep_center:   { event_count_per90: passesP90 * (lns.center?.share_of_attempts ?? 0) * 0.4, event_count: null },
            };
            maxP90 = Math.max(...Object.values(zoneData).map(z => Number(z.event_count_per90) || 0), 0.01);
        }

        const zoneRects = BU_ZONES.map(z => {
            const d = zoneData[z.id] || {};
            const p90 = Number(d.event_count_per90) || 0;
            const t = p90 / maxP90;
            return {
                x1m: z.x1, x2m: z.x2, y1m: z.y1, y2m: z.y2,
                color: zoneColor(t, 'blue'),
                label: z.label,
                sub: p90 > 0 ? `${fmt(p90)} p90` : '—',
            };
        });

        const statGrid = hasBu && buBlock.zones
            ? `<span><b>${fmt(buBlock.total_events, 0)}</b> eventi</span><span><b>${fmt(buBlock.zones?.in_box?.event_count_per90)}</b> area p90</span><span><b>${fmt(buBlock.zones?.limite?.event_count_per90)}</b> limite p90</span><span><b>${pct(distMetrics.pass_completion_pct)}</b> compl. pass</span>`
            : `<span><b>${fmt(distMetric(payload,'pass_attempts_per90') ?? 0)}</b> pass p90</span><span><b>${pct(distMetrics.pass_completion_pct)}</b> compl.</span><span><b>—</b></span><span><b>—</b></span>`;

        el.innerHTML = `${pitchDefHalfSvg(zoneRects, [], 'Heatmap orizzontale coinvolgimento costruzione portiere')}
${fieldLegend('rgba(86,152,244,.88)', 'Intensità = volume coinvolgimento in zona', '<span>Fonte: proxy da start/touch non governati; zone difensive riempiono tutto il campo visuale</span>')}
<div class="sr-gk-stat-grid" style="margin-top:.6rem;">${statGrid}</div>
<p class="sr-pitch-note" style="margin-top:.35rem;">Dove il portiere partecipa con il pallone, non dove termina il passaggio. Coinvolgimento rappresentato per zone disponibili.</p>`;
    }

    function renderVisuals() {
        const payload = visualPayload();
        renderGoalMap(payload);
        renderSweeperMap(payload);
        renderDistribution(payload);
        renderBuildUpMap(payload);
    }

    function renderMethodology() {
        const el = $('gkMethodology');
        if (!el) return;
        el.innerHTML = `<p class="sr-narrative">Questa pagina confronta Vicario con la stanza portieri dell’Inter. Martínez è incluso come riferimento interno anche se il campione è ridotto; questa inclusione non modifica i benchmark ufficiali. La V1 GK non usa una sezione di similarità.</p><div class="sr-footnotes"><span class="sr-footnote-chip">Fonte: SoccerDB role artifacts</span><span class="sr-footnote-chip">Ruolo: GK</span><span class="sr-footnote-chip">Radar GK a 4 assi</span><span class="sr-footnote-chip">Benchmark ufficiali invariati</span><span class="sr-footnote-chip">Visual geometry: ${esc(summaryEnvelope.metadata?.visual_geometry_status || 'prototype')}</span><span class="sr-footnote-chip">Source freshness: ${esc(summaryEnvelope.metadata?.source_freshness_status || 'mixed')}</span></div>`;
    }

    function renderAll() {
        if (!targetPayload()) return;
        renderHeader();
        setupRadarSelector();
        setupVisualSelector();
        renderRadar();
        renderBars();
        renderVisuals();
        renderMethodology();
    }

    if (!players.length) {
        const main = $('gkHeader');
        if (main) main.innerHTML = '<div class="sr-gk-empty">Nessun payload GK disponibile.</div>';
        return;
    }
    renderAll();
}

// Sprint 4C: if SR_GK_PAYLOAD_READY is set (external loader present), wait for
// it before rendering.  Otherwise render immediately from inline globals.
if (window.SR_GK_PAYLOAD_READY && typeof window.SR_GK_PAYLOAD_READY.then === "function") {
    window.SR_GK_PAYLOAD_READY.then(initGkReport);
} else {
    initGkReport();
}
