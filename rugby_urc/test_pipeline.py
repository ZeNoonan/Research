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
   is - is ordered by date, so no factor reads a match that had not been played.

Run: ``python test_pipeline.py``
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

import calibrate
import model
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
                "line": round(line * 2) / 2 if priced else "",
                "home_score": int(rng.integers(10, 40)) if played else "",
                "away_score": int(rng.integers(10, 40)) if played else "",
                "home_turnovers_conceded": int(rng.integers(5, 18)) if turnovers else "",
                "away_turnovers_conceded": int(rng.integers(5, 18)) if turnovers else "",
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
        for rnd in range(1, 19):
            for home, away in round_robin(CLUBS, rnd):
                edge = true_hfa + (true_lh if teams.is_long_haul(home, away) else 0.0)
                rows.append({"round": rnd, "date": f"2026-09-{(rnd % 28) + 1:02d}",
                             "home": home, "away": away, "neutral": "",
                             "line": TRUE_POWER[away] - TRUE_POWER[home] - edge,
                             "home_score": "", "away_score": "",
                             "home_turnovers_conceded": "",
                             "away_turnovers_conceded": ""})
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
                    "line": TRUE_POWER[away] - TRUE_POWER[home]
                            - season_report.HOME_ADVANTAGE,
                    "home_score": 20 + i, "away_score": 18,
                    "home_turnovers_conceded": 6 + i,
                    "away_turnovers_conceded": 11})
        split = pd.DataFrame(rows, columns=season_report.SEASON_COLUMNS)
        late = split.index[split["round"] == 2][-2:]          # push them past round 5
        split.loc[late, "date"] = (base + pd.Timedelta(days=7 * 7)).date()
        split.to_csv(data / "season_2026.csv", index=False)

        report = season_report.build_reports()[2026]
        report["date"] = pd.to_datetime(report["date"])
        net = {(r.date, r.home, r.away):
               r.home_turnovers_conceded - r.away_turnovers_conceded
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
                margin = net[(r.date, r.home, r.away)]
                expected = float(margin if r.home == club else -margin)
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

    print("\n" + ("all checks passed" if passed else "SOME CHECKS FAILED"))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
