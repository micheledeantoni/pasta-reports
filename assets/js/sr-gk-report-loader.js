// sr-gk-report-loader.js
// GK-specific external legacy payload loader — Sprint 4C.
//
// Mirrors the architecture of sr-report-loader.js but uses the GK schema:
//   GK_PAGE_V1_PLAYERS, GK_PAGE_V1_TEAM_COMPARISONS, GK_PAGE_V1_SUMMARY
//
// Reads:   window.SR_GK_EXTERNAL_PAYLOAD_URL
// Sets:    window.GK_PAGE_V1_PLAYERS
//          window.GK_PAGE_V1_TEAM_COMPARISONS
//          window.GK_PAGE_V1_SUMMARY
//          window.SR_GK_PAYLOAD_LOAD_STATUS
//          window.SR_GK_PAYLOAD_READY  (Promise — always resolves)
//
// sr-gk-runtime.js checks SR_GK_PAYLOAD_READY before rendering; if absent it
// renders immediately from whatever globals are already on window (inline path).
//
// Does NOT touch role globals (ROLE_META, RADAR_DATA, etc.) or SR_PAYLOAD_READY.
// Does NOT modify sr-report-loader.js behaviour in any way.

(function () {
  var REQUIRED_KEYS = [
    "GK_PAGE_V1_PLAYERS",
    "GK_PAGE_V1_TEAM_COMPARISONS",
    "GK_PAGE_V1_SUMMARY",
  ];

  // Only these keys are copied to window; anything else in the JSON is ignored.
  var ALLOWED_KEYS = [
    "GK_PAGE_V1_PLAYERS",
    "GK_PAGE_V1_TEAM_COMPARISONS",
    "GK_PAGE_V1_SUMMARY",
  ];

  var url = window.SR_GK_EXTERNAL_PAYLOAD_URL;

  if (!url) {
    // No GK external URL configured — leave window globals untouched.
    // Resolve immediately so sr-gk-runtime.js can proceed with inline globals.
    window.SR_GK_PAYLOAD_LOAD_STATUS = {
      mode: "inline_fallback",
      url: null,
      ok: false,
      error: "no_url_configured",
    };
    window.SR_GK_PAYLOAD_READY = Promise.resolve();
    return;
  }

  window.SR_GK_PAYLOAD_READY = fetch(url)
    .then(function (res) {
      if (!res.ok) {
        throw new Error("HTTP " + res.status + " fetching " + url);
      }
      return res.json();
    })
    .then(function (data) {
      var missing = REQUIRED_KEYS.filter(function (k) {
        return !(k in data);
      });
      if (missing.length) {
        throw new Error("Missing required keys in GK payload: " + missing.join(", "));
      }
      ALLOWED_KEYS.forEach(function (k) {
        if (k in data) {
          window[k] = data[k];
        }
      });
      window.SR_GK_PAYLOAD_LOAD_STATUS = {
        mode: "external",
        url: url,
        ok: true,
        error: null,
      };
    })
    .catch(function (err) {
      // Detect whether inline GK globals are present.
      // GK_PAGE_V1_PLAYERS is the canary: live page defines it inline;
      // the external-only canary does not.
      var hasInlineFallback =
        typeof window.GK_PAGE_V1_PLAYERS !== "undefined";
      window.SR_GK_PAYLOAD_LOAD_STATUS = {
        mode: hasInlineFallback
          ? "inline_fallback"
          : "external_failed_no_inline_fallback",
        url: url,
        ok: false,
        error: String(err),
      };
    });
})();
