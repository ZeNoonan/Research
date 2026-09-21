"""Per-factor diagnostics: is any one of the five actually carrying the system?

Two tables, both from the NFL project's reading of Brown's monitoring tools:

**Marginal contribution** - net wins charged to each factor on the close calls
its vote alone decided. On a bet made at exactly the threshold every aligned
vote is decisive, so each is charged the result; on a near-miss one short of the
threshold the bet was blocked, so every *opposing* vote is charged the opposite
of what the blocked bet would have done. Pure leave-one-out; the NFL version
reproduces every value in Brown's published Table 3.

**Standalone success** - each factor as its own betting rule across all matches,
ignoring the other four.

Neither is meaningful on a handful of matches, so a rate is withheld until the
factor has cast ``MIN_VOTES`` settled votes. Early in a season both tables will
be mostly dashes, which is the honest answer rather than a flattering one.

Run: ``python factor_analysis.py``
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

import model
import season_report

DATA_DIR = Path(__file__).parent / "data"

FACTORS = ["power", "turnover_home", "turnover_away", "hunger_home", "hunger_away"]
FACTOR_LABELS = {
    "power": "Power / over-reaction",
    "turnover_home": "Turnover - home",
    "turnover_away": "Turnover - away",
    "hunger_home": "Hunger - home",
    "hunger_away": "Hunger - away",
}
MIN_VOTES = 25  # below this a rate is noise, not signal


def available_years() -> list[int]:
    return sorted(
        int(m.group(1))
        for f in DATA_DIR.glob("report_*.csv")
        if (m := re.match(r"report_(\d{4})\.csv", f.name))
    )


def factor_frame(year: int) -> pd.DataFrame:
    """Per-match factor votes, System # and cover sign for one season."""
    df = pd.read_csv(DATA_DIR / f"report_{year}.csv")
    df = df[df["line"].notna()].copy()  # no handicap: no bet was possible
    if df.empty:
        return df

    df["power"] = [model.power_factor(r.home_power, r.away_power, r.line)
                   for r in df.itertuples()]
    df["turnover_home"] = df["home_lgt"].map(model.turnover_factor_home)
    df["turnover_away"] = df["away_lgt"].map(model.turnover_factor_away)
    df["hunger_home"] = df["home_stdc"].map(model.hunger_factor_home)
    df["hunger_away"] = df["away_stdc"].map(model.hunger_factor_away)

    bad = df[FACTORS].sum(axis=1) != df["system_num"]
    if bad.any():
        raise ValueError(f"{year}: {int(bad.sum())} matches where the five votes "
                         f"do not sum to the stored System #")

    df["cover"] = [model.cover(r.home_score, r.away_score, r.line)
                   for r in df.itertuples()]
    return df


def marginal_contributions(df: pd.DataFrame) -> pd.Series:
    """Net wins charged to each factor over one season."""
    net = dict.fromkeys(FACTORS, 0)
    for r in df.itertuples():
        s = r.system_num
        if abs(s) < model.BET_THRESHOLD - 1:
            continue
        side = 1 if s > 0 else -1
        result = 1 if r.cover == side else -1 if r.cover == -side else 0
        if abs(s) == model.BET_THRESHOLD:        # bet made: aligned votes decisive
            for f in FACTORS:
                if getattr(r, f) == side:
                    net[f] += result
        elif abs(s) == model.BET_THRESHOLD - 1:  # bet blocked by opposing votes
            for f in FACTORS:
                if getattr(r, f) == -side:
                    net[f] -= result
    return pd.Series(net)


def standalone_rates(df: pd.DataFrame) -> pd.Series:
    """Share of each factor's settled votes that covered."""
    rates = {}
    for f in FACTORS:
        votes = df[(df[f] != 0) & (df["cover"] != 0)]
        rates[f] = (votes[f] == votes["cover"]).sum() / len(votes) \
            if len(votes) >= MIN_VOTES else float("nan")
    return pd.Series(rates)


def build_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(marginal net wins, standalone cover rates); factors x seasons."""
    frames = {y: factor_frame(y) for y in available_years()}
    frames = {y: f for y, f in frames.items() if not f.empty}
    if not frames:
        return pd.DataFrame(), pd.DataFrame()
    marginal = pd.DataFrame({y: marginal_contributions(f) for y, f in frames.items()})
    standalone = pd.DataFrame({y: standalone_rates(f) for y, f in frames.items()})
    return marginal, standalone


def main() -> None:
    marginal, standalone = build_tables()
    if marginal.empty:
        print("no priced matches yet - nothing to diagnose")
        return
    label = {y: season_report.season_label(y) for y in marginal.columns}

    print("Marginal contribution (net wins charged to each factor)\n")
    print(marginal.rename(index=FACTOR_LABELS, columns=label).to_string())
    print("\n\nStandalone success (each factor as its own rule; "
          f"'-' until {MIN_VOTES} settled votes)\n")
    shown = standalone.rename(index=FACTOR_LABELS, columns=label)
    print(shown.map(lambda v: "-" if pd.isna(v) else f"{v:.1%}").to_string())


if __name__ == "__main__":
    main()
