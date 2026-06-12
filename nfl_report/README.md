# NFL Report — replicating Aaron Brown's demonstration system

A project to **replicate the published `NFL Report 2016`** (and its 2015
sibling): a weekly NFL against-the-spread betting system built by Aaron Brown as
a public demonstration that a simple, additive, binary-factor model can beat the
spread. The source write-ups are in [`reference/`](reference/).

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

`validate.py` rebuilds the derived columns from raw inputs and compares them to
the published reports:

| Check | 2015 | 2016 |
|---|---|---|
| **System #** (from LGT/STDC/Power + line) | 265/267 (99.3%) | **267/267 (100%)** |
| **Bet side** (from System #) | 90/90 bets | 85/85 bets |
| **Result** (from scores + line + #) | 90/90 | 85/85 |
| **STDC** rebuilt independently from scores + lines | ~90% | ~92% |

So the **betting logic is fully reproduced**. The two 2015 `System #` misses are
the rounded-power ties noted above. The STDC reconstruction — done from scratch,
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
├── factor_analysis.py # Brown's factor diagnostics (marginal contributions)
├── heatmaps.py        # team x week STDC / power pivots + RdYlGn heatmaps
├── validate.py        # rebuild columns and compare to the published reports
├── app.py             # Streamlit viewer for the replicated reports
├── build_site.py      # data CSVs -> index.html (static mobile-friendly report)
├── index.html         # generated web view of the analysis (works on phones)
├── data/
│   ├── report_2015.csv, report_2016.csv     # parsed from the published PDFs
│   ├── report_{2019..2025}.csv              # generated by season_report.py
│   ├── results_{2019..2025}.csv             # raw: PFR games + turnovers
│   └── odds_{2019..2025}.csv                # raw: aussportsbetting odds
└── reference/         # source material
    ├── NFL_Report_2015.pdf
    ├── NFL_Report_2016.pdf
    ├── NFL_Demonstration.pdf      # how the system is built
    └── Wilmott_NFL_Article.docx   # the published article
```

## Seasons generated from raw data

`season_report.py` produces the same report table, from raw inputs, for every
season with files in `data/`: currently **2019 through 2025**, a fully
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
weeks. This applies to 2020–2025; only **2019** (no 2018 file) keeps a blank
week 1 (LGT 0, power neutral). Team names are normalised to current nicknames
so a franchise tracks across renames (Washington Redskins → Football Team →
**Commanders**; Oakland/Las Vegas **Raiders**).

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
python season_report.py   # regenerate every report_<year>.csv from the raw data
python build_site.py      # regenerate index.html, the static web view
streamlit run app.py      # browse the replicated reports
```

## Factor diagnostics

`factor_analysis.py` rebuilds Brown's two monitoring tools per season: the
**marginal contribution** table (net wins charged to each factor on the close
calls its vote alone decided) and **standalone success** (each factor as its
own betting rule over all games). The marginal accounting is pure
leave-one-out — on a bet made at exactly ±3 every aligned factor is charged
the result; on a near-miss at ±2 every *opposing* factor is charged the
opposite of what the blocked bet would have done — and is validated against
Table 3 of the Wilmott article: **all ten published 2015/2016 values are
reproduced exactly**. (The article's prose suggests neutral factors also get
blocking credit; that variant does *not* reproduce the published table.)
Both tables render in the web view's "Factor diagnostics" section.

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
