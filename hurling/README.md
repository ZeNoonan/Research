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
- **Hurler of the Week: most awards** — leaderboard of winners

> `standalone.html` is a frozen snapshot — regenerate it with `python3 build_standalone.py`
> after any data change. The live `index.html` (below) always reflects the latest JSON.

## Files
- `index.html` — responsive app (renders from the JSON data files). On a phone, the team
  tables collapse into stacked cards; the grid scrolls horizontally. Filters by week/county
  plus a player search.
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
Each week is an object in `weeks[]`:

```json
{
  "id": "2026-06-22",
  "label": "Week of 22 June 2026",
  "date": "2026-06-22",
  "round": "All-Ireland SHC Quarter-Finals",
  "source_url": "https://www.gaa.ie/article/gaa-ie-hurling-team-of-the-week-x2851",
  "hurler_of_the_week": { "player": "Brian Hayes", "county": "Cork" },
  "players": [
    { "no": 1, "position": "Goalkeeper", "player": "Éibhear Quilligan", "club": "",
      "county": "Clare", "opponent": "Dublin", "notes": "", "confidence": "confirmed" }
  ]
}
```

Per-player fields: `county` (blank when not yet confirmed), `opponent` (the team that county
played in the round that earned the selection), `confidence` (`confirmed` or `unconfirmed`),
`notes` (free text), and optional `club`/`source`. The standard 1–15 hurling position names
are listed in the `positions` array at the top of the JSON.

## Data status
Built from the official **GAA.ie Hurling Team of the Week graphics** (supplied as
screenshots), championship weeks only. Player names are transcribed directly from each
graphic, so the XVs are complete and accurate.

Two known gaps, both flagged in the data:
- **Counties** that couldn't be read from the tiny on-graphic crest are left **blank** with
  `confidence: "unconfirmed"` (shown with an "unconfirmed" chip on the page).
- **Opponents** are filled from the Munster/Leinster SHC and All-Ireland QF results. Tier-2
  players (Joe McDonagh Cup / Christy Ring) have a **blank opponent** where the fixture
  couldn't be verified (direct access to gaa.ie/Wikipedia is blocked by the egress policy;
  fixtures were reconstructed via web search).

Weeks before 20 April and after the quarter-finals (provincial finals, semi-finals, final)
are not yet added — supply the graphic and they can be appended the same way.
