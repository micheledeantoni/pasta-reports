# GK Provedel/Vicario Mobile Audit

Branch: `feature/mobile-report-ui-audit`

Reference page on `main`: `ivan-provedel.html`

Vicario page on branch: `gk_report.html`

Scope: frontend template/generator, generated GK HTML, GK CSS, GK runtime JavaScript. Payloads and backend/export files are intentionally untouched.

| Area | Provedel | Vicario | Differenza | Azione |
| ---- | -------- | ------- | ---------- | ------ |
| File generated page | `ivan-provedel.html` exists after merge from `main`. | `gk_report.html` existed before the merge and had older hygiene issues. | Provedel had the newer GK report structure; Vicario was structurally older. | Regenerated both GK pages from the GK render path, preserving player-specific content. |
| Payload | `data/report_legacy_payloads/ivan-provedel.legacy_gk_payload.json`. | `data/report_legacy_payloads/gk_report.legacy_gk_payload.json`. | Both payloads expose three GK players, four radar axes, and visual blocks: `goal_map_save_map`, `sweeper_actions_map`, `distribution_profile`, `build_up_map`. | No payload changes. |
| Player content | Lazio, Serie A, 2,430 minutes, Provedel editorial notes. | Tottenham, Premier League, 2,250 minutes, Vicario narrative from index/generator metadata. | Content is player-specific. Vicario payload has no `PROFILE_READING` object. | Did not copy Provedel copy into Vicario. Documented missing payload narrative as payload/editorial follow-up only. |
| Head metadata | OG/Twitter card metadata exists. | Older page lacked normalized generated metadata. | Generator could duplicate metadata because GK source is a generated HTML page. | `render_gk()` now normalizes existing head metadata before inserting player-specific metadata. |
| Viewport | Previously inherited `user-scalable=no` from GK source. | Previously had `user-scalable=no`. | Violates mobile requirement. | Generated GK pages now use `width=device-width, initial-scale=1`. |
| CSS | Uses `sr-gk-report.css` and `pasta-theme.css`. | Uses `sr-gk-report.css` and `pasta-theme.css`. | Version strings were old/inconsistent. | GK CSS now loads with `?v=gk-mobile-20260605`; shared theme/common versions unchanged. |
| Runtime | Uses `sr-gk-runtime.js`. | Uses `sr-gk-runtime.js`. | Runtime version string was old/inconsistent. | GK runtime now loads with `?v=gk-mobile-20260605`. No role runtime is loaded on GK pages. |
| Menu/footer links | Provedel reference still had `generic.html` in generated output before this task. | Vicario had `generic.html` and placeholder social links. | Both needed page hygiene. | Generator now emits `method.html`, X, LinkedIn, and method footer links for GK pages. |
| Hero/banner | Provedel uses player image and banner chips. | Vicario now uses player image and the same banner chip structure. | Structure reusable; image and labels player-specific. | Ported structure only, not Provedel content. |
| Radar mobile | Full radar canvas was the default mobile view. | Same issue. | Selector could be visually tied to an oversized radar area. | GK runtime now adds a compact mobile summary and wraps full radar in an expandable `details`; selector remains visible outside the collapsed full radar. |
| Radar data | Four GK axes are present for both. | Four GK axes are present for Vicario. | Same structure, different axis scores. | Summary uses existing radar axis scores only. |
| Radar colors | Existing runtime already reads CSS variables for target/comparator colors. | Same. | No need for hardcoded comparator color. | Summary markers reuse runtime `COLORS` from CSS variables/fallbacks. |
| Metric bars mobile | Desktop-style rows were dense and prone to cramped labels/value text. | Same. | Mobile needed compact default while preserving individual values. | Runtime now keeps desktop rows for desktop and adds mobile `details` per metric with target summary plus all individual values/raw counts when available. |
| Metric data | Values derive from existing `action_split`, radar, and visual metrics. | Same. | No missing metric data detected for the required compact views. | No aggregation replacement; no frontend recomputation beyond existing display normalization already in runtime. |
| Visual blocks | Four visual blocks available. | Four visual blocks available. | Same structural availability. | Mobile CSS constrains visual grid to one column and prevents horizontal overflow. |
| Desktop | Provedel should remain structurally the same. | Vicario should remain structurally the same except page hygiene and generated hero/meta. | Mobile additions should not replace desktop. | CSS hides compact radar/bars on desktop and keeps existing desktop chart/bar layout. |
| Role page risk | Role pages use `sr-role-runtime.js` and `sr-role-report.css`. | GK pages use GK runtime/CSS. | Cross-role regression risk is mainly generator shared constants. | Did not modify role runtime/CSS or payloads. Role runtime version remains `radar-mobile-20260604`; heatmap MID/DEF branch untouched. |

## Structural Changes Ported

- Player-image hero and banner chips from the newer GK structure.
- Generated OG/Twitter metadata and player-specific report URLs.
- Method/footer/social hygiene aligned with role pages.
- GK-only compact mobile principles for radar and metrics.

## Not Ported

- Provedel editorial copy was not copied into Vicario.
- Provedel payload values, minutes, sample statuses, visual metrics, radar scores, and player IDs were not copied.
- Backend/export/parquet/DuckDB/pipeline changes were not made.

## Payload Notes

Vicario payload has the GK visual and radar data required for the requested UI work. It does not expose `PROFILE_READING`; Vicario narrative remains sourced from existing index/generator metadata. A payload/editorial follow-up can add `PROFILE_READING` later if the data contract should match Provedel more closely.

## Regression Risks

- The GK generator uses `gk_report.html` as its structure source, so it must normalize generated head metadata and section notes before reinserting player-specific values. This was fixed to keep repeated generation idempotent.
- Radar chart rendering inside a closed mobile `details` can size incorrectly; the runtime resizes the Chart.js radar when the full radar is opened.
- Role pages were intentionally not regenerated in this task.

## Browser QA Results

Local URL: `http://localhost:8765/`

| Page | Viewport | Result |
| ---- | -------- | ------ |
| Vicario | 320px | No horizontal overflow, compact radar summary visible, full radar closed, selector visible, 17 mobile metric details present, footer/method links correct, no JS errors. |
| Vicario | 375px | No horizontal overflow, compact radar summary visible, selector visible, no JS errors. |
| Vicario | 390px | No horizontal overflow, comparator changed to Josep Martínez, compact radar summary visible, 17 mobile metric details present, no JS errors. |
| Vicario | 430px | No horizontal overflow, compact radar summary visible, selector visible, no JS errors. |
| Vicario | 768px | No horizontal overflow, compact radar summary visible at breakpoint, selector visible, no JS errors. |
| Vicario | 1440px | No horizontal overflow, desktop full radar open, compact summary hidden, footer/method links correct, no JS errors. |
| Vicario | 390px radar open | No horizontal overflow after opening full radar, comparator remains Josep Martínez, radar details open, no JS errors. |
| Provedel | 390px | No horizontal overflow, compact radar summary visible, selector visible, no JS errors. |
| Provedel | 1440px | No horizontal overflow, desktop full radar open, compact summary hidden, no JS errors. |
| Stankovic role control | 390px | No horizontal overflow, role runtime loaded, GK runtime absent, role compact radar candidate and comparator present, 4 heatmap panels including `pitchProg`, no JS errors. |
| Stankovic role control | 1440px | No horizontal overflow, footer/method links correct, no JS errors. |

Screenshots:

- `docs/screenshots/gk_mobile/vicario-320-mobile.png`
- `docs/screenshots/gk_mobile/vicario-390-mobile.png`
- `docs/screenshots/gk_mobile/vicario-390-radar-open.png`
- `docs/screenshots/gk_mobile/vicario-1440-desktop.png`
- `docs/screenshots/gk_mobile/provedel-390-mobile.png`
- `docs/screenshots/gk_mobile/provedel-1440-desktop.png`
- `docs/screenshots/gk_mobile/role-stankovic-390-control.png`
