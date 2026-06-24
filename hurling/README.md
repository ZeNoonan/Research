# Hurling — GAA.ie Hurling Team of the Week 2026

A mobile-friendly table of every player picked in the **GAA.ie Hurling Team of the Week**
during the 2026 season.

## Files
- `index.html` — responsive table (renders from the JSON data file). On a phone, each row
  collapses into a stacked card; on desktop it's a full table. Includes filters by week and
  county, plus a player/club search box.
- `data/teams_of_the_week_2026.json` — the canonical data store. The page reads from this,
  and any later analysis should reuse it too.

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
    { "no": 1, "position": "Goalkeeper", "player": "", "club": "", "county": "", "notes": "" }
  ]
}
```

`notes` is free text for extra detail (e.g. a player's scoreline). The standard 1–15 hurling
position names are listed in the `positions` array at the top of the JSON.

## Data status
The data is **not yet populated**. The build environment's network policy blocks all direct
web access (gaa.ie, Twitter/X, Facebook, Wikipedia, local county sites all return 403), and
web search only returns short snippets — not the full 15-player team sheets. The full teams
need to be supplied from an accessible source before the table can be filled in.
