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

## Data status — PARTIAL / INDICATIVE
The table is **not complete**. The build environment's network policy blocks all direct web
access (gaa.ie, Twitter/X, Facebook, Wikipedia and local county sites all return 403), and
web search only returns short snippets — never the full 15-player team sheets.

What's loaded is a **best-effort, partial set of individual selections** corroborated from
county/news sources, with a `confidence` flag and a `source` link on each entry. They are
**not full XVs**, positions/clubs are mostly unknown, and the search summariser was observed
to hallucinate (e.g. it returned "Brian Hayes (Dublin)" — Hayes is a Cork player), so only
corroborated entries were kept. **Verify everything against gaa.ie before relying on it.**

To complete the table, paste the full weekly teams from gaa.ie (or have the network policy
allow `gaa.ie`/`x.com` so they can be fetched directly).
