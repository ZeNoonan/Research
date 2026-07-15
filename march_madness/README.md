# March Madness — Aaron Brown's factor-investing bracket model

A web view and verified re-implementation of **Aaron Brown's "Quants go mad in
March"** NCAA bracket-pool spreadsheet (March 18, 2019 version), with a bug in
its Value-pick pipeline found and fixed. The source workbook and paper are in
[`reference/`](reference/).

**Open [`index.html`](index.html)** — a self-contained page (no external
assets) showing the Bracket tab's star ratings, the editable picks grid, the
live pool win-probability calculation and per-team slot-calculation detail.
Round points, pool size and picks are all editable, and a toggle switches
between the published and fixed formulas.

**Open [`value_tutorial.html`](value_tutorial.html)** — an in-depth tutorial
on the **Value factor**: why variance wins pools, the full derivation of the
ΔEV/ΔVar/ratio pipeline, a two-team toy example small enough to check by hand
(with live sliders), a step-by-step trace of the calculation for any 2019
team and round (fixed or as-published formulas, replaying both bugs), and a
"value frontier" chart of all 64 teams against the ratio boundary.

## The model

Five factors, in the spirit of Fama–French factor investing, each contribute
one star to a team's rating for a round (0–5 stars):

| Factor | Level | Rule |
|---|---|---|
| **Quality** | team | ESPN BPI above the median of the four teams sharing the seed |
| **Size** | team | recent-tournament-success score above seed median |
| **Momentum** | team | top-8 seeds: >3 wins in last 5 regular-season games; bottom-8 seeds: <4 (inverted — weak finishers earned at-large bids) |
| **Value** | slot/round | picking the team gains at least as much score variance (vs the pool average) as it costs in expected points — or it is the favorite |
| **Bet against beta** | slot/round | non-favorite within 0.5 win probability of the favorite, picked less often by the field relative to its probability |

The page also reproduces the workbook's estimate of your chance of winning the
pool: a Gaussian approximation of your score deviation versus the field's,
integrated against the order statistic of the pool (`NORMSINV`/`NORMDIST`
columns O:AB of the Bracket tab).

## The bug (and the fix)

The 'Slot calculations' tab, columns **AL:AQ "Variance difference"**, computes
the variance gained by picking team *i* over the slot favorite. The paper's
formula is

> ΔVar = (p − p₀)(1 + 2S) − p² + p₀² − 2(p·f − p₀·f₀)

with S = the slot's expected wins for the average entry — already computed in
column B *of the same row*.

1. **The reference bug** — `AL3` reads `(1+2*B41)`: the S of the team **38
   rows further down**, a fill-down error. From row 29 onward the reference
   walks off the data entirely, so more than half the teams were computed with
   S = 0 (Excel treats the empty cells as 0).
2. **The sign bug (surfaced by fixing #1)** — the Value flag (`BD:BI`) tests
   `ratio > 1`, where ratio = cumulative ΔVar ÷ cumulative ΔEV. The sheet
   stores ΔEV as a *negative* number for non-favorites, so the paper's rule
   ("must increase variance by at least as much as it reduces expected value")
   is `ratio ≤ −1`. As published the flag fired only for picks whose variance
   *loss* exceeded the EV loss — the opposite of the intent.

**Effect:** 100 of 384 Value flags change (98 gained, 2 lost). As published,
the only championship-column Value pick was Duke. Fixed, the championship
Value picks are Duke, Virginia Tech, Michigan State, Gonzaga, Texas Tech,
Michigan, Virginia and Kentucky — the 2019 final was **Virginia over Texas
Tech**, with **Michigan State** also in the Final Four, and Texas Tech becomes
the only 5-star champion pick on the board.

[`March_Madness_20190318_fixed.xlsx`](March_Madness_20190318_fixed.xlsx)
contains both formula fixes (values recalculate when opened in
Excel/LibreOffice); everything else is untouched.

## Verification

`extract_model.py --report` re-implements the workbook in Python — including
both bugs, and Excel's 15-significant-digit comparison fuzz — and checks it
against the workbook's cached values:

| Check | Result |
|---|---|
| Slot calculations (S, p₀, p₀f₀, ΔEV, variance, ΔVar, ratio, Value, BAB) | **4,224/4,224 cells exact** |
| Bracket star ratings | **384/384 exact** |
| Expected points / variances (you & field) | exact to 1e-13 |
| Pool win probability | matches to 4×10⁻⁸ (Excel's own `NORMSINV` precision) |

The page's JavaScript was cross-checked against the Python: identical flags
everywhere, win probability within 1.4×10⁻⁹.

## Data notes

- Probabilities, pick frequencies, factor values, default picks, round points
  and pool size all come from the workbook (frequencies from ESPN pool data).
- Play-in slots (NDS/NCC, FD/PV, Bel/Tem, AS/SJ) carry the average
  Quality/Size/Momentum of the two candidate teams, as in the workbook.
- The workbook lists "Mississippi State" twice; the South 8 seed should be
  Mississippi (Ole Miss) and its factor lookups therefore return Mississippi
  State's values. Kept as-is, flagged with * on the page.

## Files

```
extract_model.py         xlsx -> data/model_2019.json, + --report verification
fix_workbook.py          writes March_Madness_20190318_fixed.xlsx
build_site.py            data/model_2019.json -> index.html
build_value_tutorial.py  data/model_2019.json -> value_tutorial.html
data/                    extracted model inputs
reference/               original workbook + Aaron Brown's paper
```

Rebuild: `python3 extract_model.py && python3 build_site.py &&
python3 build_value_tutorial.py` (extraction needs `openpyxl`; the two site
builders are stdlib-only).

## Next — validation against actual results

Planned: validate the factor model against real tournament outcomes for recent
years (2021–2026; 2020 was cancelled), scoring the star ratings against what
happened — the same treatment as [`nfl_report/`](../nfl_report/).

Inputs needed per season, and where each comes from:

| Input | Source | Status |
|---|---|---|
| Results (who beat whom) | public records | easy, exact |
| **Size** factor | computed from prior results via Brown's formula | exact, no external data |
| **Momentum** factor | last-5 regular-season records | exact, no external data |
| Win probabilities (per round) | [FiveThirtyEight forecast archive](https://github.com/fivethirtyeight/data/tree/master/historical-ncaa-forecasts) (through 2023) | reachable |
| **Quality** (BPI) | ESPN BPI / a public power rating | obtainable |
| **Pick frequencies** | see below | the hard one |

Only the **Value** and **Bet-against-beta** flags and the win-probability block
need pick frequencies; Quality/Size/Momentum validate against results alone.

### Pick-frequency data: two collection paths

ESPN published "Who Picked Whom" (pick % per team per round) every year. We
have 2019 complete from Brown's workbook (our calibration year). For the rest:

- **`scrape_pick_frequencies.py`** — pulls archived ESPN Who-Picked-Whom pages
  from the Wayback Machine (2010–2022, ex-2020) across the three URL hosts ESPN
  used over the years. Needs `web.archive.org` network egress. Parser is
  stubbed until we inspect one year's markup.
- **`ingest_kaggle.py`** — fallback for years the Wayback route can't reach
  (notably 2023+, after ESPN moved to a JS platform). Ingests a downloaded
  Kaggle dataset (e.g. `nishaanamin/march-madness-data`) — works from a manual
  browser download (no special egress) or the Kaggle API with a token. Run
  `--inspect` first to see each CSV's schema, then ingest to
  `data/pick_freq_<year>.csv`.

Where no real frequencies exist, a **proxy** is planned (seed-level pick curves
× within-seed allocation by win probability and Size/brand, with a
championship-futures adjustment), fit and tested out-of-sample against the 2019
ground-truth sheet so we can quantify how much the Value/BAB flags move when
proxy frequencies replace real ones.
