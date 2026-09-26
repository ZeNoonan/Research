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
- `football_data.csv` — optional: the season's
  [football-data.co.uk](https://www.football-data.co.uk/englandm.php)
  export, used for its Asian handicap lines (see below). A season without one
  falls back to `results.csv` when that file is itself a football-data export
  with an `AHh` column, as 2025/26's is.
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

## Against the market: the Asian handicap

The pre-season handicap is one rating per club, fixed in August. The Asian
handicap is the market's line for each individual match, re-set before every
game, so the page's second part asks a different question: not who is beating
what was expected in August, but who has beaten the market's line match by
match.

- **The line.** football-data's `AHh` is the pre-closing market handicap for
  the **home** team; negative means the home side gives goals. The away side's
  line is its negation. A side **covers** when its goal difference plus its line
  is positive; zero is a push.
- **Quarter lines** (x.25 / x.75) split the stake across the two neighbouring
  lines — −0.75 is half on −0.5 and half on −1 — so they can settle as a half
  win or half loss. About half of all lines are quarter lines (24 of 50 in
  2026/27 so far, 198 of 380 in 2025/26), so this is the common case, not an
  edge case.
- **STDC** (season-to-date cover) is net covers: +1 a win, +½ a half win, 0 a
  push, −½ a half loss, −1 a loss. It is the same measure as the NFL report's
  STDC, extended to half results. The table sorts on it, then on **goals vs
  line** (the summed margin by which a side beat or missed its lines).
- **The comparison.** Each club's Asian handicap position is set against its
  position in the adjusted league table. **A gap between the two is not in
  itself the market mis-rating a club**: each weekly line allows for the
  opponent and venue where the flat August handicap does not, the adjusted table
  counts points where covers count goal margins, and much of any gap is chance.
  Over 2025/26 the gap correlates +0.50 with the average line a club faced —
  underdogs rank systematically higher against the market — which is largely
  structural. Whether the market has under- or over-rated a club so far is its
  **STDC sign**: positive, its lines were too cautious; negative, too generous.
- **How much is chance.** Against an efficient market, covers are close to coin
  flips. The page compares the spread of STDC across clubs with what coin-flip
  covers would produce. In 2025/26 it was 5.05 against 5.63 (below chance), and
  a club's first-half and second-half cover records correlated −0.13, so runs
  did not persist. Read the table as a record of what happened, not proof of
  which clubs the market mis-rated.
- **Checks.** Settlement is zero-sum — every bet has an equal and opposite side —
  so total STDC and total goals vs line are exactly zero league-wide. Where a
  season has both a lines file and `results.csv`, every fixture in both must
  agree on date and score, or the build stops with the clashing fixtures listed.
- **Missing lines.** If `AHh` is missing but the closing line `AHCh` exists, the
  closing line stands in and the page says so. (One 2025/26 match, Brighton v
  Chelsea on 21 April, has no pre-closing line; Brighton won 3–0, so they cover
  at any line short of giving three goals.) A match with neither is left out.

Prices (the odds attached to each line) are not used: the table measures
whether sides covered, not what backing them would have returned. The page
states the typical price and the break-even cover rate it implies (about 1.87
and 53.5% in 2026/27), since a side with an even record against its lines has
lost money for anyone backing it.

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
    └── 2026_2027/{season_handicap.csv, results.csv, football_data.csv}
```

A season becomes buildable as soon as it has a `season_handicap.csv`: with no
results yet the page shows the handicaps and the odds market, and the table,
race and grids appear once `results.csv` lands. The Asian handicap part appears
once there are results and a lines file.

**Weekly update:** refresh `results.csv` and `football_data.csv`, then run
`python build_site.py`. If the two files disagree on any fixture the build
stops and lists it; if one is simply a week behind, the page says the two
parts are not yet level.
