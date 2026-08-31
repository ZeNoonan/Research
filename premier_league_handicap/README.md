# Premier League — Handicap Analysis

Handicap-adjusted analysis of the Premier League: each club is assigned a
**handicap** (bonus points), which is applied to the season to give adjusted
standings, both at season level and game by game.

Seasons covered:

| Season | State | Page |
|---|---|---|
| 2026-2027 | in progress — awaiting results | `2026_2027/index.html` (built once results land) |
| 2025-2026 | complete | `2025_2026/index.html` |

The folder's canonical Pages URL always serves the **most recent season that
has results**:

<https://zenoonan.github.io/Research/premier_league_handicap/>

## The handicap

- **Season totals:** `adjusted points = actual points + handicap`.
- **Game by game:** the handicap is spread evenly across the 38 games of a
  season (`handicap ÷ 38` per game) and added to each result. With a 38-point
  handicap that is `+1` per game: a win becomes `3 + 1 = 4`, a draw
  `1 + 1 = 2`.
- **Part-played seasons:** a team only banks the share of the handicap it has
  earned so far, `handicap × played ÷ 38`, so the table is fair while the
  season is in progress. The pages also show the full-handicap total. Once
  every team has played 38 games the two are identical.

## Data

Each season lives in `data/<season>/`:

- `season_handicap.csv` — `team`, `handicap`, and optionally `odds`
  (decimal odds on that team to win the handicap-adjusted league).
- `results.csv` — match results. Either the full
  [football-data.co.uk](https://www.football-data.co.uk/englandm.php) layout
  (`Date`, `HomeTeam`, `AwayTeam`, `FTHG`, `FTAG`, …) or a minimal file with
  `date`, `home`, `away`, `home_goals`, `away_goals`. Rows with blank scores
  are treated as unplayed fixtures and ignored, so a part-season export works
  as-is.

Actual points are always derived from the results (3 for a win, 1 for a draw),
never hard-coded. Team names differ between the two files (e.g.
`Manchester Utd` vs `Man United`); the mapping lives in `analysis.py`, which
raises if any team in the results has no handicap entry.

## Build

```bash
pip install -r requirements.txt
python build_site.py              # every season that has results
python build_site.py 2026_2027    # just one
streamlit run app.py              # interactive version, season picker in the sidebar
```

`build_site.py` fills `template.html` with the season's data and writes
`<season>/index.html`, plus `index.html` for the latest season.

## Layout

```
premier_league_handicap/
├── index.html        # latest season with results (generated)
├── template.html     # shared page source — edit this, not index.html
├── build_site.py     # renders template + season data -> pages
├── analysis.py       # loading, handicap maths, standings
├── app.py            # Streamlit version
├── requirements.txt
├── README.md
├── 2025_2026/index.html
└── data/
    ├── 2025_2026/{season_handicap.csv, results.csv}
    └── 2026_2027/{season_handicap.csv}
```
