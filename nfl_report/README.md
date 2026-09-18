# NFL Report — replicating Aaron Brown's demonstration system

## 📋 What I need from you

*Anything I'm waiting on lives here, newest first. Nothing is urgent unless marked.*

### Every week, to keep 2026–27 running

1. **Results** — the pro-football-reference rows for the games just played,
   including the `TOW`/`TOL` turnover columns. **Turnovers are the blocker:** two
   of the five factors read them, and without them the next week cannot be picked
   at all (the system deliberately declines rather than guessing).
2. **Odds** — the nflverse `games` export (what you have been sending). Ideally
   **as late as practical before the Thursday kick-off**: lines are imported once
   and never overwritten, so a later export means a number closer to closing.
   Week 2's Lions–Bills came in at −3.5 on the Tuesday and had moved to −5.5 by
   kick-off. It did not change that result, but one day it will.

### One decision, whenever you feel like it

3. **2025's 64 opening lines.** Those games use an *opening* price because the
   close was missing. They match the second source far worse than real closes do
   (11% exact vs 37%), and one — Raiders **+15.5** as a home underdog — is almost
   certainly corrupt. Replacing them with closing lines would make the season's
   basis consistent. I have not done it because it rewrites 64 existing prices
   **and it happens to improve the record** (44–43 → 50–40), which is a reason for
   caution rather than a reason to do it. Your call: leave, or replace.

### Optional, only if it is easy

4. **2018 results with turnovers** (PFR format). It is the one thing that would
   finish 2019: with no 2018 file, that season's week 1 has no last-game
   turnovers and no power ratings. Lines for 2018 are already on hand — only the
   turnovers are missing.

### Nothing needed for these

- 2025's 14 unpriced games — **fixed**, all now have lines.
- Missing neutral-venue flags — **fixed** for 2020, 2022, 2025 and 2026.
- The 2026 opener's transposed team labels and misplaced spread column — **fixed**.


A project to **replicate Aaron Brown's published `NFL Report`** sheets
(2010–2016): a weekly NFL against-the-spread betting system built as a public
demonstration that a simple, additive, binary-factor model can beat the spread,
then extended to generate the same report from raw data for 2019–2026 —
including the 2026–27 season as it is played. The
source write-ups are in [`reference/`](reference/).

The reports are tables of one row per game. This project reproduces, in
particular, the columns we set out to replicate:

| Column | Meaning |
|---|---|
| **Home / Away LGT** | *Last Game Turnover* — net giveaways in the team's previous game |
| **Home / Away STDC** | *Season To Date Cover* — net spread covers so far this season |
| **Home / Away Power** | *Power rating* — the team's strength in points |
| **System #** | net count of factors favouring the home (+) or away (−) team |
| **System Bet** | the team the model bets on |
| **Result** | whether that pick won (`W`) or lost (`L`) against the spread |

## The model

Five **binary factors** each cast one vote: **+1** favours the home team, **−1**
favours the away team, **0** is neutral. Their sum is the **System #**. The
system **bets the home team when System # ≥ +3** and the **away team when
System # ≤ −3**; otherwise it passes. (Equivalently: bet once at least three
factors agree and none of the rest oppose.)

| # | Factor | Votes home (+1) when… | Votes away (−1) when… |
|---|---|---|---|
| 1 | **Power / over-reaction** | the line makes home a bigger underdog / smaller favourite than the power ratings imply | the reverse |
| 2 | **Turnover — home** | `home_lgt > 0` (home gave the ball away last game) | `home_lgt < 0` |
| 3 | **Turnover — away** | `away_lgt < 0` (away took the ball away last game) | `away_lgt > 0` |
| 4 | **Hunger — home** | `home_stdc < 0` (home is "hungry": failing to cover) | `home_stdc > 0` |
| 5 | **Hunger — away** | `away_stdc > 0` (away is "fat": covering too much) | `away_stdc < 0` |

The intuitions, straight from the source:

- **Over-reaction** — line moves overshoot, so back the team the line moved
  against relative to a slow-moving power rating.
- **Turnovers** — turnovers are largely random, so a team that gave the ball
  away last game is better than its result looked (and the line over-corrects).
- **Hunger** — bookmakers like every team to cover ~half the time, so back the
  team that has been failing to cover ("hungry") and fade the one that has been
  covering ("fat").

### Sign conventions (as stored in the report and these CSVs)

- **`line`** — home spread. **Negative = home favoured**, positive = home
  underdog (the points the home team receives).
- **`lgt`** — `giveaways − takeaways` in the team's last game. Positive = gave
  the ball away more than it took it.
- **`stdc`** — `covers − non-covers` this season so far. Negative = hungry.
- **`power`** — team power rating in points. The power-implied line is
  `away_power − home_power` (see note below).

> **Power factor detail.** The 3-point home-field advantage lives *inside the
> rating fit* (the ratings are neutral-field), but at pick time the published
> reports compare the line to the raw power difference `away_power − home_power`
> with **no** home-field term re-added. Refitting ratings from the reports' own
> lines (4-week window, weights 1/½/¼/⅛, 3-point HFA) reproduces the published
> implied lines at 0.999 correlation from week 5 on. Because no HFA is re-added,
> the comparison carries a ~2-point average home-edge residual and the power
> factor leans away (2016: 195 away votes vs 72 home) — a genuine feature of the
> published system. Using the raw difference reproduces 532/534 published
> `System #` values; the 2 misses are exact ties created by the power column
> being rounded to one decimal in the PDF.

## Replication status

`validate.py` rebuilds the derived columns from each published report and
compares them to Brown's values, for all seven sheets (2010–2016):

| Check | result across 2010–2016 |
|---|---|
| **System #** (from LGT/STDC/Power + line) | **1846/1869 (98.8%)** |
| **Bet side** (from System #) | 595/599 bets |
| **Result** (from scores + line + #) | 595/599 graded bets |
| **STDC** rebuilt independently from scores + lines | ~90% |

So the **betting logic is fully reproduced**. The handful of `System #` misses are
the rounded-power ties noted above (a power column shown to one decimal creates
the occasional exact tie). The STDC reconstruction — done from scratch,
using only prior scores and lines — lands ~90–92%; the remaining gap comes from
occasional half-point/push differences between the displayed `Line` and the
spread used to grade an earlier game's cover. Closing that is a Phase 2 data
task. (The denominator excludes each team's first game of the season, whose true
STDC is 0 by definition.)

### Data note: the Seahawks & Steelers names

In the source PDFs the two tracking teams, **Seahawks** and **Steelers**, sit on
a separate text layer, so in the flat text stream their *team-name* cells are
emitted out of order (they pile up at the foot of each page) rather than in their
rows. The parser therefore reads **team names from word coordinates** — grouping
words into rows by their y-position and taking the home/away name from the home
(x ≈ 97) and away (x ≈ 145) columns — which places every name correctly. Two
games drop the tracking team's name from the PDF entirely; those two are filled
explicitly (see `STRAGGLERS` in `parse_reports.py`), each verified both from the
schedule and from internal evidence (the other tracking team already appears on
that date, and the blank side's power rating continues the remaining team's
week-to-week trajectory). All team names are now recovered — there are no blank
cells.

## Files

```
nfl_report/
├── README.md          # this file
├── requirements.txt
├── parse_reports.py   # PDFs -> data/report_2015.csv, report_2016.csv
├── model.py           # the five-factor engine (the system logic)
├── season_report.py   # raw odds + results -> data/report_<year>.csv (Phase 2)
├── enrich_odds.py     # repair odds gaps from the nflverse schedule export
├── factor_analysis.py # Brown's factor diagnostics (marginal contributions)
├── heatmaps.py        # team x week STDC / power pivots + RdYlGn heatmaps
├── validate.py        # rebuild columns and compare to the published reports
├── app.py             # Streamlit viewer for the replicated reports
├── build_site.py      # data CSVs -> index.html (static mobile-friendly report)
├── index.html         # generated web view of the analysis (works on phones)
├── data/
│   ├── report_2015.csv, report_2016.csv     # parsed from the published PDFs
│   ├── report_{2019..2026}.csv              # generated by season_report.py
│   ├── results_{2019..2026}.csv             # raw: PFR games + turnovers
│   ├── odds_{2019..2026}.csv                # raw: aussportsbetting odds
│   └── schedule_lines.csv                   # nflverse schedule + closing spreads
└── reference/         # source material
    ├── NFL_Report_2015.pdf
    ├── NFL_Report_2016.pdf
    ├── NFL_Demonstration.pdf      # how the system is built
    └── Wilmott_NFL_Article.docx   # the published article
```

## Seasons generated from raw data

`season_report.py` produces the same report table, from raw inputs, for every
season with files in `data/`: currently **2019 through 2026**, a fully
consecutive run (plus the published 2015/2016). Seasons are named by **start
year** (a season runs Sept–Feb), matching `report_2016`. Note the source files
are named by the Super-Bowl calendar year, one ahead — the file labelled
"2025" is the **2024** season.

Each season uses two raw inputs (slimmed to CSV in `data/`): a
pro-football-reference games table with turnovers, and an aussportsbetting odds
export whose spread is **`Home Line Close`** (falling back to `Home Line Open`
where the close is missing). Games are matched on team pair within ±1 day (the
odds export dates some late/international kick-offs a day differently);
neutral-venue games are re-oriented to the odds file's home team. Scores come
from the results file; the odds file is used only for the line, and a score
disagreement is reported as a warning (one occurs — a wrong score in the 2023
odds row for Buccaneers–Panthers).

**Power ratings** are fit per week as the demonstration describes — a weighted
least-squares fit of the last four weeks' lines (weights 1, ½, ¼, ⅛) with a
3-point home-field advantage inside the fit (0 for neutral venues) — the
construction verified at 0.999 correlation against the published 2016 implied
lines.

**Prior-season carryover.** When the immediately preceding season is present,
week 1's last-game turnovers carry over from the prior season's last game, and
the first weeks' power ratings are fit on the prior season's last regular
weeks. This applies to 2020–2026; only **2019** (no 2018 file) keeps a blank
week 1 (LGT 0, power neutral). Team names are normalised to current nicknames
so a franchise tracks across renames (Washington Redskins → Football Team →
**Commanders**; Oakland/Las Vegas **Raiders**).

### Repairing the odds files (`enrich_odds.py`)

`data/schedule_lines.csv` is a slimmed [nflverse](https://github.com/nflverse)
`games` export (2018–2026) — an independent second source carrying each game's
closing spread and whether it was played at a **neutral venue**. It cross-checks
cleanly against the primary data: every game matches on team pair within ±1 day,
with **zero score disagreements across ~1,900 games**, and its spreads land
within a point of ours 94% of the time (it is a different book, so exact
agreement is only ~59%).

`enrich_odds.py` uses it to repair two specific gaps, and **never overwrites a
line we already have**, so each season keeps the book it was built on:

- **Missing lines** — 14 games of 2025 (all of week 5) had neither a closing nor
  an opening line and so could never be bet. All 14 are now filled.
- **Neutral venues** — an international or relocated game has no home-field
  advantage, and the power fit zeroes its 3-point term accordingly. The odds
  export flags only some: 6 were missing in 2025, 2 in 2020 (the COVID-era 49ers
  "home" games played in Arizona), 1 in 2022, and 8 in 2026.

Both repairs shift some history, which is recorded here rather than quietly
absorbed: 2025 goes from 78 bets / 41–37 / +0.3u to **87 bets / 44–43 / −3.3u**
(the 14 newly-priced games went 3–6), and the 2020 neutral flags propagate
through the season-boundary power seed to give 2021 one extra winning bet
(48–35 → **49–35**). 2020 and 2022 keep their records; every published-report
season is untouched.

One judgement call is deliberately **not** taken: 64 games of 2025 use an
*opening* line because the close was missing, and those agree with the second
source far worse than real closes do (11% exact, mean 2.3 points off, versus 37%
and 0.9). One of them — Raiders +15.5 as a home underdog — is almost certainly
corrupt. Replacing all 64 with the second source's closing lines would make the
season's line basis consistent, but it would also rewrite 64 existing prices,
and it happens to improve the record (to 50–40, +6.0u). That is a reason for
caution, not for adoption, so it is left to an explicit decision.

### A season in progress (2026–27)

The pipeline also runs on a season that is only partly played. A results file
may carry the full remaining schedule with scores and turnovers left blank;
those fixtures still feed the factors, but the report lists only the games that
are **actionable** — already played, or priced so the system can pick them.
Unplayed picks are shown with a `·` result and excluded from the win/loss
record until they settle. A completed season is entirely played, so nothing is
dropped and every earlier report is byte-for-byte unchanged.

**Turnovers gate the picks.** Two of the five factors read the previous game's
turnovers, and the nflverse export does not carry them — only pro-football-
reference does. So a game is priced but *not picked* while that input is
missing: if a team has a previous game on the schedule but no turnover margin
for it — whether because the turnovers have not been loaded, or because the game
has not been played yet — `lgt_unknown` is set and the system declines rather
than treating the factor as neutral. Having no previous game at all is
different, and stays 0 as in the published reports.

Neither case is hypothetical, and both were caught live. Pricing week 2 of 2026
from the nflverse export before the turnovers arrived produced four games at
`|System #| ≥ 3` that would have been bet on two dead factors. Then, with week 2
priced while the week-1 Monday night game was still to come, Jaguars–Broncos was
held back because Denver's last-game turnovers did not exist yet — and when that
result landed the pick came back at **+5**, not the +3 it would have shown, since
Denver's turnover margin *and* their week-1 cover had both been missing. The
provisional number would have been wrong in both size and composition.

A matching rule governs *importing* lines. `pricing_horizon()` only pulls a line
for a week the model could actually pick — the next one after the last completed
week — because a line imported further ahead just locks in an early number when a
closer-to-closing one will exist by the time the game matters. A finished season
has no horizon, so every line is imported, playoffs included.

Two quirks in the 2026–27 source files are corrected when the raw exports are
slimmed into `data/`, and are worth knowing if you refresh them:

- The week-1 spreads arrived in the **`Home Odds Close`** column rather than
  `Home Line Close`. They are unambiguously spreads — all half-point values,
  12 of the 16 negative, which decimal odds can never be (that column runs
  1.06–7.50 in the same file's 2025 rows).
- The Kickoff Game row (9 Sep 2026) has its **team labels transposed** relative
  to pro-football-reference: Seattle, the defending champion, hosts. The scores
  already sit in the correct home/away slots, so only the two names are
  swapped and the line stays with the home slot. Every one of the other 271
  games matches the odds export exactly on (date, home, away).

Remaining data gap: the 2025 odds export has **no lines for the 14 week-5
games** — they appear in the report but recommend no bet.

## View on a phone

`index.html` is a self-contained, mobile-friendly page with the season
summaries, cumulative-profit charts and the full game-by-game tables. It is
generated from the data CSVs by `build_site.py` (rerun it after the data
changes).

- While this work lives on a feature branch, view it via
  [raw.githack](https://raw.githack.com/ZeNoonan/Research/claude/laughing-hopper-eujimb/nfl_report/index.html).
- Once merged into the default branch, the GitHub Pages URL (same setup as
  `kelly_sim/`) is permanent: <https://zenoonan.github.io/Research/nfl_report/>.

## Run

```bash
pip install -r requirements.txt

python validate.py        # print the replication scorecard above
python parse_reports.py   # regenerate the 2015/2016 CSVs from the PDFs (needs pymupdf)
python enrich_odds.py     # repair odds gaps from the nflverse schedule export
python season_report.py   # regenerate every report_<year>.csv from the raw data
python build_site.py      # regenerate index.html, the static web view
streamlit run app.py      # browse the replicated reports
```

### Updating the season in progress

Each week, refresh the two 2026 inputs and re-run — no code changes needed:

1. **`data/results_2026.csv`** — paste the new rows from pro-football-reference
   over the matching fixtures, filling `Pts`, `Pts.1`, `TOW`, `TOL`. Leave the
   rest of the schedule in place with those four columns blank.
2. **`data/odds_2026.csv`** — add each newly-priced game's spread in
   `Home Line Close` (negative = home favoured). Check whether the source still
   puts spreads in the `Home Odds Close` column, and whether any row's team
   labels are transposed relative to pro-football-reference.
3. `python season_report.py && python build_site.py`.

The report grows a week at a time: newly-played games get graded, newly-priced
games appear as picks.

## Factor diagnostics

`factor_analysis.py` rebuilds Brown's two monitoring tools per season: the
**marginal contribution** table (net wins charged to each factor on the close
calls its vote alone decided) and **standalone success** (each factor as its
own betting rule over all games). The marginal accounting is pure
leave-one-out — on a bet made at exactly ±3 every aligned factor is charged
the result; on a near-miss at ±2 every *opposing* factor is charged the
opposite of what the blocked bet would have done — and is validated against
Table 3 of the Wilmott article: **every value Brown published is reproduced
exactly — all 35 (seven seasons 2010–2016 × five factors)**. (The article's
prose suggests neutral factors also get blocking credit; that variant does
*not* reproduce the published table.)
Both tables render in the web view's "Factor diagnostics" section. A standalone
rate is only shown once at least 25 of that factor's votes have settled, so a
season in progress shows a dash rather than a meaningless 0% or 100%.

## Heatmaps

Each season tab also shows two **team × week heatmaps** (`heatmaps.py`): the
season-to-date cover (STDC) and the power rating, one value per team per week
on a red-yellow-green diverging scale centred at zero, with teams sorted by
their season mean. STDC green = a team that has been covering ("fat", which the
hunger factor fades); red = "hungry". Power green = strong. Week numbers come
from the generated reports (authoritative, from pro-football-reference) and are
derived from the date for the published 2015/2016 reports.

## Roadmap

1. ~~**Game results & closing spreads** — covers (STDC) and graded results.~~ ✅
2. ~~**Per-game turnovers** — to compute LGT.~~ ✅
3. ~~**Power ratings** — weighted (1, ½, ¼, ⅛) least-squares fit to the last four
   weeks of lines.~~ ✅ Verified against the published 2016 lines (0.999 corr).
4. ~~**Prior-season carryover** — week-1 LGT and early-week power seeded from the
   previous season.~~ ✅ Done for 2020–2025.
5. **Add the 2018 file** so 2019 also gets a seeded week 1.
6. **Fill the missing week-5 lines** in the 2025 odds export.
