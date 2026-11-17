"""Independent checks of the published report, recomputed from the season files.

``test_pipeline.py`` proves the plumbing on generated data, and it does so by
calling the pipeline's own functions. This file is the other half: it takes the
**real** season files and works every published number out again from the
written rules, then compares. For each season in ``data/``:

1. the source data: 16 known clubs, eight matches a round and each club once,
   no fixture twice, every date on a Friday-to-Sunday match day unless listed,
   handicaps in half points, a score and both turnover counts together or not
   at all - and every scraped round in ``entry/scraped/`` agreeing with the
   season file on the score and the turnovers it was loaded from;
2. the report, ``data/report_<year>.csv``, row by row: the line the model runs
   on, each side's last-game turnover margin, season-to-date covers and power
   rating, the five votes, the System #, the pick and its grade, and the
   matches held back;
3. the season's record: bets, wins, losses, units;
4. the site, ``index.html``: the tiles, every row of *Every match*, the profit
   curve, both heatmaps, the spot-check card and the bet tracker - against
   these recomputed numbers, not against the report file.

Independence is the point. This file imports nothing from the project: it has
its own club list, its own date and number parsing, its own rating fit (exact
fractions solved by elimination, where the pipeline uses floating-point least
squares) and its own grading. A check that reuses the pipeline's code repeats
the pipeline's mistakes. Keep it that way.

Run after every build::

    python3 test_independent.py              # check every season
    python3 test_independent.py --self-test  # plant faults in copies of the
                                             # data; confirm each is caught

Exit status 0 means every check passed. With ``--self-test`` it means every
planted fault was caught.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction as F
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent

# --- the rules, restated here rather than imported ---------------------------

CLUBS = {"Leinster", "Munster", "Ulster", "Connacht", "Cardiff", "Dragons", "Ospreys",
         "Scarlets", "Edinburgh", "Glasgow", "Benetton", "Zebre", "Bulls", "Lions",
         "Sharks", "Stormers"}
# What the scraped files call them; a name not listed here fails the check.
SCRAPED_NAMES = {
    "Leinster Rugby": "Leinster", "Munster Rugby": "Munster", "Ulster Rugby": "Ulster",
    "Connacht Rugby": "Connacht", "Cardiff Rugby": "Cardiff", "Dragons RFC": "Dragons",
    "Ospreys": "Ospreys", "Scarlets": "Scarlets", "Edinburgh Rugby": "Edinburgh",
    "Glasgow Warriors": "Glasgow", "Benetton Rugby": "Benetton", "Zebre Parma": "Zebre",
    "Vodacom Bulls": "Bulls", "Emirates Lions": "Lions", "10bet Lions": "Lions",
    "Fidelity SecureDrive Lions": "Lions", "Lions": "Lions",
    "Hollywoodbets Sharks": "Sharks", "DHL Stormers": "Stormers",
}
REGULAR_ROUNDS = 18                 # rounds above this are play-offs
HOME_ADVANTAGE = F(5)               # points, inside the rating fit only
FIT_WEIGHTS = [F(1), F(1, 2), F(1, 4), F(1, 8)]   # most recent match-week first
BET_AT = 3                          # bet home at +3 or more, away at -3 or less
JUICE = F(11, 10)                   # a losing bet costs 1.1 units
NEUTRAL_MARKS = {"Y", "YES", "TRUE", "1", "N/V"}
MATCH_DAYS = {4, 5, 6}              # Friday, Saturday, Sunday

# The ten shadow factors: tracked beside the five, never bet.
COUNTRY = {"Leinster": "IE", "Munster": "IE", "Ulster": "IE", "Connacht": "IE",
           "Cardiff": "WA", "Dragons": "WA", "Ospreys": "WA", "Scarlets": "WA",
           "Edinburgh": "SC", "Glasgow": "SC", "Benetton": "IT", "Zebre": "IT",
           "Bulls": "ZA", "Lions": "ZA", "Sharks": "ZA", "Stormers": "ZA"}
BIG_MISS = 10                       # missed or beat the last line by this much
TOUR_GAP_DAYS = 8                   # two long-haul away matches this close are a tour
BIG_LINE = 14                       # a handicap this big
BIG_MOVE = 2                        # the close this far from the open
HOME_BACK = 3                       # the power variant adds this much home advantage back
SHADOWS = {                         # key -> the name the site shows
    "last_cover": "Last result v the line", "cards": "Cards", "kicking": "Goal-kicking",
    "red_zone": "Scoring from the 22", "long_haul": "Long-haul trip",
    "tour_leg2": "Second match of a tour", "derby": "Derby", "big_line": "Big handicap",
    "line_move": "Line move", "power_3": "Power, 3-point home edge"}


# --- reading -----------------------------------------------------------------

def number(text: str) -> F | None:
    """A cell as an exact number; blank is None."""
    text = (text or "").strip()
    return F(text) if text else None


def whole(text: str) -> int | None:
    n = number(text)
    if n is None:
        return None
    if n.denominator != 1:
        raise ValueError(f"expected a whole number, got {text!r}")
    return int(n)


@dataclass
class Match:
    season: int
    round: int
    day: date
    home: str
    away: str
    neutral: bool
    opening: F | None
    closing: F | None
    home_score: int | None
    away_score: int | None
    home_conceded: int | None
    away_conceded: int | None
    home_won: int | None
    away_won: int | None
    # worked out below
    home_lgt: int = 0
    away_lgt: int = 0
    held: bool = False               # a side's last match has no turnover count
    home_stdc: int = 0
    away_stdc: int = 0
    home_power: F | None = None      # rounded to a tenth, as the model uses it
    away_power: F | None = None
    power_options: dict = field(default_factory=dict)   # side -> admissible tenths
    votes: tuple = ()
    system: int = 0
    bet: str | None = None
    result: str | None = None
    shadow: dict = field(default_factory=dict)       # factor -> +1 home, -1 away, 0, None

    @property
    def line(self) -> F | None:
        """The handicap the model runs on: the close, or the open until then."""
        return self.closing if self.closing is not None else self.opening

    @property
    def played(self) -> bool:
        return self.home_score is not None and self.away_score is not None

    @property
    def listed(self) -> bool:
        """In the report: already played, or priced so it can be picked."""
        return self.played or self.line is not None

    @property
    def key(self) -> tuple:
        return (self.day.isoformat(), self.home, self.away)


def read_season(path: Path, year: int) -> list[Match]:
    matches = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not (row["home"].strip() and row["away"].strip()):
                continue
            matches.append(Match(
                season=year, round=whole(row["round"]),
                day=date.fromisoformat(row["date"].strip()),
                home=row["home"].strip(), away=row["away"].strip(),
                neutral=row.get("neutral", "").strip().upper() in NEUTRAL_MARKS,
                opening=number(row["opening_line"]), closing=number(row["closing_line"]),
                home_score=whole(row["home_score"]), away_score=whole(row["away_score"]),
                home_conceded=whole(row["home_turnovers_conceded"]),
                away_conceded=whole(row["away_turnovers_conceded"]),
                home_won=whole(row.get("home_turnovers_won", "")),
                away_won=whole(row.get("away_turnovers_won", ""))))
    return matches


def seasons_present(data: Path) -> list[int]:
    return sorted(int(m.group(1)) for p in data.glob("season_*.csv")
                  if (m := re.fullmatch(r"season_(\d{4})\.csv", p.name)))


# --- the model, from its written rules ---------------------------------------

def sign(x) -> int:
    return (x > 0) - (x < 0)


def cover(m: Match) -> int:
    """+1 the home side covered, -1 the away side, 0 a push or not known yet."""
    if not m.played or m.line is None:
        return 0
    return sign(m.home_score - m.away_score + m.line)


def blocks(years: list[int]) -> list[list[int]]:
    """Runs of consecutive seasons. Turnovers and ratings carry within a run."""
    out: list[list[int]] = []
    for y in years:
        if out and y == out[-1][-1] + 1:
            out[-1].append(y)
        else:
            out.append([y])
    return out


def last_game_turnovers(matches: list[Match]) -> None:
    """Each side's turnovers conceded minus its opponent's, last time out."""
    last: dict[str, tuple[bool, int | None]] = {}     # club -> (had a match, margin)
    for m in sorted(matches, key=lambda x: (x.day, x.round, x.home)):
        for side, club in (("home", m.home), ("away", m.away)):
            had, margin = last.get(club, (False, None))
            setattr(m, f"{side}_lgt", margin if margin is not None else 0)
            if had and margin is None:
                m.held = True
        counted = m.home_conceded is not None and m.away_conceded is not None
        margin = m.home_conceded - m.away_conceded if counted else None
        last[m.home] = (True, margin)
        last[m.away] = (True, -margin if counted else None)


def season_covers(matches: list[Match]) -> None:
    """Each side's net covers this season, entering the match."""
    running: dict[str, int] = defaultdict(int)
    for m in sorted((x for x in matches if x.listed), key=lambda x: (x.day, x.round, x.home)):
        m.home_stdc, m.away_stdc = running[m.home], running[m.away]
        c = cover(m)
        running[m.home] += c
        running[m.away] -= c


def solve(a: list[list[F]], b: list[F]) -> list[F]:
    """Gauss-Jordan elimination, exactly."""
    n = len(a)
    m = [row[:] + [rhs] for row, rhs in zip(a, b)]
    for c in range(n):
        pivot = next(r for r in range(c, n) if m[r][c] != 0)
        m[c], m[pivot] = m[pivot], m[c]
        m[c] = [x / m[c][c] for x in m[c]]
        for r in range(n):
            if r != c and m[r][c] != 0:
                m[r] = [x - m[r][c] * y for x, y in zip(m[r], m[c])]
    return [row[n] for row in m]


def fit_ratings(window: list[tuple[F, Match]]) -> dict[str, F]:
    """Weighted least squares on ``line + home edge = away rating - home rating``.

    The ratings are fixed only up to a constant within each group of clubs the
    window's matches connect, so each group is centred on zero - which is the
    smallest solution, the one floating-point least squares returns.
    """
    lap: dict[str, dict[str, F]] = defaultdict(lambda: defaultdict(F))
    rhs: dict[str, F] = defaultdict(F)
    link: dict[str, str] = {}

    def root(c: str) -> str:
        while link.setdefault(c, c) != c:
            c = link[c]
        return c

    for weight, m in window:
        target = m.line + (0 if m.neutral else HOME_ADVANTAGE)
        lap[m.away][m.away] += weight
        lap[m.home][m.home] += weight
        lap[m.away][m.home] -= weight
        lap[m.home][m.away] -= weight
        rhs[m.away] += weight * target
        rhs[m.home] -= weight * target
        link[root(m.home)] = root(m.away)

    groups: dict[str, list[str]] = defaultdict(list)
    for club in sorted(lap):
        groups[root(club)].append(club)
    ratings: dict[str, F] = {}
    for clubs in groups.values():
        a = [[lap[i][j] for j in clubs] for i in clubs]
        b = [rhs[i] for i in clubs]
        a[-1], b[-1] = [F(1)] * len(clubs), F(0)       # the group sums to zero
        ratings.update(zip(clubs, solve(a, b)))
    return ratings


def tenths(x: F) -> list[F]:
    """x to one decimal. Two values when x sits on a rounding boundary, where
    the pipeline's floating-point answer could fall either way."""
    scaled = x * 10
    low = F(scaled.numerator // scaled.denominator)
    gap = scaled - low - F(1, 2)
    if abs(gap) < F(1, 10 ** 8):
        return [low / 10, (low + 1) / 10]
    return [(low + (1 if gap > 0 else 0)) / 10]


def week_of(day: date) -> tuple[int, int]:
    """The match-week: ISO year and week, Monday to Sunday."""
    iso = day.isocalendar()
    return (iso[0], iso[1])


def power_ratings(matches: list[Match]) -> dict[tuple[int, int], dict[str, F]]:
    """Each match-week's ratings, fit on the four priced regular-season
    match-weeks before it. Returns the exact ratings by week."""
    usable = [m for m in matches if m.line is not None and m.round <= REGULAR_ROUNDS]
    by_week: dict[tuple[int, int], list[Match]] = defaultdict(list)
    for m in usable:
        by_week[week_of(m.day)].append(m)
    weeks = sorted(by_week)
    exact: dict[tuple[int, int], dict[str, F]] = {}
    for wk in sorted({week_of(m.day) for m in matches}):
        sources = [w for w in weeks if w < wk][-len(FIT_WEIGHTS):][::-1]
        if sources:
            exact[wk] = fit_ratings([(weight, m) for weight, w in zip(FIT_WEIGHTS, sources)
                                     for m in by_week[w]])
    return exact


def five_votes(m: Match) -> tuple[int, int, int, int, int]:
    """(power, turnover home, turnover away, hunger home, hunger away); each
    +1 for the home side, -1 for the away side."""
    power = 0
    if m.line is not None and m.home_power is not None and m.away_power is not None:
        power = sign(m.line - (m.away_power - m.home_power))
    return (power, sign(m.home_lgt), -sign(m.away_lgt), -sign(m.home_stdc), sign(m.away_stdc))


def run_model(seasons: dict[int, list[Match]], reported: dict | None = None) -> None:
    """Work out every derived number, in place.

    ``reported`` gives the report's own rating where a rating sits exactly on a
    rounding boundary, so the comparison that follows is of like with like.
    """
    for run in blocks(sorted(seasons)):
        block = [m for y in run for m in seasons[y]]
        last_game_turnovers(block)
        exact = power_ratings(block)
        for m in block:
            ratings = exact.get(week_of(m.day))
            for side, club in (("home", m.home), ("away", m.away)):
                if ratings is None:
                    continue
                options = tenths(ratings.get(club, F(0)))
                m.power_options[side] = options
                seen = (reported or {}).get((m.key, side))
                setattr(m, f"{side}_power", seen if seen in options else options[0])
    for matches in seasons.values():
        season_covers(matches)
        for m in matches:
            m.votes = five_votes(m)
            m.system = sum(m.votes)
            m.bet = None
            if m.line is not None and m.home_power is not None and not m.held:
                m.bet = m.home if m.system >= BET_AT else m.away if m.system <= -BET_AT else None
            m.result = None
            if m.bet and cover(m):
                m.result = "W" if (m.bet == m.home) == (cover(m) > 0) else "L"


# --- the ten shadow factors, from their written rules -------------------------

def scraped_stats(root: Path, year: int) -> dict:
    """Each scraped match's cards, missed kicks and visits to the 22, by side,
    read from the scraped files themselves rather than the stats file built
    from them."""
    out = {}
    for path in sorted((root / "entry" / "scraped").glob(f"urc_{year}01_*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                home, away = SCRAPED_NAMES.get(row["Home Team"]), SCRAPED_NAMES.get(row["Away Team"])
                out[(row["Date"][:10], home, away)] = {
                    side: {k: number(row.get(f"{side}_{k}", "")) for k in
                           ("yellow_cards", "red_cards", "missed_conversion_goals",
                            "missed_penalty_goals", "points_from_visits_to22",
                            "num_visits_to22")}
                    for side in ("home", "away")}
    return out


def shadow_votes(seasons: dict[int, list[Match]], root: Path) -> None:
    """Each factor's vote on every listed match, as tracked: +1 backs home."""
    def diff(a, b):
        return None if a is None or b is None else a - b

    for run in blocks(sorted(seasons)):
        stats = {}
        for y in run:
            stats.update(scraped_stats(root, y))
        last: dict[str, dict] = {}                   # club -> its previous match
        block = sorted((m for y in run for m in seasons[y] if m.listed),
                       key=lambda m: (m.day, m.round, m.home))
        for m in block:
            score = {}
            for side, club in (("home", m.home), ("away", m.away)):
                prev = last.get(club)
                if prev is None:
                    score[side] = dict.fromkeys(("last_cover", "cards", "kicking", "red_zone"))
                    continue
                margin = prev["margin"]
                score[side] = {
                    "last_cover": None if margin is None else
                    1 if margin <= -BIG_MISS else -1 if margin >= BIG_MISS else 0,
                    "cards": None if prev["cards"] is None else sign(prev["cards"]),
                    "kicking": None if prev["missed"] is None else sign(prev["missed"]),
                    "red_zone": None if prev["per_visit"] is None else -sign(prev["per_visit"]),
                }
            for f in ("last_cover", "cards", "kicking", "red_zone"):
                h, a = score["home"][f], score["away"][f]
                m.shadow[f] = None if h is None or a is None else sign(h - a)

            long_haul = (COUNTRY[m.home] == "ZA") != (COUNTRY[m.away] == "ZA") and not m.neutral
            m.shadow["long_haul"] = int(long_haul)
            before = last.get(m.away)
            m.shadow["tour_leg2"] = int(bool(
                long_haul and before and before["abroad"]
                and (m.day - before["day"]).days <= TOUR_GAP_DAYS))
            underdog = None if m.line is None else sign(m.line)      # +1 = home is the dog
            m.shadow["derby"] = underdog if COUNTRY[m.home] == COUNTRY[m.away] else 0
            # Tracked reversed: 2025-26 said back the favourite on a big handicap.
            m.shadow["big_line"] = (-underdog if m.line is not None
                                    and abs(m.line) >= BIG_LINE else 0)
            move = diff(m.closing, m.opening)
            m.shadow["line_move"] = sign(move) if move is not None and abs(move) >= BIG_MOVE else 0
            # The power vote, with home advantage added back (none at a neutral venue).
            rated = None not in (m.line, m.home_power, m.away_power)
            m.shadow["power_3"] = (sign(m.line + (0 if m.neutral else HOME_BACK)
                                        - (m.away_power - m.home_power)) if rated else None)

            # What this match says about each club, for its next one.
            s = stats.get(m.key)
            for side, other, club in (("home", "away", m.home), ("away", "home", m.away)):
                def per(k, s=s, side=side, other=other):
                    return None if s is None else diff(s[side][k], s[other][k])

                def weighted(a, wa, b, wb, s=s, side=side, other=other):
                    if s is None or None in (s[side][a], s[side][b], s[other][a], s[other][b]):
                        return None
                    return wa * s[side][a] + wb * s[side][b] - wa * s[other][a] - wb * s[other][b]

                def per_visit(s=s, side=side, other=other):
                    if s is None:
                        return None
                    rate = {}
                    for x in (side, other):
                        pts, visits = s[x]["points_from_visits_to22"], s[x]["num_visits_to22"]
                        if pts is None or not visits:
                            return None
                        rate[x] = pts / visits
                    return rate[side] - rate[other]

                own = m.home_score if side == "home" else m.away_score
                opp = m.away_score if side == "home" else m.home_score
                own_line = None if m.line is None else (m.line if side == "home" else -m.line)
                last[club] = {
                    "day": m.day,
                    "margin": own - opp + own_line if m.played and own_line is not None else None,
                    "cards": weighted("yellow_cards", 1, "red_cards", 2),
                    "missed": weighted("missed_conversion_goals", 2, "missed_penalty_goals", 3),
                    "per_visit": per_visit(),
                    "abroad": (not m.neutral
                               and (COUNTRY[club] == "ZA") != (COUNTRY[m.home] == "ZA")),
                }


def shadow_table(matches: list[Match]) -> dict[str, dict]:
    """Each factor's season: votes cast, its record, and the system's with it
    counted as a sixth vote - or, for the power variant, in place of the power
    vote."""
    out = {}
    listed = [m for m in matches if m.listed]
    for f in SHADOWS:
        votes = won = lost = sys_won = sys_lost = 0
        for m in listed:
            vote, c = m.shadow.get(f), cover(m)
            if vote in (1, -1):
                votes += 1
                won += c != 0 and vote == c
                lost += c != 0 and vote != c
            total = m.system + (vote or 0)
            if f == "power_3":                      # stands in for the power vote
                total -= m.votes[0]
            pick = sign(total) if abs(total) >= BET_AT else 0
            if (pick and c and m.line is not None and m.home_power is not None
                    and not m.held):
                sys_won += pick == c
                sys_lost += pick != c
        out[f] = {"votes": votes, "won": won, "lost": lost, "sys_won": sys_won,
                  "sys_lost": sys_lost, "sys_units": sys_won - JUICE * sys_lost}
    return out


# --- checking ----------------------------------------------------------------

class Checks:
    def __init__(self, quiet: bool = False):
        self.failed: list[str] = []
        self.count = 0
        self.quiet = quiet

    def __call__(self, label: str, problems: list[str] | bool, detail: str = "") -> bool:
        """``problems`` is a list of what is wrong (empty = pass), or a bool."""
        if isinstance(problems, bool):
            problems = [] if problems else [detail or "failed"]
            detail = "" if problems else detail
        self.count += 1
        ok = not problems
        if not ok:
            self.failed.append(label)
        if not self.quiet:
            shown = "; ".join(problems[:4]) + (f"; and {len(problems) - 4} more"
                                               if len(problems) > 4 else "")
            tail = shown if problems else detail
            print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f" - {tail}" if tail else ""))
        return ok


def name(m: Match) -> str:
    return f"R{m.round} {m.home} v {m.away}"


def check_sources(check: Checks, year: int, matches: list[Match], root: Path) -> None:
    unknown = sorted({c for m in matches for c in (m.home, m.away)} - CLUBS)
    check("every club is one of the sixteen", [f"unknown club {c!r}" for c in unknown])

    problems = []
    by_round: dict[int, list[Match]] = defaultdict(list)
    for m in matches:
        by_round[m.round].append(m)
    for rnd, ms in sorted(by_round.items()):
        clubs = Counter(c for m in ms for c in (m.home, m.away))
        twice = sorted(c for c, n in clubs.items() if n > 1)
        if twice:
            problems.append(f"round {rnd}: {', '.join(twice)} appear twice")
        if rnd <= REGULAR_ROUNDS and len(ms) != 8:
            problems.append(f"round {rnd} has {len(ms)} matches")
    check("eight matches a regular round, each club once", problems)

    pairs = Counter(m.key for m in matches)
    same_day = Counter((m.day, c) for m in matches for c in (m.home, m.away))
    check("no fixture twice, no club twice in a day",
          [f"{k} listed {n} times" for k, n in pairs.items() if n > 1]
          + [f"{c} plays twice on {d}" for (d, c), n in same_day.items() if n > 1])

    home_away = Counter((m.home, m.away) for m in matches if m.round <= REGULAR_ROUNDS)
    check("no club hosts the same opponent twice in the regular season",
          [f"{h} v {a} x{n}" for (h, a), n in home_away.items() if n > 1])

    span = [m for m in matches if not (date(year, 8, 1) <= m.day <= date(year + 1, 7, 31))]
    odd_day = [m for m in matches if m.day.weekday() not in MATCH_DAYS]
    check("every date falls inside the season",
          [f"{name(m)} on {m.day}" for m in span])
    check("every match is on a Friday, Saturday or Sunday", True,
          f"{len(odd_day)} on another day: " + ", ".join(
              f"{name(m)} {m.day:%a %d %b}" for m in odd_day[:6]) if odd_day else "")

    problems = []
    for m in matches:
        for what, v in (("opening", m.opening), ("closing", m.closing)):
            if v is not None and (v * 2).denominator != 1:
                problems.append(f"{name(m)} {what} line {float(v)}")
            if v is not None and abs(v) > 60:
                problems.append(f"{name(m)} {what} line {float(v)} is not credible")
        counts = [m.home_score, m.away_score, m.home_conceded, m.away_conceded]
        if any(v is None for v in counts) and any(v is not None for v in counts):
            problems.append(f"{name(m)} has only part of its result")
        if any(v is not None and v < 0 for v in counts):
            problems.append(f"{name(m)} has a negative count")
    check("handicaps in half points; a result is complete or absent", problems)

    order = sorted(matches, key=lambda m: m.day)
    unplayed_before = [m for i, m in enumerate(order) if not m.played
                       and any(n.played for n in order[i + 1:])
                       and any(n.played and n.day > m.day for n in order[i + 1:])]
    check("no unplayed match is dated before a played one",
          [f"{name(m)} on {m.day}" for m in unplayed_before])

    check_scrapes(check, year, matches, root)


def check_scrapes(check: Checks, year: int, matches: list[Match], root: Path) -> None:
    """Every scraped file against the season file it was loaded into."""
    by_key = {m.key: m for m in matches}
    files = sorted((root / "entry" / "scraped").glob(f"urc_{year}01_*.csv"))
    if not files:
        check("scraped files agree with the season file", True, "no scraped files")
        return
    problems, seen, points = [], set(), []
    for path in files:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    home, away = SCRAPED_NAMES[row["Home Team"]], SCRAPED_NAMES[row["Away Team"]]
                except KeyError as e:
                    problems.append(f"{path.name}: unknown club {e}")
                    continue
                m = by_key.get((row["Date"][:10], home, away))
                if m is None:
                    problems.append(f"{path.name}: {row['Date']} {home} v {away} is not a fixture")
                    continue
                seen.add(m.key)
                got = (whole(row["home_score"]), whole(row["away_score"]),
                       whole(row["home_turnovers_lost"]), whole(row["away_turnovers_lost"]),
                       whole(row["home_turnovers_won"]), whole(row["away_turnovers_won"]))
                want = (m.home_score, m.away_score, m.home_conceded, m.away_conceded,
                        m.home_won, m.away_won)
                if got != want:
                    problems.append(f"{name(m)}: scrape {got} v season file {want}")
                for side in ("home", "away"):
                    cells = [number(row.get(f"{side}_{k}", "")) for k in
                             ("tries", "penalty_tries", "conversion_goals", "penalty_goals",
                              "drop_goals_converted")]
                    if None in cells:
                        continue
                    tries, pen_tries, cons, pens, drops = cells
                    total = 5 * (tries - pen_tries) + 7 * pen_tries + 2 * cons + 3 * (pens + drops)
                    if total != number(row[f"{side}_score"]):
                        points.append(f"{name(m)} {side}: scoring adds to {total}, "
                                      f"score {row[f'{side}_score']}")
    check("scraped files agree with the season file on scores and turnovers", problems,
          f"{len(seen)} matches in {len(files)} file(s)")
    check("each scraped side's tries and kicks add up to its score", points)
    unscraped = [m for m in matches if m.played and m.key not in seen]
    check("every played match has its scrape on file",
          [name(m) for m in unscraped])


def read_report(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def reported_powers(rows: list[dict]) -> dict:
    out = {}
    for r in rows:
        key = (r["date"], r["home"], r["away"])
        for side in ("home", "away"):
            out[(key, side)] = number(r[f"{side}_power"])
    return out


def check_report(check: Checks, year: int, matches: list[Match], rows: list[dict]) -> None:
    listed = sorted((m for m in matches if m.listed), key=lambda m: (m.day, m.round, m.home))
    by_key = {(r["date"], r["home"], r["away"]): r for r in rows}
    missing = [name(m) for m in listed if m.key not in by_key]
    extra = [f"{k}" for k in by_key if k not in {m.key for m in listed}]
    check("the report lists exactly the played and priced matches",
          [f"missing {x}" for x in missing] + [f"unexpected {x}" for x in extra],
          f"{len(listed)} matches")

    columns = {
        "the round and both handicaps": lambda m: {
            "round": m.round, "opening_line": m.opening, "line": m.line},
        "the scores": lambda m: {"home_score": m.home_score, "away_score": m.away_score},
        "last-game turnover margins": lambda m: {
            "home_lgt": m.home_lgt, "away_lgt": m.away_lgt},
        "matches held back for a missing turnover count": lambda m: {"lgt_unknown": m.held},
        "season-to-date covers": lambda m: {"home_stdc": m.home_stdc, "away_stdc": m.away_stdc},
        "power ratings": lambda m: {"home_power": m.home_power, "away_power": m.away_power},
        "the System #": lambda m: {"system_num": m.system},
        "the pick": lambda m: {"system_bet": m.bet},
        "the grade": lambda m: {"result": m.result},
    }
    for label, want_of in columns.items():
        problems = []
        for m in listed:
            row = by_key.get(m.key)
            if row is None:
                continue
            for col, want in want_of(m).items():
                raw = row[col].strip()
                if isinstance(want, bool):
                    got = {"True": True, "False": False}.get(raw, raw)
                elif isinstance(want, str) or (want is None and col in ("system_bet", "result")):
                    got = raw or None
                else:
                    got = number(raw)
                if got != want:
                    show = lambda v: v if v is None or isinstance(v, (str, bool)) else float(v)
                    problems.append(f"{name(m)} {col}: report {show(got)}, "
                                    f"recomputed {show(want)}")
        check(f"{label} match", problems)

    on_edge = [f"{name(m)} {side} rating"
               for m in listed for side in ("home", "away")
               if len(m.power_options.get(side, [])) > 1]
    check("no rating sits exactly on a rounding boundary", True,
          f"{len(on_edge)} do: " + ", ".join(on_edge[:4]) if on_edge else "")


def check_shadow_file(check: Checks, matches: list[Match], path: Path) -> None:
    if not path.exists():
        check("the shadow-factor file exists", False, f"no {path.name}")
        return
    with open(path, newline="", encoding="utf-8") as f:
        rows = {(r["date"], r["home"], r["away"]): r for r in csv.DictReader(f)}
    listed = [m for m in matches if m.listed]
    problems = [f"{name(m)} is missing" for m in listed if m.key not in rows]
    for m in listed:
        row = rows.get(m.key)
        for f in SHADOWS if row else ():
            got = whole(row[f])
            if got != m.shadow[f]:
                problems.append(f"{name(m)} {f}: file {got}, recomputed {m.shadow[f]}")
    check("every shadow-factor vote matches", problems,
          f"{len(listed)} matches x {len(SHADOWS)} factors")


# --- the bet tracker, from the bet log ----------------------------------------

STANDARD_PRICE = F(21, 11)          # 1.91: what a unit at -110 pays back
SETTLEMENTS = {"won": "Won", "lost": "Lost", "void": "Void", "cashed out": "Cashed Out"}


def read_bets(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def verdict(system: int, backing_home: bool) -> str:
    if abs(system) < BET_AT:
        return "no"
    return "yes" if (system > 0) == backing_home else "against"


def assess_bets(rows: list[dict], matches: list[Match], year: int, current: bool) -> list[dict]:
    """The season's URC bets, each matched to its fixture and graded."""
    out = []
    for b in rows:
        if b["sport"].strip().lower() != "rugby" or b["competition"].strip().upper() not in ("URC", ""):
            continue
        when = b["event_date"].strip() or b["placed"].strip()
        if when:
            if not date(year, 8, 1) <= date.fromisoformat(when[:10]) <= date(year + 1, 7, 31):
                continue
        elif not current:
            continue
        club = b["team"].strip()
        mine = [m for m in matches if club in (m.home, m.away) and m.listed]
        if b["event_date"].strip():
            mine = [m for m in mine if m.day.isoformat() == b["event_date"].strip()[:10]]
        else:
            rnd = re.search(r"\d+", b["round_week"])
            mine = [m for m in mine if rnd and m.round == int(rnd.group())]
        if len(mine) != 1:
            out.append({"id": b["bet_id"], "problem": f"bet {b['bet_id']} ({club}) fits "
                                                       f"{len(mine)} matches"})
            continue
        m = mine[0]
        home = club == m.home
        line = number(b["line"])
        close = None if m.line is None else (m.line if home else -m.line)
        rated = m.home_power is not None and not m.held
        at_close = verdict(m.system, home) if rated and m.line is not None else "?"
        if line is None:
            label = "?" if at_close == "?" else f"{at_close} at close"
        else:
            power = sign((line if home else -line) - (m.away_power - m.home_power)) if rated else 0
            yours = verdict(power + sum(m.votes[1:]), home) if rated else "?"
            label = yours if at_close in (yours, "?") else f"{yours}, {at_close} at close"
        margin = ((m.home_score - m.away_score) * (1 if home else -1)) if m.played else None
        graded = None
        if margin is not None and line is not None:
            graded = {1: "Won", -1: "Lost", 0: "Void"}[sign(margin + line)]
        logged = SETTLEMENTS.get(b["result"].strip().lower())
        result = logged or graded or "Pending"
        stake, odds = number(b["stake_eur"]), number(b["decimal_odds"])
        if logged and number(b["profit_eur"]) is not None:
            profit = number(b["profit_eur"])
        elif result == "Won":
            profit = None if odds is None else stake * (odds - 1)
        else:
            profit = {"Lost": -stake, "Void": F(0)}.get(result)
        tail = b["selection"].split()[-1] if b["selection"].split() else ""
        out.append({
            "id": int(b["bet_id"]), "match": m, "home": home, "club": club, "line": line,
            "label": (f"{club} {float(line):+g}" if line is not None
                      else f"{club} {tail if tail[:1] in '+-' and tail else '?'}"),
            "opponent": m.away if home else m.home, "odds": odds, "stake": stake,
            "close": close, "value": None if line is None or close is None else line - close,
            "system": label, "result": result, "profit": profit, "logged": logged,
            "graded": graded, "returns": number(b["returns_eur"]),
        })
    return sorted(out, key=lambda x: (x["match"].day, x["id"]) if "match" in x else (date.max, 0))


def bet_summary(bets: list[dict], matches: list[Match]) -> dict:
    bets = [b for b in bets if "match" in b]
    won = sum(b["result"] == "Won" for b in bets)
    lost = sum(b["result"] == "Lost" for b in bets)
    priced = [b for b in bets if b["result"] in ("Won", "Lost", "Cashed Out")
              and b["profit"] is not None]
    staked = sum((b["stake"] for b in priced), F(0))
    profit = sum((b["profit"] for b in priced), F(0))
    per_match: dict[tuple, F] = defaultdict(F)
    for b in bets:
        per_match[b["match"].key] += b["stake"]
    stakes = sorted(per_match.values())
    n = len(stakes)
    stake = F(25) if not n else (stakes[n // 2] if n % 2 else (stakes[n // 2 - 1] + stakes[n // 2]) / 2)
    rounds = {b["match"].round for b in bets}
    sys_won = sum(m.result == "W" for m in matches if m.round in rounds)
    sys_lost = sum(m.result == "L" for m in matches if m.round in rounds)
    values = [b["value"] for b in bets if b["value"] is not None]
    return {"won": won, "lost": lost, "pending": sum(b["result"] == "Pending" for b in bets),
            "cashed": sum(b["result"] == "Cashed Out" for b in bets),
            "staked": staked, "profit": profit, "roi": profit / staked if staked else None,
            "value": sum(values, F(0)) / len(values) if values else None,
            "sys_won": sys_won, "sys_lost": sys_lost, "stake": stake,
            "sys_profit": sys_won * stake * (STANDARD_PRICE - 1) - sys_lost * stake}


def check_bet_log(check: Checks, bets: list[dict]) -> None:
    """The log's own arithmetic, and each settlement against the score."""
    sums, grades = [], []
    for b in bets:
        if "problem" in b:
            sums.append(b["problem"])
            continue
        if b["logged"] and b["returns"] is not None and b["profit"] is not None:
            if b["returns"] - b["stake"] != b["profit"]:
                sums.append(f"bet {b['id']}: returns {float(b['returns'])} less stake "
                            f"{float(b['stake'])} is not profit {float(b['profit'])}")
            if (b["logged"] == "Won" and b["odds"] is not None
                    and abs(b["stake"] * b["odds"] - b["returns"]) > F(1, 100)):
                sums.append(f"bet {b['id']}: {float(b['stake'])} at {float(b['odds'])} "
                            f"does not return {float(b['returns'])}")
            if b["logged"] == "Lost" and b["returns"] != 0:
                sums.append(f"bet {b['id']}: a lost bet with returns")
        if b["logged"] in ("Won", "Lost", "Void") and b["graded"] and b["logged"] != b["graded"]:
            grades.append(f"bet {b['id']} {b['label']}: settled {b['logged']}, the score "
                          f"makes it {b['graded']}")
    check("each bet's stake, price, returns and profit agree", sums, f"{len(bets)} URC bets")
    check("each settlement agrees with the score at the bet's own line", grades)


# --- the site ----------------------------------------------------------------

class Page(HTMLParser):
    """The built page as data: tiles, tables and charts, by section."""

    VOID = {"br", "meta", "link", "img", "input", "hr"}

    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.marks: list[tuple[int, str]] = []         # (depth, id) of open sections
        self.heading = ""
        self.tiles: dict[tuple, dict] = defaultdict(dict)
        self.tables: list[dict] = []
        self.charts: dict[str, list[str]] = {}
        self.text: dict[str, str] = defaultdict(str)
        self._caps: list[list] = []                    # [depth, kind, text]
        self._table = self._row = None
        self._label = ""
        self.feed(source)

    @property
    def section(self) -> str:
        return self.marks[-1][1] if self.marks else "top"

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.VOID:
            if tag == "br":
                self.handle_data(" / ")
            return
        self.stack.append(tag)
        depth, cls = len(self.stack), (a.get("class") or "").split()
        if "id" in a:
            self.marks.append((depth, a["id"]))
            self.heading = ""
        self.text[self.section] += " "
        if tag in ("h2", "h3"):
            self._caps.append([depth, "heading", ""])
        elif tag == "div" and cls[:1] == ["k"]:
            self._caps.append([depth, "label", ""])
        elif tag == "div" and cls[:1] == ["v"]:
            self._caps.append([depth, "value", ""])
        elif tag == "table":
            self._table = {"section": self.section, "heading": self.heading,
                           "head": [], "rows": []}
            self.tables.append(self._table)
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._caps.append([depth, "cell", ""])
        elif tag == "figure" and "chart" in cls and a.get("data-points"):
            self.charts[self.section] = [pt["label"] for pt in json.loads(a["data-points"])]

    def handle_startendtag(self, tag, attrs):
        pass                                           # self-closed SVG shapes

    def handle_endtag(self, tag):
        if tag in self.VOID or tag not in self.stack:
            return
        in_head = "thead" in self.stack
        while self.stack.pop() != tag:
            pass
        depth = len(self.stack)
        while self._caps and self._caps[-1][0] > depth:
            _, kind, text = self._caps.pop()
            text = " ".join(text.split())
            if kind == "heading":
                self.heading = text
            elif kind == "label":
                self._label = text
            elif kind == "value":
                self.tiles[(self.section, self.heading)][self._label] = text
            elif kind == "cell" and self._row is not None:
                self._row.append(text)
        if tag == "tr" and self._row is not None and self._table is not None:
            self._table["head" if in_head else "rows"].append(self._row)
            self._row = None
        elif tag == "table":
            self._table = None
        self.text[self.section] += " "
        while self.marks and self.marks[-1][0] > depth:
            self.marks.pop()

    def handle_data(self, data):
        for cap in self._caps:
            cap[2] += data
        self.text[self.section] += data

    def table(self, section: str, heading: str) -> dict | None:
        return next((tb for tb in self.tables
                     if tb["section"] == section and tb["heading"] == heading), None)

    def words(self, section: str) -> str:
        return " ".join(self.text[section].split())


def signed(x, places: int = 1) -> str:
    return "" if x is None else f"{float(x):+.{places}f}"


def euros(x) -> str:
    if x is None:
        return "?"
    return ("+" if x > 0 else "\u2212" if x < 0 else "") + f"\u20ac{abs(float(x)):.2f}"


def percent(won: int, lost: int) -> str:
    return "\u2014" if not won + lost else f"{float(F(won, won + lost)):.0%}"


def compare(got: list, want: list, what: str) -> list[str]:
    """Row-by-row differences between two tables of text."""
    problems = []
    if len(got) != len(want):
        problems.append(f"{what}: {len(got)} rows on the page, {len(want)} expected")
    for g, w in zip(got, want):
        if g != w:
            where = next((i for i, (x, y) in enumerate(zip(g, w)) if x != y), min(len(g), len(w)))
            problems.append(f"{what} {' '.join(w[:4])}: column {where + 1} shows "
                            f"{g[where] if where < len(g) else 'nothing'!r}, expected "
                            f"{w[where] if where < len(w) else 'nothing'!r}")
    return problems


def check_site_season(check: Checks, page: Page, year: int, matches: list[Match],
                      before: list[Match] | None) -> None:
    section = f"s{year}"
    listed = sorted((m for m in matches if m.listed), key=lambda m: (m.day, m.round, m.home))
    r = record(matches)
    want = {"Matches": str(r["matches"]), "Priced": str(r["priced"]), "Played": str(r["played"]),
            "Bets": str(r["bets"]), "Record": f"{r['won']}\u2013{r['lost']}",
            "Win rate": percent(r["won"], r["lost"]),
            "Profit (units)": f"{float(r['units']):+.1f}"}
    got = page.tiles.get((section, ""), {})
    check("the season's tiles match",
          [f"{k}: page {got.get(k)!r}, recomputed {v!r}" for k, v in want.items()
           if got.get(k) != v])

    has_open = any(m.opening is not None for m in listed)
    rows = []
    for m in listed:
        rated = m.home_power is not None and m.away_power is not None
        rows.append(
            [m.day.isoformat(), str(m.round), m.home, m.away]
            + ([signed(m.opening)] if has_open else [])
            + [signed(m.line),
               f"{m.home_score}\u2013{m.away_score}" if m.played else "\u2014",
               signed(m.home_lgt, 0), signed(m.home_stdc, 0), signed(m.home_power),
               signed(m.away_lgt, 0), signed(m.away_stdc, 0), signed(m.away_power),
               "\u2014" if m.held or not rated else f"{m.system:+d}",
               "held" if m.held else (m.bet or ""),
               m.result or ("\u00b7" if m.bet else "")])
    table = page.table(section, "Every match")
    check("every row of Every match matches",
          compare(table["rows"], rows, "row") if table else ["the table is missing"],
          f"{len(rows)} rows")

    running, labels = F(0), []
    for m in listed:
        if m.result:
            running += 1 if m.result == "W" else -JUICE
            labels.append(f"{m.day.isoformat()} \u00b7 {m.home} v {m.away} \u00b7 {m.result} "
                          f"\u00b7 {float(running):+.1f}u")
    check("the profit curve is the graded bets in order",
          [f"point {i + 1}: page {g!r}, recomputed {w!r}"
           for i, (g, w) in enumerate(zip(page.charts.get(section, []), labels)) if g != w]
          + ([] if len(page.charts.get(section, [])) == len(labels)
             else [f"{len(page.charts.get(section, []))} points, {len(labels)} expected"]))

    for heading, attr, places in (("Season to date cover, club \u00d7 round", "stdc", 0),
                                  ("Power rating, club \u00d7 round", "power", 1)):
        table, problems = page.table(section, heading), []
        if table is None:
            problems.append("the table is missing")
        else:
            rounds = table["head"][0][1:]
            cell = {(m.home if side == "home" else m.away, str(m.round)):
                    getattr(m, f"{side}_{attr}") for m in listed for side in ("home", "away")}
            means = []
            for row in table["rows"]:
                club, shown = row[0], row[1:]
                vals = [cell.get((club, rnd)) for rnd in rounds]
                for rnd, got_v, v in zip(rounds, shown, vals):
                    if got_v != signed(v, places):
                        problems.append(f"{club} round {rnd}: page {got_v!r}, "
                                        f"recomputed {signed(v, places)!r}")
                known = [v for v in vals if v is not None]
                means.append(sum(known, F(0)) / len(known) if known else None)
            if {row[0] for row in table["rows"]} != {c for c, _ in cell if cell[(c, _)] is not None}:
                problems.append("the clubs listed are not the clubs rated")
            if any(a < b for a, b in zip(means, means[1:]) if a is not None and b is not None):
                problems.append("clubs are not in order of their season mean")
        check(f"the {attr} heatmap matches, club by round", problems)

    mine = shadow_table(matches)
    prior = shadow_table(before) if before else None
    rows = []
    for f, label in SHADOWS.items():
        s = mine[f]
        rows.append([label, str(s["votes"]), f"{s['won']}\u2013{s['lost']}",
                     percent(s["won"], s["lost"])]
                    + ([percent(prior[f]["won"], prior[f]["lost"])] if prior else [])
                    + [f"{s['sys_won']}\u2013{s['sys_lost']} / {float(s['sys_units']):+.1f}"])
    table = page.table(section, "Shadow factors")
    marks = "\u2020\u2021"
    shown = [[row[0].rstrip(marks).strip()] + row[1:] for row in table["rows"]] if table else []
    check("the shadow-factor table matches", compare(shown, rows, "factor")
          if table else ["the table is missing"])
    # ‡ tells the reader its With it is in place of the power vote, not a sixth.
    swapped = [row[0].rstrip(marks).strip() for row in (table or {}).get("rows", [])
               if row[0].rstrip("\u2020").endswith("\u2021")]
    check("only the power variant is marked as standing in for the power vote",
          swapped == [SHADOWS["power_3"]], f"marked: {swapped}")


def check_site_tracker(check: Checks, page: Page, label: str, bets: list[dict],
                       matches: list[Match]) -> None:
    good = [b for b in bets if "match" in b]
    s = bet_summary(bets, matches)
    want = {"Record": f"{s['won']}\u2013{s['lost']}" + (f" +{s['pending']}" if s["pending"] else ""),
            "Staked": f"\u20ac{float(s['staked']):.0f}", "Profit": euros(s["profit"]),
            "Return": "\u2014" if s["roi"] is None else f"{float(s['roi']):+.0%}",
            "Line v close": "\u2014" if s["value"] is None else f"{float(s['value']):+.1f}",
            "System, same rounds": f"{s['sys_won']}\u2013{s['sys_lost']} \u00b7 {euros(s['sys_profit'])}"}
    got = page.tiles.get(("tracker", label), {})
    check("the bet tracker's totals match",
          [f"{k}: page {got.get(k)!r}, recomputed {v!r}" for k, v in want.items()
           if got.get(k) != v])
    tags = {"Won": "W", "Lost": "L", "Void": "void", "Cashed Out": "cashed out"}
    rows = []
    for b in good:
        odds = "" if b["odds"] is None else f" \u00b7 {float(b['odds']):.2f}"
        money = "" if b["profit"] is None else f" / {euros(b['profit'])}"
        rows.append([f"{b['label']} / R{b['match'].round} v {b['opponent']}{odds}",
                     signed(b["close"]), signed(b["value"]), b["system"],
                     tags.get(b["result"], "pending") + money])
    table = page.table("tracker", label)
    check("every row of the bet tracker matches",
          compare(table["rows"], rows, "bet") if table else ["the table is missing"],
          f"{len(rows)} bets")


def check_site(check: Checks, root: Path, seasons: dict[int, list[Match]]) -> None:
    path = root / "index.html"
    if not path.exists():
        check("the site has been built", False, "no index.html")
        return
    page = Page(path.read_text(encoding="utf-8"))
    rows = read_bets(root.parent / "bets" / "bet_log.csv")
    todo = sorted((m for m in seasons[max(seasons)] if m.line is None and not m.played),
                  key=lambda m: m.day)
    if todo:
        if not check.quiet:
            print("\nthe site: what is needed next")
        count = sum(m.round == todo[0].round for m in todo)
        want = f"Round {todo[0].round}'s handicaps. {count} match"
        check("the lead card names the next round to price",
              [] if want in page.words("top") else [f"expected to read: {want}..."])
    for year in sorted(seasons, reverse=True):
        label = f"{year}-{(year + 1) % 100:02d}"
        if not check.quiet:
            print(f"\n{label}: the site")
        if not any(m.listed for m in seasons[year]):
            continue
        check_site_season(check, page, year, seasons[year], seasons.get(year - 1))
        bets = assess_bets(rows, seasons[year], year, year == max(seasons))
        if bets:
            check_bet_log(check, bets)
            check_site_tracker(check, page, label, bets, seasons[year])
        elif page.table("tracker", label):
            check("the bet tracker shows no bets for a season without any", False)


def record(matches: list[Match]) -> dict:
    won = sum(m.result == "W" for m in matches)
    lost = sum(m.result == "L" for m in matches)
    return {"matches": sum(m.listed for m in matches),
            "priced": sum(m.listed and m.line is not None for m in matches),
            "played": sum(m.played for m in matches),
            "bets": sum(m.bet is not None for m in matches),
            "won": won, "lost": lost, "units": won - JUICE * lost,
            "held": sum(m.listed and m.held for m in matches)}


def load_all(root: Path) -> tuple[dict[int, list[Match]], dict[int, list[dict]]]:
    data = root / "data"
    seasons = {y: read_season(data / f"season_{y}.csv", y) for y in seasons_present(data)}
    reports = {y: read_report(data / f"report_{y}.csv") for y in seasons
               if (data / f"report_{y}.csv").exists()}
    seen = {}
    for rows in reports.values():
        seen.update(reported_powers(rows))
    run_model(seasons, seen)
    shadow_votes(seasons, root)
    return seasons, reports


def run(root: Path, quiet: bool = False) -> Checks:
    check = Checks(quiet)
    seasons, reports = load_all(root)
    for year, matches in seasons.items():
        label = f"{year}-{(year + 1) % 100:02d}"
        if not quiet:
            print(f"\n{label}: the source data")
        check_sources(check, year, matches, root)
        if not quiet:
            print(f"\n{label}: the report, recomputed")
        if year not in reports:
            check("a report exists for the season", not any(m.listed for m in matches),
                  "no report file")
            continue
        check_report(check, year, matches, reports[year])
        check_shadow_file(check, matches, root / "data" / f"shadow_{year}.csv")
        r = record(matches)
        if not quiet:
            print(f"  ....  {r['bets']} bets, {r['won']}-{r['lost']}, "
                  f"{float(r['units']):+.1f} units" + (f", {r['held']} held back"
                                                       if r["held"] else ""))
    check_site(check, root, seasons)
    return check


# --- the self-test: plant a fault, expect a failure ---------------------------

def _rows(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames), list(reader)


def _save(path: Path, head: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=head, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _edit(path: Path, pick, change, also_append: bool = False) -> None:
    """Change the first row of a CSV that ``pick`` accepts."""
    head, rows = _rows(path)
    row = next(r for r in rows if pick(r))
    if also_append:
        rows.append(dict(row))
    else:
        change(row)
    _save(path, head, rows)


def _bump(col: str, by) -> callable:
    def change(row: dict) -> None:
        row[col] = str(float(row[col]) + by) if "." in row[col] else str(int(row[col]) + by)
    return change


def _swap_text(path: Path, pattern: str, repl) -> None:
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(pattern, repl, text, count=1)
    assert n == 1, f"self-test: nothing to change in {path.name}"
    path.write_text(new, encoding="utf-8")


def self_test() -> int:
    """Plant one fault at a time in a copy of the files; each must fail a check."""
    year = max(seasons_present(HERE / "data"))
    season, report = f"data/season_{year}.csv", f"data/report_{year}.csv"
    graded = lambda r: r.get("result") in ("W", "L")
    played = lambda r: r["home_score"].strip() != ""

    def other_club(row: dict) -> None:
        row["system_bet"] = row["away"] if row["system_bet"] == row["home"] else row["home"]

    def regrade(row: dict) -> None:
        row["result"] = "L" if row["result"] == "W" else "W"

    faults = [
        ("a score in the season file", "the scores match",
         lambda root: _edit(root / season, played, _bump("home_score", 10))),
        ("a closing line in the season file", "the round and both handicaps match",
         lambda root: _edit(root / season, played, _bump("closing_line", -3.0))),
        ("a turnover count in the season file", "last-game turnover margins match",
         lambda root: _edit(root / season, played, _bump("home_turnovers_conceded", 9))),
        ("a fixture listed twice", "eight matches a regular round, each club once",
         lambda root: _edit(root / season, played, None, also_append=True)),
        ("a turnover count in a scraped file",
         "scraped files agree with the season file on scores and turnovers",
         lambda root: _edit(sorted((root / "entry" / "scraped").glob(f"urc_{year}01_*.csv"))[0],
                            lambda r: True, _bump("home_turnovers_lost", 1.0))),
        ("a System # in the report", "the System # match",
         lambda root: _edit(root / report, played, _bump("system_num", 1))),
        ("a pick in the report", "the pick match",
         lambda root: _edit(root / report, graded, other_club)),
        ("a grade in the report", "the grade match",
         lambda root: _edit(root / report, graded, regrade)),
        ("a rating in the report", "power ratings match",
         lambda root: _edit(root / report, played, _bump("home_power", 0.1))),
        ("a season-to-date cover in the report", "season-to-date covers match",
         lambda root: _edit(root / report, played, _bump("home_stdc", 1.0))),
        ("a shadow-factor vote", "every shadow-factor vote matches",
         lambda root: _edit(root / f"data/shadow_{year}.csv", lambda r: r["long_haul"] == "0",
                            _bump("long_haul", 1))),
        ("a 3-point power vote", "every shadow-factor vote matches",
         lambda root: _edit(root / f"data/shadow_{year}.csv", lambda r: r["power_3"] == "-1",
                            lambda r: r.update(power_3="1"))),
        ("the power variant's With it on the site", "the shadow-factor table matches",
         lambda root: _swap_text(root / "index.html",
                                 r"(Power, 3-point home edge.*?<td>)(\d+)(\u2013\d+<br>)",
                                 lambda m: m.group(1) + str(int(m.group(2)) + 1) + m.group(3))),
        ("the record on the site", "the season's tiles match",
         lambda root: _swap_text(root / "index.html",
                                 r'(<div class="k">Record</div><div class="v ">)(\d+)',
                                 lambda m: m.group(1) + str(int(m.group(2)) + 1))),
        ("a System # on the site", "every row of Every match matches",
         lambda root: _swap_text(root / "index.html", r"<strong>([+-]\d)</strong></td>",
                                 lambda m: f"<strong>{int(m.group(1)) + 1:+d}</strong></td>")),
        ("a rating in the site's heatmap", "the power heatmap matches, club by round",
         lambda root: _swap_text(root / "index.html",
                                 r"(Power rating, club . round.*?<td style=[^>]*>)([+-]\d+\.\d)",
                                 lambda m: m.group(1) + f"{float(m.group(2)) + 1:+.1f}")),
        ("a profit in the bet log", "each bet's stake, price, returns and profit agree",
         lambda root: _edit(root.parent / "bets" / "bet_log.csv",
                            lambda r: r["sport"] == "rugby" and r["profit_eur"].strip(),
                            _bump("profit_eur", 1.0))),
        ("a bet's result in the bet log",
         "each settlement agrees with the score at the bet's own line",
         lambda root: _edit(root.parent / "bets" / "bet_log.csv",
                            lambda r: r["sport"] == "rugby" and r["result"] == "Won"
                            and r["line"].strip(),
                            lambda r: r.update(result="Lost"))),
        ("a stale site: a result added to the bet log only", "the bet tracker's totals match",
         lambda root: _edit(root.parent / "bets" / "bet_log.csv",
                            lambda r: r["sport"] == "rugby" and r["result"] == "Lost",
                            lambda r: r.update(stake_eur=str(float(r["stake_eur"]) + 5),
                                               profit_eur=str(float(r["profit_eur"]) - 5)))),
    ]

    missed = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, (what, expect, plant) in enumerate(faults):
            root = Path(tmp) / str(i) / HERE.name
            root.mkdir(parents=True)
            shutil.copytree(HERE / "data", root / "data")
            shutil.copytree(HERE / "entry" / "scraped", root / "entry" / "scraped")
            shutil.copy(HERE / "index.html", root / "index.html")
            (root.parent / "bets").mkdir()
            shutil.copy(HERE.parent / "bets" / "bet_log.csv", root.parent / "bets" / "bet_log.csv")
            if i == 0 and run(root, quiet=True).failed:
                print("  FAIL  the untouched copy does not pass; fix that first")
                return 1
            plant(root)
            failed = run(root, quiet=True).failed
            caught = expect in failed
            missed += not caught
            print(f"  {'PASS' if caught else 'FAIL'}  planted: {what} - "
                  + (f"caught by '{expect}'" + (f" and {len(failed) - 1} more"
                                                if len(failed) > 1 else "")
                     if caught else f"NOT caught; failed only {failed or 'nothing'}"))
    print(f"\n{len(faults)} faults planted; "
          + ("every one was caught" if not missed else f"{missed} NOT caught"))
    return 1 if missed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true",
                    help="plant faults in copies of the data and confirm each is caught")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    check = run(HERE)
    print(f"\n{check.count} checks; "
          + ("all checks passed" if not check.failed
             else f"{len(check.failed)} FAILED: " + "; ".join(check.failed)))
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(main())
