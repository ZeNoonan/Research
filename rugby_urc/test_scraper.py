"""Checks on ``urc_scraper.py``, runnable without reaching the live feed.

The scraper cannot be tested against stats.unitedrugby.com from everywhere it
is developed, and the one thing nobody documents - where the team stats sit in
a match response - is exactly what it has to find. So these checks feed it the
layouts team stats are usually published in and assert it finds the same
numbers in each, and that it does not mistake a player's count for the team's.

If Streamlit is installed, the app itself is also run headless: once against
the real network (it must fail cleanly if the feed is unreachable) and once
against a faked feed, clicking through a whole round. The report viewer,
``app.py``, is run too. Run these under the oldest Streamlit you support as
well as the newest: the first bug found this way (``width="stretch"``) only
existed on older releases.

Run: ``python test_scraper.py``
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import requests

import urc_scraper as s

HERE = Path(__file__).parent


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f" - {detail}" if detail else ""))
    return ok


HOME = {"id": 11, "name": "Benetton Rugby", "score": 24}
AWAY = {"id": 22, "name": "Dragons RFC", "score": 17}
# A player carrying the same stat names as the team, with an impossible value.
TRAP = [{"name": "A Player", "positionId": 7,
         "stats": {"turnoversWon": 99, "turnoversConceded": 99}}]
META = {"date": "2026-09-25T18:45:00.000Z", "round": 1, "status": "Result"}

LAYOUTS = {
    "paired list": {"data": {
        "homeTeam": {**HOME, "players": TRAP}, "awayTeam": {**AWAY, "players": TRAP},
        **META, "stats": [
            {"name": "Turnovers Won", "home": 7, "away": 5},
            {"name": "Ruck Turnovers Won", "home": 3, "away": 2},
            {"name": "Turnovers Conceded", "home": "9", "away": "12"},
            {"name": "Tackles", "home": 150, "away": 140}]}},
    "per-team dict": {"data": {
        "homeTeam": {**HOME, "players": TRAP,
                     "stats": {"turnoversWon": 7, "turnoversConceded": 9}},
        "awayTeam": {**AWAY, "players": TRAP,
                     "stats": {"turnoversWon": 5, "turnoversConceded": 12}}, **META}},
    "per-team list": {"data": {
        "homeTeam": {**HOME, "stats": [{"label": "Turnovers Won", "value": "7"},
                                       {"label": "Turnovers Lost", "value": "9 (43%)"}]},
        "awayTeam": {**AWAY, "stats": [{"label": "Turnovers Won", "value": "5"},
                                       {"label": "Turnovers Lost", "value": "12"}]},
        **META}},
    "keyed home/away": {"data": {
        "homeTeam": HOME, "awayTeam": AWAY, **META,
        "teamStats": {"turnoversWon": {"home": 7, "away": 5},
                      "turnoversConceded": {"home": 9, "away": 12}}}},
}
WANT = {"home_turnovers_won": 7, "away_turnovers_won": 5,
        "home_turnovers_lost": 9, "away_turnovers_lost": 12}


def pure_checks() -> bool:
    passed = True
    print("\n1. reading a match-centre link")
    link = ("https://stats.unitedrugby.com/match-centre/202601/united-rugby-championship/"
            "benetton-rugby-vs-dragons-rfc-2026-09-25/292584#tabs-stats")
    passed &= check("the link from the match centre", s.parse_match_url(link) == ("202601", "292584"))
    passed &= check("without the #tabs-stats anchor",
                    s.parse_match_url(link.split("#")[0]) == ("202601", "292584"))
    passed &= check("a bare match id takes the season given",
                    s.parse_match_url("291999", "202501") == ("202501", "291999"))
    try:
        s.parse_match_url("https://example.com/not-a-match")
        passed &= check("a non-match link is rejected", False)
    except ValueError:
        passed &= check("a non-match link is rejected", True)

    print("\n2. finding turnovers wherever the feed keeps them")
    for name, body in LAYOUTS.items():
        row = s.match_row(body, "292584")
        got = {k: row[k] for k in WANT}
        passed &= check(f"{name}", got == WANT and s.complete(row),
                        f"won {got['home_turnovers_won']}/{got['away_turnovers_won']}, "
                        f"lost {got['home_turnovers_lost']}/{got['away_turnovers_lost']}")

    row = s.match_row(LAYOUTS["per-team dict"], "292584")
    passed &= check("a player's count is never taken for the team's",
                    99 not in {row[k] for k in WANT})
    row = s.match_row(LAYOUTS["paired list"], "292584")
    passed &= check("plain 'Turnovers Won' beats 'Ruck Turnovers Won'",
                    row["home_turnovers_won"] == 7, f"found as {row['found_as']!r}")
    passed &= check("score and teams come through",
                    (row["Home Team"], row["home_score"], row["away_score"])
                    == ("Benetton Rugby", 24, 17))

    bare = {"data": {"homeTeam": HOME, "awayTeam": AWAY, **META,
                     "stats": [{"name": "Turnovers", "home": 8, "away": 6}]}}
    row = s.match_row(bare, "1")
    passed &= check("a bare 'Turnovers' is not guessed as won or conceded",
                    not s.complete(row) and row["home_turnovers_won"] is None)

    frame = pd.DataFrame([{**WANT, "away_turnovers_lost": None}])
    passed &= check("a count missing after a DataFrame round-trip is caught",
                    not s.complete(frame.iloc[0].to_dict()))
    return passed


def clean(at, label: str) -> bool:
    """PASS when a run raised nothing; otherwise FAIL with the app's own error.

    Checks after a failed run would only index into elements that were never
    drawn, so callers stop there instead of crashing the suite.
    """
    errors = [e.value for e in at.exception]
    return check(label, not errors, errors[0][:90] if errors else "")


def app_checks() -> bool:
    try:
        from streamlit.testing.v1 import AppTest
    except ImportError:
        print("\n3. the app - skipped (streamlit not installed)")
        return True

    passed = True
    tmp = Path(tempfile.mkdtemp())      # so the saved CSV lands here, not in entry/
    shutil.copy(HERE / "urc_scraper.py", tmp / "urc_scraper.py")
    script = str(tmp / "urc_scraper.py")
    real_get = requests.get
    try:
        print("\n3. the app, headless")
        try:
            real_get(s.FEED, timeout=5)
            reachable = True
        except requests.RequestException:
            reachable = False
        if not reachable:
            at = AppTest.from_file(script, default_timeout=60).run()
            passed &= check("an unreachable feed shows an error, not a traceback",
                            not at.exception and bool(at.error))

        clubs = [("Benetton Rugby", "Dragons RFC"), ("Connacht Rugby", "DHL Stormers"),
                 ("Ulster Rugby", "Edinburgh Rugby"), ("Emirates Lions", "Leinster Rugby"),
                 ("Munster Rugby", "Glasgow Warriors"), ("Scarlets", "Cardiff Rugby"),
                 ("Hollywoodbets Sharks", "Ospreys"), ("Zebre Parma", "Vodacom Bulls")]
        fixtures = [{"id": 292584 + i, "date": "2026-09-26T15:00:00.000Z", "round": 1,
                     "roundTypeId": 1, "status": "Result",
                     "homeTeam": {"name": h, "score": 20 + i}, "awayTeam": {"name": a, "score": 15}}
                    for i, (h, a) in enumerate(clubs)]
        fixtures.append({"id": 292600, "date": "2026-10-02T18:45:00.000Z", "round": 2,
                         "roundTypeId": 1, "status": "Fixture",
                         "homeTeam": {"name": "Cardiff Rugby"}, "awayTeam": {"name": "Zebre Parma"}})
        short = 292591  # this match's feed is missing the conceded stat

        class Response:
            def __init__(self, body):
                self.body, self.status_code = body, 200
            def json(self):
                return self.body
            def raise_for_status(self):
                pass

        def fake_get(url, **_):
            if m := re.search(r"/matches/(\d+)\?", url):
                f = next(x for x in fixtures if x["id"] == int(m.group(1)))
                stats = [{"name": "Turnovers Won", "home": 6, "away": 4},
                         {"name": "Turnovers Conceded", "home": 9, "away": 11}]
                return Response({"data": {**f, "stats": stats[:1] if f["id"] == short else stats}})
            if "/matches?" in url:
                return Response({"data": fixtures})
            raise AssertionError(url)

        requests.get = fake_get
        at = AppTest.from_file(script, default_timeout=60).run()
        if not clean(at, "the round page renders"):
            return False
        passed &= check("defaults to the latest played round", at.selectbox[0].value == 1)
        passed &= check("offers only the played matches",
                        at.button[0].label == "Fetch stats for 8 match(es)", at.button[0].label)
        at.button[0].click().run()
        if not clean(at, "a whole round fetches and displays"):
            return False
        home, away = clubs[short - fixtures[0]["id"]]
        passed &= check("a match missing a stat is called out by name",
                        bool(at.warning) and f"{home} v {away}" in at.warning[0].value,
                        at.warning[0].value[:60] if at.warning else "no warning")
        saved = list((tmp / "entry" / "scraped").glob("urc_202601_round01.csv"))
        passed &= check("the round is saved for import_turnovers.py", len(saved) == 1)
        if saved:
            got = pd.read_csv(saved[0])
            passed &= check("in the columns import_turnovers.py reads",
                            list(got.columns) == s.COLUMNS and len(got) == 8)

        at = AppTest.from_file(script, default_timeout=60).run()
        at.radio[0].set_value("Paste match links").run()
        at.button[0].click().run()
        if clean(at, "paste mode fetches and displays"):
            passed &= check("paste mode reads the example link", bool(at.success)
                            and at.dataframe[0].value["match_id"].iloc[0] == "292584")

        print("\n4. the report viewer (app.py), headless")
        requests.get = real_get
        at = AppTest.from_file(str(HERE / "app.py"), default_timeout=60).run()
        if clean(at, "app.py renders"):
            passed &= check("with its tables drawn", len(at.dataframe) >= 1,
                            f"{len(at.dataframe)} table(s)")
    finally:
        requests.get = real_get
        shutil.rmtree(tmp, ignore_errors=True)
    return passed


def main() -> int:
    passed = pure_checks() & app_checks()
    print("\n" + ("all checks passed" if passed else "SOME CHECKS FAILED"))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
