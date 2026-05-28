// sr-report-loader.js
// Optional external legacy payload loader.
//
// If window.SR_EXTERNAL_PAYLOAD_URL is set, fetches the JSON and copies
// allowed legacy globals to window before sr-role-runtime.js renders.
// If the URL is absent or loading fails, the inline fallback globals are
// left untouched and the runtime renders from them as before.
//
// Pages that do not set SR_EXTERNAL_PAYLOAD_URL are completely unaffected.

(function () {
  var REQUIRED_KEYS = [
    "ROLE_META",
    "PAGE_META",
    "SUBJECT_ID",
    "PLAYER_META",
    "RADAR_AXES",
    "RADAR_DATA",
    "METRICS",
    "HEATMAP_DATA",
    "SIMILARITY_DATA",
    "FOOTNOTES",
  ];

  // Only these keys are copied to window; anything else in the JSON is ignored.
  var ALLOWED_KEYS = [
    "ROLE_META",
    "PAGE_META",
    "SUBJECT_ID",
    "PLAYER_META",
    "PROFILE_READING",
    "COMPARISON_GROUPS",
    "RADAR_AXES",
    "RADAR_DATA",
    "METRIC_FORMATS",
    "METRIC_RANGES",
    "METRICS",
    "TARGET_COMPARISON_BARS",
    "SOURCE_TEAM_COMPARISON_BARS",
    "HEATMAP_DATA",
    "SIMILARITY_DATA",
    "FOOTNOTES",
    "RADAR_AXIS_RANGES",
  ];

  var url = window.SR_EXTERNAL_PAYLOAD_URL;

  if (!url) {
    window.SR_PAYLOAD_LOAD_STATUS = {
      mode: "inline_fallback",
      url: null,
      ok: false,
      error: "no_url_configured",
    };
    window.SR_PAYLOAD_READY = Promise.resolve();
    return;
  }

  window.SR_PAYLOAD_READY = fetch(url)
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
        throw new Error("Missing required keys in payload: " + missing.join(", "));
      }
      ALLOWED_KEYS.forEach(function (k) {
        if (k in data) {
          window[k] = data[k];
        }
      });
      window.SR_PAYLOAD_LOAD_STATUS = {
        mode: "external",
        url: url,
        ok: true,
        error: null,
      };
    })
    .catch(function (err) {
      // Detect whether inline fallback globals are present (ROLE_META is the
      // canary: live pages define it inline; the external-only canary does not).
      var hasInlineFallback = typeof window.ROLE_META !== "undefined";
      window.SR_PAYLOAD_LOAD_STATUS = {
        mode: hasInlineFallback ? "inline_fallback" : "external_failed_no_inline_fallback",
        url: url,
        ok: false,
        error: String(err),
      };
    });
})();
