"""Checks on ``urc_scraper.py``, runnable without reaching the live site.

The scraper cannot be tested against stats.unitedrugby.com from everywhere it
is developed, and the one thing nobody documents - where the team stats sit in
a match response - is exactly what it has to find. So these checks feed it the
layouts team stats are usually published in and assert it finds the same
numbers in each, and that it does not mistake a player's count for the team's.
Since the match centre moved to the URC site's own GraphQL API, they also run
it on that API's real replies for one match, kept in ``test_data/``.

If Streamlit is installed, the app itself is also run headless: once against
the real network (it must fail cleanly if the feed is unreachable) and once
against a faked feed, clicking through a whole round. The report viewer,
``app.py``, is run too. Run these under the oldest Streamlit you support as
well as the newest: the first bug found this way (``width="stretch"``) only
existed on older releases.

Run: ``python test_scraper.py``
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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

    print("\n3. every other stat on the page")
    row = s.match_row(LAYOUTS["paired list"], "292584")
    passed &= check("other stats come through as home_/away_ pairs",
                    row.get("home_tackles") == 150 and row.get("away_tackles") == 140)
    passed &= check("and qualified turnover stats are kept as extras",
                    row.get("home_ruck_turnovers_won") == 3)
    passed &= check("the turnover stats already used are not repeated",
                    "home_turnovers_conceded" not in row)
    row = s.match_row(LAYOUTS["per-team dict"], "292584")
    passed &= check("a player's stats never become team columns",
                    99 not in row.values())

    tricky = {"data": {"homeTeam": HOME, "awayTeam": AWAY, **META, "stats": [
        {"name": "Turnovers Won", "home": 7, "away": 5},
        {"name": "Turnovers Conceded", "home": 9, "away": 12},
        {"name": "Score", "home": 999, "away": 999},
        {"name": "Possession %", "home": "54%", "away": "46%"},
        {"name": "Tackles Made", "home": 150, "away": 140}]}}
    row = s.match_row(tricky, "1")
    passed &= check("a stat labelled 'Score' cannot overwrite the real score",
                    (row["home_score"], row["away_score"]) == (24, 17),
                    f"{row['home_score']}-{row['away_score']}")
    passed &= check("percentages parse, and are named as such",
                    row.get("home_possession_pct") == 54, 
                    str({k: v for k, v in row.items() if "possession" in k}))

    # The first real run produced home_date = 2026: the team objects carry a
    # date, and its leading digits were read as a stat.
    dated = {"data": {**META,
        "homeTeam": {**HOME, "date": "2026-09-25T18:45:00.000Z", "kickOff": "19:45",
                     "stats": {"turnoversWon": 7, "turnoversConceded": 9}},
        "awayTeam": {**AWAY, "date": "2026-09-25T18:45:00.000Z", "kickOff": "19:45",
                     "stats": {"turnoversWon": 5, "turnoversConceded": 12}}}}
    row = s.match_row(dated, "1")
    junk = [k for k in row if any(w in k for w in ("date", "kick_off")) and k != "Date"]
    passed &= check("dates and kick-off times are not read as stats", not junk, str(junk))
    passed &= check("a string is a number only when all of it is",
                    [s.number(v) for v in ("54%", "7 (54%)", "2026-09-25T18:45:00Z",
                                           "19:45", "150/12")] == [54, 7, None, None, None])

    a = s.match_row(LAYOUTS["paired list"], "1")
    b = s.match_row(tricky, "2")
    cols = s.table_columns([a, b])
    passed &= check("a round's columns: the report's first, then the union of stats",
                    cols[:len(s.COLUMNS)] == s.COLUMNS
                    and {"home_tackles", "home_tackles_made"} <= set(cols))

    # On 2 Nov 2026 the old feed began refusing outside requests, and the match
    # centre moved to the URC site's own GraphQL API.
    print("\n4. the site's GraphQL API, on its real replies")
    real = json.loads((HERE / "test_data" / "urc_graphql_292616.json").read_text())
    sent = []

    def site(url, **_):
        q = parse_qs(urlparse(url).query)
        sent.append((q["operationName"][0], q["variables"][0],
                     json.loads(q["extensions"][0])["persistedQuery"]["sha256Hash"]))
        return Reply({"data": real[q["operationName"][0]]})

    real_get = requests.get
    requests.get = site
    try:
        row = s.match_row(s.fetch_match("292616", "202601"), "292616")
        fixtures = s.fetch_fixtures("202601")
    finally:
        requests.get = real_get
    asked = {(op, var) for op, var, _ in sent}
    passed &= check("each query is sent as the page sends it: name, variables, hash",
                    asked == {("GetHomeTeamStatsQuery", '{"match_id":292616}'),
                              ("GetAwayTeamStatsQuery", '{"match_id":292616}'),
                              ("GetMatchEventsByTeamsQuery", '{"match_id":[292616]}'),
                              ("GetRoundsData", '{"seasonId":202601}')}
                    and all(h == s.QUERIES[op] for op, _, h in sent), str(sorted(asked)))
    got = (row["Home Team"], row["Away Team"], row["home_score"], row["away_score"],
           row["home_turnovers_lost"], row["away_turnovers_lost"],
           row["home_turnovers_won"], row["away_turnovers_won"])
    passed &= check("Connacht 5-50 Leinster, with both sides' turnovers",
                    got == ("Connacht Rugby", "Leinster Rugby", 5, 50, 18, 14, 8, 6), str(got))
    kicks = {k: (row[f"home_{k}"], row[f"away_{k}"])
             for k in ("tries", "conversion_goals", "missed_conversion_goals", "penalty_goals")}
    passed &= check("tries and kicks counted from the events, side by side",
                    kicks == {"tries": (1, 7), "conversion_goals": (0, 6),
                              "missed_conversion_goals": (1, 1), "penalty_goals": (0, 1)},
                    str(kicks))
    points = [5 * (row[f"{x}_tries"] - row[f"{x}_penalty_tries"]) + 7 * row[f"{x}_penalty_tries"]
              + 2 * row[f"{x}_conversion_goals"]
              + 3 * (row[f"{x}_penalty_goals"] + row[f"{x}_drop_goals_converted"])
              for x in ("home", "away")]
    passed &= check("and they add up to the score and to the team stats' points",
                    points == [row["home_score"], row["away_score"]]
                    == [row["home_points"], row["away_points"]], str(points))
    r5 = fixtures[fixtures["round"] == 5]
    passed &= check("the season's matches: round 5 played, the play-offs knockouts",
                    len(r5) == 8 and r5["status"].map(s.is_played).all()
                    and set(r5["round_type"]) == {"league"}
                    and set(fixtures.loc[fixtures["round"] > 18, "round_type"]) == {"knockout"})

    requests.get = lambda url, **_: Reply({"errors": [{"message": "PersistedQueryNotFound"}]})
    try:
        s.graphql("GetRoundsData", {"seasonId": 202601})
        said = ""
    except s.FeedError as exc:
        said = str(exc)
    finally:
        requests.get = real_get
    passed &= check("a query the site no longer knows says so, and what to do",
                    "PersistedQueryNotFound" in said and "HAR" in said, said[:70])

    print("\n5. when the site refuses")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        passed &= check("with no round saved, no ids are guessed",
                        s.next_match_ids("202601", out) == [])
        for first in (292608, 292584):
            pd.DataFrame({"match_id": range(first, first + 8)}).to_csv(
                out / f"urc_202601_{first}.csv", index=False)
        passed &= check("the next round's ids follow the last round saved",
                        s.next_match_ids("202601", out)
                        == [str(i) for i in range(292616, 292624)])
    requests.get = lambda url, **_: Refused()
    try:
        s.fetch_json(s.API)
        said = ""
    except requests.HTTPError as exc:
        said = str(exc)
    finally:
        requests.get = real_get
    passed &= check("a refusal shows the site's own reply, not just its status",
                    "400 Client Error" in said and "Unknown season" in said, said)
    return passed


class Reply:
    """A site answering 200 with a JSON body."""
    status_code = 200

    def __init__(self, body):
        self.body, self.text = body, json.dumps(body)

    def json(self):
        return self.body

    def raise_for_status(self):
        pass


class Refused:
    """A site that answers 400, with a reason in the body."""
    status_code, text = 400, '{"message": "Unknown season"}'

    def raise_for_status(self):
        raise requests.HTTPError("400 Client Error: Bad Request", response=self)


def import_turnovers_reads(csv: Path) -> bool:
    """The importer must take the real columns, not a lookalike extra stat."""
    import import_turnovers
    found = import_turnovers.find_columns(pd.read_csv(csv))
    return found == {"home_turnovers_conceded": "home_turnovers_lost",
                     "away_turnovers_conceded": "away_turnovers_lost",
                     "home_turnovers_won": "home_turnovers_won",
                     "away_turnovers_won": "away_turnovers_won"}


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
        print("\n6. the app - skipped (streamlit not installed)")
        return True

    passed = True
    tmp = Path(tempfile.mkdtemp())      # so the saved CSV lands here, not in entry/
    shutil.copy(HERE / "urc_scraper.py", tmp / "urc_scraper.py")
    script = str(tmp / "urc_scraper.py")
    real_get = requests.get
    try:
        print("\n6. the app, headless")
        try:
            real_get(s.API, timeout=5)
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
                     "status": "result", "home": h, "away": a, "scores": (20 + i, 15)}
                    for i, (h, a) in enumerate(clubs)]
        fixtures.append({"id": 292600, "date": "2026-10-02T18:45:00.000Z", "round": 2,
                         "status": "fixture", "home": "Cardiff Rugby", "away": "Zebre Parma",
                         "scores": (None, None)})
        short = 292591  # this match's team stats are missing the conceded count

        def teams(f: dict, score: str) -> dict:
            return {side: {"team": {"name": f[side[:4]]}, "score": {score: f["scores"][i]}}
                    for i, side in enumerate(("homeTeam", "awayTeam"))}

        def fake_get(url, **_):
            """The site's GraphQL API, answering the four queries the scraper sends."""
            q = parse_qs(urlparse(url).query)
            op, var = q["operationName"][0], json.loads(q["variables"][0])
            if op == "GetRoundsData":
                return Reply({"data": {"matchstats": [
                    {"match_id": f["id"], "match_status": f["status"],
                     "stats_data": {"dateTime": f["date"], "round": f["round"],
                                    **teams(f, "finalScore")}} for f in fixtures]}})
            mid = var["match_id"][0] if isinstance(var["match_id"], list) else var["match_id"]
            f = next(x for x in fixtures if x["id"] == mid)
            if op == "GetMatchEventsByTeamsQuery":
                return Reply({"data": {"matchstats": [{"match_status": f["status"], "stats_data": {
                    "dateTime": f["date"], **teams(f, "currentScore"),
                    "events": [{"display": "try", "team": {"name": f["home"]}}]}}]}})
            side = {"GetHomeTeamStatsQuery": "homeTeam", "GetAwayTeamStatsQuery": "awayTeam"}[op]
            attack = {"offload": 5, **({} if mid == short else {"totalTurnovers": 11})}
            return Reply({"data": {"matchstats": [{"stats_data": {side: {"teamStats": {
                "attack": attack,
                "defence": {"turnoverWon": 6, "totalSuccessfulTackles": 140}}}}}]}})

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
            passed &= check("with the report's columns first, then every stat",
                            list(got.columns[:len(s.COLUMNS)]) == s.COLUMNS
                            and "home_total_successful_tackles" in got.columns
                            and len(got) == 8)
            passed &= check("and import_turnovers.py reads the right columns from it",
                            import_turnovers_reads(saved[0]))
        passed &= check("both tables are drawn", len(at.dataframe) >= 3,
                        f"{len(at.dataframe)} tables")

        at = AppTest.from_file(script, default_timeout=60).run()
        at.radio[0].set_value("Paste match links").run()
        at.button[0].click().run()
        if clean(at, "paste mode fetches and displays"):
            passed &= check("paste mode reads the example link", bool(at.success)
                            and at.dataframe[0].value["match_id"].iloc[0] == "292584")

        import streamlit as st
        st.cache_data.clear()            # the fixture list above is cached
        requests.get = lambda url, **_: Refused()
        at = AppTest.from_file(script, default_timeout=60).run()
        ids = at.code[0].value.split() if at.code else []
        passed &= check("a refused fixture list shows the feed's reply, and the ids "
                        "after the last round saved, for paste mode",
                        not at.exception and bool(at.error)
                        and "Unknown season" in at.error[0].value
                        and ids == [str(i) for i in range(292592, 292600)],
                        f"ids {ids[:1]}..." if ids else "no ids shown")

        print("\n7. the report viewer (app.py), headless")
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
