# Direct Engagements V1 Visual Check

Local server: `python -m http.server 8765` from `/Users/michele/Documents/Data_scouting_app/html5up-forty`.

| Page | Role | Payload OK | New group visible | Radar unchanged | Desktop OK | Mobile OK | Notes |
|---|---|---:|---:|---:|---:|---:|---|
| `oumar-solet.html` | DEF | Yes | Yes | Yes | Yes | Yes | group rendered as Italian label; lower-is-better Tempo bars ok |
| `marco-palestra.html` | DEF | Yes | Yes | Yes | Yes | n/a | group rendered as Italian label; lower-is-better Tempo bars ok |
| `curtis_jones.html` | MID | Yes | Yes | Yes | Yes | n/a | group rendered as Italian label; lower-is-better Tempo bars ok |
| `kone.html` | MID | Yes | Yes | Yes | Yes | n/a | group rendered as Italian label; lower-is-better Tempo bars ok |
| `stankovic.html` | MID | Yes | Yes | Yes | Yes | Yes | group rendered as Italian label; lower-is-better Tempo bars ok |

## Screenshot inventory

- `desktop_curtis_jones_direct_group.png`
- `desktop_kone_direct_group.png`
- `desktop_marco-palestra_direct_group.png`
- `desktop_oumar-solet_direct_group.png`
- `desktop_stankovic_direct_group.png`
- `mobile_oumar-solet_direct_group.png`
- `mobile_stankovic_direct_group.png`
- `radar_oumar-solet.png`
- `radar_stankovic.png`

## Verification notes

- No JavaScript console errors were reported in the browser verification pass.
- External payloads are referenced from the page HTML and the payload JSON files contain the direct-engagement group and labels.
- The rendered group label is localized as `Ingaggio difensivo diretto`; the requested metric labels render as `Ingaggi diretti /90`, `Tempo mediano di ingaggio`, and `Ingaggi entro 2s`.
- Detail bars render for both target and source comparison blocks. `Tempo mediano di ingaggio` uses lower-is-better scaling in the payload comparison bars.
- Radar payloads remain five axes, contain no direct-engagement metric names/labels, and keep `usesPca: false`.
- Desktop overflow was `0` for all five pages. Mobile overflow at 390px was `0` for `oumar-solet.html` and `stankovic.html`.
