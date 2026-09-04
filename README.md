# Research

A workspace for experimental projects, proof-of-concepts, and research work —
much of it recreating and extending the quantitative-finance-meets-sports
work of **Aaron Brown** (Wilmott magazine, *Pulling the Goalie*, the NFL
demonstration system, the March Madness bracket model), plus assorted games
and analysis apps.

Most projects generate a **self-contained, phone-friendly web page**
(`<project>/index.html`) served from GitHub Pages at
`https://zenoonan.github.io/Research/<project>/`.

## Projects

| Project | What it is | Web view |
|---|---|---|
| [`fantasy_premier_league/`](fantasy_premier_league/) | Seven-factor weekly FPL pick sheet (Quality, Value, Form, Minutes, Nailed, Justice, Crowd vs position peers), backtested on 2025/26, ready for 2026/27; plus a pre-season draft board and a shots/xG/xA board by gameweek | [open](https://zenoonan.github.io/Research/fantasy_premier_league/) · [pre-season](https://zenoonan.github.io/Research/fantasy_premier_league/preseason.html) · [shots & xG](https://zenoonan.github.io/Research/fantasy_premier_league/shots.html) |
| [`nfl_report/`](nfl_report/) | Replication of Aaron Brown's NFL against-the-spread five-factor demonstration system (2010–2016), extended to 2019–2025 from raw data | [open](https://zenoonan.github.io/Research/nfl_report/) |
| [`march_madness/`](march_madness/) | Brown's "Quants go mad in March" factor-investing bracket model, re-implemented and verified, with a Value-pipeline bug found and fixed | [open](https://zenoonan.github.io/Research/march_madness/) · [Value tutorial](https://zenoonan.github.io/Research/march_madness/value_tutorial.html) |
| [`pulling_the_goalie/`](pulling_the_goalie/) | Replication of Asness & Brown (2018), *Pulling the Goalie: Hockey and Investment Implications* | [open](https://zenoonan.github.io/Research/pulling_the_goalie/) |
| [`monopoly/`](monopoly/) | Brown's "Monopoly 101" (Wilmott 2003): Monopoly as quantitative finance, recreated, validated and extended | [open](https://zenoonan.github.io/Research/monopoly/) |
| [`security_trading_game/`](security_trading_game/) | Brown's "Rouge et Noir" (Wilmott 2013): a security-pricing dice game | [open](https://zenoonan.github.io/Research/security_trading_game/) |
| [`VAR/`](VAR/) | Value-at-Risk backtesting on the NASDAQ Composite, from Brown's *"Forced by the Sternest Circumstances"* (Wilmott 2009) | — |
| [`kelly_sim/`](kelly_sim/) | Kelly Criterion coin-flip game: optimal bet sizing, in web and Python CLI versions | [open](https://zenoonan.github.io/Research/kelly_sim/) |
| [`premier_league_handicap/`](premier_league_handicap/) | Per-team handicap (bonus points) applied to the Premier League: adjusted table, game-by-game race, who beat their handicap. 2025/26 complete; 2026/27 handicaps and odds market live (web + Streamlit) | [26/27](https://zenoonan.github.io/Research/premier_league_handicap/) · [25/26](https://zenoonan.github.io/Research/premier_league_handicap/2025_2026/) |
| [`baseball_var/`](baseball_var/) | Little League WAR/WAA explorer, from the GameChanger spreadsheet | [open](https://zenoonan.github.io/Research/baseball_var/) |
| [`golf/`](golf/) | Golf form and course-fit research | [open](https://zenoonan.github.io/Research/golf/) |
| [`hurling/`](hurling/) | GAA.ie Hurling Team of the Week, 2026 championship | [open](https://zenoonan.github.io/Research/hurling/) |
| [`generals.bot/`](generals.bot/) | Guide to [generals.io](https://generals.io) and the [Generals bot competition](https://generals.bot), with a playable 12x12 game porting the real engine's rules | [open](https://zenoonan.github.io/Research/generals.bot/) |

Each project folder has its own README with the model details, data notes,
validation results and how to run it. The web-view links are GitHub Pages,
which serves the repo's default branch — a change goes live when its branch
is merged.

## Highlights

- **Fantasy Premier League** (new): an additive binary-factor model in the
  family of `nfl_report/` and `march_madness/` — six one-star factors
  judged against position peers behind a minutes gate. Backtested over the
  full 2025/26 season: star buckets rise from 1.27 to 3.61 actual
  next-week points, and the 5–6★ pick sheet beat the eligible pool 3.19 vs
  2.21 points per week.
- **NFL Report**: the betting logic of Brown's published sheets is fully
  reproduced (System # 98.8%, 595/599 bets), then the same report is
  generated from raw odds and results for 2019–2025.
- **March Madness**: 4,224/4,224 slot-calculation cells reproduced exactly,
  plus a fill-down bug and a sign bug in the published Value pipeline,
  found and fixed — with an in-depth
  [Value-factor tutorial](https://zenoonan.github.io/Research/march_madness/value_tutorial.html)
  (derivation, hand-checkable toy example, live trace of any 2019 team).

## Development

- **For AI assistants**: see [CLAUDE.md](CLAUDE.md) for repo conventions,
  git workflow and guidelines.
- **Branching**: feature work happens on `claude/<name>-<session-id>`
  branches and merges to the default branch by pull request.
- **Python projects**: each carries its own `requirements.txt`; typically
  `pip install -r <project>/requirements.txt` then run the scripts named in
  the project README.

---

**Status**: Active

**Last Updated**: 2026-07-17
