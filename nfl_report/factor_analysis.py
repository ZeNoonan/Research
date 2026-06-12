"""Rebuild Aaron Brown's season-by-season factor diagnostics.

Two tables, per season, for every report in ``data/``:

* **Marginal contributions** — Brown's close-call accounting (Wilmott article,
  Table 3). A factor is charged only on games where leaving it out would have
  changed the betting decision:

  - bet made with ``|System #| == 3`` exactly: every factor that voted with
    the bet is charged the bet's result (+1 win, -1 loss, 0 push) — leaving
    any one of them out would have killed the bet;
  - no bet with ``|System #| == 2``: every factor that voted *against* the
    would-be bet side is charged the opposite of the result that bet would
    have had — leaving the blocker out would have created the bet;
  - any other count: no charges (no single factor was decisive).

  (The article's prose suggests neutral factors also get blocking credit, but
  the pure leave-one-out rule above is what reproduces the published Table 3:
  all ten 2015/2016 values match exactly; the prose variant does not.)

* **Standalone success** — each factor as a binary indicator over all games:
  how often the team it points at covers the spread.

The marginal rule is validated against Brown's published Table 3: this code
reproduces his 2015 and 2016 rows exactly from the replicated reports.

Run: ``python factor_analysis.py``
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

import model

DATA_DIR = Path(__file__).parent / "data"

FACTORS = ["power", "turnover_home", "turnover_away", "hunger_home", "hunger_away"]
FACTOR_LABELS = {
    "power": "Power",
    "turnover_home": "Turnover — home",
    "turnover_away": "Turnover — away",
    "hunger_home": "Hunger — home",
    "hunger_away": "Hunger — away",
}


def available_years() -> list[int]:
    return sorted(int(p.stem.split("_")[1]) for p in DATA_DIR.glob("report_*.csv"))


def factor_frame(year: int) -> pd.DataFrame:
    """Per-game factor votes, system number, and cover sign for one season.

    Factor votes are recomputed with the model engine. For the published
    reports (2015/2016) the power column is rounded to one decimal, which
    creates two exact ties in 2015 where the recomputed sum differs from the
    published System #; there the power vote is recovered exactly as
    ``published # − (sum of the other four votes)``.
    """
    df = pd.read_csv(DATA_DIR / f"report_{year}.csv")
    df = df[df["line"].notna()].copy()  # no line: no bet was possible

    df["power"] = [
        model.power_factor(r.home_power, r.away_power, r.line) for r in df.itertuples()
    ]
    df["turnover_home"] = df["home_lgt"].map(model.turnover_factor_home)
    df["turnover_away"] = df["away_lgt"].map(model.turnover_factor_away)
    df["hunger_home"] = df["home_stdc"].map(model.hunger_factor_home)
    df["hunger_away"] = df["away_stdc"].map(model.hunger_factor_away)

    other = df[FACTORS[1:]].sum(axis=1)
    recovered = df["system_num"] - other
    fixable = (df[FACTORS].sum(axis=1) != df["system_num"]) & recovered.isin([-1, 0, 1])
    df.loc[fixable, "power"] = recovered[fixable]

    bad = df[FACTORS].sum(axis=1) != df["system_num"]
    if bad.any():
        raise ValueError(f"{year}: {bad.sum()} games where votes don't sum to System #")

    df["cover"] = [
        model.cover(r.home_score, r.away_score, r.line) for r in df.itertuples()
    ]
    return df


def marginal_contributions(df: pd.DataFrame) -> pd.Series:
    """Net wins charged to each factor over one season (Brown's Table 3)."""
    net = dict.fromkeys(FACTORS, 0)
    for r in df.itertuples():
        s = r.system_num
        if abs(s) < 2:
            continue
        side = 1 if s > 0 else -1
        result = 1 if r.cover == side else -1 if r.cover == -side else 0
        if abs(s) == model.BET_THRESHOLD:  # bet made, every aligned vote decisive
            for f in FACTORS:
                if getattr(r, f) == side:
                    net[f] += result
        elif abs(s) == model.BET_THRESHOLD - 1:  # bet blocked by opposing votes
            for f in FACTORS:
                if getattr(r, f) == -side:
                    net[f] -= result
    return pd.Series(net)


def standalone_rates(df: pd.DataFrame) -> pd.Series:
    """Each factor as a binary indicator: share of its votes that cover."""
    rates = {}
    for f in FACTORS:
        votes = df[(df[f] != 0) & (df["cover"] != 0)]
        wins = (votes[f] == votes["cover"]).sum()
        rates[f] = wins / len(votes) if len(votes) else float("nan")
    return pd.Series(rates)


def build_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(marginal net wins, standalone cover rates); factors x seasons."""
    years = available_years()
    frames = {y: factor_frame(y) for y in years}
    marginal = pd.DataFrame({y: marginal_contributions(f) for y, f in frames.items()})
    standalone = pd.DataFrame({y: standalone_rates(f) for y, f in frames.items()})
    return marginal, standalone


def main() -> None:
    marginal, standalone = build_tables()
    marginal.index = [FACTOR_LABELS[f] for f in marginal.index]
    standalone.index = [FACTOR_LABELS[f] for f in standalone.index]

    print("Marginal contributions (net wins charged to each factor):")
    out = marginal.copy()
    out.loc["Total"] = out.sum()
    print(out.to_string())

    print("\nStandalone success (share of factor votes that cover):")
    print(standalone.map(lambda x: f"{x:.1%}").to_string())


if __name__ == "__main__":
    main()
