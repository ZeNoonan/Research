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

> **Power factor detail.** The write-up describes a 3-point home-field
> advantage, but the *published reports* compare the line to the raw power
> difference `away_power − home_power` with **no** extra home-field term — it is
> already absorbed into the fitted ratings. Using the raw difference reproduces
> 532/534 published `System #` values; the 2 misses are exact ties created by
> the power column being rounded to one decimal in the PDF.

## Replication status

`validate.py` rebuilds the derived columns from raw inputs and compares them to
the published reports:

| Check | 2015 | 2016 |
|---|---|---|
| **System #** (from LGT/STDC/Power + line) | 265/267 (99.3%) | **267/267 (100%)** |
| **Bet side** (from System #) | 90/90 bets | 85/85 bets |
| **Result** (from scores + line + #) | 90/90 | 85/85 |
| **STDC** rebuilt independently from scores + lines | ~92% | ~92% |

So the **betting logic is fully reproduced**. The two 2015 `System #` misses are
the rounded-power ties noted above. The STDC reconstruction — done from scratch,
using only prior scores and lines — lands ~92%; the gap comes from (a) the
Seahawks/Steelers PDF quirk below and (b) occasional half-point/push differences
between the displayed `Line` and the spread used for an earlier game's cover.
Closing those is a Phase 2 data task.

### Known data quirk: Seahawks & Steelers

In the source PDFs the two tracking teams, **Seahawks** and **Steelers**, are on
a separate text layer; their *team-name* cells are pulled out of each row and
dumped at the foot of the page. The parser strips that footer and recovers the
name from the `Bet` column where it can; the rest are left blank. This affects
only some team *labels* — every numeric column is intact, so the model
validation above is unaffected.

## Files

```
nfl_report/
├── README.md          # this file
├── requirements.txt
├── parse_reports.py   # PDFs -> data/report_2015.csv, report_2016.csv
├── model.py           # the five-factor engine (the system logic)
├── validate.py        # rebuild columns and compare to the published reports
├── app.py             # Streamlit viewer for the replicated reports
├── build_site.py      # data CSVs -> index.html (static mobile-friendly report)
├── index.html         # generated web view of the analysis (works on phones)
├── data/
│   ├── report_2015.csv
│   └── report_2016.csv
└── reference/         # source material
    ├── NFL_Report_2015.pdf
    ├── NFL_Report_2016.pdf
    ├── NFL_Demonstration.pdf      # how the system is built
    └── Wilmott_NFL_Article.docx   # the published article
```

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
python parse_reports.py   # regenerate the CSVs from the PDFs (needs pymupdf)
python build_site.py      # regenerate index.html, the static web view
streamlit run app.py      # browse the replicated reports
```

## Roadmap

The current work replicates the reports **from their own published factor
columns**, proving the system logic end to end. The next phase is to rebuild
those factor columns **from raw data**, so the whole report can be produced for
any season without the published sheet:

1. **Game results & closing spreads** — to compute covers (STDC) and grade
   results without the published `Line`.
2. **Per-game turnovers** — fumbles lost + interceptions, to compute LGT.
3. **Power ratings** — weighted (1, ½, ¼, ⅛) least-squares fit to the last four
   weeks of lines, as described in the demonstration, to compute the Power
   column and the over-reaction factor from scratch.

With those three inputs the model in `model.py` produces every column in the
report directly.
