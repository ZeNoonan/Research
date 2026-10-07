"""Your actual bets, beside the system's picks.

Reads the shared bet log, ``../bets/bet_log.csv`` (every sport, one row per
bet), keeps the URC bets of a season and matches each to its fixture in the
report: the club backed, on the match date, or in the round when no date is
logged. For each bet it works out:

* **the line against the close** - the handicap you took minus the closing
  one, from the side you backed: +14 means you got 14 points more than the
  close offered. Over a season this is the best single test of whether bets
  are being placed well, because it does not wait for results to even out.
* **the system's view** - whether the System # backs your side at the line you
  took, and at the close. The two can differ: a line that moves on team news
  can turn a pick into a pass.
* **the result** - the bookmaker's settlement where the log has one, otherwise
  graded from the score at your line, so a bet logged as Pending settles
  itself once the round is scraped. A settlement that disagrees with the score
  is flagged: either the line was logged wrong or the bookmaker graded it
  differently.
* **profit** at your price.

Run: ``python my_bets.py`` -> each season's bets and totals.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

import model
import season_report
import teams

LOG = Path(__file__).resolve().parent.parent / "bets" / "bet_log.csv"
STANDARD_ODDS = 1 + 1 / 1.1      # -110, the price the system's record is graded at
SETTLED = ("Won", "Lost", "Void")

COLUMNS = ["bet_id", "date", "round", "match", "bet", "team", "line", "odds", "stake",
           "close", "line_value", "system", "result", "profit", "check", "source"]


def load_log(path: Path | None = None) -> pd.DataFrame:
    """The bet log, or an empty frame if there is none yet."""
    path = path or LOG
    if not path.exists():
        return pd.DataFrame(columns=["bet_id", "sport", "competition", "event_date",
                                     "round_week", "team", "line", "decimal_odds",
                                     "stake_eur", "result", "profit_eur", "placed", "source"])
    return pd.read_csv(path, dtype={"event_date": str, "round_week": str, "placed": str,
                                    "competition": str, "result": str, "team": str})


def _verdict(system_num: float, home_side: bool) -> str:
    """Does a System # back the side bet on? 'yes', 'against' or 'no'."""
    if pd.isna(system_num):
        return "?"
    side = model.pick(int(system_num))
    if side is None:
        return "no"
    return "yes" if (side == "home") == home_side else "against"


def _graded(margin: float, line: float) -> str | None:
    covered = margin + line
    return None if pd.isna(covered) else "Won" if covered > 0 else "Lost" if covered < 0 else "Void"


def _in_season(row: pd.Series, year: int, current: bool) -> bool:
    """Is a bet in this season? By its match date, else the date placed.

    A bet with neither (only a round number) is taken to be this season's.
    """
    for col in ("event_date", "placed"):
        when = pd.to_datetime(row.get(col), errors="coerce")
        if pd.notna(when):
            return pd.Timestamp(f"{year}-08-01") <= when <= pd.Timestamp(f"{year + 1}-07-31")
    return current


def assess(log: pd.DataFrame, report: pd.DataFrame, year: int, current: bool = True
           ) -> tuple[pd.DataFrame, list[str]]:
    """The season's URC bets, each matched and graded; and any that could not be.

    ``current`` marks the season being played, which claims bets logged with a
    round number but no date.
    """
    rugby = log[(log["sport"].fillna("").str.lower() == "rugby")
                & (log["competition"].fillna("").str.upper().isin(["URC", ""]))]
    rep = report.assign(date=report["date"].astype(str))
    rows, problems = [], []
    for _, b in rugby.iterrows():
        if not _in_season(b, year, current):
            continue
        shown = b.get("selection")
        label = f"bet {b['bet_id']} ({shown if isinstance(shown, str) and shown else b['team']})"
        try:
            team = teams.canonical(b["team"])
        except KeyError:
            problems.append(f"{label}: '{b['team']}' is not a URC club")
            continue
        cand = rep[(rep["home"] == team) | (rep["away"] == team)]
        if pd.notna(b.get("event_date")) and str(b["event_date"]).strip():
            cand = cand[cand["date"] == str(b["event_date"])[:10]]
        elif pd.notna(b.get("round_week")) and re.search(r"\d+", str(b["round_week"])):
            cand = cand[cand["round"] == int(re.search(r"\d+", str(b["round_week"])).group())]
        else:
            problems.append(f"{label}: needs event_date or round_week to find the match")
            continue
        if len(cand) != 1:
            problems.append(f"{label}: no {team} match on that date" if cand.empty
                            else f"{label}: {len(cand)} {team} matches fit; add the date")
            continue

        m = cand.iloc[0]
        home_side = team == m["home"]
        # A line cut off on the screenshot is logged blank: the bet still counts,
        # on the bookmaker's settlement, but has no line to compare or grade.
        line = pd.to_numeric(b.get("line"), errors="coerce")
        known = pd.notna(line)
        close = m["line"] if home_side else -m["line"]
        rated = pd.notna(m["home_power"]) and pd.notna(m["away_power"])
        at_line = (model.system_number(m["home_lgt"], m["home_stdc"], m["home_power"],
                                       m["away_lgt"], m["away_stdc"], m["away_power"],
                                       line if home_side else -line)
                   if rated and known else np.nan)
        yours = _verdict(at_line, home_side)
        at_close = _verdict(m["system_num"] if rated and pd.notna(m["line"]) else np.nan,
                            home_side)
        if not known:
            system = "?" if at_close == "?" else f"{at_close} at close"
        else:
            system = yours if at_close in (yours, "?") else f"{yours}, {at_close} at close"
        if known:
            bet = f"{team} {line:+g}"
        else:
            tail = shown.split()[-1] if isinstance(shown, str) and shown.split() else ""
            bet = f"{team} {tail if tail[:1] in ('+', '-') else '?'}"

        played = pd.notna(m["home_score"]) and pd.notna(m["away_score"])
        margin = ((m["home_score"] - m["away_score"]) * (1 if home_side else -1)
                  if played else np.nan)
        graded = _graded(margin, line)
        logged = str(b["result"]).strip().title() if pd.notna(b["result"]) else ""
        result = logged if logged in SETTLED else graded or "Pending"
        check = (f"settled {logged}, but {int(m['home_score'])}-{int(m['away_score'])} "
                 f"grades it {graded} at {line:+g}"
                 if logged in SETTLED and graded and logged != graded else "")

        stake = float(b["stake_eur"])
        odds = float(b["decimal_odds"]) if pd.notna(b.get("decimal_odds")) else np.nan
        if logged in SETTLED and pd.notna(b.get("profit_eur")):
            profit = float(b["profit_eur"])
        else:
            profit = {"Won": stake * (odds - 1), "Lost": -stake, "Void": 0.0}.get(result, np.nan)

        rows.append({
            "bet_id": b["bet_id"], "date": m["date"], "round": int(m["round"]),
            "match": f"{m['home']} v {m['away']}",
            "bet": bet, "team": team, "line": line, "odds": odds,
            "stake": stake, "close": close, "line_value": line - close,
            "system": system, "result": result, "profit": profit, "check": check,
            "source": b.get("source", ""),
        })
    return (pd.DataFrame(rows, columns=COLUMNS).sort_values(["date", "bet_id"])
            .reset_index(drop=True)), problems


def summary(bets: pd.DataFrame, report: pd.DataFrame) -> dict:
    """Totals for your bets, and the system's picks over the same rounds.

    The system is staked the way you stake - your median total stake on a match,
    since one pick is sometimes split across two slips - at the standard 1.91,
    so the two profits compare like with like. Only rounds you have bets logged
    for are counted, so a round missing from the log is not held against
    either side.
    """
    settled = bets[bets["result"].isin(["Won", "Lost"])]
    w, l = int((settled["result"] == "Won").sum()), int((settled["result"] == "Lost").sum())
    staked = float(settled["stake"].sum())
    profit = float(settled["profit"].sum(min_count=1)) if len(settled) else 0.0
    stake = (float(bets.groupby(["date", "match"])["stake"].sum().median())
             if len(bets) else 25.0)
    rounds = report[report["round"].isin(set(bets["round"])) & report["result"].notna()]
    sw, sl = int((rounds["result"] == "W").sum()), int((rounds["result"] == "L").sum())
    return {
        "bets": len(bets), "won": w, "lost": l,
        "pending": int((bets["result"] == "Pending").sum()),
        "staked": staked, "profit": profit,
        "roi": profit / staked if staked else None,
        "line_value": float(bets["line_value"].mean()) if bets["line_value"].notna().any() else None,
        "system_picks": int((bets["system"].str.startswith("yes")).sum()),
        "sys_won": sw, "sys_lost": sl, "sys_stake": stake,
        "sys_profit": sw * stake * (STANDARD_ODDS - 1) - sl * stake,
        "unknown_profit": int(settled["profit"].isna().sum()),
    }


def season(year: int) -> tuple[pd.DataFrame, list[str], dict] | None:
    """A season's bets from the files on disk, or None if there are none."""
    path = season_report.DATA_DIR / f"report_{year}.csv"
    if not path.exists():
        return None
    report = pd.read_csv(path)
    bets, problems = assess(load_log(), report, year,
                            current=year == max(season_report.available_seasons()))
    if bets.empty and not problems:
        return None
    return bets, problems, summary(bets, report)


def main() -> None:
    for year in season_report.available_seasons():
        got = season(year)
        if got is None:
            continue
        bets, problems, s = got
        print(f"\n{season_report.season_label(year)}: {s['won']}-{s['lost']}"
              + (f", {s['pending']} pending" if s["pending"] else "")
              + f" | staked EUR {s['staked']:.2f} | profit EUR {s['profit']:+.2f}"
              + (f" | line v close {s['line_value']:+.1f} a bet" if s["line_value"] is not None else ""))
        print(f"  the system's picks in the same rounds, EUR {s['sys_stake']:.0f} at 1.91: "
              f"{s['sys_won']}-{s['sys_lost']}, EUR {s['sys_profit']:+.2f}\n")
        show = bets[["round", "bet", "match", "odds", "close", "line_value", "system",
                     "result", "profit"]]
        print(show.to_string(index=False))
        for line in [c for c in bets["check"] if c] + problems:
            print(f"  ! {line}")


if __name__ == "__main__":
    main()
