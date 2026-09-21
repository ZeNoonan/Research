# URC Report — the five-factor system, ported to rugby

A port of [`nfl_report`](../nfl_report/) to the **United Rugby Championship**,
set up and ready for the **2026-27 season**. Same engine, same five binary
factors, same betting rule; the inputs are rugby's.

The NFL project exists to *replicate* Aaron Brown's published sheets, and it
does — seven seasons, 98.8% of his System # values, every figure in his
published factor table. **This project cannot do that**, because there is no
published rugby report to replicate. What it inherits is the machinery and the
discipline; whether the system's three intuitions survive the move to rugby is
an open question, and the season is the test. Nothing here should be read as a
finding yet.

---

## 📋 What I need from you

*The pipeline is built and tested. It has almost no data, and cannot get any on
its own: this environment's network policy blocks Wikipedia, oddsportal.com and
stats.unitedrugby.com, so every one of these has to be pasted or typed in.*

### 1. The rest of the 2026-27 fixture list — the one blocker

**Round 1 is loaded** (all eight matches, cross-checked against two sources).
**Rounds 2-18 are not.** Web search returns rounds in fragments — six of eight,
with no way to tell which two are missing without checking every club — so
rather than half-fill the schedule with guesses, it is empty.

Copy the fixture list from
<https://www.unitedrugby.com/latest/news/2026-27-fixtures-in-full/> (or the
Wikipedia regular-season section) into a text file and run:

```bash
python import_fixtures.py paste.txt --season 2026
```

Layout does not matter much — sponsor names, venues, kick-off times, footnotes
and TV listings are all stripped. What matters is that each line names two
clubs. The importer then checks the shape a real URC season must have (every
round pairs all 16 clubs exactly once; each club plays 9 home and 9 away) and
**tells you exactly what is missing** rather than accepting it silently.

Why this matters beyond the schedule: a missing fixture does not just leave a
gap, it makes the *next* match wrong, because a club's "last match" turnover
margin is read off the fixture order.

### 2. Round 1 handicaps

Eight numbers. Open `entry/urc_2026_entry.xlsx`, fill the yellow `line` column
— **negative when the home side is favoured** — and run:

```bash
python entry_sheet.py import --season 2026 && python season_report.py
```

### 3. The 2025-26 seed — what makes round 1 pickable at all

Two factors reach back across the season boundary, so **without this the model
declines every round-1 pick**. It needs less than a full season:

| What | Which matches | Why |
|---|---|---|
| **Handicaps** | rounds 15, 16, 17, 18 (32 matches) | fits the opening power ratings — the last four rounds, weighted 1, ½, ¼, ⅛ |
| **Turnovers conceded** | round 18 **and** the 7 playoff matches | seeds round 1's LGT from each club's *last* match of the season |

**Scores are not needed** for the seed: the power fit reads handicaps only, and
season-to-date cover resets at the season boundary. Leave them blank.

`entry/urc_2025_entry.xlsx` is already laid out with the right number of blank
rows and the round numbers pre-filled (15-18, then 19 = quarter-final,
20 = semi-final, 21 = grand final). The club columns are dropdowns, so a
misspelling is rejected at the cell. Fill the fixtures, handicaps and
turnovers, then:

```bash
python entry_sheet.py import --season 2025 && python season_report.py
```

### 4. Once a season of handicaps exists — calibrate

`HOME_ADVANTAGE` is currently a **provisional 5.0**. The NFL system uses a
well-established 3-point home field; the URC has no settled equivalent and its
handicaps are wider. `python calibrate.py` fits it — and the Europe ↔ South
Africa travel term — from the handicaps themselves, and refuses to report a
number until there are enough matches to support one. Adopt the fitted value
rather than leaving my guess in.

---

## The model

Five **binary factors** each cast one vote: **+1** favours the home side, **−1**
the away side, **0** neither. Their sum is the **System #**. The system **bets
home at System # ≥ +3** and **away at ≤ −3**, and passes otherwise.

| # | Factor | Votes home (+1) when… | Votes away (−1) when… |
|---|---|---|---|
| 1 | **Power / over-reaction** | the handicap makes home a bigger underdog / smaller favourite than the power ratings imply | the reverse |
| 2 | **Turnover — home** | `home_lgt > 0` (home lost the turnover count last match) | `home_lgt < 0` |
| 3 | **Turnover — away** | `away_lgt < 0` (away won the turnover count last match) | `away_lgt > 0` |
| 4 | **Hunger — home** | `home_stdc < 0` (home is "hungry": failing to cover) | `home_stdc > 0` |
| 5 | **Hunger — away** | `away_stdc > 0` (away is "fat": covering too much) | `away_stdc < 0` |

The intuitions, unchanged from the source:

- **Over-reaction** — line moves overshoot, so back the side the line moved
  against relative to a slow-moving power rating.
- **Turnovers** — turnovers are largely random, so a side that coughed up the
  ball last time out is better than its result looked, and the line
  over-corrects.
- **Hunger** — bookmakers like every side to cover about half the time, so back
  the one that has been failing to cover and fade the one that has been
  covering.

### Sign conventions

- **`line`** — the home handicap. **Negative = home favoured** (−7.5 means home
  must win by 8 to cover); positive = home receiving points.
- **`lgt`** — net turnovers **conceded** in the side's previous match
  (own conceded − opponent's conceded). Positive = gave up more ball than it won.
- **`stdc`** — covers − non-covers this season. Negative = hungry.
- **`power`** — rating in points; the power-implied handicap is
  `away_power − home_power`.

> **Power factor detail.** Home advantage lives *inside the rating fit* (the
> ratings are neutral-venue) and is **not** re-added when the factor compares
> the handicap to the raw rating difference. That is the construction validated
> against Brown's published reports, so it carries over unchanged — but it means
> the factor leans away by roughly whatever `HOME_ADVANTAGE` is set to, which
> for the URC is still a guess. This is the single biggest reason to run
> `calibrate.py` early.

## What is different from the NFL project, and why

| | `nfl_report` | here |
|---|---|---|
| **Raw inputs** | two machine-generated exports (pro-football-reference, nflverse), joined on team pair ± 1 day | **one hand-keyed file per season** |
| **Turnovers** | giveaways − takeaways | **turnovers conceded**, home minus away |
| **Home edge** | 3.0 points, well established | **5.0, provisional**, plus an optional long-haul term |
| **Heatmap scale** | red-yellow-green | **blue ↔ grey ↔ red** |
| **Validation** | 7 published seasons | none — generated-data tests only |

**One file per season.** Both rugby inputs are read off web pages by hand, so
joining two hand-keyed tables would turn every typo into a silently dropped
match. `data/season_<year>.csv` carries the fixture, the handicap, the score
and the turnover counts in one row, and `entry_sheet.py` keeps the typing in a
spreadsheet rather than in the CSV.

**Turnovers conceded, home minus away.** The URC match centre publishes both
"turnovers won" and "turnovers conceded" per side. Using the *conceded*
differential mirrors the NFL's giveaway differential exactly, is zero-sum
between the two sides, and halves the typing. Recording won/conceded separately
per side would be a defensible alternative — it is a modelling choice, so it is
written down here rather than buried.

**Blue ↔ red heatmaps.** A red-yellow-green ramp puts a hue at the midpoint,
where it reads as a third category rather than as zero, and red/green is the
least colour-vision-safe pair available. The diverging pair used here was
checked with a validator in both light and dark mode.

## Files

```
rugby_urc/
├── README.md
├── requirements.txt
├── teams.py            # the 16 clubs + every sponsor spelling the sources use
├── model.py            # the five-factor engine
├── import_fixtures.py  # pasted fixture text -> data/season_<year>.csv
├── entry_sheet.py      # export a sheet to type into, and read it back
├── season_report.py    # season files -> data/report_<year>.csv
├── calibrate.py        # fit HOME_ADVANTAGE from the handicaps
├── factor_analysis.py  # marginal contribution + standalone success
├── heatmaps.py         # club x round diverging heatmaps
├── build_site.py       # data -> index.html
├── app.py              # Streamlit viewer
├── test_pipeline.py    # end-to-end checks on generated data
├── data/
│   ├── season_2026.csv   # 2026-27: round 1 loaded, handicaps empty
│   ├── season_2025.csv   # 2025-26 seed: empty, awaiting the tail of last season
│   └── report_<year>.csv # generated
└── entry/
    └── urc_<year>_entry.{xlsx,csv}   # the sheets to type into
```

## How the pieces gate each other

The system **declines to pick rather than guessing**, in three distinct cases,
and the report says which:

1. **No handicap** — nothing to bet against.
2. **No power ratings** — fewer than one prior round of handicaps exists.
3. **`lgt_unknown`** — a side's previous match is on the schedule but has no
   turnover count, because it has not been played or has not been typed in.
   Two of the five factors read that number, so treating it as neutral would be
   a bet on dead inputs. Having *no* previous match is different, and is
   legitimately 0.

This is inherited from the NFL project, where it was not hypothetical: a week
priced before the turnovers arrived produced four picks resting on two dead
factors, and one held-back match came back at +5 rather than the +3 it would
have shown.

## Replication status

There is none, and there cannot be — no published rugby reports exist. What
there is instead is `test_pipeline.py`, which generates handicaps from **known**
power ratings and turnover counts and asserts the pipeline recovers them:

| Check | result |
|---|---|
| Weighted fit recovers the generating ratings | max error **0.20 pts** |
| LGT carries across the season boundary, and nowhere else | pass |
| A missing turnover count blocks the pick | pass |
| STDC resets each season | pass |
| System #, pick and grade reproducible from the stored columns | pass |
| `calibrate.py` recovers the edge terms that built the handicaps | **exact** |

That is a test of the plumbing, not evidence the system works on rugby.

## Run

```bash
pip install -r requirements.txt

python test_pipeline.py                            # the checks above
python import_fixtures.py paste.txt --season 2026  # fixture text -> season file
python entry_sheet.py export --season 2026         # -> entry/urc_2026_entry.xlsx
python entry_sheet.py import --season 2026         # filled sheet -> data/
python season_report.py                            # -> data/report_<year>.csv
python calibrate.py                                # fit the home-advantage terms
python factor_analysis.py                          # per-factor diagnostics
python build_site.py                               # -> index.html
streamlit run app.py                               # browse it
```

### Each week, once the season is running

1. **Handicaps** for the coming round, as late as practical before kick-off —
   they are imported once and not overwritten, so a later entry is closer to the
   close.
2. **Scores and turnovers** for the round just played, from
   <https://stats.unitedrugby.com/match-centre/2026-27/>. **Turnovers are the
   blocker**: without them the next round cannot be picked at all.
3. `python entry_sheet.py import --season 2026 && python season_report.py && python build_site.py`

## View on a phone

`index.html` is self-contained and mobile-friendly — season tabs, the record,
the cumulative-profit curve, every match, and the club × round heatmaps, in
light and dark. Regenerate it with `build_site.py` after the data changes.

Until it is merged, view it through
[raw.githack](https://raw.githack.com/ZeNoonan/Research/claude/beautiful-planck-uh4wot/rugby_urc/index.html);
once on the default branch the GitHub Pages URL is
<https://zenoonan.github.io/Research/rugby_urc/>.

## Roadmap

1. ~~Port the engine, the pipeline and the viewer.~~ ✅
2. ~~Fixture importer with URC shape checks.~~ ✅
3. ~~Spreadsheet data entry with club validation.~~ ✅
4. **Load rounds 2-18 of the 2026-27 fixture list.** ← blocked on the paste
5. **Enter the 2025-26 seed** so round 1 is pickable.
6. **Calibrate `HOME_ADVANTAGE`** once a season of handicaps exists.
7. Revisit the turnover definition (conceded differential vs won/conceded
   separately) once a season of match-centre data is in.
