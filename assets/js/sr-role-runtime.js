// sr-role-runtime.js
// Role-aware HTML scouting report runtime. Data comes from the inline DATA block.

function initRoleReport() {
    function readGlobal(name, fallback) {
        try {
            return Function("fallback", `return typeof ${name} !== "undefined" ? ${name} : fallback;`)(fallback);
        } catch (_err) {
            return fallback;
        }
    }

    // ── Sprint 6E: CSS variable reader ───────────────────────────────────────
    // Reads a CSS custom property from :root. Returns fallback when absent.
    // Used by radarPalette below — harmless when no theme variables are defined.
    function getCssVar(name, fallback) {
        try {
            const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
            return v || fallback;
        } catch (_) {
            return fallback;
        }
    }

    const subjectId = readGlobal("SUBJECT_ID", null);
    const roleMeta = readGlobal("ROLE_META", { role: "", label: "" });
    const pageMeta = readGlobal("PAGE_META", {});
    const playerMeta = readGlobal("PLAYER_META", {});
    const profileReading = readGlobal("PROFILE_READING", {});
    const comparisonGroups = readGlobal("COMPARISON_GROUPS", []);
    const radarAxes = readGlobal("RADAR_AXES", []);
    const radarData = readGlobal("RADAR_DATA", {});
    const metricFormats = readGlobal("METRIC_FORMATS", {});
    const targetBars = readGlobal("TARGET_COMPARISON_BARS", null);
    const sourceBars = readGlobal("SOURCE_TEAM_COMPARISON_BARS", null);
    const heatmapData = readGlobal("HEATMAP_DATA", {});
    const similarityData = readGlobal("SIMILARITY_DATA", []);
    const footnotes = readGlobal("FOOTNOTES", []);
    const metrics = readGlobal("METRICS", {});
    const metricRanges = readGlobal("METRIC_RANGES", {});

    const SVG_W = 360, SVG_H = 240, GRID_X = 12, GRID_Y = 8;
    const PITCH_L = 105.0, PITCH_W = 68.0;
    const SVG_CW = SVG_W / GRID_X, SVG_CH = SVG_H / GRID_Y;
    const CELL_W_M = PITCH_L / GRID_X, CELL_H_M = PITCH_W / GRID_Y;
    const M_TO_PX = SVG_W / PITCH_L;
    const NS = "http://www.w3.org/2000/svg";

    function $(id) { return document.getElementById(id); }
    function meta(id) { return playerMeta[String(id)] || playerMeta[id] || {}; }
    function esc(value) {
        return String(value ?? "").replace(/[&<>"']/g, ch => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
        }[ch]));
    }
    function fmt(metric, value) {
        if (value === null || value === undefined || Number.isNaN(value)) return "—";
        const globalFmt = readGlobal("fmt", null);
        if (typeof globalFmt === "function") return globalFmt(metric, value);
        const kind = metricFormats[metric] || "number";
        if (kind === "percent") return (value * 100).toFixed(1) + "%";
        if (kind === "meters") return value.toFixed(1) + " m";
        if (kind === "one_decimal") return value.toFixed(1);
        return value.toFixed(2);
    }
    function svgEl(tag, attrs) {
        const el = document.createElementNS(NS, tag);
        Object.entries(attrs || {}).forEach(([key, value]) => el.setAttribute(key, value));
        return el;
    }
    function svgTip(el, text) {
        const title = document.createElementNS(NS, "title");
        title.textContent = text;
        el.appendChild(title);
        return el;
    }
    function pitchGridY(iy) {
        return GRID_Y - 1 - iy;
    }
    function pitchDy(dy) {
        return -dy;
    }

    function renderHeader() {
        const el = $("roleReportHeader");
        if (!el) return;
        if (el.dataset.static === "true") return;
        const p = meta(subjectId);
        const chips = [
            p.competition,
            p.season ? `Stagione ${p.season}` : "",
            p.mins ? `${Number(p.mins).toLocaleString("it-IT")} minuti` : "",
            pageMeta.templateVersion,
        ].filter(Boolean);
        el.innerHTML = `
            <div class="sr-header-top">
                <div class="sr-header-left">
                    <div class="sr-player-photo"><div class="sr-photo-placeholder">${(p.name || "?").slice(0, 1)}</div></div>
                    <div>
                        <h2 class="sr-player-name">${esc(p.name || pageMeta.title || "Player report")}</h2>
                        <span class="sr-clubs-line">${esc(p.team || "")} · ${esc(pageMeta.subtitle || "")}</span>
                    </div>
                </div>
                <span class="sr-role-pill">${esc(roleMeta.label || roleMeta.role)} · ${esc(roleMeta.role || "")}</span>
            </div>
            <div class="sr-meta-row">
                ${chips.map(chip => `<span class="sr-meta-chip">${esc(chip)}</span>`).join("")}
            </div>
        `;
    }

    function renderProfileReading() {
        const el = $("profileReading");
        if (!el) return;
        if (el.dataset.static === "true") return;
        const title = profileReading.title || "Lettura del profilo";
        const paragraphs = profileReading.paragraphs || [];
        el.innerHTML = `
            <p class="sr-section-label">${esc(title)}</p>
            ${paragraphs.map(text => `<p class="sr-narrative">${esc(text)}</p>`).join("")}
        `;
    }

    function renderRadar() {
        // ── axis guide (accordion content) ──────────────────────────────────
        const guide = $("radarAxisGuide");
        if (guide) {
            guide.innerHTML = radarAxes.map(axis => {
                const metricList = (axis.metrics || []).join(" · ");
                const isDefensive = axis.key === "defensive_contribution";
                const caveat = isDefensive
                    ? `<em class="sr-axis-caveat">Misura presenza e coinvolgimento nei duelli; non è un punteggio puro di qualità difensiva.</em>`
                    : "";
                return `
                    <li class="sr-axis-card">
                        <strong>${esc(axis.label || axis.key)}</strong>
                        <span>${esc(axis.description || "")}</span>
                        ${metricList ? `<span class="sr-axis-metrics">${esc(metricList)}</span>` : ""}
                        ${caveat}
                    </li>
                `;
            }).join("");
        }

        const canvas = $("radarChart");
        if (!canvas || typeof Chart === "undefined" || !radarAxes.length) return;

        const ctx = canvas.getContext("2d");
        const p = meta(subjectId);
        const subjectColor = p.color || "#4ade80";

        // ── Sprint 6E: theme-aware radar palette ─────────────────────────────
        // getCssVar reads CSS custom properties when a theme defines them.
        // Fallback values exactly match prior hardcoded production values,
        // so live pages without theme variables are visually unchanged.
        const radarPalette = {
            subjectBorder: getCssVar("--sr-radar-subject-border", subjectColor),
            subjectFill:   getCssVar("--sr-radar-subject-fill",   subjectColor + "30"),
            compBorder:    getCssVar("--sr-radar-comparison-border", "rgba(251,146,60,.72)"),
            compFill:      getCssVar("--sr-radar-comparison-fill",   "rgba(251,146,60,.04)"),
            gridColor:     getCssVar("--sr-radar-grid-color",     "rgba(255,255,255,.045)"),
            angleColor:    getCssVar("--sr-radar-angle-color",    "rgba(255,255,255,.05)"),
            labelColor:    getCssVar("--sr-radar-label-color",    "rgba(255,255,255,.68)"),
        };
        window.SR_RADAR_THEME_PALETTE = radarPalette;  // read-only debug marker

        const subjectValues = radarData.subject?.values || [];
        const targetProfiles = radarData.targetProfiles || [];
        const targetAvg = radarData.target || {};

        // ── per-axis normalization ────────────────────────────────────────────
        // RADAR_AXIS_RANGES (emitted by exporter for MID) is [{min,max},…], one
        // entry per radar axis, derived from the global MID population.
        // Each stored axis score (0-100 role-minmax) is linearly rescaled into
        // the population range so every axis has equal visual headroom.
        // Stored DATA values are never modified; this is display-only.
        const _axisRanges = (typeof RADAR_AXIS_RANGES !== "undefined" && Array.isArray(RADAR_AXIS_RANGES))
            ? RADAR_AXIS_RANGES : null;
        function normAxisVals(rawArr) {
            if (!_axisRanges || !rawArr || !rawArr.length) return rawArr.slice();
            return rawArr.map((v, i) => {
                const r = _axisRanges[i];
                if (!r || r.max <= r.min || !Number.isFinite(v)) return v;
                return Math.round(Math.min(1, Math.max(0, (v - r.min) / (r.max - r.min))) * 10000) / 100;
            });
        }
        const normSubjectValues  = normAxisVals(subjectValues);
        const normTargetProfiles = targetProfiles.map(tp => ({...tp, values: normAxisVals(tp.values || [])}));
        const normTargetAvg      = {...targetAvg, values: normAxisVals(targetAvg.values || [])};

        // ── short axis labels for chart polygon (full labels stay in accordion) ──
        const SHORT_LABELS = {
            technical_security: "Sicurezza",
            progression: "Progressione",
            creation: "Creazione",
            direct_threat: "Minaccia",
            defensive_contribution: "Duelli",
            defensive_activity: "Attività difensiva",
            duel_aerial_presence: ["Duelli", "presenza aerea"],
            build_up_involvement: ["Costruzione", "coinvolgimento"],
            progression_from_the_back: ["Progressione", "dal basso"],
            territorial_advanced_involvement: ["Territorio", "avanzato"],
        };
        function wrapAxisLabel(label) {
            if (Array.isArray(label)) return label;
            const text = String(label || "");
            const words = text.split(/\s+/).filter(Boolean);
            if (text.length <= 18 || words.length < 2) return text;
            const lines = [];
            let current = "";
            words.forEach(word => {
                const next = current ? `${current} ${word}` : word;
                if (next.length > 16 && current) {
                    lines.push(current);
                    current = word;
                } else {
                    current = next;
                }
            });
            if (current) lines.push(current);
            return lines.slice(0, 2);
        }
        const chartLabels = radarAxes.map(a => wrapAxisLabel(SHORT_LABELS[a.key] || a.label || a.key));

        // ── find most similar individual by radar-axis Euclidean distance ────
        // Uses normalized values so "closest" is measured on the displayed scale.
        function radarEuclid(a, b) {
            if (!a || !b || !a.length) return Infinity;
            return Math.sqrt(a.reduce((sum, v, i) => sum + Math.pow(v - (b[i] || 0), 2), 0));
        }
        let defaultIdx = 0;
        let minDist = Infinity;
        normTargetProfiles.forEach((profile, i) => {
            const d = radarEuclid(normSubjectValues, profile.values || []);
            if (d < minDist) { minDist = d; defaultIdx = i; }
        });

        // ── populate selector ────────────────────────────────────────────────
        const select = $("radarTargetSelect");
        if (select) {
            const opts = normTargetProfiles.map((profile, i) =>
                `<option value="p${i}">${esc(profile.label || `Player ${profile.id}`)}</option>`
            );
            if ((normTargetAvg.values || []).length) {
                opts.push(`<option value="avg">${esc(normTargetAvg.label || "Media")}</option>`);
            }
            select.innerHTML = opts.join("");
            select.value = normTargetProfiles.length ? `p${defaultIdx}` : "avg";
        }

        function getCompValues() {
            if (!select) return normTargetAvg.values || [];
            const v = select.value;
            if (v === "avg") return normTargetAvg.values || [];
            return normTargetProfiles[parseInt(v.slice(1))]?.values || [];
        }
        function getCompLabel() {
            if (!select) return normTargetAvg.label || "Target";
            const v = select.value;
            if (v === "avg") return normTargetAvg.label || "Media";
            return normTargetProfiles[parseInt(v.slice(1))]?.label || "Target";
        }

        // ── custom legend ────────────────────────────────────────────────────
        const legendEl = $("radarCustomLegend");
        function updateLegend() {
            if (!legendEl) return;
            legendEl.innerHTML = `
                <div class="sr-rcl-item">
                    <span class="sr-rcl-line sr-rcl-line--subject"></span>
                    <span>${esc(radarData.subject?.label || p.name || "Subject")}</span>
                </div>
                <div class="sr-rcl-item">
                    <span class="sr-rcl-line sr-rcl-line--comp"></span>
                    <span id="radarLegendCompName">${esc(getCompLabel())}</span>
                </div>
            `;
        }
        updateLegend();

        // ── datasets: comparator first (behind), subject second (foreground) ──
        const datasets = [
            {
                // [0] Comparator — secondary visual weight
                label: getCompLabel(),
                data: getCompValues(),
                borderColor: radarPalette.compBorder,
                backgroundColor: radarPalette.compFill,
                pointBackgroundColor: radarPalette.compBorder,
                pointBorderColor: "rgba(255,255,255,.55)",  // subtle halo so dots read on dark bg
                pointBorderWidth: 1.5,
                borderWidth: 1.5,
                borderDash: [5, 5],
                pointRadius: 4,
                pointHoverRadius: 6,
            },
            {
                // [1] Subject — protagonist (drawn on top)
                label: radarData.subject?.label || p.name || "Subject",
                data: normSubjectValues,
                borderColor: radarPalette.subjectBorder,
                backgroundColor: radarPalette.subjectFill,
                pointBackgroundColor: radarPalette.subjectBorder,
                pointBorderColor: "rgba(255,255,255,.90)",  // crisp white halo — makes dots pop
                pointBorderWidth: 2,
                borderWidth: 3,
                pointRadius: 6,
                pointHoverRadius: 8,
            },
        ];

        // ── Radar scale ───────────────────────────────────────────────────────
        // After per-axis normalization values are 0-100. Use a fixed scale so
        // the chart is always interpretable regardless of which player is loaded.
        // radarMax = 85: the outer ring represents ~P90 of the comparison pool.
        // With P05–P95 normalization most "good" players score 50–80, filling
        // 59–94% of the radius instead of 50–80% with radarMax=100.
        // Truly exceptional players (>85) visually reach or slightly exceed the
        // outer ring — which is accurate and matches how DATAMB-style radars look.
        const radarMax  = 85;
        const radarStep = 20;   // rings at 20 / 40 / 60 / 80 (clean 4-ring grid)

        const radarChart = new Chart(ctx, {
            type: "radar",
            data: { labels: chartLabels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: { padding: { top: 18, right: 28, bottom: 18, left: 28 } },
                scales: {
                    r: {
                        min: 0,
                        max: radarMax,
                        ticks: {
                            display: false,
                            stepSize: radarStep,
                        },
                        grid: {
                            circular: true,                 // concentric circles, not polygon
                            color: radarPalette.gridColor,
                            lineWidth: 1,
                        },
                        angleLines: {
                            color: radarPalette.angleColor,
                            lineWidth: 0.9,
                        },
                        pointLabels: {
                            color: radarPalette.labelColor,
                            font: { size: 11, weight: "600", lineHeight: 1.16 },
                            padding: 10,
                        },
                    },
                },
                plugins: {
                    legend: { display: false },   // custom legend rendered in DOM
                    tooltip: { enabled: true },
                },
            },
        });

        // ── selector change handler ───────────────────────────────────────────
        if (select) {
            select.addEventListener("change", () => {
                radarChart.data.datasets[0].data = getCompValues();
                radarChart.data.datasets[0].label = getCompLabel();
                radarChart.update();
                const nameEl = $("radarLegendCompName");
                if (nameEl) nameEl.textContent = getCompLabel();
            });
        }

        // ── Mobile radar summary (compact default on narrow viewports) ────────
        const scrollWrap = canvas.closest(".sr-radar-scroll-wrap");
        if (scrollWrap) {
            const radarParent = scrollWrap.parentElement;
            const radarTools  = radarParent.querySelector(".sr-radar-tools");

            // Remove any previous summary (guards against double-render)
            radarParent.querySelector(".sr-radar-mobile-summary")?.remove();

            const pct = v => Math.min(100, ((v || 0) / radarMax * 100)).toFixed(1);

            function axisRows(compVals) {
                return radarAxes.map((axis, i) => {
                    const sv = Math.round(subjectValues[i] || 0);
                    const sl = SHORT_LABELS[axis.key];
                    const label = Array.isArray(sl) ? sl.join(" ") : (sl || axis.label || axis.key);
                    return `
                    <div class="sr-rm-axis-row">
                        <span class="sr-rm-axis-label">${esc(label)}</span>
                        <div class="sr-rm-bar-wrap">
                            <div class="sr-rm-bar-track">
                                <div class="sr-rm-bar-fill" style="width:${pct(subjectValues[i])}%;background:${radarPalette.subjectBorder}"></div>
                                <div class="sr-rm-comp-marker" style="left:${pct(compVals[i])}%" aria-hidden="true"></div>
                            </div>
                        </div>
                        <span class="sr-rm-axis-score">${sv}</span>
                    </div>`;
                }).join("");
            }

            const summary = document.createElement("div");
            summary.className = "sr-radar-mobile-summary";
            summary.innerHTML = `
                <div class="sr-rm-axes">${axisRows(getCompValues())}</div>
                <div class="sr-rm-comp-note">
                    <span class="sr-rm-comp-dot" style="background:${radarPalette.compBorder}"></span>
                    <span class="sr-rm-comp-name">${esc(getCompLabel())}</span>
                    <span class="sr-rm-comp-hint">· marcatore di confronto</span>
                </div>
                <button class="sr-rm-expand-btn" aria-expanded="false">
                    Visualizza radar completo
                </button>`;

            radarParent.insertBefore(summary, scrollWrap);

            summary.querySelector(".sr-rm-expand-btn").addEventListener("click", function () {
                const opening = this.getAttribute("aria-expanded") !== "true";
                this.setAttribute("aria-expanded", String(opening));
                this.textContent = opening ? "Chiudi radar" : "Visualizza radar completo";
                scrollWrap.classList.toggle("sr-mobile-open", opening);
                if (radarTools) radarTools.classList.toggle("sr-mobile-open", opening);
            });

            // Sync markers when comparison selector changes
            if (select) {
                select.addEventListener("change", () => {
                    const cv = getCompValues();
                    summary.querySelectorAll(".sr-rm-comp-marker").forEach((m, i) => {
                        m.style.left = pct(cv[i]) + "%";
                    });
                    const nameEl = summary.querySelector(".sr-rm-comp-name");
                    if (nameEl) nameEl.textContent = getCompLabel();
                });
            }
        }
    }

    function metricValue(playerId, metric) {
        const row = metrics[String(playerId)] || metrics[playerId] || {};
        return row[metric];
    }
    function metricScore(metric, value) {
        if (value === null || value === undefined || Number.isNaN(value)) return null;
        const range = metricRanges[metric];
        if (!range || range.max === range.min) return null;
        return Math.max(0, Math.min(100, ((value - range.min) / (range.max - range.min)) * 100));
    }

    function renderMetricBars(sectionId, data, legendId) {
        const el = $(sectionId);
        if (!el || !data) return;
        const subject = meta(data.subjectId || subjectId);
        const referenceIds = data.baselineIds || [];
        const legend = $(legendId);
        const showAverage = data.showAverage !== false;

        // Compact abbreviation: initials from each word, max 3 chars
        function abbrev(name) {
            return String(name || "").split(/\s+/).filter(Boolean)
                .map(w => w[0]).join("").toUpperCase().slice(0, 3);
        }

        // Stagger overlapping markers (within 5 percentile points) vertically
        function calcYOffsets(scores) {
            const indexed = scores.map((s, i) => ({ s: s ?? 0, i })).sort((a, b) => a.s - b.s);
            const offsets = new Array(scores.length).fill(0);
            for (let k = 1; k < indexed.length; k++) {
                if (indexed[k].s - indexed[k - 1].s < 5)
                    offsets[indexed[k].i] = offsets[indexed[k - 1].i] === 0 ? -6 : 0;
            }
            return offsets;
        }

        const tagItems = [
            `<div class="sr-player-tag is-subject"><span class="sr-ptag-dot" style="background:${subject.color || "#4ade80"}"></span>${esc(subject.name || "Subject")}</div>`,
            ...referenceIds.map(id => {
                const p = meta(id);
                return `<div class="sr-player-tag"><span class="sr-ptag-dot" style="background:${p.color || "#fff"}"></span>${esc(p.name || id)}</div>`;
            }),
        ];
        if (showAverage) tagItems.push(`<div class="sr-player-tag"><span class="sr-ptag-dot" style="background:rgba(0,0,0,.2)"></span>${esc(data.baselineLabel || "Average")}</div>`);
        const tags = tagItems.join("");
        if (legend) legend.innerHTML = tags;
        const title = $(sectionId)?.classList.contains("sr-card") ? `<p class="sr-section-label">${esc(data.label || "Metric comparison")}</p>` : "";

        el.innerHTML = `
            ${title}
            ${legend ? "" : `<div class="sr-player-tags">${tags}</div>`}
            ${data.groups.map((group, gIdx) => `
                <div class="sr-dot-group">
                    <div class="sr-dot-group-title">${esc(group.label)}</div>
                    ${group.metrics.map((row, mIdx) => {
                        const subjectScore = row.subjectScore ?? 0;
                        const baselineScore = row.baselineScore ?? 0;

                        // ── Desktop row (unchanged) ──────────────────────────
                        const refBars = referenceIds.map(id => {
                            const p = meta(id);
                            const value = metricValue(id, row.metric);
                            const score = metricScore(row.metric, value);
                            if (score === null) return "";
                            const color = p.color || "#fff";
                            return `<div class="sr-bar-track"><div class="sr-bar-fill" style="width:${score}%; background:color-mix(in srgb, ${color} 72%, transparent)" data-tip="${esc(p.name || id)}: ${esc(fmt(row.metric, value))}"></div></div>`;
                        }).join("");
                        const baselineBar = showAverage
                            ? `<div class="sr-bar-track"><div class="sr-bar-fill" style="width:${baselineScore}%; background:rgba(255,255,255,.42)" data-tip="${esc(data.baselineLabel || "Average")}: ${esc(fmt(row.metric, row.baselineValue))}"></div></div>`
                            : "";

                        // ── Mobile: build per-player data once ──────────────
                        const allPlayers = [
                            { id: String(data.subjectId || subjectId), isSubject: true },
                            ...referenceIds.map(id => ({ id: String(id), isSubject: false })),
                        ];
                        const pData = allPlayers.map(({ id, isSubject }) => {
                            const p = meta(id);
                            const value = isSubject ? row.subjectValue : metricValue(id, row.metric);
                            const score = isSubject ? subjectScore : (metricScore(row.metric, value) ?? null);
                            return { id, isSubject, name: p.name || id, color: p.color || (isSubject ? "#4ade80" : "#fff"), value, score };
                        });

                        // ── Mobile compact: markers on shared 0–100 bar ─────
                        const yOffsets = calcYOffsets(pData.map(p => p.score));
                        const markers = pData.map((p, i) => {
                            const pos = Math.max(0, Math.min(100, p.score ?? 0));
                            const sz  = p.isSubject ? 13 : 10;
                            return `<div class="sr-mc-marker${p.isSubject ? " is-subject" : ""}" style="left:${pos}%;width:${sz}px;height:${sz}px;background:${p.color};transform:translate(-50%,calc(-50% + ${yOffsets[i]}px))"></div>`;
                        }).join("");

                        const chips = pData.map(p => {
                            const val = (p.value !== null && p.value !== undefined) ? fmt(row.metric, p.value) : "—";
                            return `<span class="sr-mc-chip${p.isSubject ? " is-subject" : ""}"><span class="sr-mc-chip-dot" style="background:${p.color}"></span>${esc(abbrev(p.name))} ${esc(val)}</span>`;
                        }).join("");

                        const subjectVal = (row.subjectValue !== null && row.subjectValue !== undefined) ? fmt(row.metric, row.subjectValue) : "—";
                        const detailId  = `srmc-${sectionId}-${gIdx}-${mIdx}`;

                        // ── Mobile detail: Sprint 1 per-player rows ──────────
                        const bmMarker = showAverage && baselineScore > 0
                            ? `<div class="sr-mobile-bm-marker" style="left:${baselineScore}%"></div>` : "";
                        const detailRows = pData.map(p => {
                            const ds  = p.score ?? 0;
                            const dv  = (p.value !== null && p.value !== undefined) ? fmt(row.metric, p.value) : "—";
                            const bg  = p.isSubject ? p.color : `color-mix(in srgb,${p.color} 72%,transparent)`;
                            return `
                            <div class="sr-mobile-player-row${p.isSubject ? " is-subject" : ""}">
                                <div class="sr-mobile-player-header">
                                    <span class="sr-mobile-player-name"><span class="sr-ptag-dot" style="background:${p.color}"></span>${esc(p.name)}</span>
                                    <span class="sr-mobile-player-val">${esc(dv)}</span>
                                </div>
                                <div class="sr-bar-track${p.isSubject ? " main" : ""}">
                                    <div class="sr-bar-fill" style="width:${ds}%;background:${bg}"></div>
                                    ${bmMarker}
                                </div>
                                ${p.score !== null ? `<div class="sr-mobile-player-sub">P${Math.round(ds)}</div>` : ""}
                            </div>`;
                        }).join("");

                        return `
                            <div class="sr-dot-row">
                                <span class="sr-dot-label">${esc(row.label || row.metric)}</span>
                                <div class="sr-bar-group">
                                    <div class="sr-bar-track main"><div class="sr-bar-fill" style="width:${subjectScore}%;background:${subject.color || "#4ade80"}" data-tip="${esc(subject.name || "Subject")}: ${esc(fmt(row.metric, row.subjectValue))}"></div></div>
                                    ${refBars}
                                    ${baselineBar}
                                </div>
                                <div class="sr-dot-val">${esc(fmt(row.metric, row.subjectValue))}</div>
                            </div>
                            <div class="sr-mobile-metric">
                                <div class="sr-mobile-compact">
                                    <div class="sr-mc-header">
                                        <span class="sr-mc-label">${esc(row.label || row.metric)}</span>
                                        <span class="sr-mc-subject-val">${esc(subjectVal)} · P${Math.round(subjectScore)}</span>
                                    </div>
                                    <div class="sr-mc-bar-wrap">
                                        <div class="sr-mc-bar-track">${markers}</div>
                                    </div>
                                    <div class="sr-mc-player-strip">${chips}</div>
                                    <button class="sr-mc-toggle" aria-expanded="false" aria-controls="${detailId}">Mostra dettaglio</button>
                                </div>
                                <div class="sr-mc-detail" id="${detailId}" hidden>
                                    ${detailRows}
                                </div>
                            </div>
                        `;
                    }).join("")}
                </div>
            `).join("")}
        `;

        // Toggle expand/collapse — one open at a time per section
        el.querySelectorAll(".sr-mc-toggle").forEach(btn => {
            btn.addEventListener("click", () => {
                const isOpen = btn.getAttribute("aria-expanded") === "true";
                const detail = document.getElementById(btn.getAttribute("aria-controls"));
                // Close all others in this section
                el.querySelectorAll(".sr-mc-toggle[aria-expanded='true']").forEach(other => {
                    if (other === btn) return;
                    other.setAttribute("aria-expanded", "false");
                    other.textContent = "Mostra dettaglio";
                    const d = document.getElementById(other.getAttribute("aria-controls"));
                    if (d) d.hidden = true;
                });
                if (isOpen) {
                    btn.setAttribute("aria-expanded", "false");
                    btn.textContent = "Mostra dettaglio";
                    if (detail) detail.hidden = true;
                } else {
                    btn.setAttribute("aria-expanded", "true");
                    btn.textContent = "Nascondi dettaglio";
                    if (detail) detail.hidden = false;
                }
            });
        });
    }

    function drawPitchLines(svg) {
        const line = { stroke: "rgba(255,255,255,.10)", "stroke-width": 1, fill: "none" };
        svg.appendChild(svgEl("rect", { x: 0, y: 0, width: SVG_W, height: SVG_H, ...line }));
        svg.appendChild(svgEl("line", { x1: SVG_W / 2, y1: 0, x2: SVG_W / 2, y2: SVG_H, ...line }));
        svg.appendChild(svgEl("circle", { cx: SVG_W / 2, cy: SVG_H / 2, r: 32, ...line }));
        svg.appendChild(svgEl("rect", { x: 0, y: 60, width: 65, height: 120, ...line }));
        svg.appendChild(svgEl("rect", { x: SVG_W - 65, y: 60, width: 65, height: 120, ...line }));
    }
    function drawAttShotPitchLines(svg) {
        const line = { stroke: "rgba(255,255,255,.12)", "stroke-width": 1, fill: "none" };
        const x0 = 52.5;
        const cropW = PITCH_L - x0;
        const sx = x => ((x - x0) / cropW) * SVG_W;
        const sy = y => (y / PITCH_W) * SVG_H;
        svg.appendChild(svgEl("rect", { x: 0, y: 0, width: SVG_W, height: SVG_H, ...line }));
        svg.appendChild(svgEl("line", { x1: SVG_W - 1, y1: 0, x2: SVG_W - 1, y2: SVG_H, ...line }));
        svg.appendChild(svgEl("rect", { x: sx(88.5), y: sy(13.84), width: sx(105) - sx(88.5), height: sy(54.16) - sy(13.84), ...line }));
        svg.appendChild(svgEl("rect", { x: sx(99.5), y: sy(24.84), width: sx(105) - sx(99.5), height: sy(43.16) - sy(24.84), ...line }));
        svg.appendChild(svgEl("circle", { cx: sx(94), cy: sy(34), r: 2.4, fill: "rgba(255,255,255,.28)" }));
        svg.appendChild(svgEl("line", { x1: sx(105), y1: sy(30.34), x2: sx(105), y2: sy(37.66), stroke: "rgba(255,255,255,.55)", "stroke-width": 3, "stroke-linecap": "round" }));
    }
    function drawCellArrow(svg, cx, cy, dx, dy, color) {
        const len = Math.sqrt(dx * dx + dy * dy);
        if (len < 0.01) return;
        const scale = Math.min(11 / (len * M_TO_PX), 1) * M_TO_PX;
        const ex = cx + dx * scale, ey = cy + dy * scale;
        svg.appendChild(svgEl("line", { x1: cx, y1: cy, x2: ex, y2: ey, stroke: color, "stroke-width": 1.6, "stroke-linecap": "round", opacity: 0.85 }));
    }
    function buildDensity(svgId, grid, colorFn) {
        const svg = $(svgId);
        if (!svg) return;
        svg.innerHTML = "";
        drawPitchLines(svg);
        if (!grid) return;
        const maxN = Math.max(...grid.flat().map(v => Number(v) || 0), 0);
        grid.forEach((col, cx) => col.forEach((val, ry) => {
            if (!val || val <= 0) return;
            const n = maxN > 0 ? val / maxN : 0;
            const displayY = pitchGridY(ry);
            const rect = svgEl("rect", { x: cx * SVG_CW, y: displayY * SVG_CH, width: SVG_CW, height: SVG_CH, fill: colorFn(n), rx: 2 });
            svgTip(rect, `x≈${((cx + 0.5) * CELL_W_M).toFixed(1)}m y≈${((ry + 0.5) * CELL_H_M).toFixed(1)}m`);
            svg.appendChild(rect);
        }));
    }
    function buildShotField(svgId, grid) {
        const svg = $(svgId);
        if (!svg) return;
        svg.innerHTML = "";
        drawAttShotPitchLines(svg);
        if (!grid) return;
        const cropX = 52.5;
        const cropW = PITCH_L - cropX;
        const counts = grid.flat().map(cell => Number(cell?.[0]) || 0);
        const maxN = Math.max(...counts, 0);
        grid.forEach((col, ix) => col.forEach((cell, iy) => {
            const shots = Number(cell?.[0]) || 0;
            if (!shots) return;
            const cellLeftM = ix * CELL_W_M;
            const cellRightM = (ix + 1) * CELL_W_M;
            if (cellRightM <= cropX) return;
            const visualLeftM = Math.max(cellLeftM, cropX);
            const visualRightM = Math.min(cellRightM, PITCH_L);
            const goals = Number(cell?.[1]) || 0;
            const xg = Number(cell?.[2]) || 0;
            const xgAvg = cell?.[3] == null ? null : Number(cell[3]);
            const intensity = maxN > 0 ? shots / maxN : 0;
            const fill = `rgba(${Math.round(190 + intensity * 55)},${Math.round(90 + intensity * 95)},80,${(0.18 + intensity * 0.62).toFixed(2)})`;
            const x = ((visualLeftM - cropX) / cropW) * SVG_W;
            const width = ((visualRightM - visualLeftM) / cropW) * SVG_W;
            const displayY = pitchGridY(iy);
            const rect = svgEl("rect", { x, y: displayY * SVG_CH, width, height: SVG_CH, fill, rx: 2 });
            svgTip(rect, `${shots} tiri · ${goals} gol · xG ${xg.toFixed(2)}${xgAvg == null ? "" : ` · xG/tiro ${xgAvg.toFixed(2)}`}`);
            svg.appendChild(rect);
            if (goals > 0) {
                svg.appendChild(svgTip(svgEl("circle", {
                    cx: x + width / 2,
                    cy: (displayY + 0.5) * SVG_CH,
                    r: Math.min(9, 3 + goals * 1.7),
                    fill: "rgba(255,255,255,.88)",
                    stroke: "rgba(15,23,42,.62)",
                    "stroke-width": 1,
                }), `${goals} gol`));
            }
        }));
    }
    function buildGoalmouth(svgId, grid) {
        const svg = $(svgId);
        if (!svg) return;
        svg.innerHTML = "";
        if (!grid) {
            svg.style.display = "none";
            return;
        }
        const counts = grid.flat().map(cell => Number(cell?.[0]) || 0);
        const maxN = Math.max(...counts, 0);
        if (!maxN) {
            svg.style.display = "none";
            return;
        }
        svg.style.display = "";
        const w = 180, h = 90, cw = w / 3, ch = h / 3;
        svg.appendChild(svgEl("rect", { x: 1, y: 1, width: w - 2, height: h - 2, fill: "rgba(255,255,255,.025)", stroke: "rgba(255,255,255,.20)", "stroke-width": 1.2 }));
        for (let x = 1; x < 3; x += 1) svg.appendChild(svgEl("line", { x1: x * cw, y1: 0, x2: x * cw, y2: h, stroke: "rgba(255,255,255,.14)", "stroke-width": 1 }));
        for (let y = 1; y < 3; y += 1) svg.appendChild(svgEl("line", { x1: 0, y1: y * ch, x2: w, y2: y * ch, stroke: "rgba(255,255,255,.14)", "stroke-width": 1 }));
        grid.forEach((col, ix) => col.forEach((cell, iy) => {
            const shots = Number(cell?.[0]) || 0;
            if (!shots) return;
            const goals = Number(cell?.[1]) || 0;
            const intensity = shots / maxN;
            const rect = svgEl("rect", {
                x: ix * cw + 2,
                y: (2 - iy) * ch + 2,
                width: cw - 4,
                height: ch - 4,
                fill: `rgba(251,191,36,${(0.18 + intensity * 0.64).toFixed(2)})`,
                rx: 2,
            });
            svgTip(rect, `${shots} tiri verso porta · ${goals} gol`);
            svg.appendChild(rect);
        }));
    }
    function buildVectorGrid(svgId, grid, mode) {
        const svg = $(svgId);
        if (!svg) return;
        svg.innerHTML = "";
        drawPitchLines(svg);
        if (!grid) return;
        const counts = grid.flat().map(cell => Number(cell?.[0]) || 0);
        const maxN = Math.max(...counts, 0);
        grid.forEach((col, ix) => col.forEach((cell, iy) => {
            const n = Number(cell?.[0]) || 0;
            if (!n) return;
            const displayY = pitchGridY(iy);
            const intensity = maxN > 0 ? n / maxN : 0;
            const fill = mode === "pass"
                ? `rgba(${Math.round(80 + intensity * 120)},${Math.round(130 + intensity * 90)},80,${(0.16 + intensity * 0.62).toFixed(2)})`
                : `rgba(60,140,${Math.round(150 + intensity * 90)},${(0.16 + intensity * 0.62).toFixed(2)})`;
            svg.appendChild(svgTip(svgEl("rect", { x: ix * SVG_CW, y: displayY * SVG_CH, width: SVG_CW, height: SVG_CH, fill, rx: 2 }), `${n} eventi`));
            const dx = mode === "carry" ? cell[8] : (cell.length >= 7 ? cell[2] : cell[1]);
            const dy = mode === "carry" ? cell[9] : (cell.length >= 7 ? cell[3] : cell[2]);
            const arrow = mode === "carry" ? cell[10] : (cell.length >= 7 ? cell[6] : cell[3]);
            if (arrow && dx != null && dy != null) drawCellArrow(svg, (ix + 0.5) * SVG_CW, (displayY + 0.5) * SVG_CH, dx, pitchDy(dy), "rgba(255,255,255,.82)");
        }));
    }
    function note(id, text) {
        const el = $(id);
        if (el) el.textContent = text || "";
    }
    function setHeatmapPlayer(id) {
        document.querySelectorAll(".sr-heatmap-btn").forEach(btn => {
            btn.classList.toggle("active", String(btn.dataset.id) === String(id));
        });
        const d = heatmapData[String(id)] || heatmapData[id];
        if (!d) return;
        const isAttSpatialV2 = roleMeta.role === "ATT" && d.spatialVersion === "att_heatmap_view_v2";
        if (isAttSpatialV2) {
            buildShotField("pitchPos", d.hasShotFieldMap ? d.shotField : null);
            buildGoalmouth("pitchGoalmouth", d.hasShotGoalmouthMap ? d.shotGoalmouth : null);
            buildDensity("pitchCarry", d.ip, n => `rgba(20,${Math.round(120 + n * 135)},80,${(0.12 + n * 0.72).toFixed(2)})`);
            buildVectorGrid("pitchPass", d.hasPassDirection ? d.pass : null, "pass");
            buildVectorGrid("pitchProg", d.hasCarryDirection ? d.carry : null, "carry");
            note("pitchPosNote", `${d.shotNote || "Shot map unavailable"} · ${d.goalmouthNote || "Goal-mouth placement unavailable"}`);
            note("pitchCarryNote", d.ipNote || (d.ipCx ? `Centroide: x=${d.ipCx}` : ""));
            note("pitchPassNote", d.passNote || "Pass direction unavailable");
            note("pitchProgNote", d.carryNote || "Carry direction unavailable");
            note("pitchDefNote", d.defNote || "");
            const defBlock = $("defSummaryBlock");
            if (defBlock) {
                const cx = d.defCx != null ? Number(d.defCx).toFixed(0) : "—";
                defBlock.innerHTML =
                    `<span class="sr-def-stat"><strong>${d.defN ?? "—"}</strong> azioni work-rate</span>` +
                    `<span class="sr-def-stat">baricentro fallback x≈<strong>${cx}m</strong></span>` +
                    `<span class="sr-def-stat">non pressing puro</span>`;
            }
            const twin = $("twinNote");
            if (twin) twin.textContent = d.twinNote || "";
            return;
        }
        buildGoalmouth("pitchGoalmouth", null);
        buildDensity("pitchPos", d.ip, n => `rgba(20,${Math.round(120 + n * 135)},80,${(0.12 + n * 0.72).toFixed(2)})`);
        buildVectorGrid("pitchCarry", d.carry, "carry");
        buildVectorGrid("pitchPass", d.pass, "pass");
        if (roleMeta.role === "DEF") {
            buildDensity("pitchProg", d.def, n => `rgba(${Math.round(80 + n * 120)},160,220,${(0.12 + n * 0.72).toFixed(2)})`);
        } else {
            buildVectorGrid("pitchProg", d.prog, "prog");
        }
        note("pitchPosNote", d.ipNote || (d.ipCx ? `Centroide: x=${d.ipCx}` : ""));
        note("pitchCarryNote", d.carryN ? `${d.carryN} conduzioni · ${d.carryProgN || 0} progressive` : "");
        note("pitchPassNote", d.passN ? `${d.passN} passaggi` : "");
        if (roleMeta.role === "DEF") {
            note("pitchProgNote", d.defNote || (d.defCx ? `Centroide difensivo: x=${d.defCx}` : ""));
        } else {
            note("pitchProgNote", d.progN ? `${d.progN} passaggi progressivi` : "");
        }
        const defBlock = $("defSummaryBlock");
        if (defBlock) {
            const oppPct = d.defOppPct != null ? (d.defOppPct * 100).toFixed(0) + "%" : "—";
            const cx = d.defCx != null ? Number(d.defCx).toFixed(0) : "—";
            defBlock.innerHTML =
                `<span class="sr-def-stat"><strong>${d.defN ?? "—"}</strong> azioni difensive</span>` +
                `<span class="sr-def-stat"><strong>${oppPct}</strong> in metà avversaria</span>` +
                `<span class="sr-def-stat">baricentro difensivo x≈<strong>${cx}m</strong></span>`;
        }
        const twin = $("twinNote");
        if (twin) twin.textContent = d.twinNote || "";
    }
    function hasUsableHeatmap(id) {
        const d = heatmapData[String(id)] || heatmapData[id];
        if (!d) return false;
        return Boolean(d.ip || d.carry || d.pass || d.def || d.prog || d.shotField || d.shotGoalmouth);
    }
    function renderHeatmaps() {
        const toggle = $("heatmapToggle");
        if (!toggle) return;
        const ids = [subjectId, ...(comparisonGroups[0]?.ids || [])].filter(hasUsableHeatmap);
        toggle.innerHTML = ids.map(id => {
            const p = meta(id);
            return `<button class="sr-heatmap-btn" data-id="${id}"><span class="sr-heatmap-btn-dot" style="background:${p.color || "#fff"}"></span>${esc(p.name || id)}</button>`;
        }).join("");
        toggle.querySelectorAll("button").forEach(btn => btn.addEventListener("click", () => setHeatmapPlayer(btn.dataset.id)));
        if (ids.length) setHeatmapPlayer(ids[0]);
    }

    function renderSimilarity() {
        const el = $("similarityGrid");
        if (!el) return;
        el.innerHTML = similarityData.map(space => `
            <div class="sr-sim-space">
                <div class="sr-sim-space-title">${esc(space.space)}</div>
                <p class="sr-sim-desc">${esc(space.description || "")}</p>
                ${(space.matches || []).map(match => `
                    <div class="sr-sim-match">
                        <span class="sr-sim-name">${esc(match.name)}</span>
                        <span class="sr-sim-score">${Number(match.score || 0).toFixed(1)}%</span>
                        <div class="sr-sim-bar"><div class="sr-sim-bar-fill" style="width:${Number(match.score || 0)}%"></div></div>
                    </div>
                `).join("") || `<div class="sr-sim-empty">Nessun match disponibile</div>`}
            </div>
        `).join("");
    }

    function renderFootnotes() {
        const el = $("footnotes");
        if (!el) return;
        el.innerHTML = footnotes.map(text => `<span class="sr-footnote-chip">${esc(text)}</span>`).join("");
    }

    renderHeader();
    renderProfileReading();
    renderRadar();
    renderMetricBars("interComparison", targetBars, "interLegend");
    renderHeatmaps();
    if ($("sourceTeamComparison")) {
        renderMetricBars("sourceTeamComparison", sourceBars, "sourceTeamLegend");
    } else {
        renderMetricBars("bruggeComparison", sourceBars, "bruggeLegend");
    }
    renderSimilarity();
    renderFootnotes();
}

if (window.SR_PAYLOAD_READY && typeof window.SR_PAYLOAD_READY.then === "function") {
    window.SR_PAYLOAD_READY.then(initRoleReport);
} else {
    initRoleReport();
}
