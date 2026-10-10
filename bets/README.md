# Bet log

Your actual bets, every sport, one row per bet, in **`bet_log.csv`**. It is
kept here, outside any one project: `rugby_urc/` shows the URC rows beside its
system's picks. `nfl_report/` does not read it. The NFL report keeps its own
private ledger (`nfl_report/ledger.html`), so the NFL rows here are a record
only.

**This repository is public**, so anything in this file, stakes and returns
included, can be read on GitHub, and the rugby site shows the URC bets.

## Adding bets

Send a screenshot of the bet slip (open bets or settled, both work) and it is
transcribed here, or add a row yourself. The open-bets list shows the stake and
line but no price (its figure is the cash-out value); the price comes from the
settled slip of a win, or from the bet's own detail screen. A settled losing
bet shows no price either.

A URC bet only needs `sport`, `team`, `line`, `decimal_odds` and `stake_eur`,
plus `event_date` or `round_week` to pin the match (a round number alone means
the current season). The rugby app fills in everything else from its own data:
the fixture, the closing line, and the result once the round is scraped. So a
bet logged as `Pending` settles itself. When the settled slip for an open bet
arrives, it updates that bet's row (result, returns, price) rather than adding a
second one; until then a win graded from the score has no profit, and is left
out of the totals.

## Columns

| column | what goes in it |
|---|---|
| `bet_id` | a number, unique and never reused |
| `placed` | date the bet was placed, if known (`YYYY-MM-DD`) |
| `sport` | `nfl`, `rugby`, `soccer`, `boxing`, `racing`, ... |
| `competition` | `NFL`, `URC`, ... (blank if unknown) |
| `event_date` | date of the match (`YYYY-MM-DD`) |
| `round_week` | `R1` for URC round 1, `W3` for NFL week 3, ... |
| `event` | the match, home side first: `Ulster v Edinburgh` |
| `bet_type` | `Single`, `Bet Builder`, `Doubles`, ... |
| `selection` | as shown on the bet slip (`...` where the screen cut it off) |
| `team` | the side backed, for a handicap bet |
| `line` | the handicap taken, from the backed side's view: `+6.5` = receiving 6.5 points, `-8.5` = giving them |
| `decimal_odds` | the price taken; blank if unknown |
| `stake_eur` | stake in euros |
| `result` | `Won`, `Lost`, `Void` or `Pending` |
| `returns_eur` | total paid out (0 for a loss); blank while pending |
| `profit_eur` | `returns_eur - stake_eur`; blank while pending |
| `source` | where the row came from, e.g. `screenshots 2026-10-02, 4/7` (screenshot 4, 7th bet) |
| `notes` | anything uncertain: a line cut off on screen, a guessed sport |

The first 28 rows were transcribed from four settled-bets screenshots, which
show no dates. The URC rows were dated from the fixtures; the NFL rows still
need their week.
