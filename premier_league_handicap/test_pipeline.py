"""Independent checks of the built handicap pages, recomputed from the raw data.

Each page carries its numbers as JSON between ``/*__DATA__*/`` and
``/*__END_DATA__*/``. This file recomputes every one of them from the CSVs in
``data/`` and reports any that disagree. For every season with a
``season_handicap.csv``:

1. the page: ``<season>/index.html`` exists, the root ``index.html`` carries
   the latest season, no ``{{PLACEHOLDER}}`` is left, the status line ("10
   games played", "final") is right and the links to other seasons work;
2. the source data: every club resolves to the handicap file, no fixture
   appears twice, each FBref date falls on FBref's own weekday, and FBref and
   the football-data export agree on the date and score of every fixture in
   both;
3. standings: each club's record, actual points, the handicap earned so far
   (handicap x played / 38) and adjusted points; the table order, both ranks,
   the game-by-game list, both cumulative series and the summary figures;
4. the odds market on the handicap league, in seasons that have odds;
5. Asian handicap: every match settled in exact fractions against ``AHh``,
   with ``AHCh`` standing in where ``AHh`` is blank. Checks the table, its
   order and ranks, each club's cover series, each game's line and result, the
   spread against chance, the typical price and the gap/line correlation;
6. win-and-draw bets, in both splits (EUR10 + EUR10, and the equal-payout
   split). Checks each game's stake and profit, the table, both series, the
   league totals, the draw share, profit by result, and the best-available,
   Bet365 and closing-price comparisons. The chance figures are checked
   against this file's own Monte Carlo.

Independence is the point. This file never imports ``analysis.py`` or
``build_site.py``; it keeps its own club names, date parsing and settlement
rules. A check that reuses the pipeline's code repeats the pipeline's
mistakes. When a day-first date parse turned 2026-09-05 into 9 May, a check
built on the same loader passed it. Keep it that way.

Run after every build:

    python3 test_pipeline.py              # check every season's page
    python3 test_pipeline.py --self-test  # plant faults in copies of the
                                          # pages; confirm each one is caught

Exit status 0 means every check passed. With ``--self-test`` it means every
planted fault was caught.
"""

from __future__ import annotations

import argparse
import copy
import csv
import itertools
import json
import math
import re
import statistics
import sys
from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
GAMES_PER_SEASON = 38
STAKE = 10.0                    # on the win, and again on the draw: 2 x STAKE a game
PRICE_SETS = (("Max", "best available"), ("B365", "Bet365"), ("AvgC", "closing market-average"))
SPLITS = (("wd", "even"), ("wde", "equal"))
BUILD_SIMS = 5000               # seasons in the build's Monte Carlo; sets its noise
CHECK_SIMS, CHECK_SEED = 20000, 424242
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DATA_RE = re.compile(r"/\*__DATA__\*/(.*?)/\*__END_DATA__\*/", re.S)
SCORE_RE = re.compile(r"(\d+)\s*[-‐-―−]\s*(\d+)")

# A figure published to n decimal places sits within half a unit in the nth
# place of the exact one.
DP = {n: 0.5 * 10 ** -n + 1e-9 for n in range(7)}

# Each source spells some clubs its own way. These groups resolve any
# spelling to the handicap file's, which the pages use. They are kept apart
# from analysis.CLUB_ALIASES on purpose.
SAME_CLUB = (
    ("Manchester Utd", "Manchester United", "Man United", "Man Utd"),
    ("Manchester City", "Man City"),
    ("Newcastle Utd", "Newcastle United", "Newcastle"),
    ("Nott'ham Forest", "Nottingham Forest", "Nott'm Forest", "Nottingham", "Nottm Forest"),
    ("Leeds United", "Leeds Utd", "Leeds"),
    ("Tottenham", "Tottenham Hotspur", "Spurs"),
    ("West Ham", "West Ham United", "West Ham Utd"),
    ("Wolves", "Wolverhampton Wanderers", "Wolverhampton"),
    ("Brighton", "Brighton & Hove Albion", "Brighton and Hove Albion"),
    ("Bournemouth", "AFC Bournemouth"),
    ("Hull", "Hull City"),
    ("Coventry", "Coventry City"),
    ("Ipswich", "Ipswich Town"),
    ("Leicester City", "Leicester"),
    ("Luton Town", "Luton"),
    ("Sheffield Utd", "Sheffield United"),
    ("West Brom", "West Bromwich Albion", "West Bromwich"),
)
# How the pages shorten a club's name in tables and as an opponent.
SHORT = {"Manchester City": "Man City", "Manchester Utd": "Man Utd", "Newcastle Utd": "Newcastle",
         "Nott'ham Forest": "Forest", "Crystal Palace": "Palace", "Leeds United": "Leeds"}


def short(club):
    return SHORT.get(club, club)


def resolve(name, clubs):
    """The handicap file's spelling of a club, or None when it cannot be placed."""
    name = name.strip()
    if name in clubs:
        return name
    for group in SAME_CLUB:
        if name in group:
            hits = [c for c in group if c in clubs]
            if len(hits) == 1:
                return hits[0]
    return None


def day_month(d):
    """A date as the pages write it, e.g. 05 Sep."""
    return f"{d.day:02d} {MONTHS[d.month - 1]}"


def near(value, exact, tol):
    """Whether a published number lies within tol of the exact figure."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return abs(value - float(exact)) <= tol


def close_list(values, exact, tol):
    return (isinstance(values, list) and len(values) == len(exact)
            and all(near(v, x, tol) for v, x in zip(values, exact)))


def pearson(xs, ys):
    xs, ys = [float(x) for x in xs], [float(y) for y in ys]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else None


class Expect:
    """Collects the description of every check that fails."""

    def __init__(self, problems=None, prefix=""):
        self.problems = [] if problems is None else problems
        self.prefix = prefix

    def __call__(self, ok, message):
        if not ok:
            self.problems.append(self.prefix + message)
        return bool(ok)

    def under(self, label):
        return Expect(self.problems, f"{self.prefix}{label}: ")


# --- the raw data -------------------------------------------------------------

@dataclass
class Match:
    d: date
    h: str
    a: str
    hg: int
    ag: int
    line: Fraction | None = None    # Asian handicap line on the home side
    stand_in: bool = False          # the closing line (AHCh) because AHh was blank
    prices: dict = field(default_factory=dict)   # "Avg", "Max", ... -> (home, draw, away)


@dataclass
class Season:
    key: str
    handicap: dict                  # club -> handicap points
    odds: dict | None = None        # club -> decimal odds to win the handicap league
    results: list | None = None     # played matches in results.csv; None before a ball is kicked
    lines_file: str | None = None   # the file with Asian handicap lines and 1X2 prices
    lines: list = field(default_factory=list)       # its played matches
    columns: set = field(default_factory=set)       # its header
    ah_prices: list = field(default_factory=list)   # (AvgAHH, AvgAHA) per priced row
    problems: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    @property
    def label(self):
        return self.key.replace("_", "-")


def cell(row, key):
    return (row.get(key) or "").strip()


def read_rows(path, tamper=None):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        header = list(reader.fieldnames or [])
    if tamper:
        tamper(path.name, rows)
    return header, rows


def parse_date(text):
    """ISO (FBref) or day-first (football-data). Never guesses the order."""
    iso = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if iso:
        y, m, d = map(int, iso.groups())
        return date(y, m, d)
    dmy = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})", text)
    if dmy:
        d, m, y = map(int, dmy.groups())
        return date(y + 2000 if y < 100 else y, m, d)
    raise ValueError(f"unrecognised date {text!r}")


def check_fixtures(S, matches, source):
    seen, busy = set(), set()
    for m in matches:
        if m.h == m.a:
            S.problems.append(f"{source}: {m.h} listed against itself")
        if (m.h, m.a) in seen:
            S.problems.append(f"{source}: {m.h} v {m.a} appears twice")
        seen.add((m.h, m.a))
        for club in (m.h, m.a):
            if (club, m.d) in busy:
                S.problems.append(f"{source}: {club} has two games on {m.d}")
            busy.add((club, m.d))


def read_results(S, header, rows):
    if {"Home", "Away", "Score"} <= set(header):
        home_col, away_col, fbref = "Home", "Away", True
    elif {"HomeTeam", "AwayTeam", "FTHG", "FTAG"} <= set(header):
        home_col, away_col, fbref = "HomeTeam", "AwayTeam", False
    else:
        S.problems.append("results.csv is in neither FBref's layout (Home, Score, Away) nor "
                          "football-data's (HomeTeam, AwayTeam, FTHG, FTAG)")
        return []
    matches = []
    for line_no, r in enumerate(rows, start=2):
        where = f"results.csv line {line_no}"
        home, away = cell(r, home_col), cell(r, away_col)
        if fbref:
            if not home or not cell(r, "Score"):
                continue                # a separator row, or a fixture not yet played
            score = SCORE_RE.fullmatch(cell(r, "Score"))
            if not score:
                S.problems.append(f"{where}: cannot read the score {cell(r, 'Score')!r}")
                continue
            hg, ag = int(score.group(1)), int(score.group(2))
        else:
            if not home or not cell(r, "FTHG") or not cell(r, "FTAG"):
                continue
            hg, ag = int(float(cell(r, "FTHG"))), int(float(cell(r, "FTAG")))
        try:
            d = parse_date(cell(r, "Date"))
        except ValueError as err:
            S.problems.append(f"{where}: {err}")
            continue
        day = cell(r, "Day")
        if day and WEEKDAYS[d.weekday()] != day[:3]:
            S.problems.append(f"{where}: {cell(r, 'Date')} is a {WEEKDAYS[d.weekday()]}, "
                              f"but the Day column says {day}")
        h, a = resolve(home, S.handicap), resolve(away, S.handicap)
        if h is None or a is None:
            S.problems.append(f"{where}: cannot match {home!r} v {away!r} to the handicap file")
            continue
        matches.append(Match(d, h, a, hg, ag))
    matches.sort(key=lambda m: (m.d, m.h))
    check_fixtures(S, matches, "results.csv")
    return matches


def read_lines(S, header, rows):
    """The football-data export: Asian handicap lines and 1X2 prices."""
    S.columns = set(header)
    sets = ("Avg",) + tuple(pre for pre, _ in PRICE_SETS)
    for line_no, r in enumerate(rows, start=2):
        where = f"{S.lines_file} line {line_no}"
        if cell(r, "AvgAHH") and cell(r, "AvgAHA"):
            S.ah_prices.append((float(cell(r, "AvgAHH")), float(cell(r, "AvgAHA"))))
        home, away = cell(r, "HomeTeam"), cell(r, "AwayTeam")
        if not home or not away or not cell(r, "FTHG") or not cell(r, "FTAG"):
            continue
        h, a = resolve(home, S.handicap), resolve(away, S.handicap)
        if h is None or a is None:
            S.problems.append(f"{where}: cannot match {home!r} v {away!r} to the handicap file")
            continue
        try:
            d = parse_date(cell(r, "Date"))
        except ValueError as err:
            S.problems.append(f"{where}: {err}")
            continue
        m = Match(d, h, a, int(float(cell(r, "FTHG"))), int(float(cell(r, "FTAG"))))
        opening, closing = cell(r, "AHh"), cell(r, "AHCh")
        if opening or closing:
            m.line, m.stand_in = Fraction(opening or closing), not opening
            if (4 * m.line).denominator != 1:
                S.problems.append(f"{where}: Asian handicap line {opening or closing} "
                                  "is not a multiple of 0.25")
                m.line = None
        for pre in sets:
            keys = [pre + k for k in "HDA"]
            if set(keys) <= S.columns:
                quoted = [cell(r, k) for k in keys]
                m.prices[pre] = tuple(float(x) for x in quoted) if all(quoted) else None
        S.lines.append(m)
    S.lines.sort(key=lambda m: (m.d, m.h))
    check_fixtures(S, S.lines, S.lines_file)


def compare_sources(S):
    """FBref and football-data must agree on every fixture they both have."""
    known = {(m.h, m.a): m for m in S.results}
    shared = 0
    for m in S.lines:
        r = known.get((m.h, m.a))
        if r is None:
            continue
        shared += 1
        if (r.d, r.hg, r.ag) != (m.d, m.hg, m.ag):
            S.problems.append(f"{m.h} v {m.a}: results.csv has {r.d} {r.hg}-{r.ag}, "
                              f"{S.lines_file} has {m.d} {m.hg}-{m.ag}")
    if len(S.results) > shared:
        S.notes.append(f"{len(S.results) - shared} result(s) not yet in {S.lines_file}")
    if len(S.lines) > shared:
        S.notes.append(f"{len(S.lines) - shared} match(es) in {S.lines_file} not in results.csv")


def load_season(key, tamper=None):
    folder = DATA / key
    header, rows = read_rows(folder / "season_handicap.csv", tamper)
    S = Season(key, {})
    if "odds" in header:
        S.odds = {}
    for r in rows:
        team = cell(r, "team")
        if not team:
            continue
        S.handicap[team] = Fraction(cell(r, "handicap"))
        if S.odds is not None:
            if cell(r, "odds"):
                S.odds[team] = float(cell(r, "odds"))
            else:
                S.problems.append(f"season_handicap.csv: no odds for {team}")

    results_header, results_rows = [], []
    if (folder / "results.csv").exists():
        results_header, results_rows = read_rows(folder / "results.csv", tamper)
        S.results = read_results(S, results_header, results_rows)
    if (folder / "football_data.csv").exists():
        S.lines_file = "football_data.csv"
        read_lines(S, *read_rows(folder / S.lines_file, tamper))
        if S.results is not None:
            compare_sources(S)
    elif "AHh" in results_header:
        # a football-data export doubling as the results file, as 2025/26's is
        S.lines_file = "results.csv"
        read_lines(S, results_header, results_rows)
    return S


def read_page(path):
    """[html, payload] for a built page; None when the page does not exist."""
    if not path.exists():
        return None
    html = path.read_text(encoding="utf-8")
    found = DATA_RE.search(html)
    try:
        return [html, json.loads(found.group(1)) if found else None]
    except json.JSONDecodeError:
        return [html, None]


def discover():
    return sorted(p.name for p in DATA.iterdir()
                  if p.is_dir() and (p / "season_handicap.csv").exists())


def load_site(seasons):
    site = {key: read_page(HERE / key / "index.html") for key in seasons}
    site["root"] = read_page(HERE / "index.html")
    return site


# --- 1. the page itself ---------------------------------------------------------

def page_season(path, seasons):
    """Which season a page shows: the root index.html is the latest one."""
    if path == HERE / "index.html":
        return seasons[-1]
    return path.parent.name if path.parent.parent == HERE else None


def check_shell(S, html, path, status, expect, seasons):
    where = path.relative_to(HERE).as_posix()
    left = sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", html)))
    expect(not left, f"{where}: placeholder(s) left unfilled: {left}")
    kicker = re.search(r'class="kicker">([^<]*)</div>', html)
    want = f"Premier League &middot; {S.label} &middot; {status}"
    expect(kicker is not None and kicker.group(1).strip() == want,
           f"{where}: status line {kicker.group(1).strip() if kicker else None!r}, expected {want!r}")
    nav = re.search(r'<nav class="seasons"[^>]*>(.*?)</nav>', html, re.S)
    linked = set()
    for href in re.findall(r'href="([^"]*)"', nav.group(1) if nav else ""):
        target = (path.parent / href).resolve()
        target = target / "index.html" if target.is_dir() else target
        if expect(target.exists(), f"{where}: the link {href!r} leads nowhere"):
            linked.add(page_season(target, seasons))
    others = set(seasons) - {S.key}
    expect(linked == others, f"{where}: links to {sorted(x for x in linked if x)}, "
                             f"expected the other seasons {sorted(others)}")


def check_root(site, latest, expect):
    root, page = site.get("root"), site.get(latest)
    if not expect(root is not None and root[1] is not None, "index.html is missing or has no data"):
        return
    expect(page is not None and root[1] == page[1],
           f"index.html does not carry the latest season's page ({latest}/index.html); "
           "run build_site.py")


# --- 3. standings ---------------------------------------------------------------

@dataclass
class TeamGame:
    d: date
    opp: str
    v: str
    gf: int
    ga: int

    @property
    def p(self):
        return 3 if self.gf > self.ga else 1 if self.gf == self.ga else 0


def check_preseason(S, pl, expect):
    expect(pl.get("hasResults") is False and pl.get("complete") is False
           and pl.get("maxPlayed") == 0, "pre-season page with results flags set")
    teams = pl.get("teams", [])
    order = sorted(S.handicap, key=lambda c: (S.handicap[c], c))
    expect([t.get("name") for t in teams] == order, "pre-season list is not in handicap order")
    for t in teams:
        c = t.get("name")
        if c not in S.handicap:
            continue
        ok = (t.get("short") == short(c) and t.get("handicap") == S.handicap[c]
              and near(t.get("perGame"), S.handicap[c] / GAMES_PER_SEASON, DP[4]))
        if S.odds is not None:
            ok = ok and t.get("odds") == S.odds.get(c)
        expect(ok, f"{c}: pre-season row {t}")
    return "before a ball is kicked"


def check_standings(S, pl, expect):
    """Returns the status line the page should show."""
    games = {c: [] for c in S.handicap}
    for m in S.results:
        games[m.h].append(TeamGame(m.d, m.a, "H", m.hg, m.ag))
        games[m.a].append(TeamGame(m.d, m.h, "A", m.ag, m.hg))
    rec = {}
    for c, g in games.items():
        g.sort(key=lambda x: x.d)
        n, pts = len(g), sum(x.p for x in g)
        earned = S.handicap[c] * n / GAMES_PER_SEASON          # exact, as a Fraction
        rec[c] = dict(played=n, actual=pts, gf=sum(x.gf for x in g), ga=sum(x.ga for x in g),
                      w=sum(x.p == 3 for x in g), dr=sum(x.p == 1 for x in g),
                      l=sum(x.p == 0 for x in g), earned=earned, to_date=pts + earned)

    played = [r["played"] for r in rec.values()]
    complete, most = all(n == GAMES_PER_SEASON for n in played), max(played)
    expect(pl.get("hasResults") is True and pl.get("complete") == complete
           and pl.get("maxPlayed") == most,
           f"flags: complete {pl.get('complete')}, maxPlayed {pl.get('maxPlayed')}; "
           f"expected {complete}, {most}")

    teams = pl.get("teams", [])
    names = [t.get("name") for t in teams]
    expect(sorted(names) == sorted(S.handicap),
           f"the table's clubs differ from the handicap file's: {sorted(set(names) ^ set(S.handicap))}")

    def adj_key(c):
        return (rec[c]["to_date"], rec[c]["gf"] - rec[c]["ga"], rec[c]["gf"])

    def act_key(c):
        return (rec[c]["actual"], rec[c]["gf"] - rec[c]["ga"], rec[c]["gf"])

    # clubs level on all three tie-breaks may be listed either way round
    listed = [c for c in names if c in rec]
    for above, below in zip(listed, listed[1:]):
        expect(adj_key(above) >= adj_key(below), f"adjusted table lists {above} above {below}")
    expect([t.get("adjRank") for t in teams] == list(range(1, len(teams) + 1)),
           "adjusted ranks do not run 1, 2, 3, ... down the table")
    by_actual = sorted((t for t in teams if t.get("name") in rec),
                       key=lambda t: t.get("actualRank") or 0)
    expect([t.get("actualRank") for t in by_actual] == list(range(1, len(by_actual) + 1)),
           "actual ranks are not 1 to 20")
    for above, below in zip(by_actual, by_actual[1:]):
        expect(act_key(above["name"]) >= act_key(below["name"]),
               f"actual table ranks {above['name']} above {below['name']}")

    for t in teams:
        c = t.get("name")
        if c not in rec:
            continue
        r, e = rec[c], expect.under(c)
        e(t.get("short") == short(c), f"short name {t.get('short')!r}")
        e(t.get("handicap") == S.handicap[c], f"handicap {t.get('handicap')} vs {S.handicap[c]}")
        for k in ("actual", "played", "w", "dr", "l", "gf", "ga"):
            e(t.get(k) == r[k], f"{k} {t.get(k)} vs {r[k]}")
        full = round(r["actual"] + S.handicap[c])
        e(t.get("adjusted") == full and t.get("adjustedFull") == full,
          f"adjusted {t.get('adjusted')}/{t.get('adjustedFull')} vs {full}")
        e(near(t.get("adjustedToDate"), r["to_date"], DP[3]),
          f"adjustedToDate {t.get('adjustedToDate')} vs {float(r['to_date']):.3f}")
        e(near(t.get("handicapToDate"), r["earned"], DP[3]),
          f"handicapToDate {t.get('handicapToDate')} vs {float(r['earned']):.3f}")
        if S.odds is not None:
            e(t.get("odds") == S.odds.get(c), f"odds {t.get('odds')} vs {S.odds.get(c)}")
        else:
            e("odds" not in t, "odds shown in a season without them")
        page_games, cum, cum_actual = t.get("games", []), t.get("cum", []), t.get("cumActual", [])
        e(len(page_games) == len(cum) == len(cum_actual) == r["played"],
          f"{len(page_games)} games, {len(cum)}/{len(cum_actual)} cumulative values; "
          f"played {r['played']}")
        run, run_actual = Fraction(0), 0
        for i, (x, g) in enumerate(zip(games[c], page_games)):
            want = (day_month(x.d), short(x.opp), x.v, x.gf, x.ga, x.p)
            got = tuple(g.get(k) for k in ("d", "o", "v", "gf", "ga", "p"))
            e(got == want, f"game {i + 1} is {got}, results say {want}")
            run += x.p + S.handicap[c] / GAMES_PER_SEASON
            run_actual += x.p
            if i < len(cum):
                e(near(cum[i], run, DP[3]), f"cumulative adjusted after game {i + 1}: "
                                            f"{cum[i]} vs {float(run):.3f}")
            if i < len(cum_actual):
                e(cum_actual[i] == run_actual, f"cumulative actual after game {i + 1}: "
                                               f"{cum_actual[i]} vs {run_actual}")

    mean = sum(r["to_date"] for r in rec.values()) / len(rec)
    expect(near(pl.get("meanAdjusted"), mean, DP[2] + DP[3]),
           f"meanAdjusted {pl.get('meanAdjusted')} vs {float(mean):.3f}")
    corr = pearson([rec[c]["actual"] for c in rec], [S.handicap[c] for c in rec])
    expect(near(pl.get("handicapActualCorr"), corr or 0.0, DP[3]),
           f"handicapActualCorr {pl.get('handicapActualCorr')} vs {corr}")
    if complete:
        return "final"
    return "1 game played" if most == 1 else f"{most} games played"


# --- 4. the odds market on the handicap league ---------------------------------

def check_market(S, pl, expect):
    M = pl.get("market")
    if S.odds is None:
        expect(not M, "a market section in a season without odds")
        return
    if not expect(isinstance(M, dict) and M.get("rows"), "no market section"):
        return
    implied = {c: 1 / o for c, o in S.odds.items()}
    book = sum(implied.values())
    expect(near(M.get("book"), book, DP[4]) and near(M.get("overround"), book - 1, DP[4]),
           f"market book {M.get('book')} / overround {M.get('overround')} vs {book:.4f}")
    order = sorted(S.odds, key=lambda c: (S.odds[c], c))
    expect([r.get("name") for r in M["rows"]] == order, "market rows are not in odds order")
    for r in M["rows"]:
        c = r.get("name")
        if c not in S.odds:
            continue
        fair = implied[c] / book
        expect(r.get("short") == short(c) and r.get("handicap") == S.handicap[c]
               and r.get("odds") == S.odds[c] and near(r.get("implied"), implied[c], DP[5])
               and near(r.get("fairProb"), fair, DP[5]) and near(r.get("fairOdds"), 1 / fair, DP[2]),
               f"market row {c}: {r}; expected implied {implied[c]:.5f}, fair {fair:.5f}, "
               f"fair odds {1 / fair:.2f}")


# --- 5. Asian handicap ----------------------------------------------------------

def settle(quarters):
    """One side's result from its margin over the line, in quarter goals.

    A quarter line splits the stake across the two neighbouring lines, so a
    margin of one quarter is half won (or half lost). Two quarters or more
    either way is a full win or a full loss, and zero is a push.
    """
    return {2: Fraction(1), 1: Fraction(1, 2), 0: Fraction(0),
            -1: Fraction(-1, 2), -2: Fraction(-1)}[max(-2, min(2, quarters))]


def check_asian_handicap(S, pl, expect):
    A = pl.get("ah")
    if S.lines_file is None:
        expect(A is None, "an Asian handicap section without a lines file")
        return
    if not expect(isinstance(A, dict), "no Asian handicap section"):
        return
    with_line = [m for m in S.lines if m.line is not None]
    expect(A.get("matches") == len(with_line) and A.get("noLine") == len(S.lines) - len(with_line)
           and A.get("source") == S.lines_file,
           f"matches {A.get('matches')}, noLine {A.get('noLine')}, source {A.get('source')}; "
           f"expected {len(with_line)}, {len(S.lines) - len(with_line)}, {S.lines_file}")
    stand_ins = sorted((f"{day_month(m.d)} {m.d.year}", m.h, m.a, float(m.line))
                       for m in with_line if m.stand_in)
    shown = sorted((x.get("d"), x.get("h"), x.get("a"), x.get("line")) for x in A.get("standIns", []))
    expect(shown == stand_ins, f"closing-line stand-ins {shown}, expected {stand_ins}")

    covers = {c: [] for c in S.handicap}      # per club: (date, opponent, venue, line, cover, margin)
    for m in with_line:
        quarters = int(4 * (m.hg - m.ag + m.line))
        covers[m.h].append((m.d, m.a, "H", m.line, settle(quarters), m.hg - m.ag + m.line))
        covers[m.a].append((m.d, m.h, "A", -m.line, settle(-quarters), m.ag - m.hg - m.line))
    covers = {c: sorted(g, key=lambda x: x[0]) for c, g in covers.items() if g}
    rows = []
    for c, g in covers.items():
        results = [x[4] for x in g]
        rows.append(dict(name=c, played=len(g), w=results.count(1), hw=results.count(Fraction(1, 2)),
                         p=results.count(0), hl=results.count(Fraction(-1, 2)), l=results.count(-1),
                         stdc=sum(results), margin=sum(x[5] for x in g)))
    rows.sort(key=lambda r: (-r["stdc"], -r["margin"], r["name"]))

    page_rows = A.get("rows", [])
    expect([r.get("name") for r in page_rows] == [r["name"] for r in rows],
           "Asian handicap table order (net covers, then goals beaten the line by, then name)")
    adj_rank = {t.get("name"): t.get("adjRank") for t in pl.get("teams", [])}
    for i, (shown_row, r) in enumerate(zip(page_rows, rows)):
        if shown_row.get("name") != r["name"]:
            continue
        e = expect.under(f"Asian handicap {r['name']}")
        e(shown_row.get("rank") == i + 1 and shown_row.get("short") == short(r["name"]),
          f"rank {shown_row.get('rank')} / short {shown_row.get('short')!r}")
        for k in ("played", "w", "hw", "p", "hl", "l"):
            e(shown_row.get(k) == r[k], f"{k} {shown_row.get(k)} vs {r[k]}")
        e(near(shown_row.get("stdc"), r["stdc"], 1e-9), f"net covers {shown_row.get('stdc')} vs {float(r['stdc'])}")
        e(near(shown_row.get("margin"), r["margin"], DP[2]),
          f"margin {shown_row.get('margin')} vs {float(r['margin'])}")
        hr = adj_rank.get(r["name"])
        e(hr is not None and shown_row.get("handicapRank") == hr and shown_row.get("rankDiff") == hr - (i + 1),
          f"handicapRank {shown_row.get('handicapRank')}, rankDiff {shown_row.get('rankDiff')}; "
          f"the adjusted table has it {hr}")

    series = A.get("series", {})
    expect(sorted(series) == sorted(covers), "the cover series list the wrong clubs")
    for c, g in covers.items():
        want = list(itertools.accumulate(x[4] for x in g))
        expect(close_list(series.get(c), want, 1e-9), f"Asian handicap series for {c}: "
                                                       f"{series.get(c)} vs {[float(v) for v in want]}")

    lookup = {(c, short(x[1]), x[2]): x for c, g in covers.items() for x in g}
    for t in pl.get("teams", []):
        for g in t.get("games", []):
            x = lookup.get((t.get("name"), g.get("o"), g.get("v")))
            where = f"{t.get('name')} v {g.get('o')} ({g.get('v')}, {g.get('d')})"
            if x is None:
                expect("ahl" not in g and "ahc" not in g, f"{where}: a line is shown but none is on file")
            else:
                expect(near(g.get("ahl"), x[3], 1e-9) and near(g.get("ahc"), x[4], 1e-9),
                       f"{where}: line {g.get('ahl')}, result {g.get('ahc')}; "
                       f"expected {float(x[3])}, {float(x[4])}")

    if rows:
        spread = A.get("spread") or {}
        observed = statistics.pstdev([float(r["stdc"]) for r in rows])
        per_game = statistics.fmean([float(x[4]) ** 2 for g in covers.values() for x in g])
        chance = math.sqrt(statistics.median([r["played"] for r in rows]) * per_game)
        expect(near(spread.get("observed"), observed, DP[2]) and near(spread.get("chance"), chance, DP[2]),
               f"spread {spread}; expected observed {observed:.2f}, chance {chance:.2f}")
        diffs = [adj_rank.get(r["name"]) for r in rows]
        if None not in diffs:
            diffs = [hr - (i + 1) for i, hr in enumerate(diffs)]
            avg_line = [statistics.fmean([float(x[3]) for x in covers[r["name"]]]) for r in rows]
            corr = pearson(diffs, avg_line)
            expect(A.get("gapLineCorr") is None if corr is None else near(A.get("gapLineCorr"), corr, DP[2]),
                   f"gapLineCorr {A.get('gapLineCorr')} vs {corr}")

    price = A.get("price")
    if not S.ah_prices:
        expect(price is None, "an Asian handicap price summary without AvgAHH/AvgAHA prices")
    else:
        median = statistics.median([p for pair in S.ah_prices for p in pair])
        book = statistics.fmean([1 / h + 1 / a for h, a in S.ah_prices])
        expect(isinstance(price, dict) and near(price.get("median"), median, DP[2])
               and near(price.get("breakEven"), 100 / median, DP[1]) and near(price.get("book"), book, DP[3]),
               f"Asian handicap price {price}; expected median {median:.2f}, "
               f"break-even {100 / median:.1f}%, book {book:.3f}")


# --- 6. win-and-draw bets -------------------------------------------------------

def wd_stakes(split, win_odds, draw_odds):
    """(stake on the win, stake on the draw). 'equal' makes both results pay the same."""
    if split == "even":
        return STAKE, STAKE
    on_win = 2 * STAKE * draw_odds / (win_odds + draw_odds)
    return on_win, 2 * STAKE - on_win


def wd_profit(split, gf, ga, win_odds, draw_odds):
    on_win, on_draw = wd_stakes(split, win_odds, draw_odds)
    back = on_win * win_odds if gf > ga else on_draw * draw_odds if gf == ga else 0.0
    return back - 2 * STAKE


@dataclass
class Bet:
    d: date
    opp: str
    v: str
    gf: int
    ga: int
    ow: float
    od: float
    on_win: float
    profit: float

    @property
    def result(self):
        return "W" if self.gf > self.ga else "D" if self.gf == self.ga else "L"


def club_bets(S, split):
    priced = [m for m in S.lines if m.prices.get("Avg")]
    bets = {c: [] for c in S.handicap}
    for m in priced:
        oh, od, oa = m.prices["Avg"]
        for club, opp, v, gf, ga, ow in ((m.h, m.a, "H", m.hg, m.ag, oh), (m.a, m.h, "A", m.ag, m.hg, oa)):
            bets[club].append(Bet(m.d, opp, v, gf, ga, ow, od, wd_stakes(split, ow, od)[0],
                                  wd_profit(split, gf, ga, ow, od)))
    return priced, {c: sorted(b, key=lambda x: x.d) for c, b in bets.items() if b}


def monte_carlo(S, split, priced, clubs, cache):
    """Each club's season total in CHECK_SIMS seasons drawn from the market's
    margin-free probabilities. One result per match, shared by both clubs."""
    key = (S.key, split, tuple((m.h, m.a) + m.prices["Avg"] for m in priced))
    if key not in cache:
        P = np.array([m.prices["Avg"] for m in priced], float)
        fair = (1 / P) / (1 / P).sum(axis=1, keepdims=True)
        edges = fair.cumsum(axis=1)[:, :2]       # home win below the first edge, draw below the second
        home = np.array([[wd_profit(split, 1, 0, oh, od), wd_profit(split, 0, 0, oh, od), -2 * STAKE]
                         for oh, od, _ in P])
        away = np.array([[-2 * STAKE, wd_profit(split, 0, 0, oa, od), wd_profit(split, 1, 0, oa, od)]
                         for _, od, oa in P])
        col = {c: i for i, c in enumerate(clubs)}
        H, A = np.zeros((len(priced), len(clubs))), np.zeros((len(priced), len(clubs)))
        for j, m in enumerate(priced):
            H[j, col[m.h]] = A[j, col[m.a]] = 1
        rng, idx, totals = np.random.default_rng(CHECK_SEED), np.arange(len(priced)), []
        for _ in range(CHECK_SIMS // 5000):
            outcome = (rng.random((5000, len(priced)))[:, :, None] > edges[None]).sum(axis=2)
            totals.append(home[idx, outcome] @ H + away[idx, outcome] @ A)
        cache[key] = np.vstack(totals)
    return cache[key]


def check_win_draw(S, pl, key, split, expect, cache):
    B = pl.get(key)
    if S.lines_file is None or not {"AvgH", "AvgD", "AvgA"} <= S.columns:
        expect(B is None, "a win-and-draw section without 1X2 prices")
        return
    if not expect(isinstance(B, dict), "no win-and-draw section"):
        return
    priced, bets = club_bets(S, split)
    if not expect(bets, "no priced matches"):
        return
    expect(B.get("split") == split and B.get("stake") == STAKE and B.get("source") == "market-average"
           and B.get("file") == S.lines_file,
           f"split/stake/source/file {B.get('split')}/{B.get('stake')}/{B.get('source')}/{B.get('file')}")
    expect(B.get("matches") == len(priced) and B.get("noOdds") == len(S.lines) - len(priced),
           f"matches {B.get('matches')}, noOdds {B.get('noOdds')}; "
           f"expected {len(priced)}, {len(S.lines) - len(priced)}")

    # each game in the game-by-game list
    field_ = "wdp" if split == "even" else "ewp"
    lookup = {(c, short(b.opp), b.v): b for c, bs in bets.items() for b in bs}
    for t in pl.get("teams", []):
        for g in t.get("games", []):
            b = lookup.get((t.get("name"), g.get("o"), g.get("v")))
            where = f"{t.get('name')} v {g.get('o')} ({g.get('v')}, {g.get('d')})"
            if b is None:
                expect(field_ not in g, f"{where}: a {field_} is shown but the match has no prices")
                continue
            ok = near(g.get("ow"), b.ow, 1e-9) and near(g.get("od"), b.od, 1e-9)
            ok = ok and near(g.get(field_), b.profit, DP[2])
            if split == "equal":
                ok = ok and near(g.get("ews"), b.on_win, DP[2])
            expect(ok, f"{where}: prices {g.get('ow')}/{g.get('od')}, stake on win {g.get('ews')}, "
                       f"profit {g.get(field_)}; expected {b.ow}/{b.od}, {b.on_win:.2f}, {b.profit:.2f}")

    # each club's series and the table
    each, running = B.get("each", {}), B.get("running", {})
    expect(sorted(each) == sorted(bets) and sorted(running) == sorted(bets),
           "the per-club series list the wrong clubs")
    for c, bs in bets.items():
        mine = [b.profit for b in bs]
        expect(close_list(each.get(c), mine, DP[2]), f"{c}: game-by-game returns")
        expect(close_list(running.get(c), list(itertools.accumulate(mine)), DP[2]),
               f"{c}: running returns")
    total = {c: sum(b.profit for b in bs) for c, bs in bets.items()}
    rows = B.get("rows", [])
    expect(sorted(r.get("name") for r in rows) == sorted(bets), "the table lists the wrong clubs")
    for i, r in enumerate(rows):
        c = r.get("name")
        if c not in bets:
            continue
        bs, e = bets[c], expect.under(c)
        staked = 2 * STAKE * len(bs)
        e(r.get("rank") == i + 1 and r.get("short") == short(c) and r.get("played") == len(bs),
          f"rank {r.get('rank')}, short {r.get('short')!r}, played {r.get('played')}")
        e((r.get("w"), r.get("d"), r.get("l")) == tuple(sum(b.result == k for b in bs) for k in "WDL"),
          f"W/D/L {r.get('w')}/{r.get('d')}/{r.get('l')}")
        e(near(r.get("staked"), staked, DP[2]) and near(r.get("profit"), total[c], DP[2])
          and near(r.get("returned"), staked + total[c], DP[2])
          and near(r.get("roi"), total[c] / staked, DP[6]),
          f"profit {r.get('profit')} (staked {r.get('staked')}, returned {r.get('returned')}, "
          f"roi {r.get('roi')}); expected {total[c]:.2f}")
        above = rows[i - 1].get("name") if i else None
        if above in total:      # level profits may be listed either way round
            e(total[above] >= total[c] - 1e-6, f"listed below {above}, which made less")

    # the league as a whole
    n_bets = sum(len(bs) for bs in bets.values())
    staked, league = 2 * STAKE * n_bets, sum(total.values())
    expect(near(B.get("staked"), staked, DP[2]) and near(B.get("profit"), league, DP[2])
           and near(B.get("roi"), league / staked, DP[6]),
           f"league profit {B.get('profit')} (staked {B.get('staked')}, roi {B.get('roi')}); "
           f"expected {league:.2f}")
    width = max(len(bs) for bs in bets.values())
    by_game = [sum(bs[k].profit for bs in bets.values() if len(bs) > k) for k in range(width)]
    expect(close_list(B.get("leagueEach"), by_game, DP[2]), "league return game by game")
    expect(close_list(B.get("leagueRunning"), list(itertools.accumulate(by_game)), DP[2]),
           "league running return")
    columns = B.get("columns") or {}
    expect(columns.get("bets") == [sum(len(bs) > k for bs in bets.values()) for k in range(width)],
           f"bets per grid column {columns.get('bets')}")
    nth = {(c, b.d): k for c, bs in bets.items() for k, b in enumerate(bs)}
    out_of_step = sum(nth[(m.h, m.d)] != nth[(m.a, m.d)] for m in priced)
    expect(columns.get("out_of_step") == out_of_step,
           f"matches whose clubs sit in different grid columns: {columns.get('out_of_step')} vs {out_of_step}")
    share = sum(2 * STAKE - b.on_win for bs in bets.values() for b in bs) / staked
    expect(near(B.get("drawShare"), share, DP[6]), f"draw share {B.get('drawShare')} vs {share:.6f}")
    by_result = B.get("byResult") or {}
    for k in "WDL":
        mine = [b.profit for bs in bets.values() for b in bs if b.result == k]
        expect(near(by_result.get(k), sum(mine), DP[2]) if mine else k not in by_result,
               f"profit on {k} {by_result.get(k)} vs {sum(mine):.2f}")

    # the same bets at other prices
    sets = [(pre, label) for pre, label in PRICE_SETS if {pre + k for k in "HDA"} <= S.columns]
    alternatives = B.get("alternatives", [])
    expect([x.get("label") for x in alternatives] == [label for _, label in sets],
           f"price comparisons {[x.get('label') for x in alternatives]}")
    for (pre, label), alt in zip(sets, alternatives):
        am = [m for m in S.lines if m.prices.get(pre)]
        if not am:
            continue
        profit = sum(wd_profit(split, m.hg, m.ag, m.prices[pre][0], m.prices[pre][1])
                     + wd_profit(split, m.ag, m.hg, m.prices[pre][2], m.prices[pre][1]) for m in am)
        books = [sum(1 / x for x in m.prices[pre]) for m in am]
        expected = statistics.fmean([1 / b for b in books]) - 1
        expect(alt.get("label") == label and near(alt.get("profit"), profit, DP[2])
               and near(alt.get("roi"), profit / (4 * STAKE * len(am)), DP[6])
               and near(alt.get("expected"), expected, DP[6])
               and alt.get("arbs") == sum(b < 1 for b in books) and alt.get("matches") == len(am),
               f"{label} prices: {alt}; expected profit {profit:.2f}, expected return {expected:.6f}, "
               f"{sum(b < 1 for b in books)} arbitrages in {len(am)} matches")

    # against chance: the exact figures first, then the simulated ones
    C = B.get("chance") or {}
    P = np.array([m.prices["Avg"] for m in priced], float)
    book = (1 / P).sum(axis=1)
    fair_draw = (1 / P[:, 1]) / book
    observed = list(total.values())
    spread = statistics.pstdev(observed)
    expect(near(C.get("expected_roi"), float(np.mean(1 / book) - 1), DP[4])
           and near(C.get("book"), float(book.mean()), DP[4])
           and C.get("draws") == sum(m.hg == m.ag for m in priced)
           and near(C.get("draws_implied"), float(fair_draw.sum()), DP[4])
           and near(C.get("spread_observed"), spread, DP[4]),
           f"chance figures {C}; expected return {float(np.mean(1 / book) - 1):.4f}, "
           f"book {float(book.mean()):.4f}, draws {sum(m.hg == m.ag for m in priced)} "
           f"(implied {float(fair_draw.sum()):.4f}), spread {spread:.4f}")
    sims = monte_carlo(S, split, priced, sorted(bets), cache)
    spreads, leagues, best = sims.std(axis=1), sims.sum(axis=1), sims.max(axis=1)
    k = math.sqrt(1 / BUILD_SIMS + 1 / CHECK_SIMS)       # noise in the gap between two simulations
    expect(near(C.get("spread_chance"), spreads.mean(), 4 * spreads.std() * k + DP[4]),
           f"chance spread {C.get('spread_chance')} vs this check's {spreads.mean():.4f}")
    for name, p in (("spread_p", (spreads >= spread).mean()),
                    ("league_percentile", (leagues <= league).mean()),
                    ("league_at_least", (leagues >= league).mean()),
                    ("best_of_field", (best >= max(observed)).mean())):
        tol = 4 * math.sqrt(max(p * (1 - p), 1e-4)) * k + 1e-3
        expect(near(C.get(name), p, tol), f"chance {name} {C.get(name)} vs this check's {p:.4f}")


# --- the whole site -------------------------------------------------------------

def check_season(S, pl, expect, cache):
    """Checks one season's data block; returns the status line it should carry."""
    expect(pl.get("season") == S.label and pl.get("gamesPerSeason") == GAMES_PER_SEASON,
           f"season {pl.get('season')!r}, gamesPerSeason {pl.get('gamesPerSeason')}")
    check_market(S, pl, expect)
    if S.results is None:
        return check_preseason(S, pl, expect)
    status = check_standings(S, pl, expect)
    check_asian_handicap(S, pl, expect)
    for key, split in SPLITS:
        check_win_draw(S, pl, key, split, expect.under(key), cache)
    return status


def check_all(data, site, cache):
    expect = Expect()
    seasons = sorted(data)
    for key in seasons:
        S, e = data[key], expect.under(key)
        for problem in S.problems:
            e(False, problem)
        page = site.get(key)
        if not e(page is not None, f"no page at {key}/index.html; run build_site.py"):
            continue
        html, pl = page
        if not e(pl is not None, f"{key}/index.html has no readable data block"):
            continue
        status = check_season(S, pl, e, cache)
        check_shell(S, html, HERE / key / "index.html", status, e, seasons)
        if key == seasons[-1]:
            check_root(site, key, expect)
            if site.get("root") is not None:
                check_shell(S, site["root"][0], HERE / "index.html", status, e, seasons)
    return expect.problems


def summary(key, S, page):
    pl = page[1] if page else None
    if not pl:
        return f"{key}: no page"
    if not pl.get("hasResults"):
        return f"{key}: pre-season, {len(pl.get('teams', []))} handicaps"
    top = pl["teams"][0]
    parts = [f"{key}: {len(S.results)} results, " + ("final" if pl["complete"] else
             f"{pl['maxPlayed']} games played"),
             f"adjusted leader {top['name']} {top['adjustedToDate']}"]
    if pl.get("ah"):
        lead = pl["ah"]["rows"][0]
        parts.append(f"Asian handicap leader {lead['name']} {lead['stdc']:+g}")
    if pl.get("wd") and pl.get("wde"):
        parts.append(f"win-and-draw {pl['wd']['profit']:+.2f} (even) / {pl['wde']['profit']:+.2f} (equal)")
    return "; ".join(parts)


def run(seasons):
    data = {key: load_season(key) for key in seasons}
    site = load_site(seasons)
    problems = check_all(data, site, {})
    for key in seasons:
        print(summary(key, data[key], site.get(key)))
        for note in data[key].notes:
            print(f"  note: {note}")
    if problems:
        print(f"\nMISMATCHES: {len(problems)}")
        for p in problems[:40]:
            print("  " + p)
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more")
        return 1
    print("\nAll checks passed: every published figure matches an independent recomputation.")
    return 0


# --- self-test: plant faults in copies of the pages and confirm each is caught --

def seasons_with_results(site, newest_first=True):
    keys = [k for k in site if k != "root" and site[k] and site[k][1] and site[k][1].get("hasResults")]
    return sorted(keys, reverse=newest_first)


def recompute_cum(team):
    """Make a doctored club's cumulative series agree with its games again."""
    per_game, run, run_actual = team["handicap"] / GAMES_PER_SEASON, 0.0, 0
    team["cum"], team["cumActual"] = [], []
    for g in team["games"]:
        run, run_actual = run + g["p"] + per_game, run_actual + g["p"]
        team["cum"].append(round(run, 3))
        team["cumActual"].append(run_actual)


def fault_day_first_date(site, data):
    """the 2026/27 bug: a date read day-first, so 05 Sep shows as 09 May and sorts first"""
    for key in seasons_with_results(site):
        for t in site[key][1]["teams"]:
            for i, g in enumerate(t["games"]):
                day, month = int(g["d"][:2]), MONTHS.index(g["d"][3:]) + 1
                if day <= 7 and day != month:
                    old, g["d"] = g["d"], f"{month:02d} {MONTHS[day - 1]}"
                    t["games"].insert(0, t["games"].pop(i))
                    recompute_cum(t)
                    return f"{key}: {t['name']}'s game on {old} shown as {g['d']} and sorted first"


def fault_draw_scored_as_win(site, data):
    """a draw scored as a win, with every total that depends on it updated to match"""
    for key in seasons_with_results(site):
        for t in site[key][1]["teams"]:
            for g in t["games"]:
                if g["p"] == 1:
                    g["p"] = 3
                    t["w"], t["dr"] = t["w"] + 1, t["dr"] - 1
                    for k in ("actual", "adjusted", "adjustedFull"):
                        t[k] += 2
                    t["adjustedToDate"] = round(t["adjustedToDate"] + 2, 3)
                    recompute_cum(t)
                    return f"{key}: {t['name']}'s draw on {g['d']} scored as a win"


def fault_wrong_opponent(site, data):
    """a game listed against the wrong opponent"""
    for key in seasons_with_results(site):
        teams = site[key][1]["teams"]
        g = teams[0]["games"][-1]
        old = g["o"]
        g["o"] = next(t["short"] for t in teams[1:] if t["short"] != old)
        return f"{key}: {teams[0]['name']}'s last game listed against {g['o']}, not {old}"


def fault_cumulative_total(site, data):
    """one cumulative adjusted total 0.01 out"""
    for key in seasons_with_results(site):
        t = site[key][1]["teams"][-1]
        t["cum"][-1] = round(t["cum"][-1] + 0.01, 3)
        return f"{key}: {t['name']}'s latest cumulative adjusted total 0.01 too high"


def fault_half_win_as_win(site, data):
    """an Asian handicap half win counted as a full win, in the table and the series"""
    for key in seasons_with_results(site, newest_first=False):
        A = site[key][1].get("ah")
        for r in (A or {}).get("rows", []):
            s = A["series"][r["name"]]
            steps = [b - a for a, b in zip([0.0] + s, s)]
            if 0.5 in steps:
                i = steps.index(0.5)
                r["hw"], r["w"], r["stdc"] = r["hw"] - 1, r["w"] + 1, r["stdc"] + 0.5
                A["series"][r["name"]] = s[:i] + [v + 0.5 for v in s[i:]]
                return f"{key}: {r['name']}'s Asian handicap half win counted as a win"


def fault_line_wrong_side(site, data):
    """a game shown with the other side's Asian handicap line"""
    for key in seasons_with_results(site):
        for t in site[key][1]["teams"]:
            for g in t["games"]:
                if g.get("ahl"):
                    g["ahl"] = -g["ahl"]
                    return f"{key}: {t['name']} v {g['o']} on {g['d']} shown with the other side's line"


def fault_game_profit(site, data):
    """one game's win-and-draw profit EUR10 out"""
    for key in seasons_with_results(site):
        for t in site[key][1]["teams"]:
            for g in t["games"]:
                if "wdp" in g:
                    g["wdp"] = round(g["wdp"] + 10, 2)
                    return f"{key}: {t['name']} v {g['o']} on {g['d']}: win-and-draw profit EUR10 high"


def fault_even_stake_in_equal_split(site, data):
    """the equal-payout split showing the even EUR10 on the win"""
    for key in seasons_with_results(site):
        for t in site[key][1]["teams"]:
            for g in t["games"]:
                if "ews" in g and abs(g["ews"] - STAKE) > 0.01:
                    old, g["ews"] = g["ews"], STAKE
                    return f"{key}: {t['name']} v {g['o']}: equal-payout stake on the win {old} shown as 10"


def fault_league_total(site, data):
    """the win-and-draw league total EUR5 out"""
    for key in seasons_with_results(site):
        B = site[key][1].get("wd")
        if B:
            B["profit"] = round(B["profit"] - 5, 2)
            return f"{key}: win-and-draw league profit EUR5 low"


def fault_chance_figure(site, data):
    """a simulated chance figure (best club's season) 0.25 out"""
    for key in seasons_with_results(site):
        B = site[key][1].get("wd")
        if B:
            v = B["chance"]["best_of_field"]
            B["chance"]["best_of_field"] = round(v + 0.25 if v < 0.5 else v - 0.25, 4)
            return f"{key}: best_of_field {v} shown as {B['chance']['best_of_field']}"


def fault_price_comparison(site, data):
    """the best-available price comparison EUR3 out"""
    for key in seasons_with_results(site):
        B = site[key][1].get("wd")
        if B and B.get("alternatives"):
            B["alternatives"][0]["profit"] = round(B["alternatives"][0]["profit"] + 3, 2)
            return f"{key}: {B['alternatives'][0]['label']} profit EUR3 high"


def fault_draw_share(site, data):
    """the older season's equal-split draw share shown as the even split's 0.5"""
    for key in seasons_with_results(site, newest_first=False):
        B = site[key][1].get("wde")
        if B and abs(B["drawShare"] - 0.5) > 0.01:
            old, B["drawShare"] = B["drawShare"], 0.5
            return f"{key}: equal-split draw share {old} shown as 0.5"


def fault_market_odds(site, data):
    """one club's fair odds in the handicap-league market 0.5 out"""
    for key in sorted((k for k in site if k != "root" and site[k] and site[k][1]), reverse=True):
        M = site[key][1].get("market")
        if M and M.get("rows"):
            r = M["rows"][0]
            r["fairOdds"] = round(r["fairOdds"] + 0.5, 2)
            return f"{key}: {r['name']}'s fair odds 0.5 high"


def fault_stale_root(site, data):
    """the root index.html left on an older build"""
    if site.get("root") and site["root"][1]:
        site["root"][1] = copy.deepcopy(site["root"][1])    # stop sharing the season page's data
        site["root"][1]["maxPlayed"] -= 1
        return "index.html one game behind its season's page"


def fault_stale_status(site, data):
    """the status line left on last week's count"""
    for key in seasons_with_results(site):
        html = site[key][0]
        found = re.search(r"&middot; (\d+) games? played</div>", html)
        old = found.group(0) if found else "&middot; final</div>"
        if old in html:
            new = (f"&middot; {int(found.group(1)) - 1} games played</div>" if found
                   else "&middot; 37 games played</div>")
            site[key][0] = html.replace(old, new)
            return f"{key}/index.html: status line says {new[9:-6]!r}"


def fault_date_typo_in_results(site, data):
    """a date in results.csv typed with day and month swapped (the source data, not the page)"""
    for key in sorted(data, reverse=True):
        if data[key].results is None:
            continue
        typed = {}

        def tamper(name, rows):
            if name != "results.csv" or typed:
                return
            for r in rows:
                d = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})|(\d{2})/(\d{2})/(\d{4})", cell(r, "Date"))
                if not d or not cell(r, "Score" if "Score" in r else "FTHG"):
                    continue
                y, m, dd = (d.group(1), d.group(2), d.group(3)) if d.group(1) else (d.group(6), d.group(5), d.group(4))
                if int(dd) <= 12 and dd != m:
                    swapped = f"{y}-{dd}-{m}" if d.group(1) else f"{m}/{dd}/{y}"
                    typed["typo"] = (r["Date"], swapped)
                    r["Date"] = swapped
                    return

        S = load_season(key, tamper)
        if typed:
            return f"{key}: results.csv date {typed['typo'][0]} typed as {typed['typo'][1]}", {key: S}


FAULTS = (fault_day_first_date, fault_draw_scored_as_win, fault_wrong_opponent,
          fault_cumulative_total, fault_half_win_as_win, fault_line_wrong_side,
          fault_game_profit, fault_even_stake_in_equal_split, fault_league_total,
          fault_chance_figure, fault_price_comparison, fault_draw_share,
          fault_market_odds, fault_stale_root, fault_stale_status, fault_date_typo_in_results)


def self_test(seasons):
    data = {key: load_season(key) for key in seasons}
    site = load_site(seasons)
    cache = {}
    real = check_all(data, site, cache)
    if real:
        print(f"The real pages already fail {len(real)} check(s), so a planted fault would prove "
              "nothing. Run without --self-test and fix those first.")
        return 1
    failed = 0
    for fault in FAULTS:
        trial = copy.deepcopy(site)
        # The root page and the latest season's page share one data block, so a
        # fault planted in it must be caught by the check it targets, not merely
        # by the root page no longer matching.
        trial["root"][1] = trial[seasons[-1]][1]
        planted = fault(trial, data)
        if planted is None:
            print(f"  NOT PLANTED  {fault.__doc__} (nowhere suitable)")
            failed += 1
            continue
        what, changed = planted if isinstance(planted, tuple) else (planted, {})
        problems = check_all({**data, **changed}, trial, cache)
        if problems:
            more = f" (+{len(problems) - 1} more)" if len(problems) > 1 else ""
            print(f"  caught  {what}\n          -> {problems[0]}{more}")
        else:
            print(f"  MISSED  {what}")
            failed += 1
    print(f"\n{len(FAULTS) - failed} of {len(FAULTS)} planted faults caught.")
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true",
                        help="plant faults in copies of the pages and confirm each one is caught")
    args = parser.parse_args(argv)
    seasons = discover()
    if not seasons:
        print("No data/<season>/season_handicap.csv found.")
        return 1
    status = self_test(seasons) if args.self_test else run(seasons)
    if {"analysis", "build_site"} & set(sys.modules):
        print("test_pipeline.py imported the pipeline it is meant to check independently.")
        return 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
