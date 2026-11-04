"""Checks on ``urc_season_scraper.py``, runnable without reaching the live site.

The stat-finding it borrows from ``urc_scraper`` is tested in
``test_scraper.py``; these cover only what the season scraper adds - playoff
round numbering, the retry, and the whole-season app flow, run headless against
a faked site: a season's played matches fetched in one click, one flaky match
recovered by the retry, one dead match reported, the results surviving a rerun,
and a second click fetching only what failed.

Run: ``python test_season_scraper.py``
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import requests

import urc_scraper as base
import urc_season_scraper as season

HERE = Path(__file__).parent


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f" - {detail}" if detail else ""))
    return ok


CLUBS = [("Leinster Rugby", "Munster Rugby"), ("Ulster Rugby", "Connacht Rugby"),
         ("Glasgow Warriors", "Edinburgh Rugby"), ("Cardiff Rugby", "Ospreys"),
         ("Scarlets", "Dragons RFC"), ("Benetton Rugby", "Zebre Parma"),
         ("Vodacom Bulls", "Emirates Lions"), ("DHL Stormers", "Hollywoodbets Sharks")]


def fake_season() -> list[dict]:
    """Two regular rounds, the three playoff stages, and one unplayed fixture."""
    out, mid = [], 290000
    def add(date, rnd, home, away, status="result"):
        nonlocal mid
        mid += 1
        out.append({"id": mid, "date": f"{date}T15:00:00.000Z", "round": rnd,
                    "status": status, "home": home, "away": away, "scores": (24, 17)})
    for rnd, day in ((1, "2025-09-27"), (2, "2025-10-04")):
        for home, away in CLUBS:
            add(day, rnd, home, away)
    # The site numbers the play-off stages 19, 20 and 21; the quarter-finals
    # fall on a Friday and a Saturday, one week.
    for i, (home, away) in enumerate(CLUBS[:4]):
        add("2026-05-29" if i == 0 else "2026-05-30", 19, home, away)
    add("2026-06-06", 20, "Leinster Rugby", "Glasgow Warriors")
    add("2026-06-06", 20, "Vodacom Bulls", "DHL Stormers")
    add("2026-06-19", 21, "Leinster Rugby", "Vodacom Bulls")
    add("2025-10-11", 3, "Leinster Rugby", "Ulster Rugby", status="fixture")
    return out


class Reply:
    """A site answering 200 with a JSON body."""
    status_code = 200

    def __init__(self, body):
        self.body, self.text = body, json.dumps(body)

    def json(self):
        return self.body

    def raise_for_status(self):
        pass


def pure_checks() -> bool:
    passed = True
    print("\n1. playoff rounds, by the week each stage is played")
    fx = pd.DataFrame([{"match_id": str(m["id"]), "date": m["date"][:10], "round": m["round"],
                        "round_type": ("knockout" if m["round"] > base.REGULAR_ROUNDS
                                       else "league")}
                       for m in fake_season()])
    fx["report_round"] = season.report_rounds(fx)
    ko = fx[fx["round_type"] == "knockout"].groupby("report_round").size().to_dict()
    passed &= check("quarter-finals over two days are one round, then semis, then final",
                    ko == {19: 4, 20: 2, 21: 1}, str(ko))
    league = fx[fx["round_type"] == "league"]
    passed &= check("regular-season matches keep the feed's round",
                    (league["report_round"] == league["round"]).all())

    print("\n2. a failed request is retried once")
    season.RETRY_WAIT = 0
    calls = []
    def flaky(match_id, s):
        calls.append(match_id)
        if len(calls) == 1:
            raise requests.ConnectionError("blip")
        return {"data": {}}
    passed &= check("recovered on the second try",
                    season.fetch_with_retry(flaky, "1", "202501") == {"data": {}}
                    and len(calls) == 2)
    def dead(match_id, s):
        raise requests.ConnectionError("down")
    try:
        season.fetch_with_retry(dead, "1", "202501")
        passed &= check("still failing after the retry is raised", False)
    except requests.RequestException:
        passed &= check("still failing after the retry is raised", True)
    return passed


def app_checks() -> bool:
    try:
        from streamlit.testing.v1 import AppTest
    except ImportError:
        print("\n3. the app - skipped (streamlit not installed)")
        return True

    passed = True
    fixtures = fake_season()
    flaky_id, dead_id = str(fixtures[3]["id"]), str(fixtures[5]["id"])
    detail_calls: dict[str, int] = {}

    def teams(f: dict, score: str) -> dict:
        return {side: {"team": {"name": f[side[:4]]}, "score": {score: f["scores"][i]}}
                for i, side in enumerate(("homeTeam", "awayTeam"))}

    def fake_get(url, **_):
        """The site's GraphQL API: the season's matches, and each match's replies."""
        q = parse_qs(urlparse(url).query)
        op, var = q["operationName"][0], json.loads(q["variables"][0])
        if op == "GetRoundsData":
            return Reply({"data": {"matchstats": [
                {"match_id": f["id"], "match_status": f["status"],
                 "stats_data": {"dateTime": f["date"], "round": f["round"],
                                **teams(f, "finalScore")}} for f in fixtures]}})
        mid = str(var["match_id"][0] if isinstance(var["match_id"], list) else var["match_id"])
        f = next(x for x in fixtures if str(x["id"]) == mid)
        if op == "GetHomeTeamStatsQuery":        # the first of a match's three requests
            detail_calls[mid] = detail_calls.get(mid, 0) + 1
            if mid == dead_id or (mid == flaky_id and detail_calls[mid] == 1):
                raise requests.ConnectionError(f"no response for {mid}")
        if op == "GetMatchEventsByTeamsQuery":
            return Reply({"data": {"matchstats": [{"match_status": f["status"], "stats_data": {
                "dateTime": f["date"], **teams(f, "currentScore"), "events": []}}]}})
        home = op == "GetHomeTeamStatsQuery"
        return Reply({"data": {"matchstats": [{"stats_data": {
            "homeTeam" if home else "awayTeam": {"teamStats": {
                "attack": {"totalTurnovers": 9 if home else 11},
                "defence": {"turnoverWon": 6 if home else 4,
                            "totalSuccessfulTackles": 150 if home else 140}}}}}]}})

    real_get, real_out = requests.get, base.OUT
    out = Path(tempfile.mkdtemp())
    script = str(HERE / "urc_season_scraper.py")
    try:
        # The app imports urc_scraper, the same module object as here, so its
        # CSV lands wherever base.OUT points - a temp folder, not entry/.
        base.OUT = out
        season.RETRY_WAIT = 0
        print("\n3. the app, headless")
        try:
            real_get(base.API, timeout=5)
            reachable = True
        except requests.RequestException:
            reachable = False
        if not reachable:
            at = AppTest.from_file(script, default_timeout=120).run()
            passed &= check("an unreachable feed shows an error, not a traceback",
                            not at.exception and bool(at.error))

        requests.get = fake_get
        at = AppTest.from_file(script, default_timeout=120).run()
        if at.exception:
            return check("the season page renders", False, at.exception[0].value[:90])
        metrics = {m.label: m.value for m in at.metric}
        passed &= check("counts the season: 23 played, 16 regular, 7 playoff, 1 not played",
                        metrics == {"Played": "23", "Regular season": "16",
                                    "Playoffs": "7", "Not played": "1"}, str(metrics))
        passed &= check("offers one button for the whole season",
                        at.button[0].label.startswith("Fetch all 23 played matches"),
                        at.button[0].label)

        at.button[0].click().run()
        if at.exception:
            return check("the whole season fetches", False, at.exception[0].value[:90])
        passed &= check("a flaky match is recovered by the retry",
                        detail_calls.get(flaky_id) == 2)
        passed &= check("a dead match is reported, not fatal",
                        any("could not be fetched" in w.value for w in at.warning))

        saved = out / "urc_202501_season.csv"
        got = pd.read_csv(saved) if saved.exists() else pd.DataFrame()
        passed &= check("the season is saved, one row per fetched match",
                        len(got) == 22, f"{len(got)} rows")
        if len(got):
            passed &= check("with the report's columns first, then stage and every stat",
                            list(got.columns[:len(base.COLUMNS) + 2])
                            == base.COLUMNS + ["stage", "feed_round"]
                            and "home_total_successful_tackles" in got.columns)
            playoff = got[got["stage"] == "playoff"].groupby("Round").size().to_dict()
            passed &= check("playoffs numbered 19, 20, 21 in the file",
                            playoff == {19: 4, 20: 2, 21: 1}, str(playoff))
            import import_turnovers
            passed &= check("and import_turnovers.py reads the right columns from it",
                            import_turnovers.find_columns(got)["home_turnovers_won"]
                            == "home_turnovers_won")

        tables = len(at.dataframe)
        at.run()                      # what a click on Download does: a rerun
        passed &= check("results survive a rerun", not at.exception
                        and len(at.dataframe) == tables, f"{len(at.dataframe)} tables")

        before = dict(detail_calls)
        at.button[0].click().run()    # a second Fetch
        fetched_again = {k for k in detail_calls if detail_calls[k] != before.get(k)}
        passed &= check("fetching again retries only the failed match",
                        fetched_again == {dead_id}, str(sorted(fetched_again)))
    finally:
        requests.get, base.OUT = real_get, real_out
    return passed


def main() -> int:
    passed = pure_checks() & app_checks()
    print("\n" + ("all checks passed" if passed else "SOME CHECKS FAILED"))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
