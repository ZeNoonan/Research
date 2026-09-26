"""Load a whole past season: results and turnovers from the feed, lines from odds.

The weekly tools are built for a season arriving a round at a time.
``import_turnovers.py`` only updates matches already in the season file, and
``import_oddsportal.py`` numbers rounds by counting back from the last one and
joins on exact dates. For a finished season there is something better to build
on: ``urc_season_scraper.py`` returns every played match, with the feed's own
dates and rounds, its scores and its turnover counts. So this takes that file
as the backbone and hangs the lines on it:

* **Fixtures, dates, rounds, scores, turnovers** - from the scraped season.
  The feed is the authority; its scores agreed with oddsportal's on all 151
  matches of 2025-26.
* **Lines** - inferred from oddsportal's 1X2 odds by ``spread_from_odds`` and
  marked ``inferred-1x2``, each quote matched to its fixture by club pair and
  nearest date.
* **Kept from the existing season file** - any line quoted as a line (blank
  ``line_source``), any opening line, and neutral-venue flags. A real handicap
  always beats an inferred one.

Existing turnover counts are **replaced** by the feed's, and every replaced
value is reported. That is deliberate: the season file must hold the same
statistic the live season is scraped with, or the turnover margin carried from
one season into the next compares two different things.

Run::

    python import_season.py entry/scraped/urc_202501_season.csv \\
        --odds odds_2025_26.txt --season 2025
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import import_oddsportal
import season_report
import spread_from_odds as sfo
import teams
from season_report import SEASON_COLUMNS

HERE = Path(__file__).parent
DATA_DIR = season_report.DATA_DIR
MATCH_DAYS = 4          # a quote belongs to a fixture of the same pair within this
QUOTE_COLUMNS = ["date", "round", "home", "away", "odds_home", "odds_draw", "odds_away"]
TURNOVERS = {           # season-file column -> the scraped column holding it
    "home_turnovers_conceded": "home_turnovers_lost",
    "away_turnovers_conceded": "away_turnovers_lost",
    "home_turnovers_won": "home_turnovers_won",
    "away_turnovers_won": "away_turnovers_won",
}


def nearest(frame: pd.DataFrame, home: str, away: str, when: pd.Timestamp):
    """The row of ``frame`` for this pairing closest to ``when``, if near enough."""
    same = frame[(frame["home"] == home) & (frame["away"] == away)]
    if same.empty:
        return None
    gap = (same["_date"] - when).abs()
    best = gap.idxmin()
    return best if gap[best] <= pd.Timedelta(days=MATCH_DAYS) else None


def build(scraped: pd.DataFrame, quotes: pd.DataFrame, existing: pd.DataFrame,
          sigma: float) -> tuple[pd.DataFrame, dict]:
    """The season file, and a record of what was matched, kept and replaced."""
    quotes = quotes.assign(_date=pd.to_datetime(quotes["date"]))
    existing = existing.assign(_date=pd.to_datetime(existing["date"])) \
        if not existing.empty else existing
    log = {"unpriced": [], "coarse": 0, "quoted_kept": 0, "replaced": [],
           "score_clash": [], "used_quotes": set(), "quotes": []}

    rows = []
    for r in scraped.itertuples(index=False):
        s = r._asdict()
        home, away = teams.canonical(s["Home_Team"]), teams.canonical(s["Away_Team"])
        when = pd.Timestamp(s["Date"])
        row = {c: "" for c in SEASON_COLUMNS}
        row.update(round=int(s["Round"]), date=when.strftime("%Y-%m-%d"),
                   home=home, away=away,
                   home_score=int(s["home_score"]), away_score=int(s["away_score"]))
        for ours, theirs in TURNOVERS.items():
            if pd.notna(s[theirs]):
                row[ours] = int(s[theirs])

        q = nearest(quotes, home, away, when)
        if q is None:
            log["unpriced"].append(f"{row['date']} {home} v {away}")
        else:
            log["used_quotes"].add(q)
            odds = quotes.loc[q, ["odds_home", "odds_draw", "odds_away"]].tolist()
            row["closing_line"] = round(sfo.line_from_odds(*odds, sigma) * 2) / 2
            row["line_source"] = season_report.LINE_INFERRED
            log["coarse"] += sfo.is_coarse(*odds, sigma)
            log["quotes"].append(dict(zip(QUOTE_COLUMNS, [row["date"], row["round"], home,
                                                          away, *odds])))

        e = nearest(existing, home, away, when) if not existing.empty else None
        if e is not None:
            old = existing.loc[e]
            if str(old.get("closing_line", "")).strip() and not str(old.get("line_source", "")).strip():
                row["closing_line"], row["line_source"] = old["closing_line"], ""
                log["quoted_kept"] += 1
            for col in ("opening_line", "neutral"):
                if str(old.get(col, "")).strip():
                    row[col] = old[col]
            for col in ("home_score", "away_score"):
                if str(old.get(col, "")).strip() and float(old[col]) != row[col]:
                    log["score_clash"].append(f"{row['date']} {home} v {away}: {col} "
                                              f"{old[col]} -> {row[col]}")
            for col in TURNOVERS:
                was = str(old.get(col, "")).strip()
                if was and float(was) != float(row[col]):
                    log["replaced"].append((row["date"], home, away, col, float(was), row[col]))
        rows.append(row)

    log["unused_quotes"] = len(quotes) - len(log["used_quotes"])
    out = (pd.DataFrame(rows, columns=SEASON_COLUMNS)
           .sort_values(["date", "round", "home"]).reset_index(drop=True))
    return out, log


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scraped", type=Path, help="urc_season_scraper.py output")
    ap.add_argument("--odds", type=Path, required=True, help="oddsportal results text")
    ap.add_argument("--season", type=int, required=True, help="season start year")
    ap.add_argument("--sigma", type=float, default=sfo.DEFAULT_SIGMA)
    args = ap.parse_args()

    scraped = pd.read_csv(args.scraped)
    scraped.columns = [c.replace(" ", "_") for c in scraped.columns]
    quotes = import_oddsportal.parse(args.odds.read_text(encoding="utf-8"))
    path = DATA_DIR / f"season_{args.season}.csv"
    existing = pd.read_csv(path, dtype=str).fillna("") if path.exists() else pd.DataFrame()

    season, log = build(scraped, quotes, existing, args.sigma)
    if path.exists():
        path.with_suffix(".csv.bak").write_bytes(path.read_bytes())
    season.to_csv(path, index=False)

    # Keep the raw quotes beside the entry sheets, as import_oddsportal does,
    # under the fixture's own date and round: line_check.py joins on them to
    # test inferred lines against real ones.
    quote_path = HERE / "entry" / f"urc_{args.season}_odds.csv"
    kept = pd.DataFrame(log["quotes"], columns=QUOTE_COLUMNS)
    if quote_path.exists():
        kept = (pd.concat([pd.read_csv(quote_path), kept])
                .drop_duplicates(subset=["date", "home", "away"], keep="last"))
    kept.sort_values(["date", "home"]).to_csv(quote_path, index=False)

    rounds = season.groupby("round").size()
    print(f"{len(season)} matches -> {path.relative_to(HERE)}  "
          f"(rounds {rounds.index.min()}-{rounds.index.max()})")
    priced = int((season["closing_line"].astype(str).str.strip() != "").sum())
    print(f"  lines: {priced} priced - {log['quoted_kept']} quoted kept, "
          f"{priced - log['quoted_kept']} inferred at sigma {args.sigma} "
          f"({log['coarse']} from quotes too coarse to pin, flagged)")
    if log["unpriced"]:
        print(f"  {len(log['unpriced'])} fixture(s) with no quote: "
              + "; ".join(log["unpriced"][:5]))
    if log["unused_quotes"]:
        print(f"  {log['unused_quotes']} quote(s) matched no fixture")
    if log["score_clash"]:
        print(f"  {len(log['score_clash'])} score(s) differ from the file's - the feed's "
              f"kept: " + "; ".join(log["score_clash"][:5]))
    if log["replaced"]:
        matches = len({r[:3] for r in log["replaced"]})
        print(f"  {len(log['replaced'])} turnover value(s) in {matches} match(es) replaced "
              f"by the feed's")


if __name__ == "__main__":
    main()
