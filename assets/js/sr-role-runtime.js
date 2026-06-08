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
        if (kind === "percent_0_100") return value.toFixed(1) + "%";
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

        // ── Mobile radar summary ─────────────────────────────────────────────
        const scrollWrap = canvas.closest(".sr-radar-scroll-wrap");
        if (scrollWrap) { try {
            const radarParent = scrollWrap.parentElement;
            const radarTools  = radarParent.querySelector(".sr-radar-tools");

            radarParent.querySelector(".sr-radar-mobile-summary")?.remove();

            const pct = v => Math.min(100, ((v || 0) / radarMax * 100)).toFixed(1);

            function buildAxisRows(compVals) {
                return radarAxes.map((axis, i) => {
                    const sv = Math.round(subjectValues[i] || 0);
                    const sl = SHORT_LABELS[axis.key];
                    // Full label — allow wrapping, no truncation
                    const label = Array.isArray(sl) ? sl.join(" ") : (sl || axis.label || axis.key);
                    return `
                    <div class="sr-rm-axis-row">
                        <span class="sr-rm-axis-label">${esc(label)}</span>
                        <div class="sr-rm-bar-wrap">
                            <div class="sr-rm-bar-track">
                                <div class="sr-rm-bar-fill" style="width:${pct(subjectValues[i])}%;background:${radarPalette.subjectBorder}"></div>
                                <div class="sr-rm-comp-marker" style="left:${pct(compVals[i])}%;background:${radarPalette.compBorder}" aria-hidden="true"></div>
                            </div>
                        </div>
                        <span class="sr-rm-axis-score">${sv}</span>
                    </div>`;
                }).join("");
            }

            // Comparison selector options — same data source as desktop select
            // Mirror the exact value format used by the desktop select ("p0","p1",..."avg")
            const mobileOpts = normTargetProfiles.map((profile, i) =>
                `<option value="p${i}">${esc(profile.label || `Player ${profile.id}`)}</option>`
            );
            if ((normTargetAvg.values || []).length) {
                mobileOpts.push(`<option value="avg">${esc(normTargetAvg.label || "Media")}</option>`);
            }
            const mobileOptions = mobileOpts.join("");

            const subjectMeta = playerMeta[String(subjectId)] || playerMeta[subjectId] || {};
            const summary = document.createElement("div");
            summary.className = "sr-radar-mobile-summary";
            summary.innerHTML = `
                <div class="sr-rm-header">
                    <span class="sr-rm-subject-name">
                        <span class="sr-ptag-dot" style="background:${radarPalette.subjectBorder}"></span>
                        ${esc(subjectMeta.name || radarData.subject?.label || "Subject")}
                    </span>
                    <div class="sr-rm-select-wrap">
                        <span class="sr-rm-vs-label">vs</span>
                        <select class="sr-rm-comp-select" aria-label="Seleziona giocatore di confronto">
                            ${mobileOptions}
                        </select>
                    </div>
                </div>
                <div class="sr-rm-axes">${buildAxisRows(getCompValues())}</div>
                <button class="sr-rm-expand-btn" aria-expanded="false">
                    Visualizza radar completo
                </button>`;

            radarParent.insertBefore(summary, scrollWrap);

            const mobileSelect = summary.querySelector(".sr-rm-comp-select");
            if (select) mobileSelect.value = select.value; // sync initial state

            // Helper: redraw markers using current comparison selection
            function syncMarkers() {
                const cv = getCompValues();
                summary.querySelectorAll(".sr-rm-comp-marker").forEach((m, i) => {
                    m.style.left  = pct(cv[i]) + "%";
                    m.style.background = radarPalette.compBorder;
                });
            }

            // Mobile select → chart + desktop select + markers (single source of truth)
            mobileSelect.addEventListener("change", () => {
                if (select && select.value !== mobileSelect.value) select.value = mobileSelect.value;
                radarChart.data.datasets[0].data  = getCompValues();
                radarChart.data.datasets[0].label = getCompLabel();
                radarChart.update();
                const nameEl = $("radarLegendCompName");
                if (nameEl) nameEl.textContent = getCompLabel();
                syncMarkers();
            });

            // Desktop select → mobile select + markers
            if (select) {
                select.addEventListener("change", () => {
                    if (mobileSelect.value !== select.value) mobileSelect.value = select.value;
                    syncMarkers();
                });
            }

            // Toggle full radar
            summary.querySelector(".sr-rm-expand-btn").addEventListener("click", function () {
                const opening = this.getAttribute("aria-expanded") !== "true";
                this.setAttribute("aria-expanded", String(opening));
                this.textContent = opening ? "Chiudi radar" : "Visualizza radar completo";
                scrollWrap.classList.toggle("sr-mobile-open", opening);
                if (radarTools) radarTools.classList.toggle("sr-mobile-open", opening);
            });
        } catch(e) { console.error("[radar-mobile] error:", e); } }
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
        svg.__attShotZones = [];
        svg.__attShotColorByXg = false;
        drawAttShotPitchLines(svg);
        if (!grid) return;
        if (buildShotMacroZones(svg, grid)) return;
        buildShotFieldGrid(svg, grid);
    }
    function buildShotFieldGrid(svg, grid) {
        const cropX = 52.5;
        const cropW = PITCH_L - cropX;
        const cells = grid.flat();
        const xgValues = cells.map(cell => Number(cell?.[2]) || 0);
        const countValues = cells.map(cell => Number(cell?.[0]) || 0);
        const maxXg = Math.max(...xgValues, 0);
        const maxShots = Math.max(...countValues, 0);
        const colorByXg = maxXg > 0;
        const maxValue = colorByXg ? maxXg : maxShots;
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
            const sot = Number(cell?.[5]) || 0;
            const value = colorByXg ? xg : shots;
            const intensity = maxValue > 0 ? value / maxValue : 0;
            const fill = `rgba(${Math.round(64 + intensity * 170)},${Math.round(155 + intensity * 70)},${Math.round(145 - intensity * 45)},${(0.12 + intensity * 0.46).toFixed(2)})`;
            const x = ((visualLeftM - cropX) / cropW) * SVG_W;
            const width = ((visualRightM - visualLeftM) / cropW) * SVG_W;
            const displayY = pitchGridY(iy);
            const rect = svgEl("rect", {
                x: x + 1.5,
                y: displayY * SVG_CH + 1.5,
                width: Math.max(0, width - 3),
                height: SVG_CH - 3,
                fill,
                stroke: "rgba(255,255,255,.16)",
                "stroke-width": 0.8,
                rx: 3,
            });
            const tipParts = [
                `${shots} tiri`,
                `${goals} gol`,
                `xG totale ${xg.toFixed(2)}`,
                `xG/tiro ${xgAvg == null || !Number.isFinite(xgAvg) ? (shots ? (xg / shots).toFixed(2) : "0.00") : xgAvg.toFixed(2)}`,
            ];
            if (sot) tipParts.push(`${sot} tiri in porta`);
            tipParts.push(colorByXg ? "colore per xG" : "colore per volume tiri");
            svgTip(rect, tipParts.join(" · "));
            svg.appendChild(rect);
            if (goals > 0) {
                svg.appendChild(svgTip(svgEl("circle", {
                    cx: x + width / 2,
                    cy: (displayY + 0.5) * SVG_CH,
                    r: Math.min(5.2, 2.3 + goals * 0.8),
                    fill: "rgba(15,23,42,.86)",
                    stroke: "rgba(255,255,255,.82)",
                    "stroke-width": 1.2,
                }), `${goals} gol`));
            }
        }));
    }
    const ATT_SHOT_ZONES = [
        { label: "Area piccola", cells: [[11, 3], [11, 4]], parts: [[[11, 3], [11, 4]]] },
        { label: "Centro area", cells: [[10, 3], [10, 4]], short: "Centro area" },
        {
            label: "Lati area",
            cells: [[10, 1], [10, 2], [10, 5], [10, 6], [11, 1], [11, 2], [11, 5], [11, 6]],
            parts: [
                [[10, 1], [10, 2], [11, 1], [11, 2]],
                [[10, 5], [10, 6], [11, 5], [11, 6]],
            ],
        },
        { label: "Limite area", cells: [[8, 2], [8, 3], [8, 4], [8, 5], [9, 2], [9, 3], [9, 4], [9, 5]] },
        { label: "Fuori area centrale", cells: [[6, 2], [6, 3], [6, 4], [6, 5], [7, 2], [7, 3], [7, 4], [7, 5]] },
        {
            label: "Corridoi larghi",
            cells: [[6, 0], [6, 1], [6, 6], [6, 7], [7, 0], [7, 1], [7, 6], [7, 7], [8, 0], [8, 1], [8, 6], [8, 7], [9, 0], [9, 1], [9, 6], [9, 7], [10, 0], [10, 7], [11, 0], [11, 7]],
            parts: [
                [[6, 0], [6, 1], [7, 0], [7, 1], [8, 0], [8, 1], [9, 0], [9, 1], [10, 0], [11, 0]],
                [[6, 6], [6, 7], [7, 6], [7, 7], [8, 6], [8, 7], [9, 6], [9, 7], [10, 7], [11, 7]],
            ],
            visible: false,
        },
    ];
    function readShotCell(grid, ix, iy) {
        const cell = grid?.[ix]?.[iy];
        if (!Array.isArray(cell)) return null;
        const shots = Number(cell[0]) || 0;
        if (!shots) return null;
        return {
            shots,
            goals: Number(cell[1]) || 0,
            xg: Number(cell[2]) || 0,
            sot: Number(cell[5]) || 0,
        };
    }
    function aggregateShotZone(grid, zone) {
        return zone.cells.reduce((acc, [ix, iy]) => {
            const cell = readShotCell(grid, ix, iy);
            if (!cell) return acc;
            acc.shots += cell.shots;
            acc.goals += cell.goals;
            acc.xg += cell.xg;
            acc.sot += cell.sot;
            return acc;
        }, { ...zone, shots: 0, goals: 0, xg: 0, sot: 0 });
    }
    function shotZoneBounds(cells, cropX, cropW) {
        const minX = Math.min(...cells.map(([ix]) => ix));
        const maxX = Math.max(...cells.map(([ix]) => ix));
        const minY = Math.min(...cells.map(([, iy]) => iy));
        const maxY = Math.max(...cells.map(([, iy]) => iy));
        const leftM = Math.max(minX * CELL_W_M, cropX);
        const rightM = Math.min((maxX + 1) * CELL_W_M, PITCH_L);
        const topDisplayY = pitchGridY(maxY);
        const bottomDisplayY = pitchGridY(minY);
        return {
            x: ((leftM - cropX) / cropW) * SVG_W,
            y: topDisplayY * SVG_CH,
            width: ((rightM - leftM) / cropW) * SVG_W,
            height: (bottomDisplayY - topDisplayY + 1) * SVG_CH,
        };
    }
    function buildShotMacroZones(svg, grid) {
        try {
            if (!Array.isArray(grid)) return false;
            const cropX = 52.5;
            const cropW = PITCH_L - cropX;
            const zones = ATT_SHOT_ZONES.map(zone => aggregateShotZone(grid, zone));
            const maxXg = Math.max(...zones.map(zone => zone.xg), 0);
            const maxShots = Math.max(...zones.map(zone => zone.shots), 0);
            const colorByXg = maxXg > 0;
            const maxValue = colorByXg ? maxXg : maxShots;
            if (!maxValue) return false;
            zones.forEach(zone => {
                if (zone.visible === false) return;
                const value = colorByXg ? zone.xg : zone.shots;
                const intensity = maxValue > 0 ? value / maxValue : 0;
                const occupied = zone.shots > 0;
                const fill = occupied
                    ? `rgba(${Math.round(54 + intensity * 170)},${Math.round(150 + intensity * 72)},${Math.round(142 - intensity * 44)},${(0.16 + intensity * 0.46).toFixed(2)})`
                    : "rgba(255,255,255,.018)";
                const xgPerShot = zone.shots ? zone.xg / zone.shots : 0;
                const tipParts = [
                    zone.label,
                    `${zone.shots} tiri`,
                    `${zone.goals} gol`,
                    `xG ${zone.xg.toFixed(2)}`,
                    `xG/tiro ${xgPerShot.toFixed(2)}`,
                ];
                if (zone.sot) tipParts.push(`${zone.sot} tiri in porta`);
                const tooltip = tipParts.join(" · ");
                const parts = zone.parts || [zone.cells];
                let labelBounds = null;
                parts.forEach(part => {
                    const bounds = shotZoneBounds(part, cropX, cropW);
                    if (!labelBounds || bounds.width * bounds.height > labelBounds.width * labelBounds.height) {
                        labelBounds = bounds;
                    }
                    const rect = svgEl("rect", {
                        x: bounds.x + 1.8,
                        y: bounds.y + 1.8,
                        width: Math.max(0, bounds.width - 3.6),
                        height: Math.max(0, bounds.height - 3.6),
                        fill,
                        stroke: occupied ? "rgba(255,255,255,.20)" : "rgba(255,255,255,.055)",
                        "stroke-width": occupied ? 0.9 : 0.6,
                        rx: 4,
                    });
                    svgTip(rect, tooltip);
                    svg.appendChild(rect);
                });
                if (!occupied || !labelBounds || labelBounds.width < 38 || labelBounds.height < 26) return;
                const cx = labelBounds.x + labelBounds.width / 2;
                const cy = labelBounds.y + labelBounds.height / 2;
                const compact = labelBounds.width < 76;
                const countSize = Math.max(12, Math.min(16, Math.min(labelBounds.width / 5.2, labelBounds.height / 3.1)));
                const secondSize = Math.max(8.4, Math.min(10.4, Math.min(labelBounds.width / 10.5, labelBounds.height / 5.4)));
                const xgLabel = compact ? xgPerShot.toFixed(2) : `${xgPerShot.toFixed(2)} xG/tiro`;
                const approxSecondWidth = xgLabel.length * secondSize * 0.56;
                const showXgPerShot = zone.shots >= 2 && labelBounds.height >= 42 && approxSecondWidth <= labelBounds.width - 8;
                const text = svgEl("text", {
                    x: cx,
                    y: cy + (showXgPerShot ? -3 : countSize / 3),
                    "text-anchor": "middle",
                    fill: "rgba(255,255,255,.90)",
                    "font-size": countSize.toFixed(1),
                    "font-weight": 750,
                    "pointer-events": "none",
                });
                text.textContent = `${zone.shots}`;
                svg.appendChild(text);
                if (!showXgPerShot) return;
                const xgPerShotText = svgEl("text", {
                    x: cx,
                    y: cy + Math.max(10, secondSize + 3),
                    "text-anchor": "middle",
                    fill: "rgba(255,255,255,.66)",
                    "font-size": secondSize.toFixed(1),
                    "font-weight": 600,
                    "pointer-events": "none",
                });
                xgPerShotText.textContent = xgLabel;
                svg.appendChild(xgPerShotText);
            });
            svg.__attShotZones = zones;
            svg.__attShotColorByXg = colorByXg;
            return true;
        } catch (_err) {
            return false;
        }
    }
    function renderShotZoneSummary(noteEl, zones) {
        if (!noteEl) return;
        const panel = noteEl.closest(".sr-pitch-wrap");
        if (!panel) return;
        let summary = panel.querySelector(".sr-shot-zone-summary");
        if (!summary) {
            summary = document.createElement("div");
            summary.className = "sr-pitch-note sr-shot-zone-summary";
            summary.style.marginTop = ".35rem";
            summary.style.lineHeight = "1.35";
            noteEl.insertAdjacentElement("afterend", summary);
        }
        const topZones = (zones || [])
            .filter(zone => zone.shots > 0)
            .sort((a, b) => (b.xg - a.xg) || (b.shots - a.shots))
            .slice(0, 3);
        if (!topZones.length) {
            summary.textContent = "";
            return;
        }
        summary.textContent = "Zone principali: " + topZones
            .map(zone => `${zone.label} ${zone.shots} tiri · ${zone.xg.toFixed(2)} xG · ${zone.goals} gol`)
            .join(" | ");
    }
    function validateGoalmouthGrid(grid) {
        const empty = { total: 0, maxCell: 0, maxCellShare: 0, centerColumnShare: 0, suspicious: false };
        if (!Array.isArray(grid)) return empty;
        let total = 0;
        let maxCell = 0;
        let centerColumn = 0;
        grid.forEach((col, ix) => {
            if (!Array.isArray(col)) return;
            col.forEach(cell => {
                const shots = Number(cell?.[0]) || 0;
                total += shots;
                maxCell = Math.max(maxCell, shots);
                if (ix === 1) centerColumn += shots;
            });
        });
        const maxCellShare = total > 0 ? maxCell / total : 0;
        const centerColumnShare = total > 0 ? centerColumn / total : 0;
        return {
            total,
            maxCell,
            maxCellShare,
            centerColumnShare,
            suspicious: total > 0 && (maxCellShare > 0.65 || centerColumnShare > 0.85),
        };
    }
    function buildGoalmouth(svgId, grid) {
        const svg = $(svgId);
        if (!svg) return false;
        const panel = svg.closest(".sr-pitch-wrap");
        if (panel) panel.hidden = false;
        svg.innerHTML = "";
        if (!grid) {
            svg.style.display = "none";
            if (panel) panel.hidden = true;
            return false;
        }
        const validation = validateGoalmouthGrid(grid);
        // ATT goalmouth is hidden when validation detects central collapse in the aggregated payload.
        // Re-enable rendering after export confirms true goalmouth coordinates and outcome filters.
        if (validation.suspicious) {
            svg.style.display = "none";
            if (panel) panel.hidden = true;
            return false;
        }
        const counts = grid.flat().map(cell => Number(cell?.[0]) || 0);
        const maxN = Math.max(...counts, 0);
        if (!maxN) {
            svg.style.display = "none";
            if (panel) panel.hidden = true;
            return false;
        }
        svg.style.display = "";
        if (panel) panel.hidden = false;
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
        return true;
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
            const hasGoalmouth = buildGoalmouth("pitchGoalmouth", d.hasShotGoalmouthMap ? d.shotGoalmouth : null);
            buildDensity("pitchCarry", d.ip, n => `rgba(20,${Math.round(120 + n * 135)},80,${(0.12 + n * 0.72).toFixed(2)})`);
            buildVectorGrid("pitchPass", d.hasPassDirection ? d.pass : null, "pass");
            buildVectorGrid("pitchProg", d.hasCarryDirection ? d.carry : null, "carry");
            const shotXg = d.shotXg == null ? null : Number(d.shotXg);
            const shotNote = d.shotN
                ? `${d.shotN} tiri · ${d.shotGoals || 0} gol${Number.isFinite(shotXg) ? ` · xG ${shotXg.toFixed(2)} · colore = xG totale` : " · colore = volume"}`
                : (d.shotNote || "Zone tiro non disponibili");
            note("pitchPosNote", shotNote);
            renderShotZoneSummary($("pitchPosNote"), $("pitchPos")?.__attShotZones || []);
            note("pitchGoalmouthNote", hasGoalmouth ? (d.goalmouthNote || "") : "");
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
