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

*The pipeline is built and tested and the full fixture list is in. What is left
is the numbers, and it cannot fetch those on its own: this environment's network
policy blocks Wikipedia, oddsportal.com and stats.unitedrugby.com, so handicaps
and turnovers have to be typed in.*

### Nothing needed for these

- **The 2026-27 fixture list** — **loaded in full**: all 144 matches, 18 rounds,
  every round pairing all 16 clubs exactly once, every club 9 home and 9 away.
  Imported from your paste with `import_fixtures.py`; the shape checks pass
  clean. Re-run that command if the URC moves a fixture.
- **Round 1's eight handicaps, opening and closing** — **received and loaded**.
  Four lines moved once the teams were named, and two of those moves change
  the picks; see *The line the model runs on*.
- **The 2025-26 turnovers** — **received and loaded**: round 18 and the seven
  playoff matches, 15 rows, giving all 16 clubs a last-match margin. **Round 1
  of 2026-27 is now pickable** — see below. The sheet also changed the turnover
  definition; that is written up under *A turnover is not a giveaway*.
- **The 2025-26 handicaps** — **derived, not needed by hand**. The oddsportal
  export carries 1X2 win odds rather than a spread, and
  [`spread_from_odds.py`](spread_from_odds.py) converts one into the other
  (below). 50 matches are loaded, covering the last five regular match-weeks
  and all seven playoffs — more than the four weeks the power seed needs. Round
  1 of 2026-27 now **has power ratings**.

### 1. Five handicaps, from the spread market rather than the win-odds market

**This is the only outstanding data ask, and it is five numbers.**

The line check settled `sigma` for the readable range (below) and showed that
the **far tail cannot be inferred at all**: two matches both quoted at 1.01
came back with real handicaps of −30.5 and −33.5, three points apart from
*identical* odds. No model separates those.

Seven matches sit in that zone. Two you have already answered, so they are
pre-filled. The remaining five are in
**`entry/urc_2025_coarse_lines.xlsx`** — open it and fill `actual_line` for:

| date | match | inferred (unreliable) |
|---|---|---|
| 2026-05-16 | Bulls v Benetton | −25.5 |
| 2026-03-27 | Leinster v Scarlets | −25.0 |
| 2026-05-16 | Sharks v Zebre | −23.5 |
| 2026-04-25 | Munster v Ulster | −23.5 |
| 2026-05-16 | Leinster v Ospreys | −21.5 |

On oddsportal these are under the **handicap / spread** tab rather than the
1X2 tab you exported before — the number wanted is the home handicap, negative
when the home side is favoured. Then:

```bash
python line_check.py apply --season 2025 && python season_report.py
```

They land marked as quoted rather than inferred, which is what stops
`import_oddsportal.py` overwriting them on its next run.

Not urgent — the round-1 picks do not move either way.

### 2. Monitoring home advantage

`HOME_ADVANTAGE` is a **provisional 5.0**. The NFL system uses a well-established
3-point home field; the URC has no settled equivalent and its handicaps are
wider. `python calibrate.py` reports two things, and the difference between them
matters:

- **The fitted estimate** — a least-squares fit of the home term and the
  Europe ↔ South Africa travel term alongside club ratings. This is the number
  to adopt, and it is **withheld below 40 priced matches**, because with less
  than that the home term and the club ratings are not separable.
- **An early read**, printed from the first handicap onwards — the mean of
  `-line`, split into domestic and long-haul trips. This measures venue *only
  once club strengths cancel*, which happens when every club has played as often
  at home as away. It prints how far from that the sample is, so it reads as a
  direction of travel rather than a measurement.

With 2025-26's tail loaded, `calibrate.py` pools 58 priced matches and clears
the 40-match floor. It fits **+5.0** for home advantage, which is the
provisional value, and **+3.1** for a long-haul trip, a term currently switched
off. The early read is **+5.5 over 26 domestic matches** and **+9.6 over 32
long-haul ones**. Neither is ready to adopt. 50 of the 58 matches are last
season's run-in, and 13 of the 16 clubs have not yet played as often at home
as away. Revisit around round 5, when this season's own matches carry the fit.

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
  must win by 8 to cover); positive = home receiving points. It is entered
  twice, as `opening_line` and `closing_line`. `line` is the close, or the open
  until the close is in.
- **`lgt`** — the side's own net turnover margin in its previous match
  (**own conceded − own won**). Positive = leaked more ball than it won back.
  Not a differential between the two sides; see *A turnover is not a giveaway*.
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

### The line the model runs on

Each match carries two handicaps. `opening_line` is taken when the round is
first priced. `closing_line` is taken after the teams are named, as late as
practical before kick-off. **The model runs on the close.** It picks on it,
fits the power ratings to it, and counts covers and grades bets against it. The
opening line stands in only until the close is entered, and after that it is a
record of how the market moved. This is `nfl_report`'s rule, whose model is
defined on the closing line, and the reason carries over: the close knows
things the open does not. In the URC that mostly means the team sheets.

Round 1 shows how much that matters. Four of the eight lines moved on team news:

| match | open | close | System # |
|---|---|---|---|
| Lions v Leinster | +7.5 | −5.5 | +3 → +1: **Lions no longer a bet** |
| Munster v Glasgow | −2.5 | +2.5 | +1 → +3: **Munster +2.5 now a bet** |
| Connacht v Stormers | −1.5 | −6.5 | −1, unchanged |
| Sharks v Ospreys | −12.5 | −11.5 | +1, unchanged |

Edinburgh (+11.5 at Ulster) and the Bulls (−11.5 at Zebre) are unchanged, so
the round still has three bets.

**Worth watching.** The power factor cannot tell a line that has overshot from
one that moved on team news. It compares the line with ratings fitted to
earlier lines. So when a club names a weakened side, the factor treats the
move as the market over-reacting and backs that club. On the round-1 closes it
now votes for Leinster and for Munster, the two sides those moves went against.
The NFL system meets the same thing when a quarterback is injured, but in the
URC rotation is routine: internationals are rested, and the South African
sides travel with reduced squads. More of each move is likely to be real
information. The close also feeds the rating fit for the weeks that follow, so
a rotated side's price drags its rating down, hardest in the next week. This
season will show whether the factor still pays under those conditions.
Keeping both lines is what makes that testable, because the factor can be
scored against the open as well as the close.

### A round is not a date: the split round 8

The URC numbers its rounds for scheduling, not chronology, and 2026-27 proves
it. **Round 8 runs from 26 December to 21 February**: six matches over the
Christmas weekend, then Lions v Sharks and Bulls v Stormers on 20-21 February,
*after* rounds 9, 10 and 11 have been played.

The NFL system takes week order and date order to be the same thing, and they
are there. Carrying that assumption across would have been wrong three ways,
all of them silent:

- **Look-ahead in the turnover factor.** In round order, the Lions' round-8
  match sorts before their round-9 match — so January's pick would have read a
  turnover margin from a match played seven weeks later. That is not a stale
  number, it is a number that did not exist.
- **Season-to-date cover** would have counted a February cover in January.
- **Power ratings** keyed on round number would have rated those two February
  matches on October form.

So ordering is **by date**, and the rating window is the last four **match-weeks**
(ISO calendar weeks) rather than the last four round numbers. Weeks split a
split round correctly and make the season boundary fall out for free — the
previous season's last weeks are just the previous weeks, with no special case.
`test_pipeline.py` check 9 pins this down: it builds a season with a deliberately
displaced round and asserts every club's LGT is its previous match **by date**.

## A turnover is not a giveaway

The NFL system's turnover factor reads `giveaways − takeaways`: how much ball a
team lost, net of how much it won back. The NFL implementation computes that as
a **differential between the two sides** — `home_giveaways − away_giveaways` —
which is exact there, because a giveaway by one team is by definition a
takeaway by the other.

This project copied the differential, on the assumption that it carried the
same meaning. **The first real match-centre data disproved that.** Across the
15 URC matches loaded, `home_turnovers_conceded` never once equalled
`away_turnovers_won` — not in a single match — and the two differed by as much
as 8. In rugby they are independently recorded events: a knock-on into touch is
a turnover conceded that nobody won.

So the differential is not a shortcut to the same number here, it is a
different quantity. And it matters: the two definitions **disagree on the sign
in 8 of 30 club-matches**, and the sign is the entire input to the factor.

The definition that carried over is therefore the original one read literally —
**a club's own turnovers conceded minus its own turnovers won** — and both
columns are required rather than one inferred from the other. A side effect
worth noting: the margin is no longer zero-sum between the two teams in a
match, so both sides can have leaked ball badly. That is a fact about rugby,
not a modelling liberty.

## Inferring a handicap from win odds

oddsportal publishes 1X2 decimal odds, not a spread. The two describe the same
distribution of margins from different angles — the win odds say how often the
home side finishes ahead, the handicap says by how much it is expected to — so
either gives the other once you assume a shape for the margin.

Take the margin as normal with standard deviation `sigma`. Then

```
P(margin > 0) = p        ->        line = -sigma * Phi^-1(p)
```

with `p = p_home + p_draw / 2`, a draw being the mass sitting exactly on zero.

Two things have to be right, and both were checked rather than assumed.

**A note on the source's own oddities.** The URC match centre publishes the
occasional negative turnover count — 2025-26's Cardiff v Stormers carries
`home_turnovers_lost = -1` on the site itself, confirmed against the source.
`import_turnovers.py` flags counts like that on every run rather than
rejecting them (refusing would block real data) or swallowing them (a negative
count can flip the sign of a club's margin, which is the factor's entire
input). That particular row does not reach round 1 — Cardiff's last 2025-26
match is the quarter-final — and its sign is negative either way.

**Removing the bookmaker's margin.** The quotes sum to about 8.3% over
certainty. Dividing through by that — the obvious fix — systematically
overstates short prices. Shin's method, which models the book as protecting
itself against better-informed traders, takes proportionally more out of the
longshots. The test is whether the resulting lines behave like lines:

| de-vig | home cover rate vs its own inferred line |
|---|---|
| proportional | 54.0% |
| additive | 48.0% |
| **Shin** | **48.0%** |

A fair line must produce ~50%, so proportional is measurably biased and Shin is
used.

**The value of `sigma`.** **13.75**, measured against 12 real quoted handicaps.

It was 16.0, fitted from results, and the reasoning that produced it was wrong.
That is recorded here rather than quietly corrected, because the mistake is
instructive: the model `M ~ Normal(sigma * z, sigma)` makes **one** number do
**two** jobs — set where the line sits, and set how far results scatter around
it. Those are different quantities. The scatter term carries n observations'
worth of information while the mean term is noisy, so the likelihood was
dominated by the scatter. The "two independent estimates agreeing" (slope 15.9,
residual spread 16.0) was not confirmation: it was both estimates measuring the
same thing, margin spread, and neither measuring the line.

Checked against real lines, the two separate cleanly:

| source | line scale | precision |
|---|---|---|
| 50 results (`fit_from_results`) | 15.94 | ±2.27 → 95% interval **11.4–20.5** |
| 12 quoted lines (`fit_from_lines`) | **13.74** | essentially exact |

No contradiction — 13.74 sits comfortably inside that interval. Just precision:
a result is a noisy draw around the line, a quoted line *is* the line. Realised
margins do scatter by about 16; that is `margin_sigma`, and it is now returned
as a separate number.

The fit is flat across the readable range — per-match estimates run 13.2 to
14.6 from |z| = 0.13 to 1.26, with no drift — so one `sigma` genuinely serves
the whole middle.

### Where it fails, and why no model can fix it

Decimal odds move in steps of 0.01, and near the short end one step is worth a
lot of handicap:

| shortest price | matches | points of line per 0.01 tick |
|---|---|---|
| 1.01–1.05 | 8 | **1.78** |
| 1.05–1.15 | 13 | 0.67 |
| 1.15–1.50 | 14 | 0.33 |
| 1.50–3.00 | 15 | 0.15 |

So a line inferred from a 1.01 shot is uncertain by a couple of points *before*
any modelling error, and the three de-vig methods duly disagree by up to 3.8
points on exactly those matches (against a median of 0.85 across all 50).

**The line check proved this, rather than leaving it as an argument.** Both
checked matches quoted at **1.01** came back with real handicaps of **−30.5**
and **−33.5** — three points apart, from identical odds. No model can separate
those, because the input does not. The same rows want `sigma` ≈ 17.3 where the
readable range wants 13.75, which is not a fitting problem to be tuned away: it
is the tail of the quote losing resolution.

Note what this did to the headline error. Overall bias across the 14 checked
matches was **−0.04 points**, which looks like near-perfect calibration and is
nothing of the sort — it is a −0.46 bias on the readable quotes cancelling a
+2.50 bias on the coarse ones. `line_check.py` therefore reports the two
groups separately and never quotes the combined figure on its own. `tick_sensitivity` reports it per match, `is_coarse` flags it,
and `import_oddsportal.py --skip-coarse` will leave those rows unpriced rather
than fill them with a number that cannot bear the weight.

Every derived line is written with `line_source = inferred-1x2`, so it is never
mistaken later for a handicap that was actually quoted.

## What is different from the NFL project, and why

| | `nfl_report` | here |
|---|---|---|
| **Raw inputs** | two machine-generated exports (pro-football-reference, nflverse), joined on team pair ± 1 day | **one hand-keyed file per season** |
| **Turnovers** | giveaways − takeaways (equivalently, a differential) | **own conceded − own won**, which is not a differential |
| **Home edge** | 3.0 points, well established | **5.0, provisional**, plus an optional long-haul term |
| **Heatmap scale** | red-yellow-green | **blue ↔ grey ↔ red** |
| **Validation** | 7 published seasons | none — generated-data tests only |

**One file per season.** Both rugby inputs are read off web pages by hand, so
joining two hand-keyed tables would turn every typo into a silently dropped
match. `data/season_<year>.csv` carries the fixture, the opening and closing
handicaps, the score and the turnover counts in one row, and `entry_sheet.py`
keeps the typing in a spreadsheet rather than in the CSV.

**Turnovers: own conceded minus own won.** See *A turnover is not a giveaway*
below — this started as the conceded differential, on an assumption the data
then disproved.

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
├── import_oddsportal.py # pasted results+odds -> season file, handicaps inferred
├── spread_from_odds.py # 1X2 decimal odds -> a handicap (Shin de-vig + normal)
├── line_check.py       # check inferred handicaps against real ones, re-fit sigma
├── import_turnovers.py # match-centre turnover sheet -> season file (scores too)
├── urc_scraper.py      # Streamlit: a round's turnovers + scores from the feed
├── urc_season_scraper.py # Streamlit: a whole past season, for backtesting
├── test_scraper.py     # scraper checks, incl. the app run headless
├── test_season_scraper.py # season-scraper checks: playoff rounds, retries, reruns
├── entry_sheet.py      # export a sheet to type into, and read it back
├── season_report.py    # season files -> data/report_<year>.csv
├── calibrate.py        # fit HOME_ADVANTAGE from the handicaps
├── factor_analysis.py  # marginal contribution + standalone success
├── heatmaps.py         # club x round diverging heatmaps
├── build_site.py       # data -> index.html
├── app.py              # Streamlit viewer
├── test_pipeline.py    # end-to-end checks on generated data
├── data/
│   ├── season_2026.csv   # 2026-27: all 144 fixtures; round 1 priced, open and close
│   ├── season_2025.csv   # 2025-26 seed: the last 50 matches, priced at the close
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
| A split round is ordered by date, so no factor reads a future match | pass |
| The early home-advantage read is exact on a balanced season | **exact** |
| Fair odds round-trip to the handicap that generated them | **exact** |
| `fit_from_results` recovers line scale and margin spread *separately* | 13.72 / 16.56 vs 13.75 / 16.5 |
| `fit_from_lines` recovers the line scale from quoted lines | **exact** |
| The model runs on the closing line, and on the opening line until then | pass |
| An entry sheet from an older export cannot erase a column it lacks | pass |

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

1. **Handicaps** for the coming round: `opening_line` when the round is first
   priced, and `closing_line` once the teams are named, as late as practical
   before kick-off. Picks made on the opening line alone are provisional. In
   round 1 the close changed two of them.
2. **Scores and turnovers** for the round just played — scraped, not typed:

   ```bash
   streamlit run urc_scraper.py
   ```

   Pick the round (it defaults to the latest one played) and press *Fetch*. It
   writes `entry/scraped/urc_202601_roundNN.csv`, then:

   ```bash
   python import_turnovers.py entry/scraped/urc_202601_round01.csv --season 2026
   ```

   **Turnovers are the blocker**: without them the next round cannot be picked
   at all.
3. `python entry_sheet.py import --season 2026 && python season_report.py && python build_site.py`

### A whole past season: `urc_season_scraper.py`

For backtesting, `streamlit run urc_season_scraper.py` fetches every played
match of a finished season in one click — about 151 for a URC season — and
writes `entry/scraped/urc_202501_season.csv`. It leaves `urc_scraper.py`
untouched and **imports** its reading of the feed instead of copying it, so the
two must sit in the same folder and a fix to that code serves both. What it adds:
playoff rounds numbered 19, 20, 21 by the week each stage is played (the feed's
own knockout numbering is undocumented, and kept in `feed_round`); one retry per
failed request, with any still failing listed and a second click retrying only
those; and results held in the session, so downloading the CSV does not throw
away a two-minute pull.

### The scraper, and what it cannot yet be sure of

The match centre is a JavaScript page; its numbers come from a JSON feed
(`rugby-union-feeds.incrowdsports.com`, data from RugbyViz). `urc_scraper.py`
reads that feed directly with `requests` — the same approach as reading the FPL
API rather than the FPL website. Both endpoints it uses, the season's match
list and a single match, are documented by working code in the public
[transientlunatic/Rugby-Data](https://github.com/transientlunatic/Rugby-Data)
project, including the URC's competition id (1068).

**What is not documented anywhere is where the team stats sit inside a match
response**, and the feed is blocked from the environment this was written in,
so the scraper has not yet read a real match. Rather than hard-code a guessed
path, it walks the whole response and collects every stat carrying a home and
an away value, then picks turnovers won and conceded out by name. It is tested
against the four layouts team stats are usually published in, and against a
player carrying the same stat names with an impossible value — a player's count
must never pass as the team's.

**It saves every stat, not just turnovers.** The same search that finds the
turnovers finds everything else carrying a home and an away value — tackles,
possession, carries, whatever the feed publishes — and each becomes a
`home_`/`away_` column pair in the round's CSV, after the columns the report
reads. `import_turnovers.py` takes only its own columns from that file, and
takes them by exact name first, so a lookalike such as `home_ruck_turnovers_won`
can never be read in their place whatever order the columns are in. A stat the
feed happened to label "Score" cannot overwrite the real score either.

**First real run (round 1, Friday's three matches).** Turnovers were found for
all three, and the reading is internally consistent: each score agrees across
the three places the feed reports it, and every team's points reconcile
exactly with its tries, conversions, penalties and drop goals — 6 of 6. That
rules out reading player-level stats or crossing home and away. It turned up
one bug, since fixed: the team objects carry a date, and the leading digits of
`"2026-09-25T…"` were read as a stat (`home_date = 2026`). A string now counts
as a number only when the whole of it is one.

So the first real run is the real test. If it cannot find turnovers it says
which match, and two panels make the fix quick: **Every stat found** shows what
the feed calls things, and **Raw JSON** downloads the response to send over,
after which the extraction can be pinned to the real path. Two cases it will
deliberately refuse to guess: a bare "Turnovers" label (it could mean either),
and a match missing one of the two counts.

## View on a phone

`index.html` is self-contained and mobile-friendly — season tabs, the record,
the cumulative-profit curve, every match, and the club × round heatmaps, in
light and dark. Regenerate it with `build_site.py` after the data changes.

**<https://zenoonan.github.io/Research/rugby_urc/>**

That is the permanent home. GitHub Pages is enabled on this repository and
serves the repository root from the **default branch** — the same setup that
puts `kelly_sim/` and `nfl_report/` on the same host — so the page appears
there as soon as this work is merged, and every later `build_site.py` run
updates it on the next push. No third-party host is involved and the URL never
changes.

Before the merge that path returns a 404, because Pages only ever builds the
default branch. For that window only, the branch renders through
[raw.githack](https://raw.githack.com/ZeNoonan/Research/claude/beautiful-planck-uh4wot/rugby_urc/index.html).

## Roadmap

1. ~~Port the engine, the pipeline and the viewer.~~ ✅
2. ~~Fixture importer with URC shape checks.~~ ✅
3. ~~Spreadsheet data entry with club validation.~~ ✅
4. ~~Load the 2026-27 fixture list.~~ ✅ all 144 matches, shape checks clean
5. ~~Handle a round whose matches are months apart.~~ ✅ date ordering + match-week
   rating windows
6. ~~Enter round 1's eight handicaps.~~ ✅
7. ~~Derive the 2025-26 handicaps from 1X2 odds.~~ ✅ 50 matches, Shin + sigma 16
8. ~~Enter the 2025-26 turnovers so round 1 is pickable.~~ ✅ 15 matches, all 16 clubs
9. ~~Revisit the turnover definition against real match-centre data.~~ ✅ switched to
   own conceded − own won
10. ~~Check the inferred handicaps against real ones and re-fit `sigma`.~~ ✅
    13.75, from 12 quoted lines; the tail shown to be un-inferable
11. ~~Record opening and closing lines, and run on the close.~~ ✅ round 1 in
    both
12. **Calibrate `HOME_ADVANTAGE`** once ~40 handicaps exist (about round 5);
    watch the early read until then.
13. Revisit the turnover definition (conceded differential vs won/conceded
   separately) once a season of match-centre data is in.
