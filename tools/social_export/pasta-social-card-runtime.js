(function () {
    "use strict";

    const STATUS = {
        ok: false,
        payloadLoaded: false,
        profiles: [],
        axes: [],
        caption: "",
        errors: [],
    };

    window.PASTA_SOCIAL_CARD_STATUS = STATUS;

    const PROFILE_COLORS = [
        {
            stroke: "rgba(36, 79, 115, .96)",
            fill: "rgba(36, 79, 115, .18)",
        },
        {
            stroke: "rgba(181, 117, 61, .88)",
            fill: "rgba(181, 117, 61, .12)",
        },
        {
            stroke: "rgba(116, 131, 91, .9)",
            fill: "rgba(116, 131, 91, .12)",
        },
    ];

    const SHORT_LABELS = {
        technical_security: "Sicurezza",
        progression: "Progressione",
        creation: "Creazione",
        direct_threat: "Minaccia",
        defensive_contribution: "Duelli",
    };

    const EXPORT_SIZE = 1080;
    const CHART_SIZE = 820;
    const CHART_X = 130;
    const CHART_Y = 92;
    const LEGEND_Y = 960;

    function esc(value) {
        return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;",
        }[ch]));
    }

    function getMeta(payload, id) {
        const playerMeta = payload.PLAYER_META || {};
        return playerMeta[String(id)] || playerMeta[id] || {};
    }

    function normalizeValues(values, axisRanges) {
        if (!Array.isArray(axisRanges) || !axisRanges.length) {
            return (values || []).slice();
        }
        return (values || []).map((value, index) => {
            const range = axisRanges[index];
            if (!range || range.max <= range.min || !Number.isFinite(value)) return value;
            const normalized = (value - range.min) / (range.max - range.min);
            return Math.round(Math.max(0, Math.min(1, normalized)) * 10000) / 100;
        });
    }

    function rawProfileById(payload, id) {
        const wanted = String(id);
        const radarData = payload.RADAR_DATA || {};
        const subject = radarData.subject || {};
        if (String(subject.id || payload.SUBJECT_ID) === wanted) return { ...subject, source: "subject" };
        const targetProfiles = Array.isArray(radarData.targetProfiles) ? radarData.targetProfiles : [];
        const target = targetProfiles.find((profile) => String(profile.id) === wanted);
        if (target) return { ...target, source: "targetProfiles by explicit id" };
        return null;
    }

    function requestedPlayerIds() {
        const params = new URLSearchParams(window.location.search);
        const raw = params.get("players") || params.get("ids") || "";
        return raw.split(",").map((id) => id.trim()).filter(Boolean).slice(0, 3);
    }

    function chooseProfiles(payload) {
        const subjectId = payload.SUBJECT_ID;
        const radarData = payload.RADAR_DATA || {};
        const subject = radarData.subject || {};
        const targetProfiles = Array.isArray(radarData.targetProfiles) ? radarData.targetProfiles : [];
        const subjectMeta = getMeta(payload, subject.id || subjectId);
        const axisRanges = payload.RADAR_AXIS_RANGES || [];
        const explicitIds = requestedPlayerIds();

        if (explicitIds.length) {
            const explicitProfiles = explicitIds.map((id) => rawProfileById(payload, id));
            const missingIds = explicitIds.filter((id, index) => !explicitProfiles[index]);
            if (missingIds.length) {
                throw new Error(`Player ids not available in this payload: ${missingIds.join(", ")}`);
            }
            return explicitProfiles.map((profile) => {
                const meta = getMeta(payload, profile.id);
                return {
                    id: profile.id,
                    label: profile.label || meta.name || `Player ${profile.id}`,
                    values: normalizeValues(profile.values || [], axisRanges),
                    minutes: Number.isFinite(Number(meta.mins)) ? Number(meta.mins) : null,
                    source: profile.source,
                };
            });
        }

        const comparisonsWithMinutes = targetProfiles
            .map((profile, index) => ({
                ...profile,
                index,
                minutes: Number(getMeta(payload, profile.id).mins),
            }))
            .filter((profile) => Number.isFinite(profile.minutes));

        const comparisonPool = comparisonsWithMinutes.length >= 2
            ? comparisonsWithMinutes.sort((a, b) => b.minutes - a.minutes)
            : targetProfiles;

        const selectedComparisons = comparisonPool.slice(0, 2);

        return [
            {
                id: subject.id || subjectId,
                label: subject.label || subjectMeta.name || "Stankovic",
                values: normalizeValues(subject.values || [], axisRanges),
                source: "subject",
            },
            ...selectedComparisons.map((profile) => ({
                id: profile.id,
                label: profile.label || getMeta(payload, profile.id).name || `Player ${profile.id}`,
                values: normalizeValues(profile.values || [], axisRanges),
                minutes: Number.isFinite(profile.minutes) ? profile.minutes : null,
                source: Number.isFinite(profile.minutes) ? "targetProfiles by minutes" : "targetProfiles fallback",
            })),
        ];
    }

    function renderLegend(profiles) {
        const legend = document.getElementById("socialRadarLegend");
        if (!legend) return;
        legend.innerHTML = profiles.map((profile, index) => `
            <div class="social-radar-legend-item">
                <span class="social-radar-legend-swatch" style="background:${PROFILE_COLORS[index].stroke}"></span>
                <span>${esc(profile.label)}</span>
            </div>
        `).join("");
    }

    function renderRadar(payload, profiles) {
        const canvas = document.getElementById("socialRadarChart");
        if (!canvas) throw new Error("Radar canvas missing.");
        if (typeof Chart === "undefined") throw new Error("Chart.js is not available.");

        const axes = payload.RADAR_AXES || [];
        const labels = axes.map((axis) => SHORT_LABELS[axis.key] || axis.label || axis.key);
        STATUS.axes = labels.slice();

        return new Chart(canvas.getContext("2d"), {
            type: "radar",
            data: {
                labels,
                datasets: profiles.map((profile, index) => ({
                    label: profile.label,
                    data: profile.values,
                    borderColor: PROFILE_COLORS[index].stroke,
                    backgroundColor: PROFILE_COLORS[index].fill,
                    pointBackgroundColor: PROFILE_COLORS[index].stroke,
                    pointBorderColor: "rgba(255, 255, 255, .92)",
                    pointBorderWidth: index === 0 ? 2.5 : 2,
                    pointHoverRadius: 0,
                    pointRadius: index === 0 ? 7 : 5,
                    borderWidth: index === 0 ? 5 : 3.5,
                    tension: 0.16,
                })),
            },
            options: {
                responsive: false,
                maintainAspectRatio: false,
                animation: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false },
                },
                scales: {
                    r: {
                        min: 0,
                        max: 85,
                        ticks: {
                            display: false,
                            stepSize: 20,
                        },
                        grid: {
                            color: "rgba(63, 50, 38, .32)",
                            circular: true,
                            lineWidth: 1.2,
                        },
                        angleLines: {
                            color: "rgba(63, 50, 38, .36)",
                            lineWidth: 1.2,
                        },
                        pointLabels: {
                            color: "#2c241e",
                            font: {
                                family: "Arial, Helvetica, sans-serif",
                                size: 28,
                                weight: "800",
                            },
                            padding: 28,
                        },
                    },
                },
            },
        });
    }

    function defaultCaption(profiles) {
        const subject = profiles[0]?.label || "Aleksandar Stankovic";
        const comps = profiles.slice(1).map((profile) => profile.label).join(" e ");
        return [
            `Radar profilo: ${subject}${comps ? ` vs ${comps}` : ""}.`,
            "Fonte dati: WhoScored · Powered by PASTA.",
            "Michele Deantoni · @macnonesiste",
        ].join("\n");
    }

    function setStatusMessage(message) {
        const el = document.getElementById("socialExportStatus");
        if (el) el.textContent = message;
    }

    function applyExportMode() {
        const params = new URLSearchParams(window.location.search);
        if (params.get("export") === "1") {
            document.documentElement.dataset.exportMode = "true";
        }
    }

    function drawLegend(ctx, profiles, scale) {
        ctx.save();
        ctx.font = `${24 * scale}px Arial, Helvetica, sans-serif`;
        ctx.textBaseline = "middle";
        ctx.fillStyle = "#4d443c";
        ctx.lineWidth = 6 * scale;

        const items = profiles.map((profile, index) => ({
            label: profile.label,
            color: PROFILE_COLORS[index].stroke,
            width: ctx.measureText(profile.label).width + 68 * scale,
        }));
        const gap = 34 * scale;
        const totalWidth = items.reduce((sum, item) => sum + item.width, 0) + gap * (items.length - 1);
        let x = (EXPORT_SIZE * scale - totalWidth) / 2;

        items.forEach((item) => {
            ctx.strokeStyle = item.color;
            ctx.beginPath();
            ctx.moveTo(x, LEGEND_Y * scale);
            ctx.lineTo(x + 42 * scale, LEGEND_Y * scale);
            ctx.stroke();

            ctx.fillText(item.label, x + 55 * scale, LEGEND_Y * scale);
            x += item.width + gap;
        });
        ctx.restore();
    }

    function buildExportCanvas(scale = 2) {
        const chartCanvas = document.getElementById("socialRadarChart");
        if (!chartCanvas) throw new Error("Radar canvas missing.");
        const canvas = document.createElement("canvas");
        canvas.width = EXPORT_SIZE * scale;
        canvas.height = EXPORT_SIZE * scale;
        const ctx = canvas.getContext("2d");

        ctx.drawImage(chartCanvas, CHART_X * scale, CHART_Y * scale, CHART_SIZE * scale, CHART_SIZE * scale);
        drawLegend(ctx, STATUS.profiles, scale);
        return canvas;
    }

    function canvasToBlob(canvas) {
        return new Promise((resolve, reject) => {
            canvas.toBlob((blob) => {
                if (blob) resolve(blob);
                else reject(new Error("Unable to create PNG blob."));
            }, "image/png");
        });
    }

    async function copyRadarWithCaption() {
        try {
            if (!STATUS.ok) throw new Error("Radar non ancora pronto.");
            const captionEl = document.getElementById("socialCaption");
            const caption = captionEl?.value || STATUS.caption;
            const blob = await canvasToBlob(buildExportCanvas(2));

            if (!navigator.clipboard || typeof ClipboardItem === "undefined") {
                throw new Error("Clipboard immagine non disponibile in questo browser.");
            }

            await navigator.clipboard.write([
                new ClipboardItem({
                    "image/png": blob,
                    "text/plain": new Blob([caption], { type: "text/plain" }),
                }),
            ]);
            setStatusMessage("Immagine HD e didascalia copiate.");
        } catch (error) {
            STATUS.errors.push(error.message || String(error));
            setStatusMessage(`Copia non riuscita: ${error.message || error}`);
        }
    }

    async function downloadRadarHd() {
        try {
            if (!STATUS.ok) throw new Error("Radar non ancora pronto.");
            const blob = await canvasToBlob(buildExportCanvas(2));
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = "stankovic_radar_hd.png";
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
            setStatusMessage("PNG HD scaricato.");
        } catch (error) {
            STATUS.errors.push(error.message || String(error));
            setStatusMessage(`Download non riuscito: ${error.message || error}`);
        }
    }

    function bindControls() {
        document.getElementById("copyRadarWithCaption")?.addEventListener("click", copyRadarWithCaption);
        document.getElementById("downloadRadarHd")?.addEventListener("click", downloadRadarHd);
    }

    function publishStatusAttributes() {
        document.documentElement.dataset.pastaSocialCardOk = STATUS.ok ? "true" : "false";
        document.documentElement.dataset.pastaSocialCardProfiles = STATUS.profiles
            .map((profile) => profile.label)
            .join("|");
        document.documentElement.dataset.pastaSocialCardCaption = STATUS.caption;
    }

    async function init() {
        try {
            applyExportMode();
            bindControls();
            const shell = document.querySelector(".social-export-shell");
            const payloadUrl = shell?.dataset.payloadUrl || "../../data/report_legacy_payloads/stankovic.legacy_role_payload.json";
            const response = await fetch(payloadUrl, { cache: "no-store" });
            if (!response.ok) throw new Error(`Unable to load payload: ${response.status}`);

            const payload = await response.json();
            STATUS.payloadLoaded = true;

            const subjectId = payload.SUBJECT_ID;
            const subjectMeta = getMeta(payload, subjectId);
            const nameEl = document.getElementById("socialPlayerName");
            if (nameEl && subjectMeta.name) nameEl.textContent = subjectMeta.name;

            const profiles = chooseProfiles(payload);
            STATUS.profiles = profiles.map((profile) => ({
                id: profile.id,
                label: profile.label,
                minutes: profile.minutes ?? null,
                source: profile.source,
            }));

            renderLegend(profiles);
            renderRadar(payload, profiles);
            STATUS.caption = defaultCaption(profiles);
            const captionEl = document.getElementById("socialCaption");
            if (captionEl) captionEl.value = STATUS.caption;

            STATUS.ok = true;
            publishStatusAttributes();
            setStatusMessage("Pronto.");
        } catch (error) {
            STATUS.ok = false;
            STATUS.errors.push(error.message || String(error));
            publishStatusAttributes();
            setStatusMessage(`Errore: ${error.message || error}`);
            const legend = document.getElementById("socialRadarLegend");
            if (legend) {
                legend.innerHTML = `<div class="social-radar-legend-item">${esc(error.message || error)}</div>`;
            }
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
}());
