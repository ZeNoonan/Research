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
is the numbers. This environment's network policy blocks Wikipedia,
oddsportal.com and stats.unitedrugby.com, so handicaps are typed in, and scores
and turnovers come from the scrapers run on your machine.*

### Nothing needed for these

- **The 2026-27 fixture list** — **loaded in full**: all 144 matches, 18 rounds,
  every round pairing all 16 clubs exactly once, every club 9 home and 9 away.
  Imported from your paste with `import_fixtures.py`; the shape checks pass
  clean. Re-run that command if the URC moves a fixture.
- **Round 1's eight handicaps, opening and closing** — **received and loaded**.
  Four lines moved once the teams were named, and two of those moves change
  the picks; see *The line the model runs on*.
- **The whole 2025-26 season** — **received and loaded**: all 151 matches (144
  regular, 7 playoff) from `urc_season_scraper.py`, with the feed's scores and
  turnover counts, and a handicap on every one: your 14 quoted lines kept, the
  other 137 inferred from your oddsportal odds. The feed's scores agree with
  oddsportal's on all 151. See *How it did on 2025-26*.

**A correction.** The turnover sheet you sent earlier for the 2025-26 run-in
had a "lost" column that was already a **net** figure — turnovers conceded
minus turnovers won, in all 30 club-matches (Cardiff's −1 against the Stormers
is 7 − 8). I loaded it as a raw count, which was my error. Those 15 matches now
carry the feed's own counts, and `import_season.py` listed every value it
replaced. With the error fixed, the full season also showed that the turnover
definition this project had switched to could not work — see *A turnover is
not a giveaway*. Between them, they swap one of round 1's picks; see *The line
the model runs on*.

### 1. Ten handicaps that would firm up the backtest (optional)

Of the 45 graded 2025-26 bets, **10 covered or missed their inferred line by
less than that line is good for**: about a point and a half, or three for a
heavy favourite quoted near 1.01. On those ten the W or L rests on the estimate
rather than the result, and seven of them are wins, so they are worth checking.

| date | match | inferred | bet | result | by |
|---|---|---|---|---|---|
| 2025-10-03 | Dragons v Sharks | +1.0 | Dragons | W | 1.0 |
| 2025-10-05 | Zebre v Lions | −2.5 | Lions | W | 0.5 |
| 2025-10-17 | Connacht v Bulls | 0.0 | Bulls | W | 1.0 |
| 2025-10-17 | Dragons v Cardiff | +8.0 | Dragons | W | 1.0 |
| 2025-10-24 | Glasgow v Bulls | −9.5 | Bulls | W | 0.5 |
| 2025-10-25 | Leinster v Zebre | −22.5 | Leinster | W | 1.5 |
| 2025-12-27 | Munster v Leinster | +5.5 | Munster | W | 0.5 |
| 2026-01-24 | Cardiff v Benetton | −7.5 | Benetton | L | −1.5 |
| 2026-03-28 | Stormers v Edinburgh | −17.5 | Edinburgh | L | −1.5 |
| 2026-05-16 | Bulls v Benetton | −25.5 | Benetton | L | −0.5 |

They are in **`entry/urc_2025_close_calls.xlsx`**. The number wanted is the
home handicap from oddsportal's handicap tab, negative when the home side is
favoured, typed into `actual_line`. Then:

```bash
python line_check.py apply --season 2025 && python season_report.py && python build_site.py
```

They land marked as quoted, so no later import overwrites them. None of this
touches the 2026-27 picks: it only says how far to trust the backtest. The four
other heavy-favourite lines asked for earlier
(`entry/urc_2025_coarse_lines.xlsx`) are lower priority still; `apply` reads
both sheets.

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

With the whole of 2025-26 loaded, `calibrate.py` pools 159 priced matches. It
fits **+5.3** for home advantage, close to the provisional 5.0, and **+3.3**
for a long-haul trip, a term currently switched off. The early read is **+5.4
over 101 domestic matches** and **+8.5 over 58 long-haul ones**.

**Not adopted, for now.** 137 of those lines are inferred rather than quoted,
and one set of ratings is fitted across a whole season, where the model refits
every week. More to the point, adopting either number did not help the
backtest: 5.3 did slightly worse than 5.0, and adding the long-haul term did
clearly worse (below). Revisit around round 5, when this season's own quoted
lines carry the fit.

## How it did on 2025-26

The whole season, run through the system exactly as 2026-27 will be:

| | bets | record | win rate | units at −110 |
|---|---|---|---|---|
| **2025-26** | 46 (one push) | **22–23** | **48.9%** | **−3.3** |

Break-even at −110 is 52.4%, so on this season the system **lost a little**.
Round 1 made no picks, because there is no 2024-25 file to seed its ratings;
nor did the playoffs, where no match reached ±3.

**Read it as one season, not a verdict.** 45 bets carry a standard error of
about 7.5 points on the win rate. This record sits as comfortably with a
system that wins 55% of the time as with one that wins 45%. Nor is it being
flattered by the settings: no value of `sigma` or home advantage tried did
better.

| what was varied | values | best | worst |
|---|---|---|---|
| `sigma` for the inferred lines | 12, 13, 13.75, 14.5, 16 | 22–23 (13–13.75) | 20–25, −7.5u (14.5) |
| `HOME_ADVANTAGE` | 3, 4, 5, 5.3, 6, 7 | 22–23 (5.0) | 20–24, −6.4u (3, 4) |
| long-haul term 3.3, home 5.3 | — | — | 20–26, −8.6u |

The run-in did no better than the start: rounds 1–9 went 13–13, rounds 10–18
went 9–10. Away picks went 17–17 and home picks 5–6. The picks lean heavily
away, 34 of 46, which is the lean the power factor's construction predicts
(see *Power factor detail*).

**Each factor on its own** (`factor_analysis.py`), as a win rate when it votes:

| factor | votes | right | rate |
|---|---|---|---|
| Power / over-reaction | 140 | 73 | 52.1% |
| Turnover — home | 133 | 70 | 52.6% |
| Turnover — away | 135 | 59 | 43.7% |
| Hunger — home | 122 | 63 | 51.6% |
| Hunger — away | 118 | 54 | 45.8% |

All five are within two standard errors of 50%, so none of them is
established either way. The away turnover factor at 43.7% is the weakest, and
the thing to watch this season, not a reason to flip it: choosing factors by
how they did on the season they are then tested on is exactly the
curve-fitting the NFL project was careful to avoid.

**How good are the inferred lines?** A fair line should see the home side
cover about half the time, and across the 151 matches it covered 77, failed 71
and pushed 3. The inference is not leaning either way. What it cannot do is
settle a bet decided by a point, hence the ten above.

**The turnover definition, varied.** For the record, since it changed on this
data (next section), the season under each candidate. None was chosen for its
number, because with 45 bets a gap of 6 wins is noise.

| turnover margin | record | units |
|---|---|---|
| **conceded − opponent's conceded** (in use; the NFL computation) | 22–23 | −3.3 |
| opponent's won − own won | 25–20 | +3.0 |
| own net − opponent's net (both counts) | 19–27 | −10.7 |
| own conceded − own won (the definition replaced) | 18–14 | +2.6 |

The last row has the best win rate, but its two turnover factors cancelled
each other on 81% of matches, so it is really a three-factor system.

## Shadow factors: nine candidates, tracked but not bet

Nine candidate factors run alongside the five in `shadow_factors.py`. Each
casts the same kind of vote (+1 home, −1 away, 0 neither), but **none counts
towards the System # or the picks**. They are there to be tested.

### The protocol

Testing nine things on one season is the easiest way there is to find an edge
that is not there. A factor that votes about 100 times has a 95% band of
roughly 40–60% with no edge at all, so on nine factors one or two will look
good by chance. So:

1. **The rules below were fixed and committed before any of them was run on
   real data**, and are not tuned afterwards. The commit history shows the
   order.
2. **2025-26 is the first look; 2026-27 is the test.** Only a factor that
   holds up on a season it was not chosen on is a candidate for the system.
3. **Every factor is reported**, not only the ones that look good.

"Last match" means a club's previous match by date, carried across the season
boundary like the turnover factor. A factor **abstains** when it cannot be
computed: a club's first match (so all of round 1 of 2025-26), or a previous
match with no stats or no line.

### The rules

**Luck** (the turnover factor's logic: something swung a club's last result
that does not repeat, so the next line over-reacts). Each compares the club
with its own opponent in its last match, and the vote backs the side the
comparison favours; if both sides score the same, no vote. The direction comes
from the theory and is fixed.

| # | factor | a club is backed (+) or faded (−) when, last match… |
|---|---|---|
| 1 | **Last result v the line** | + it missed the handicap by 10 or more; − it beat it by 10 or more |
| 2 | **Cards** | + it had more cards than its opponent (yellow 1, red 2); − fewer |
| 3 | **Goal-kicking** | + it left more points on the tee than its opponent (2 per missed conversion, 3 per missed penalty); − fewer |
| 4 | **Scoring from the 22** | + it scored fewer points per visit to the opponent's 22 than its opponent did; − more |

**Situational.** The theory does not say which way these should go, so each
is written in one direction by convention. 2025-26 decides the direction, once,
and 2026-27 tests it.

| # | factor | votes | as written |
|---|---|---|---|
| 5 | **Long-haul trip** | the away side crosses between Europe and South Africa (not at a neutral venue) | backs home |
| 6 | **Second match of a tour** | the away side's previous match was also abroad, 8 days or fewer earlier | backs home |
| 7 | **Derby** | both clubs are from the same country | backs the underdog |
| 8 | **Big handicap** | the handicap is 14 points or more | backs the underdog |

**Market** (needs opening lines, which only 2026-27 has, so 2026-27 is its
first look).

| # | factor | votes | as written |
|---|---|---|---|
| 9 | **Line move** | the close is 2 or more points from the open | backs the side the line moved against: fades the move, the over-reaction reading the power factor already takes |

### What is reported

For each factor and season: how often it voted, its record on the matches it
voted on (pushes excluded), a 95% band, and **the system's record with it
added as a sixth vote**. That is the five-factor System # plus this vote,
betting at the same ±3, and only where the system itself could bet.

The stats come from `data/stats_<year>.csv`, which holds every stat the
scrapers fetch (about 100 per match). `import_season.py` writes it for a whole
season and `import_turnovers.py` adds to it each round, so the weekly routine
does not change.

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
- **`lgt`** — the side's turnover margin in its previous match: **its
  turnovers conceded − its opponent's**. Positive = lost the turnover count.
  Zero-sum within a match, as in the NFL; see *A turnover is not a giveaway*.
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
| Lions v Leinster | +7.5 | −7.5 | +3 → +1: **Lions no longer a bet** |
| Munster v Glasgow | −2.5 | +3.5 | +1 → +3: **Munster +3.5 now a bet** |
| Connacht v Stormers | −1.5 | −6.5 | −2, unchanged |
| Sharks v Ospreys | −12.5 | −10.5 | −1, unchanged |

The Dragons (+9.5 at Benetton) and the Bulls (−11.5 at Zebre) did not move, so
the round has three bets: **Dragons, Munster, Bulls**. Until the turnover fix
it was Edinburgh (+11.5 at Ulster) in place of the Dragons. Both covered on
Friday, but Edinburgh's pick rested on the mislabelled seed and the replaced
definition, so the Dragons are the pick of record.

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
a **differential between the two sides**, `home_giveaways − away_giveaways`,
which is exact there because a giveaway by one team is by definition a
takeaway by the other.

**In use here: the same differential, on turnovers conceded.** A club's margin
is its turnovers conceded minus its opponent's: the NFL line with the match
centre's "turnovers conceded" in place of giveaways. Zero-sum, like the
original, so in every match one side lost the count and the other won it.

**The detour, and why it was wrong.** This project started with exactly that
differential. It then switched to reading the NFL definition literally, as
**own conceded − own won**, on the evidence of the first 15 matches of
match-centre data, in which one side's "conceded" never matched the other's
"won". That evidence was mislabelled, since the sheet's "conceded" column was
already net of turnovers won (see *A correction*, above), though the point
itself survives on the feed's counts: they match in only 4 of 302
club-matches. What the switch missed is the thing a full season makes
obvious:

| per club per match, 2025-26 | mean | range |
|---|---|---|
| turnovers conceded | 13.4 | 4–25 |
| turnovers won | 6.1 | 1–15 |

The two counts are different sizes: "conceded" is every way of losing the ball,
handling errors included, while "won" is only ball taken off the opponent. A
club's own conceded minus its own won was therefore **positive in 281 of 302
club-matches**. Nearly everyone "lost the count" nearly every week, so the home
turnover factor backed the home side and the away factor the away side, and on
**81% of matches the two cancelled out**. As a vote it measured nothing.

The differential does not have that problem, because it compares like with
like: two clubs' turnovers conceded, in the same match, counted the same way.
Turnovers won is still scraped and stored; the model does not read it, so a
blank never blocks a pick. `test_pipeline.py` check 14 pins the definition down.

**A note on negative turnover counts.** A count cannot be negative, so a
negative value means a column holds something else, most likely a net figure.
That is how the one seen so far arose: the −1 in 2025-26's Cardiff v Stormers
came from a sheet whose "lost" column was conceded minus won (7 − 8).
`import_turnovers.py` flags such a value on every run, and `--strict` refuses
it.

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

**Removing the bookmaker's margin.** The quotes sum to about 8.3% over
certainty. Dividing through by that — the obvious fix — systematically
overstates short prices. Shin's method, which models the book as protecting
itself against better-informed traders, takes proportionally more out of the
longshots. The test is whether the resulting lines behave like lines:

| de-vig | home cover rate vs its own inferred line: first 50 matches | all 151 |
|---|---|---|
| proportional | 54.0% | 54.7% |
| additive | 48.0% | 51.0% |
| **Shin** | **48.0%** | **52.0%** |

A fair line should produce about 50%. Proportional leans home in both samples,
while Shin and additive stay within two points of 50%. On this many matches none of
those gaps is conclusive (the standard error on 148 is about 4 points), so
Shin is used because it is built for exactly this bias, with the data
agreeing rather than proving it.

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
| **Turnovers** | `home_giveaways − away_giveaways` | **the same differential, on turnovers conceded** |
| **Home edge** | 3.0 points, well established | **5.0, provisional**, plus an optional long-haul term |
| **Heatmap scale** | red-yellow-green | **blue ↔ grey ↔ red** |
| **Validation** | 7 published seasons | none — generated-data tests only |

**One file per season.** Both rugby inputs are read off web pages by hand, so
joining two hand-keyed tables would turn every typo into a silently dropped
match. `data/season_<year>.csv` carries the fixture, the opening and closing
handicaps, the score and the turnover counts in one row, and `entry_sheet.py`
keeps the typing in a spreadsheet rather than in the CSV.

**Turnovers: the conceded differential.** The NFL computation with turnovers
conceded in place of giveaways. It went to own conceded − own won and back; see
*A turnover is not a giveaway* above.

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
├── line_check.py       # check inferred handicaps against real ones, re-fit sigma,
│                       #   and list the bets a line error could flip
├── import_turnovers.py # match-centre turnover sheet -> season file (scores too)
├── import_season.py    # a whole scraped past season + its odds -> season file
├── match_stats.py      # every scraped stat per match -> data/stats_<year>.csv
├── shadow_factors.py   # nine candidate factors, tracked but not bet
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
│   ├── season_2025.csv   # 2025-26 in full: 151 matches, priced at the close
│   ├── stats_<year>.csv  # every scraped stat, one row per match
│   ├── shadow_<year>.csv # generated: each match's shadow-factor votes
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
| LGT is the conceded differential: zero-sum, blind to turnovers won | pass |
| A scraped season loads with quoted lines kept and replaced values reported | pass |
| The close-calls sheet lists exactly the bets a line error could flip | pass |
| Each shadow factor votes as its rule is written, on a hand-built case | pass |
| Shadow factors end to end: stats stored and reloaded, a reversed direction swaps a record | pass |

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
python shadow_factors.py                           # the nine candidate factors
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

Then load it, with the season's oddsportal results page pasted to a text file:

```bash
python import_season.py entry/scraped/urc_202501_season.csv --odds odds.txt --season 2025
python season_report.py && python factor_analysis.py
```

`import_season.py` takes the scraped file as the backbone — fixtures, dates,
rounds, scores and turnover counts all come from the feed — and hangs a
handicap on every match, inferred from its 1X2 odds and matched by club pair
and nearest date. Any line already quoted in the season file is kept, along
with opening lines and neutral-venue flags. Turnover counts already there are
**replaced** by the feed's, and each replaced value is listed, so the season
file holds the same statistic the live season is scraped with. It reports any
match with no odds, any quote that matched no match, and any score that
disagrees.

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
7. ~~Derive the 2025-26 handicaps from 1X2 odds.~~ ✅ all 151 matches, Shin +
   sigma 13.75, 14 quoted lines kept
8. ~~Enter the 2025-26 turnovers so round 1 is pickable.~~ ✅ the whole season,
   from the feed
9. ~~Revisit the turnover definition once a season of match-centre data is
   in.~~ ✅ back to the conceded differential, the NFL computation; own
   conceded − own won does not vary enough to vote
10. ~~Check the inferred handicaps against real ones and re-fit `sigma`.~~ ✅
    13.75, from 12 quoted lines; the tail shown to be un-inferable
11. ~~Record opening and closing lines, and run on the close.~~ ✅ round 1 in
    both
12. ~~Backtest 2025-26.~~ ✅ 22–23, −3.3u; see *How it did on 2025-26*
13. **Calibrate `HOME_ADVANTAGE`** on this season's own quoted lines, about
    round 5. 2025-26's inferred lines fit 5.3, not adopted.
14. Firm up the backtest with the ten close-call lines (optional).
