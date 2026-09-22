# Premier League — Handicap Analysis

Handicap-adjusted analysis of the Premier League: each club is assigned a
**handicap** (bonus points), which is applied to the season to give adjusted
standings, both at season level and game by game.

Seasons covered:

| Season | State | Page |
|---|---|---|
| 2026-2027 | in progress, updated weekly | `2026_2027/index.html` |
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
- `results.csv` — match results, in any of three layouts:
  the [football-data.co.uk](https://www.football-data.co.uk/englandm.php)
  export (`Date`, `HomeTeam`, `AwayTeam`, `FTHG`, `FTAG`, …), an
  [FBref](https://fbref.com) fixture export (`Date`, `Home`, `Away`, and a
  combined `Score` like `3–0`), or a minimal file with `date`, `home`,
  `away`, `home_goals`, `away_goals`. Blank separator rows and rows with no
  score are ignored, so a part-season export with future fixtures still
  listed works as-is.

  **Dates.** Sources disagree on order — football-data writes `dd/mm/yyyy`,
  FBref writes ISO `yyyy-mm-dd`. Feeding ISO dates to a day-first parser
  silently transposes day and month whenever both are ≤ 12 (`2026-09-05`
  becomes 9 May), which reorders fixtures with no error raised. ISO rows are
  therefore parsed strictly as ISO and only the rest as day-first, and where
  the file carries a weekday column (FBref's `Day`) the parsed dates are
  checked against it — a mismatch raises at load time.

Actual points are always derived from the results (3 for a win, 1 for a draw),
never hard-coded.

**Club names.** Each source spells clubs differently — the handicap sheet says
`Nott'ham Forest`, football-data says `Nott'm Forest`, FBref says
`Nottingham`. Both sides are resolved to a canonical club through
`CLUB_ALIASES` in `analysis.py`, which normalises punctuation and the
Utd/United/City/Town variants. An unrecognised spelling raises rather than
silently dropping a team; add it to `CLUB_ALIASES` instead of editing the
source data.

## Build

```bash
pip install -r requirements.txt
python build_site.py              # every season that has handicaps
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
├── 2026_2027/index.html
└── data/
    ├── 2025_2026/{season_handicap.csv, results.csv}
    └── 2026_2027/{season_handicap.csv, results.csv}
```

A season becomes buildable as soon as it has a `season_handicap.csv`: with no
results yet the page shows the handicaps and the odds market, and the table,
race and grids appear once `results.csv` lands.
