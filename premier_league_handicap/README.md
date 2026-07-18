# Premier League 2025-2026 — Handicap Analysis

Handicap-adjusted analysis of the 2025-2026 Premier League: a per-team
**handicap** (bonus points) is applied to the season, giving adjusted
standings at season level and game by game.

Two front-ends share the same data and computations:

- **`index.html`** — a static, self-contained page served by **GitHub Pages**:
  <https://zenoonan.github.io/Research/premier_league_handicap/>
  (adjusted table, actual + handicap stacked bars, click-to-highlight race
  chart, 20×38 cumulative grid, game-by-game explorer, and
  performance-vs-handicap analysis, in light and dark mode).
  Regenerate its embedded data with `python build_site.py` after changing
  anything in `data/`.
- **`app.py`** — the original Streamlit app (`streamlit run app.py`).

## The handicap

Each team has a fixed handicap — a number of points added to their actual
season total to produce an **adjusted points** total.

- **Season table:** `adjusted points = actual points + handicap`, sorted by
  adjusted points. Actual points and the handicap are shown alongside, not
  hidden.
- **Game by game:** the handicap is spread evenly across the 38 games
  (`handicap ÷ 38` per game) and added to each game's result. For example, a
  team with a 38-point handicap gets `+1` per game: a win becomes `3 + 1 = 4`,
  a draw becomes `1 + 1 = 2`. The per-game adjusted points sum back to
  `actual points + handicap`.

## Data

- `data/season_handicap_2025_2026.csv` — the supplied handicaps (`team`, `handicap`).
- `data/premier_league_results_2025_2026.csv` — all 380 matches with scores
  (football-data.co.uk format). Actual points are derived from these results
  (3 for a win, 1 for a draw), so the standings are not hard-coded.

Team names differ slightly between the two files (e.g. `Manchester Utd` vs
`Man United`); the mapping lives in `analysis.py`.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Layout

```
premier_league_handicap/
├── index.html        # static GitHub Pages site (self-contained, data embedded)
├── build_site.py     # regenerates the data blob inside index.html
├── app.py            # Streamlit UI (adjusted table + game-by-game tabs)
├── analysis.py       # data loading and handicap computations
├── requirements.txt
├── README.md
└── data/
    ├── season_handicap_2025_2026.csv
    └── premier_league_results_2025_2026.csv
```
