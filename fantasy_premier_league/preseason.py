"""Rate the new season's player list on last season's evidence, at new prices.

Before a ball is kicked in 2026/27 there are no gameweeks to rate, but there
is a price list and there is last season's record. This module joins the two:
every player in ``data/2026-27/player_listing.csv`` is matched to his
2025/26 history and rated on the factors that survive a summer.

What carries over, and what doesn't
-----------------------------------
* **Quality**  – season-long per-90 rates. Carries.
* **Value**    – recomputed at the **new** price, which is the whole point:
  a player whose price fell while his numbers held is this month's bargain.
* **Minutes**  – last 5 matches played of 2025/26. Carries as a nailed-on
  signal, subject to the summer's transfers.
* **Justice**  – last 6 gameweeks of 2025/26. Carries, but decays.
* **Form**     – last 5 gameweeks of 2025/26. Included and flagged: three
  months stale, the weakest of the five here.
* **Crowd**    – dropped. There is no ownership data before the season
  opens, so the factor cannot be computed at all. (It was also the only
  factor with a negative edge in the 2025/26 backtest.)

So a pre-season rating is **0-5 stars** over five factors, against a
0-6 in-season rating. Once real gameweeks exist, ``weekly_report.py`` takes
over and this module is done for the year.

Name matching
-------------
The price list uses FPL "web names" (``Raya``, ``A.Becker``,
``Arrizabalaga``); the history uses full names (``David Raya Martín``,
``Alisson Becker``, ``Kepa Arrizabalaga Revuelta``). ``match_players``
normalises both (accents, and the letters NFKD leaves alone - ı ø đ ß ...),
indexes the history by name token, and resolves each listing entry by
surname, preferring a candidate at the same club and breaking ties on
last season's minutes. Players with no match - promoted-club squads and
new signings from abroad - are reported as **unrated**, not dropped: they
are exactly the players a manager has to judge by eye.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import pandas as pd

import model

HERE = Path(__file__).parent

# Factors available before the season starts (Crowd needs ownership data).
PRESEASON_FACTORS = ("quality", "value", "form", "minutes_factor", "justice")

# Letters NFKD does not decompose to ASCII.
SPECIAL = str.maketrans({"ı": "i", "ø": "o", "đ": "d", "ð": "d", "þ": "th",
                         "ł": "l", "æ": "ae", "œ": "oe", "ß": "ss", "ħ": "h",
                         "ŀ": "l"})


def normalise(name: str) -> str:
    """Lowercase, strip accents and punctuation: 'Bayındır' -> 'bayindir'."""
    s = str(name).lower().translate(SPECIAL)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z ]", " ", s).strip()


def load_listing(path: str | Path) -> pd.DataFrame:
    """Read the new season's price list (name, position, team, price)."""
    listing = pd.read_csv(path)
    missing = {"name", "position", "team", "price"} - set(listing.columns)
    if missing:
        raise ValueError(f"listing is missing columns: {sorted(missing)}")
    return listing


def _candidate_pairs(listing: pd.DataFrame, hist: pd.DataFrame,
                     by_token: dict[str, list[int]]):
    """Yield (score, entry_pos, hist_idx, how) for every plausible pairing.

    Score rewards, in order: the listing name matching the history
    **surname** (its last token) rather than a first name — 'Anthony' is
    Jaidon Anthony, not Anthony Gordon — then the club agreeing, then an
    explicit initial agreeing. Position must agree, except that an
    outfielder at the same club may have been reclassified by FPL.
    """
    for pos_i, entry in enumerate(listing.itertuples()):
        initial_match = re.match(r"^([A-Za-z])\.(.+)$", str(entry.name))
        if initial_match:
            initial = initial_match.group(1).lower()
            rest = normalise(initial_match.group(2))
        else:
            initial, rest = None, normalise(entry.name)

        tokens = [t for t in rest.split() if len(t) > 2]
        if not tokens:
            continue
        cands = set(by_token.get(tokens[-1], []))
        for tok in tokens[:-1]:
            cands &= set(by_token.get(tok, []))

        for c in cands:
            hist_tokens = hist.at[c, "_n"].split()
            if initial and not any(w.startswith(initial) for w in hist_tokens):
                continue

            same_club = hist.at[c, "team"] == entry.team
            same_pos = hist.at[c, "position"] == entry.position
            if not same_pos:
                # Reclassification is real, but only believable at the same
                # club, and never for a goalkeeper.
                if not same_club or "GK" in (hist.at[c, "position"],
                                             entry.position):
                    continue

            surname_hit = hist_tokens[-1] == tokens[-1]
            score = (4 * surname_hit + 2 * same_club + 2 * same_pos
                     + bool(initial))
            if same_club and same_pos:
                how = "team"
            elif same_club:
                how = "team-repositioned"
            else:
                how = "global"
            yield score, pos_i, c, how


def match_players(listing: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    """Attach each listing row to a history row; add ``match`` describing how.

    Assignment is **one-to-one**: a history player can be claimed by only one
    listing entry. Without that, 'B.Fernandes' (Man Utd) and 'Fernandes'
    (Spurs) both take Bruno Fernandes, and the Spurs entry inherits the wrong
    man's season. Pairs are taken best-score first, ties broken on last
    season's minutes so the regular of a shared surname is claimed first.

    ``match`` is 'team' (same club), 'team-repositioned' (same club, FPL
    changed his position), 'global' (moved club), or 'none'.
    """
    hist = hist.copy()
    hist["_n"] = hist["name"].map(normalise)

    by_token: dict[str, list[int]] = defaultdict(list)
    for idx, n in zip(hist.index, hist["_n"]):
        for tok in n.split():
            if len(tok) > 2:
                by_token[tok].append(idx)

    pairs = sorted(_candidate_pairs(listing, hist, by_token),
                   key=lambda p: (p[0], hist.at[p[2], "minutes"]), reverse=True)

    taken_entry: dict[int, tuple] = {}
    taken_hist: set = set()
    for score, pos_i, c, how in pairs:
        if pos_i in taken_entry or c in taken_hist:
            continue
        taken_entry[pos_i] = (c, how)
        taken_hist.add(c)

    out = listing.copy()
    out["_hist_idx"] = [taken_entry.get(i, (None, None))[0]
                        for i in range(len(listing))]
    out["match"] = [taken_entry.get(i, (None, "none"))[1]
                    for i in range(len(listing))]
    return out


def rate_preseason(listing_path: str | Path, history_dir: str | Path):
    """Return (rated, unrated): listing players scored on last season's data.

    ``rated`` carries the five pre-season factors, ``stars`` (0-5) and the
    **new** price; ``unrated`` is everyone with no Premier League history.
    """
    listing = load_listing(listing_path)
    hist = model.player_table(model.load_season(history_dir))
    joined = match_players(listing, hist)

    matched = joined[joined["_hist_idx"].notna()].copy()
    unrated = joined[joined["_hist_idx"].isna()].copy()

    carry = ["xpts90", "xpts90_raw", "form_points", "minutes_avg",
             "justice_margin", "gate_minutes", "minutes", "points",
             "appearances", "selected", "xg90", "xa90", "xgc90", "dc_rate"]
    idx = matched["_hist_idx"].astype(int)
    for col in carry:
        matched[col] = hist.loc[idx, col].to_numpy()
    matched["last_team"] = hist.loc[idx, "team"].to_numpy()
    matched["hist_name"] = hist.loc[idx, "name"].to_numpy()
    matched["moved"] = matched["last_team"] != matched["team"]

    # Price move over the summer, against last season's closing price. A
    # player repriced down while his numbers held is the pre-season bargain
    # the Value factor is built to find.
    matched["last_price"] = hist.loc[idx, "price"].to_numpy()
    matched["price_change"] = matched["price"] - matched["last_price"]

    # The in-season gate, on last season's appearances.
    matched["eligible"] = matched["gate_minutes"] >= model.MINUTES_PER_GW

    rated = model.rate_players(matched)
    # Crowd cannot be computed pre-season; drop it from the star count.
    rated["crowd"] = 0
    rated["stars"] = rated[list(PRESEASON_FACTORS)].sum(axis=1)
    rated["factor_letters"] = [
        "".join(model.FACTOR_LETTERS[f] for f in PRESEASON_FACTORS if r[f])
        for _, r in rated.iterrows()]
    return rated, unrated


def picks(rated: pd.DataFrame, min_stars: int = 4) -> pd.DataFrame:
    """Eligible players at ``min_stars``+, by position, strongest first."""
    out = rated[rated["eligible"] & (rated["stars"] >= min_stars)].copy()
    out["position"] = pd.Categorical(out["position"], model.POSITIONS)
    return out.sort_values(["position", "stars", "xpts90"],
                           ascending=[True, False, False])
