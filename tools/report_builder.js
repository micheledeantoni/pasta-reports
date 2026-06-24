const state = {
  playerResults: [],
  targetPeers: [],
  sourcePeers: [],
  selectedTargetPeerIds: new Set(["297390", "54968", "82399"]),
  selectedSourcePeerIds: new Set(["425115", "494398", "505567"]),
};

const $ = (id) => document.getElementById(id);

function value(id) {
  return $(id).value.trim();
}

function checked(id) {
  return $(id).checked;
}

function setValue(id, next) {
  $(id).value = next || "";
}

function idsFromSet(set) {
  return [...set].filter(Boolean).join(",");
}

function sourceRole() {
  return value("sourceRole");
}

function reportRole() {
  return value("role");
}

function describePlayer(player) {
  const minutes = player.minutes === "" ? "n/a" : `${player.minutes} min`;
  const role = player.macro_role || reportRole();
  const team = player.team_name || "Unknown team";
  return `${player.player_name} · ${player.player_id} · ${team} · ${role} · ${minutes} · ${player.availability || "unknown"}`;
}

function escapeHtml(raw) {
  return String(raw ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function getJson(url) {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || `Request failed: ${url}`);
  }
  return payload;
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || `Request failed: ${url}`);
  }
  return payload;
}

function rowButton(player, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "row-button";
  button.textContent = describePlayer(player);
  button.addEventListener("click", () => onClick(player));
  return button;
}

function renderPlayerResults() {
  const wrap = $("playerResults");
  wrap.innerHTML = "";
  if (!state.playerResults.length) {
    wrap.textContent = "No players found.";
    return;
  }
  state.playerResults.forEach((player) => {
    wrap.appendChild(rowButton(player, (selected) => {
      setValue("playerId", selected.player_id);
      setValue("playerName", selected.player_name);
      setValue("teamName", selected.team_name);
      setValue("competition", selected.competition);
      setValue("season", selected.season);
      if (selected.macro_role) {
        setValue("sourceRole", selected.macro_role);
        if (!checked("allowCrossRole")) {
          setValue("role", selected.macro_role);
        }
      }
      if (!value("slug")) {
        setValue("slug", selected.player_name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""));
      }
      updateLabels();
      updateReview();
    }));
  });
}

function renderCheckboxList(targetId, players, selectedSet, emptyText) {
  const wrap = $(targetId);
  wrap.innerHTML = "";
  if (!players.length) {
    wrap.textContent = emptyText;
    return;
  }
  players.forEach((player) => {
    const id = String(player.player_id);
    const label = document.createElement("label");
    label.className = "check-row";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = selectedSet.has(id);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        selectedSet.add(id);
      } else {
        selectedSet.delete(id);
      }
      updateReview();
    });
    const text = document.createElement("span");
    text.textContent = describePlayer(player);
    label.append(checkbox, text);
    wrap.appendChild(label);
  });
}

function selectedPlayers(players, selectedSet) {
  const byId = new Map(players.map((player) => [String(player.player_id), player]));
  return [...selectedSet].map((id) => byId.get(id) || { player_id: id, player_name: "Missing in loaded list", availability: "not loaded" });
}

function sourceContextExported() {
  return sourceRole() === reportRole();
}

function validationErrors() {
  const errors = [];
  if (!idsFromSet(state.selectedTargetPeerIds)) {
    errors.push("Select at least one main/radar peer for the report role.");
  }
  if (sourceRole() !== reportRole() && !checked("allowCrossRole")) {
    errors.push("Enable cross-role report before generating with different source/report roles.");
  }
  if (sourceRole() !== reportRole() && !value("roleOverrideReason")) {
    errors.push("Add a role override reason before generating with different source/report roles.");
  }
  return errors;
}

function buildPayload() {
  return {
    role: reportRole(),
    report_role: reportRole(),
    source_role: sourceRole(),
    allow_cross_role_report: checked("allowCrossRole"),
    role_override_reason: value("roleOverrideReason"),
    season: value("season"),
    player_id: value("playerId"),
    player_name: value("playerName"),
    slug: value("slug"),
    team_name: value("teamName"),
    source_club: value("teamName"),
    competition: value("competition"),
    target_team: value("targetTeam"),
    visibility: value("visibility"),
    report_status: value("reportStatus"),
    main_comparison_peer_ids: idsFromSet(state.selectedTargetPeerIds),
    comparison_label: value("comparisonLabel"),
    source_team_peer_ids: idsFromSet(state.selectedSourcePeerIds),
    source_team_peer_label: value("sourcePeerLabel"),
    source_context_exported: sourceContextExported(),
    narrative: value("narrative"),
    source_team_note: value("sourceTeamNote"),
    note_confronto: value("noteConfronto"),
    note_heatmap: value("noteHeatmap"),
    note_context: value("noteContext"),
    note_similarity: value("noteSimilarity"),
  };
}

function updateLabels() {
  if (!value("comparisonLabel") || value("comparisonLabel").match(/^(Inter|Napoli|Genoa|Team .+) (GK|DEF|MID|ATT)$/)) {
    setValue("comparisonLabel", `${value("targetTeam")} ${reportRole()}`);
  }
  if (!value("sourcePeerLabel") || value("sourcePeerLabel").match(/^(Inter|Napoli|Genoa|Team .+) (GK|DEF|MID|ATT)$/)) {
    setValue("sourcePeerLabel", `${value("teamName")} ${sourceRole()}`);
  }
}

function updateReview() {
  const targetPlayers = selectedPlayers(state.targetPeers, state.selectedTargetPeerIds);
  const sourcePlayers = selectedPlayers(state.sourcePeers, state.selectedSourcePeerIds);
  const targetLines = targetPlayers.map((player) => `<li>${escapeHtml(describePlayer(player))}</li>`).join("");
  const sourceLines = sourcePlayers.map((player) => `<li>${escapeHtml(describePlayer(player))}</li>`).join("");
  const errors = validationErrors();
  const roleWarning = sourceRole() === reportRole()
    ? ""
    : `This page will be generated as ${reportRole()} although the player was found as ${sourceRole()}.`;
  $("roleWarning").textContent = roleWarning;
  $("review").innerHTML = `
    <div class="review-grid">
      <div>
        <h3>Player</h3>
        <p>${escapeHtml(value("playerName"))} · ${escapeHtml(value("playerId"))} · ${escapeHtml(value("teamName"))}</p>
      </div>
      <div>
        <h3>Role interpretation</h3>
        <p>Source: ${escapeHtml(sourceRole())} · Report/exporter: ${escapeHtml(reportRole())}</p>
        ${roleWarning ? `<p class="warn">${escapeHtml(roleWarning)}</p>` : ""}
        <p>${escapeHtml(value("roleOverrideReason") || "No override reason")}</p>
      </div>
      <div>
        <h3>Main/radar peers: ${escapeHtml(value("comparisonLabel"))}</h3>
        <p>Uses report role ${escapeHtml(reportRole())}; passed to exporter as comparison IDs.</p>
        <ul>${targetLines || "<li>No main comparison peers selected.</li>"}</ul>
      </div>
      <div>
        <h3>Source-context peers: ${escapeHtml(value("sourcePeerLabel"))}</h3>
        <p>Uses source role ${escapeHtml(sourceRole())}; ${sourceContextExported() ? "passed as exporter context IDs." : "stored editorially only because roles differ."}</p>
        <ul>${sourceLines || "<li>No source context peers selected.</li>"}</ul>
      </div>
      <div>
        <h3>Page</h3>
        <p>${escapeHtml(value("slug"))}.html · ${escapeHtml(value("visibility"))} · ${escapeHtml(value("reportStatus"))}</p>
      </div>
      ${errors.length ? `<div><h3 class="warn">Blocking issues</h3><ul>${errors.map((error) => `<li>${escapeHtml(error)}</li>`).join("")}</ul></div>` : ""}
    </div>
  `;
  $("openPage").href = `http://127.0.0.1:8001/${encodeURIComponent(value("slug"))}.html`;
}

function showOutput(payload) {
  $("output").textContent = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
}

async function searchPlayers() {
  const url = `/api/search_players?role=${encodeURIComponent(value("searchRole"))}&query=${encodeURIComponent(value("playerQuery"))}&season=${encodeURIComponent(value("season"))}`;
  const payload = await getJson(url);
  state.playerResults = payload.players || [];
  renderPlayerResults();
}

async function loadTargetPeers() {
  const url = `/api/target_peers?role=${encodeURIComponent(reportRole())}&team=${encodeURIComponent(value("targetPeerTeam"))}&season=${encodeURIComponent(value("season"))}&min_minutes=${encodeURIComponent(value("targetMinMinutes"))}`;
  const payload = await getJson(url);
  state.targetPeers = payload.players || [];
  renderCheckboxList("targetPeers", state.targetPeers, state.selectedTargetPeerIds, "No target-team peers found.");
  updateReview();
}

async function loadSourcePeers() {
  const url = `/api/source_peers?role=${encodeURIComponent(sourceRole())}&player_id=${encodeURIComponent(value("playerId"))}&season=${encodeURIComponent(value("season"))}&min_minutes=${encodeURIComponent(value("sourceMinMinutes"))}`;
  const payload = await getJson(url);
  state.sourcePeers = payload.players || [];
  renderCheckboxList("sourcePeers", state.sourcePeers, state.selectedSourcePeerIds, payload.error || "No source-team peers found.");
  updateReview();
}

async function generatePrompt() {
  const errors = validationErrors().filter((error) => !error.startsWith("Select at least"));
  if (errors.length) {
    showOutput(errors.join("\n"));
    return;
  }
  const payload = await postJson("/api/prompt", buildPayload());
  $("promptBox").value = payload.prompt;
}

function applyJson() {
  const raw = value("jsonPaste");
  if (!raw) return;
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (error) {
    showOutput(`Invalid JSON: ${error.message}`);
    return;
  }
  const fields = {
    narrative: "narrative",
    source_team_note: "sourceTeamNote",
    note_confronto: "noteConfronto",
    note_heatmap: "noteHeatmap",
    note_context: "noteContext",
    note_similarity: "noteSimilarity",
  };
  Object.entries(fields).forEach(([jsonKey, elementId]) => {
    if (Object.prototype.hasOwnProperty.call(payload, jsonKey)) {
      setValue(elementId, payload[jsonKey]);
    }
  });
  const unsupported = Object.keys(payload).filter((key) => !fields[key]);
  showOutput(unsupported.length ? `Applied supported fields. Unsupported fields kept out of the page payload: ${unsupported.join(", ")}` : "Applied supported fields.");
  updateReview();
}

async function runEndpoint(endpoint) {
  const errors = validationErrors();
  if (errors.length) {
    showOutput(errors.join("\n"));
    return;
  }
  const payload = await postJson(endpoint, buildPayload());
  const command = Array.isArray(payload.command) ? payload.command.join(" ") : "";
  showOutput({
    ok: payload.ok,
    returncode: payload.returncode,
    command,
    stdout: payload.stdout,
    stderr: payload.stderr,
    url: payload.url,
  });
  if (payload.url) {
    $("openPage").href = payload.url;
  }
}

function bind(id, event, fn) {
  $(id).addEventListener(event, async () => {
    try {
      await fn();
    } catch (error) {
      showOutput(error.message);
    }
  });
}

[
  "searchRole", "sourceRole", "role", "allowCrossRole", "roleOverrideReason",
  "season", "playerId", "playerName", "slug", "teamName", "competition",
  "targetTeam", "visibility", "reportStatus", "comparisonLabel", "sourcePeerLabel",
].forEach((id) => {
  $(id).addEventListener("input", () => { updateLabels(); updateReview(); });
  $(id).addEventListener("change", () => { updateLabels(); updateReview(); });
});

bind("searchPlayer", "click", searchPlayers);
bind("loadTargetPeers", "click", loadTargetPeers);
bind("loadSourcePeers", "click", loadSourcePeers);
bind("generatePrompt", "click", generatePrompt);
bind("applyJson", "click", applyJson);
bind("dryRun", "click", () => runEndpoint("/api/dry_run"));
bind("createPage", "click", () => runEndpoint("/api/create_page"));
bind("regenCards", "click", () => runEndpoint("/api/regenerate_cards"));

updateLabels();
updateReview();
loadTargetPeers().then(loadSourcePeers).catch((error) => showOutput(error.message));
