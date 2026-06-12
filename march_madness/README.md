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
extract_model.py   xlsx -> data/model_2019.json, + --report verification
fix_workbook.py    writes March_Madness_20190318_fixed.xlsx
build_site.py      data/model_2019.json -> index.html
data/              extracted model inputs
reference/         original workbook + Aaron Brown's paper
```

Rebuild: `python3 extract_model.py && python3 build_site.py`
(needs `openpyxl`).

## Next

Planned: validate the factor model against actual tournament results for
recent years (probabilities/frequencies/factor inputs per season, then score
the star ratings against what happened) — the same treatment as
[`nfl_report/`](../nfl_report/).
