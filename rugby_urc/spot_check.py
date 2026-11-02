"""A weekly spot check: one club drawn at random, its inputs checked by hand.

Every pick rests on numbers the code builds from scraped and typed-in data:
each club's turnover margin in its last match (LGT), its season-to-date covers
(STDC), and the power ratings. So each week one club is drawn, and you check
its three numbers against their sources, and the arithmetic of its power vote.
Every draw, and whether you confirmed the check, is logged in
``data/spot_checks.csv`` and shown on the site.

The draw is random but reproducible. It is seeded by the season and round, and
made from the clubs playing that round that have not been drawn yet this
season, so every club comes up in turn before any comes up twice. Rerunning it
gives the same club.

Run::

    python spot_check.py draw --season 2026 --round 5     # draw once, print the card
    python spot_check.py confirm --season 2026 --round 5  # you checked: all agreed
    python spot_check.py confirm --season 2026 --round 5 --mismatch "what differed"
"""

from __future__ import annotations

import argparse
import random
from datetime import date

import pandas as pd

import model
import season_report

LOG_COLUMNS = ["season", "round", "team", "drawn_on", "checked_on", "result", "note"]
AGREED, MISMATCH = "agreed", "mismatch"


def log_path():
    return season_report.DATA_DIR / "spot_checks.csv"


def load_log() -> pd.DataFrame:
    path = log_path()
    if not path.exists():
        return pd.DataFrame(columns=LOG_COLUMNS)
    return pd.read_csv(path, dtype=str).fillna("")


def draw(year: int, rnd: int, today: str | None = None) -> str:
    """The club drawn for a round: drawn the first time, read back after that."""
    log = load_log()
    done = log[(log["season"] == str(year)) & (log["round"] == str(rnd))]
    if len(done):
        return done["team"].iloc[0]
    season = season_report.load_season(year)
    playing = season[season["round"] == rnd]
    clubs = sorted(set(playing["home"]) | set(playing["away"]))
    if not clubs:
        raise ValueError(f"{season_report.season_label(year)} has no round {rnd} fixtures")
    drawn = set(log.loc[log["season"] == str(year), "team"])
    pool = [c for c in clubs if c not in drawn] or clubs
    team = random.Random(f"{year}-{rnd}").choice(pool)
    row = {"season": str(year), "round": str(rnd), "team": team,
           "drawn_on": today or date.today().isoformat(),
           "checked_on": "", "result": "", "note": ""}
    pd.concat([log, pd.DataFrame([row])], ignore_index=True).to_csv(log_path(), index=False)
    return team


def confirm(year: int, rnd: int, mismatch: str = "", today: str | None = None) -> None:
    """Record that you checked a round's club: all agreed, or what differed."""
    log = load_log()
    at = (log["season"] == str(year)) & (log["round"] == str(rnd))
    if not at.any():
        raise ValueError(f"no club drawn for {season_report.season_label(year)} round {rnd}")
    log.loc[at, "checked_on"] = today or date.today().isoformat()
    log.loc[at, "result"] = MISMATCH if mismatch else AGREED
    log.loc[at, "note"] = mismatch
    log.to_csv(log_path(), index=False)


def _previous_match(team: str, before: pd.Timestamp, year: int) -> pd.Series | None:
    """A club's last match before a date, from this season or the one before."""
    seasons = [season_report.load_season(y) for y in (year - 1, year)
               if (season_report.DATA_DIR / f"season_{y}.csv").exists()]
    g = pd.concat(seasons, ignore_index=True)
    mine = g[((g["home"] == team) | (g["away"] == team)) & (g["date"] < before)]
    return mine.sort_values("date").iloc[-1] if len(mine) else None


def card(year: int, rnd: int, team: str) -> dict:
    """Everything needed to check a club's inputs for one round, from its side.

    Each number is worked out again here from the season files - the turnover
    counts, and the scores against the lines - and set beside what the report
    used, so a disagreement between the two shows up on the card as well.
    """
    report = pd.read_csv(season_report.DATA_DIR / f"report_{year}.csv")
    rows = report[(report["round"] == rnd)
                  & ((report["home"] == team) | (report["away"] == team))]
    if rows.empty:
        raise ValueError(f"{team} has no priced round {rnd} match in the report yet")
    m = rows.iloc[0]
    side, other = ("home", "away") if m["home"] == team else ("away", "home")
    to_team = 1 if side == "home" else -1   # turns a home-view vote into the club's

    prev = _previous_match(team, pd.Timestamp(m["date"]), year)
    last = None
    if prev is not None:
        p_side, p_other = ("home", "away") if prev["home"] == team else ("away", "home")
        own = prev[f"{p_side}_turnovers_conceded"]
        theirs = prev[f"{p_other}_turnovers_conceded"]
        counted = pd.notna(own) and pd.notna(theirs)
        last = {"date": prev["date"].strftime("%Y-%m-%d"), "round": int(prev["round"]),
                "opponent": prev[p_other], "venue": p_side,
                "score": (f"{prev[f'{p_side}_score']}–{prev[f'{p_other}_score']}"
                          if prev["played"] else ""),
                "own": int(own) if counted else None,
                "theirs": int(theirs) if counted else None,
                "lgt": int(own - theirs) if counted else None}

    covers = []
    earlier = report[(report["date"] < m["date"])
                     & ((report["home"] == team) | (report["away"] == team))]
    for r in earlier.itertuples():
        home = r.home == team
        c = model.cover(r.home_score, r.away_score, r.line) * (1 if home else -1)
        played = pd.notna(r.home_score) and pd.notna(r.away_score)
        covers.append({
            "round": int(r.round), "opponent": r.away if home else r.home,
            "venue": "home" if home else "away",
            "line": r.line if home else -r.line,
            "score": (f"{int(r.home_score if home else r.away_score)}–"
                      f"{int(r.away_score if home else r.home_score)}" if played else ""),
            "cover": c})

    lgt, stdc = m[f"{side}_lgt"], m[f"{side}_stdc"]
    turnover = (model.turnover_factor_home(lgt) if side == "home"
                else model.turnover_factor_away(lgt))
    hunger = (model.hunger_factor_home(stdc) if side == "home"
              else model.hunger_factor_away(stdc))
    return {
        "season": year, "round": rnd, "team": team, "opponent": m[other], "venue": side,
        "date": m["date"], "line": m["line"] * to_team, "home_line": m["line"],
        "home": m["home"], "away": m["away"],
        "last": last, "lgt": lgt, "lgt_vote": turnover * to_team,
        "covers": covers, "stdc": stdc, "stdc_calc": sum(c["cover"] for c in covers),
        "stdc_vote": hunger * to_team,
        "home_power": m["home_power"], "away_power": m["away_power"],
        "implied": round(m["away_power"] - m["home_power"], 1),
        "power_vote": model.power_factor(m["home_power"], m["away_power"], m["line"])
        * to_team,
        "system_num": m["system_num"], "system_bet": m["system_bet"],
        "held": bool(m.get("lgt_unknown", False)),
    }


def _vote(v: int, team: str) -> str:
    return f"for {team}" if v > 0 else f"against {team}" if v < 0 else "no vote"


def text(c: dict) -> str:
    """The card as plain text, for the terminal."""
    t, opp = c["team"], c["opponent"]
    out = [f"{season_report.season_label(c['season'])} round {c['round']}: {t} "
           f"({c['venue']} v {opp}, {c['date']}), line {t} {c['line']:+g}", ""]
    last = c["last"]
    if last is None:
        out.append("1. Turnovers: no previous match, so LGT is 0 by definition")
    elif last["lgt"] is None:
        out.append(f"1. Turnovers: round {last['round']} v {last['opponent']} has no "
                   f"turnover counts yet - the pick is held back")
    else:
        out.append(f"1. Turnovers, round {last['round']} {last['venue']} v "
                   f"{last['opponent']} ({last['score']}): conceded {t} {last['own']}, "
                   f"{last['opponent']} {last['theirs']} -> LGT {last['lgt']:+d} "
                   f"(report {c['lgt']:+.0f}): {_vote(c['lgt_vote'], t)}")
    out.append(f"2. Covers so far: STDC {c['stdc_calc']:+d} (report {c['stdc']:+.0f}): "
               f"{_vote(c['stdc_vote'], t)}")
    for r in c["covers"]:
        out.append(f"     R{r['round']} {r['venue']} v {r['opponent']}: {t} "
                   f"{r['line']:+g}, {r['score'] or 'not played'} -> {r['cover']:+d}")
    out.append(f"3. Power: {c['home']} {c['home_power']:.1f}, {c['away']} "
               f"{c['away_power']:.1f}; away - home = {c['implied']:+.1f}; line "
               f"{c['home_line']:+g}: {_vote(c['power_vote'], t)}")
    out.append(f"\nSystem # {c['system_num']:+.0f}"
               + (f": bet {c['system_bet']}" if isinstance(c["system_bet"], str) else ""))
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("draw", "confirm"))
    ap.add_argument("--season", type=int, required=True, help="season start year")
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--mismatch", default="", help="confirm: what differed, if anything")
    args = ap.parse_args()
    if args.action == "draw":
        team = draw(args.season, args.round)
        print(text(card(args.season, args.round, team)))
    else:
        confirm(args.season, args.round, args.mismatch)
        print(f"round {args.round}: {MISMATCH if args.mismatch else AGREED}")


if __name__ == "__main__":
    main()
