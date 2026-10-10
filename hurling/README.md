# Hurling — GAA.ie Hurling Team of the Week 2026

A mobile-friendly app covering the **GAA.ie Hurling Team of the Week** and **Hurler of the
Week** for the 2026 championship.

## 🔗 View the app

**▶ [Open the live table](https://htmlpreview.github.io/?https://github.com/ZeNoonan/Research/blob/claude/hurling-team-of-week-table-gb4eu5/hurling/standalone.html)**

This link renders `standalone.html` (data baked in) through GitHub's HTML-preview proxy, so
it works straight from a phone with no server. The view selector switches between:

- **Teams: grid (player × week)** — pivot/dataframe (jersey number per cell, totals) *(default)*
- **Teams: by week** — full XV for each week
- **Teams: most selected** — leaderboard of appearances
- **Hurler of the Week: by week** — weekly winner + the three nominees
- **Hurler of the Week: nominations grid** — player × week; ★ = won, • = nominated
- **Hurler of the Week: most awards** — leaderboard of winners

Both grids scroll inside their own pane, so the week headings (with round abbreviations such
as `RD 1`, `PROV-F`, `QTR-F`, `SEMI-F`) and the player column stay pinned while you scroll.

> `standalone.html` is a frozen snapshot — regenerate it with `python3 build_standalone.py`
> after any data change. The live `index.html` (below) always reflects the latest JSON.

## Files
- `index.html` — responsive app (renders from the JSON data files). On a phone, the list
  views collapse into stacked cards; the grids keep their columns and scroll. Filters by
  week/county plus a player search.
- `standalone.html` — self-contained build of `index.html` with both datasets inlined.
- `build_standalone.py` — regenerates `standalone.html` from `index.html` + the JSON files.
- `data/teams_of_the_week_2026.json` — Team of the Week data store.
- `data/hurlers_of_the_week_2026.json` — Hurler of the Week data store (winner + nominees).

## Viewing on your phone
The page loads its data with `fetch()`, so it must be served over HTTP (it won't load data
from a `file://` path). The simplest route is **GitHub Pages** — once pushed, the page is
available at `…/hurling/index.html`. Locally you can run `python3 -m http.server` inside the
`hurling/` folder and open `http://localhost:8000/`.

## Data model
**Team of the Week** — each week is an object in `weeks[]`:

```json
{
  "id": "ai-shc-qf",
  "label": "All-Ireland SHC Quarter-Finals (21 Jun 2026)",
  "date": "2026-06-21",
  "round": "All-Ireland SHC Quarter-Finals",
  "abbr": "Qtr-F",
  "hurler_of_the_week": { "player": "Brian Hayes", "county": "Cork" },
  "players": [
    { "no": 1, "position": "Goalkeeper", "player": "Éibhear Quilligan", "club": "",
      "county": "Clare", "opponent": "Dublin", "notes": "", "confidence": "confirmed" }
  ]
}
```

Per-player fields: `county`, `opponent` (the team that county played in the round that
earned the selection), `confidence` (`confirmed` or `unconfirmed`), `notes` (free text), and
optional `club`/`source` (`source` is only shown as a link when it is a URL). `abbr` is the
short round label shown above the date in the grid. The standard 1–15 position names are in
the `positions` array at the top of the JSON.

**Hurler of the Week** — each week has the winner (`player`, `county`, `opponent`), a
`nominees` list of `{player, county}`, and an `abbr`. This file is the source of truth for
winners: the team views badge a player as Hurler of the Week by matching the HotW week dated
within two days of the team week, on player **and** county (there are two Brian Hayes —
Cork and Dublin).

Keep player spellings identical across weeks (e.g. `Seán Rynne`, `Dónal Burke`,
`Gearóid Hegarty`) — the grids and leaderboards group on the exact name + county.

## Data status
Built from the official GAA.ie graphics (supplied as screenshots), championship weeks only.
Names are transcribed directly from each graphic and every county is confirmed.

- **Team of the Week:** 8 weeks — 20 Apr to the 6 Jul semi-finals. No graphic yet for
  **5 May** (the Clare v Limerick weekend) or for the **final**.
- **Hurler of the Week:** winner + nominees for all 8 weeks from 20 Apr to the 21 Jun
  quarter-finals. The **semi-final** and **final** weeks are still to add.
- **Opponents** come from the Munster/Leinster SHC and All-Ireland results. Six tier-2
  selections (Joe McDonagh Cup / Christy Ring) have no opponent recorded yet.
