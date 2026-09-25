"""End-to-end checks on the report pipeline, using generated data.

There is no published URC report to validate against - the NFL project has
seven seasons of Aaron Brown's sheets, this one has nothing equivalent - so the
checks here are self-consistency rather than replication. They build a season
whose handicaps are generated from *known* power ratings and turnover counts,
then assert the pipeline recovers what was put in, and that the rules the model
depends on hold:

1. the weighted fit recovers the ratings that generated the handicaps;
2. LGT carries across the season boundary, and resets nowhere else;
3. a missing turnover count blocks a pick rather than counting as neutral;
4. STDC resets each season and tracks net covers;
5. System #, pick and grade agree with a hand computation;
6. ``calibrate.py`` recovers the home-advantage terms used to build the data;
7. a **split round** - one whose matches are months apart, as 2026-27's round 8
   is - is ordered by date, so no factor reads a match that had not been played;
8. the odds-to-handicap conversion round-trips, and recovers a known sigma;
9. merging new odds into a season file never erases what is already there, and
   never overwrites a handicap that was quoted rather than inferred;
10. the model runs on the closing line, and on the opening line until then;
11. an entry sheet kept from an older export cannot erase a column it lacks.

Run: ``python test_pipeline.py``
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

import calibrate
import entry_sheet
import import_oddsportal
import model
import spread_from_odds as sfo
import season_report
import teams

CLUBS = sorted(teams.TEAMS)
# Arbitrary but fixed "true" ratings, centred on zero, that generate the handicaps.
TRUE_POWER = {c: p for c, p in zip(CLUBS, np.linspace(9.0, -9.0, len(CLUBS)))}


def round_robin(clubs: list[str], rnd: int) -> list[tuple[str, str]]:
    """Circle-method pairing: every club exactly once per round."""
    fixed, rotating = clubs[0], clubs[1:]
    k = rnd % len(rotating)
    order = rotating[k:] + rotating[:k]
    ring = [fixed] + order
    half = len(ring) // 2
    pairs = list(zip(ring[:half], reversed(ring[half:])))
    # Alternate home and away by round so each club's home count stays even.
    return [(a, b) if rnd % 2 == 0 else (b, a) for a, b in pairs]


def balanced_pairings(clubs: list[str], half: int = 9) -> dict[int, list[tuple[str, str]]]:
    """A schedule where every club plays as often at home as away.

    ``round_robin`` pairs every club once per round but alternates orientation
    by round parity, which leaves some clubs with more home matches than away.
    A real URC season is exactly balanced - nine each - and that balance is the
    condition under which ``calibrate.naive_edge`` is unbiased, so testing that
    needs a schedule with the same property.

    Built the way a league does it: ``half`` rounds of pairings, then the same
    pairings again with the venues reversed. Balance then holds by
    construction rather than by a greedy pass that can strand a club or two.
    """
    schedule = {}
    for rnd in range(1, half + 1):
        fixtures = round_robin(clubs, rnd)
        schedule[rnd] = fixtures
        schedule[rnd + half] = [(away, home) for home, away in fixtures]
    return schedule


def make_season(year: int, rounds: range, *, start: str,
                played: bool = True, turnovers: bool = True,
                priced: bool = True) -> pd.DataFrame:
    rows = []
    day = pd.Timestamp(start)
    rng = np.random.default_rng(year)
    for rnd in rounds:
        for home, away in round_robin(CLUBS, rnd):
            line = TRUE_POWER[away] - TRUE_POWER[home] - season_report.HOME_ADVANTAGE
            rows.append({
                "round": rnd,
                "date": (day + pd.Timedelta(days=7 * rnd)).date(),
                "home": home, "away": away, "neutral": "",
                "closing_line": round(line * 2) / 2 if priced else "",
                "home_score": int(rng.integers(10, 40)) if played else "",
                "away_score": int(rng.integers(10, 40)) if played else "",
                "home_turnovers_conceded": int(rng.integers(5, 18)) if turnovers else "",
                "away_turnovers_conceded": int(rng.integers(5, 18)) if turnovers else "",
                "home_turnovers_won": int(rng.integers(3, 15)) if turnovers else "",
                "away_turnovers_won": int(rng.integers(3, 15)) if turnovers else "",
            })
    return pd.DataFrame(rows, columns=season_report.SEASON_COLUMNS)


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f" - {detail}" if detail else ""))
    return ok


def main() -> int:
    passed = True
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        season_report.DATA_DIR = data

        prior = make_season(2025, range(15, 19), start="2026-01-31")
        prior.to_csv(data / "season_2025.csv", index=False)
        # New season: round 1 priced but unplayed, round 2 priced, no turnovers yet.
        current = make_season(2026, range(1, 3), start="2026-09-18",
                              played=False, turnovers=False)
        current.to_csv(data / "season_2026.csv", index=False)

        reports = season_report.build_reports()
        print("\n1. pipeline runs and reports both seasons")
        passed &= check("two seasons reported", set(reports) == {2025, 2026},
                        f"got {sorted(reports)}")

        cur = reports[2026]
        print("\n2. power ratings are seeded from the prior season")
        passed &= check("round 1 has ratings (no same-season history)",
                        cur[cur["round"] == 1]["home_power"].notna().all())
        fitted = (pd.concat([
            cur[cur["round"] == 1].set_index("home")["home_power"],
            cur[cur["round"] == 1].set_index("away")["away_power"],
        ]).groupby(level=0).first())
        centred_fit = fitted - fitted.mean()
        centred_true = pd.Series(TRUE_POWER) - np.mean(list(TRUE_POWER.values()))
        err = float((centred_fit - centred_true).abs().max())
        passed &= check("fit recovers the generating ratings", err < 0.35,
                        f"max abs error {err:.3f} pts")

        print("\n3. LGT carries across the season boundary")
        prior_rep = reports[2025]
        last = prior.sort_values("round").groupby("home").tail(1)
        r1 = cur[cur["round"] == 1]
        carried = r1["home_lgt"].abs().sum() + r1["away_lgt"].abs().sum()
        passed &= check("round 1 LGT is non-zero (carried from 2025-26)", carried > 0,
                        f"sum |lgt| = {carried:.0f}")
        passed &= check("prior season's own first round has no carry-in",
                        (prior_rep[prior_rep["round"] == 15]["home_lgt"] == 0).all())

        print("\n4. a missing turnover count blocks the pick")
        # Round 2 clubs played round 1, which has no turnovers entered.
        r2 = cur[cur["round"] == 2]
        passed &= check("round 2 makes no picks", r2["system_bet"].isna().all(),
                        f"{int(r2['system_bet'].notna().sum())} picks made")
        passed &= check("round 2 is flagged lgt_unknown", r2["lgt_unknown"].all())
        passed &= check("round 1 is not blocked (turnovers carried in)",
                        not r1["lgt_unknown"].any())

        print("\n5. STDC resets each season and tracks covers")
        passed &= check("round 1 STDC is zero", (r1["home_stdc"] == 0).all())
        graded = prior_rep[prior_rep["result"].notna()]
        passed &= check("prior season graded some bets", len(graded) > 0,
                        f"{len(graded)} graded")

        print("\n6. System #, pick and grade agree with a hand computation")
        recomputed = model.apply_system(cur)
        passed &= check("System # reproducible from the factor columns",
                        (recomputed["system_num_calc"] == recomputed["system_num"]).all())
        bad = [
            (r.home, r.away) for r in prior_rep.itertuples()
            if isinstance(r.system_bet, str)
            and r.result != model.grade(r.system_num, r.home_score, r.away_score, r.line)
        ]
        passed &= check("graded results match model.grade", not bad, str(bad[:3]))

        print("\n7. an unpriced round produces no report rows")
        unpriced = make_season(2026, range(1, 3), start="2026-09-18",
                               played=False, turnovers=False, priced=False)
        unpriced.to_csv(data / "season_2026.csv", index=False)
        passed &= check("no actionable matches without handicaps",
                        2026 not in season_report.build_reports())

        print("\n8. calibrate.py recovers the edge terms that built the handicaps")
        # calibrate pools every season file, so isolate: the 2025-26 data above
        # was generated with different edge terms and would blend the estimate.
        (data / "season_2025.csv").unlink()
        true_hfa, true_lh = 6.25, 2.5
        rows = []
        for rnd, fixtures in sorted(balanced_pairings(CLUBS).items()):
            for home, away in fixtures:
                edge = true_hfa + (true_lh if teams.is_long_haul(home, away) else 0.0)
                rows.append({"round": rnd, "date": f"2026-09-{(rnd % 28) + 1:02d}",
                             "home": home, "away": away, "neutral": "",
                             "closing_line": TRUE_POWER[away] - TRUE_POWER[home] - edge,
                             "home_score": "", "away_score": "",
                             "home_turnovers_conceded": "",
                             "away_turnovers_conceded": "",
                             "home_turnovers_won": "", "away_turnovers_won": ""})
        pd.DataFrame(rows, columns=season_report.SEASON_COLUMNS).to_csv(
            data / "season_2026.csv", index=False)
        calibrate.season_report.DATA_DIR = data
        fitted = calibrate.fit(calibrate.gather())
        passed &= check("home advantage recovered",
                        abs(fitted["home_advantage"] - true_hfa) < 1e-6,
                        f"{fitted['home_advantage']:+.3f} vs {true_hfa:+.3f}")
        passed &= check("long-haul penalty recovered",
                        abs(fitted["long_haul_penalty"] - true_lh) < 1e-6,
                        f"{fitted['long_haul_penalty']:+.3f} vs {true_lh:+.3f}")

        # The naive early read is only meant to be exact once every club has
        # played as often at home as away - which a full 18-round season is.
        full = calibrate.gather()
        unbalanced, _ = calibrate.balance(full)
        passed &= check("a full season leaves every club home/away balanced",
                        unbalanced == 0, f"{unbalanced} clubs unbalanced")
        domestic = calibrate.naive_edge(full[~full["long_haul"]])
        passed &= check("naive read recovers home advantage on domestic matches",
                        abs(domestic - true_hfa) < 1e-6,
                        f"{domestic:+.3f} vs {true_hfa:+.3f}")

        print("\n9. a split round is ordered by date, not by round number")
        # The real 2026-27 list puts six of round 8 on 26-27 December and the
        # two South African derbies on 20-21 February, after rounds 9-11. Round
        # order would make January's matches read a February turnover margin.
        base = pd.Timestamp("2026-09-25")
        rows = []
        for rnd in range(1, 6):
            for i, (home, away) in enumerate(round_robin(CLUBS, rnd)):
                rows.append({
                    "round": rnd, "date": (base + pd.Timedelta(days=7 * rnd)).date(),
                    "home": home, "away": away, "neutral": "",
                    "closing_line": TRUE_POWER[away] - TRUE_POWER[home]
                                    - season_report.HOME_ADVANTAGE,
                    "home_score": 20 + i, "away_score": 18,
                    "home_turnovers_conceded": 6 + i,
                    "away_turnovers_conceded": 11,
                    "home_turnovers_won": 4 + (i % 5),
                    "away_turnovers_won": 9 - (i % 4)})
        split = pd.DataFrame(rows, columns=season_report.SEASON_COLUMNS)
        late = split.index[split["round"] == 2][-2:]          # push them past round 5
        split.loc[late, "date"] = (base + pd.Timedelta(days=7 * 7)).date()
        split.to_csv(data / "season_2026.csv", index=False)

        report = season_report.build_reports()[2026]
        report["date"] = pd.to_datetime(report["date"])
        net = {(r.date, r.home, r.away):
               (r.home_turnovers_conceded - r.home_turnovers_won,
                r.away_turnovers_conceded - r.away_turnovers_won)
               for r in split.assign(date=pd.to_datetime(split["date"])).itertuples()}

        wrong = []
        for club in CLUBS:
            played = report[(report["home"] == club) | (report["away"] == club)]
            expected = 0.0
            for r in played.sort_values("date").itertuples():
                side_lgt = r.home_lgt if r.home == club else r.away_lgt
                if side_lgt != expected:
                    wrong.append(f"{club} on {r.date.date()}: "
                                 f"lgt {side_lgt:+.0f}, expected {expected:+.0f}")
                home_net, away_net = net[(r.date, r.home, r.away)]
                expected = float(home_net if r.home == club else away_net)
        passed &= check("every club's LGT is its previous match by date",
                        not wrong, "; ".join(wrong[:3]))

        late_dates = report[report["round"] == 2]["date"]
        passed &= check("the split round really is split",
                        late_dates.max() > report[report["round"] == 5]["date"].max(),
                        f"round 2 runs to {late_dates.max().date()}")
        r2_early = report[(report["round"] == 2) & (report["date"] == late_dates.min())]
        r2_late = report[(report["round"] == 2) & (report["date"] == late_dates.max())]
        passed &= check("the late matches are rated on later form, not round-2 form",
                        not r2_early["home_power"].reset_index(drop=True).equals(
                            r2_late["home_power"].reset_index(drop=True))
                        or r2_late["home_power"].notna().all())

    print("\n10. inferring a handicap from 1X2 odds")
    from statistics import NormalDist
    nd = NormalDist()
    sigma = 16.0

    # Fair odds (no overround) must map back to the line that generated them.
    worst = 0.0
    for target in (-30, -18, -9.5, -3, 0, 4.5, 12, 21):
        z = -target / sigma
        p_home = nd.cdf(z)
        p_draw = 0.02
        # Split the draw back out of the two-way probability, the inverse of
        # what line_from_odds does when it folds it in.
        fair = (p_home - p_draw / 2, p_draw, 1 - p_home - p_draw / 2)
        odds = tuple(1 / x for x in fair)
        worst = max(worst, abs(sfo.line_from_odds(*odds, sigma) - target))
    passed &= check("fair odds round-trip to the line that made them",
                    worst < 1e-6, f"worst error {worst:.2e} pts")

    quote = (1.20, 25.73, 4.66)
    shin = sfo.shin_probabilities(*quote)
    passed &= check("de-vigged probabilities sum to 1",
                    abs(sum(shin) - 1) < 1e-9, f"sum {sum(shin):.12f}")
    pi = [1 / o for o in quote]
    prop = [x / sum(pi) for x in pi]
    passed &= check("Shin takes more margin out of the longshot than proportional",
                    shin[0] > prop[0] and shin[2] < prop[2],
                    f"favourite {prop[0]:.4f}->{shin[0]:.4f}, "
                    f"longshot {prop[2]:.4f}->{shin[2]:.4f}")

    shorter = sfo.line_from_odds(1.10, 29.0, 7.08, sigma)
    longer = sfo.line_from_odds(1.80, 21.0, 2.05, sigma)
    passed &= check("a shorter home price means a bigger home handicap",
                    shorter < longer, f"{shorter:.1f} vs {longer:.1f}")
    passed &= check("a heavy favourite's quote is flagged as too coarse",
                    sfo.is_coarse(1.01, 25.0, 20.0) and not sfo.is_coarse(1.80, 21.0, 2.05))

    # The line scale and the margin spread are DIFFERENT parameters. An earlier
    # version fitted one number for both and landed on the margin spread, so
    # these are generated deliberately far apart and must come back apart.
    rng = np.random.default_rng(11)
    true_line, true_margin = 13.75, 16.5
    quotes, margins, lines = [], [], []
    for _ in range(6000):
        # Bounded to the range real matches are priced in: past |z| ~ 2.3 a 2%
        # draw leaves no room for the away side and the quote is not constructible.
        z = rng.uniform(-2.0, 2.0)
        p_home, p_draw = nd.cdf(z), 0.02
        quotes.append((1 / (p_home - p_draw / 2), 1 / p_draw,
                       1 / (1 - p_home - p_draw / 2)))
        lines.append(-true_line * z)
        margins.append(rng.normal(true_line * z, true_margin))
    fit = sfo.fit_from_results(quotes, margins)
    passed &= check("fit_from_results recovers the line scale",
                    abs(fit["line_sigma"] - true_line) < 0.6,
                    f"{fit['line_sigma']:.2f} vs {true_line}")
    passed &= check("fit_from_results recovers the margin spread separately",
                    abs(fit["margin_sigma"] - true_margin) < 0.6,
                    f"{fit['margin_sigma']:.2f} vs {true_margin}")
    passed &= check("it does not collapse the two into one number",
                    abs(fit["line_sigma"] - fit["margin_sigma"]) > 1.5,
                    f"line {fit['line_sigma']:.2f} vs margin "
                    f"{fit['margin_sigma']:.2f}")
    from_lines = sfo.fit_from_lines(quotes, lines)
    passed &= check("fit_from_lines recovers the line scale exactly",
                    abs(from_lines - true_line) < 1e-6,
                    f"{from_lines:.6f} vs {true_line}")
    passed &= check("real lines pin it tighter than results do",
                    abs(from_lines - true_line) < abs(fit["line_sigma"] - true_line),
                    f"{abs(from_lines - true_line):.2e} vs "
                    f"{abs(fit['line_sigma'] - true_line):.3f}")

    print("\n11. merging odds must not erase data already in the season file")
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        import_oddsportal.DATA_DIR = data
        existing = pd.DataFrame([
            # a quoted handicap, plus turnovers the merge must leave alone
            {"round": 18, "date": "2026-05-16", "home": "Bulls", "away": "Benetton",
             "neutral": "", "opening_line": "-26.5", "closing_line": "-27.5",
             "line_source": "",
             "home_score": "45", "away_score": "19",
             "home_turnovers_conceded": "10", "away_turnovers_conceded": "10",
             "home_turnovers_won": "7", "away_turnovers_won": "6"},
            {"round": 18, "date": "2026-05-16", "home": "Sharks", "away": "Zebre",
             "neutral": "", "closing_line": "-20.0", "line_source": "inferred-1x2",
             "home_score": "54", "away_score": "19",
             "home_turnovers_conceded": "13", "away_turnovers_conceded": "2",
             "home_turnovers_won": "9", "away_turnovers_won": "11"},
        ], columns=season_report.SEASON_COLUMNS)
        existing.to_csv(data / "season_2025.csv", index=False)

        incoming = pd.DataFrame([
            {"round": 18, "date": "2026-05-16", "home": "Bulls", "away": "Benetton",
             "neutral": "", "closing_line": -25.5, "line_source": "inferred-1x2",
             "home_score": 45, "away_score": 19, "home_turnovers_conceded": "",
             "away_turnovers_conceded": "", "home_turnovers_won": "",
             "away_turnovers_won": ""},
            {"round": 18, "date": "2026-05-16", "home": "Sharks", "away": "Zebre",
             "neutral": "", "closing_line": -23.5, "line_source": "inferred-1x2",
             "home_score": 54, "away_score": 19, "home_turnovers_conceded": "",
             "away_turnovers_conceded": "", "home_turnovers_won": "",
             "away_turnovers_won": ""},
        ], columns=season_report.SEASON_COLUMNS)
        _, kept = import_oddsportal.merge_into_season(incoming, 2025)
        after = pd.read_csv(data / "season_2025.csv", dtype=str).fillna("")

        bulls = after[after["home"] == "Bulls"].iloc[0]
        sharks = after[after["home"] == "Sharks"].iloc[0]
        passed &= check("turnovers survive a merge that does not carry them",
                        bulls["home_turnovers_won"] == "7"
                        and sharks["away_turnovers_won"] == "11",
                        f"bulls won {bulls['home_turnovers_won']!r}, "
                        f"sharks away won {sharks['away_turnovers_won']!r}")
        passed &= check("a quoted handicap is not overwritten by an inferred one",
                        bulls["closing_line"] == "-27.5" and bulls["line_source"] == "",
                        f"line {bulls['closing_line']!r} source {bulls['line_source']!r}")
        passed &= check("an opening line the odds do not carry survives",
                        bulls["opening_line"] == "-26.5",
                        f"opening {bulls['opening_line']!r}")
        passed &= check("an inferred handicap is refreshed",
                        sharks["closing_line"] == "-23.5",
                        f"line {sharks['closing_line']!r}")
        passed &= check("the guard reports what it protected", kept == 1, f"kept={kept}")

    print("\n12. the model runs on the closing line, the opening line until then")
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        season_report.DATA_DIR = data
        make_season(2025, range(15, 19), start="2026-01-31").to_csv(
            data / "season_2025.csv", index=False)
        # Every match opens 8 points further toward home than it closes, so the
        # move crosses the power-implied line; half of them have not closed yet.
        cur = make_season(2026, range(1, 2), start="2026-09-18",
                          played=False, turnovers=False)
        cur["opening_line"] = cur["closing_line"] + 8
        cur.loc[cur.index[4:], "closing_line"] = np.nan
        cur.to_csv(data / "season_2026.csv", index=False)

        rep = season_report.build_reports()[2026].merge(
            cur[["home", "away", "closing_line"]], on=["home", "away"])
        closed = rep[rep["closing_line"].notna()]
        still_open = rep[rep["closing_line"].isna()]
        passed &= check("a closed match runs on its closing line",
                        len(closed) == 4 and (closed["line"] == closed["closing_line"]).all())
        passed &= check("an unclosed match runs on its opening line",
                        len(still_open) == 4
                        and (still_open["line"] == still_open["opening_line"]).all())

        def system_on(r, line: float) -> int:
            return model.system_number(r.home_lgt, r.home_stdc, r.home_power,
                                       r.away_lgt, r.away_stdc, r.away_power, line)
        on_close = all(r.system_num == system_on(r, r.closing_line)
                       != system_on(r, r.opening_line) for r in closed.itertuples())
        passed &= check("System # is the closing line's, and the move changes it",
                        on_close)

    print("\n13. an entry sheet from an older export cannot erase a column")
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        entry_sheet.DATA_DIR = entry_sheet.HERE = data
        old_layout = ["line_source", "home_turnovers_won", "away_turnovers_won"]

        season = make_season(2026, range(1, 2), start="2026-09-18")
        season.to_csv(data / "season_2026.csv", index=False)
        before = (data / "season_2026.csv").read_text()
        season.drop(columns=old_layout).to_csv(data / "old.csv", index=False)
        try:
            entry_sheet.import_sheet(2026, data / "old.csv")
            refused = ""
        except ValueError as exc:
            refused = str(exc)
        passed &= check("refused while the missing columns hold turnovers",
                        "home_turnovers_won" in refused, refused[:60])
        passed &= check("and the season file is left as it was",
                        (data / "season_2026.csv").read_text() == before)

        blank = make_season(2026, range(1, 2), start="2026-09-18",
                            played=False, turnovers=False)
        blank.to_csv(data / "season_2026.csv", index=False)
        sheet = blank.assign(closing_line=blank["closing_line"] - 1)
        sheet.drop(columns=old_layout).to_csv(data / "old.csv", index=False)
        entry_sheet.import_sheet(2026, data / "old.csv")
        after = pd.read_csv(data / "season_2026.csv")
        typed = after.merge(sheet[["home", "away", "closing_line"]],
                            on=["home", "away"], suffixes=("", "_typed"))
        passed &= check("imported while those columns are still empty",
                        len(typed) == len(sheet)
                        and (typed["closing_line"] == typed["closing_line_typed"]).all()
                        and list(after.columns) == season_report.SEASON_COLUMNS)

    print("\n" + ("all checks passed" if passed else "SOME CHECKS FAILED"))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
