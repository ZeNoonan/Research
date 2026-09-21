"""Canonical URC team names, and the aliases the data sources actually use.

Every source spells these teams differently. The URC's own site and the odds
pages carry title sponsors (``Vodacom Bulls``, ``DHL Stormers``,
``Hollywoodbets Sharks``, ``Emirates Lions``), Wikipedia drops them, and the
various rugby sites add or drop the ``Rugby`` / ``RFC`` suffix. Joining an odds
row to a results row therefore needs a normaliser, not a string compare.

``canonical()`` maps any of those spellings to one short, stable name, which is
what every file in ``data/`` and every report column uses.
"""

from __future__ import annotations

import re
import unicodedata

# The 16 clubs of the 2026-27 United Rugby Championship, by the short name used
# throughout this project, grouped by the competition's five territories (the
# "shield" groupings the URC uses for its regional standings).
TEAMS: dict[str, str] = {
    # Ireland
    "Leinster": "Ireland",
    "Munster": "Ireland",
    "Ulster": "Ireland",
    "Connacht": "Ireland",
    # Wales
    "Cardiff": "Wales",
    "Dragons": "Wales",
    "Ospreys": "Wales",
    "Scarlets": "Wales",
    # Scotland
    "Edinburgh": "Scotland",
    "Glasgow": "Scotland",
    # Italy
    "Benetton": "Italy",
    "Zebre": "Italy",
    # South Africa
    "Bulls": "South Africa",
    "Lions": "South Africa",
    "Sharks": "South Africa",
    "Stormers": "South Africa",
}

# South African clubs travel to Europe and vice versa; the other four
# territories are a short hop apart. Used to flag long-haul away trips, which
# are the URC's analogue of a neutral venue in the NFL model.
SOUTH_AFRICAN = {t for t, u in TEAMS.items() if u == "South Africa"}

# Spellings seen in the wild that a suffix-strip alone will not resolve.
ALIASES: dict[str, str] = {
    "zebreparma": "Zebre",
    "zebrerugbyclub": "Zebre",
    "zebrerugby": "Zebre",
    "glasgowwarriors": "Glasgow",
    "warriors": "Glasgow",
    "cardiffblues": "Cardiff",
    "cardiffrugby": "Cardiff",
    "benettontreviso": "Benetton",
    "treviso": "Benetton",
    "newportgwentdragons": "Dragons",
    "dragonsrfc": "Dragons",
    "ospreysrugby": "Ospreys",
    "llanelliscarlets": "Scarlets",
    "capetownstormers": "Stormers",
    "westernprovince": "Stormers",
    "natalsharks": "Sharks",
    "bluebulls": "Bulls",
    "goldenlions": "Lions",
    "edinburghrugby": "Edinburgh",
}

# Title sponsors and generic suffixes, stripped before matching.
_SPONSORS = (
    "vodacom", "dhl", "hollywoodbets", "emirates", "bkt", "cell c", "cellc",
    "toyota", "isuzu", "sigma lithium", "sigma",
)
_SUFFIXES = ("rugby club", "rugby", "rfc", "rc", "fc")


def _slug(name: str) -> str:
    """Lower-case, accent- and punctuation-free key for matching."""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def canonical(name: str) -> str:
    """Any known spelling of a URC club -> its short canonical name.

    Raises ``KeyError`` rather than guessing: an unrecognised team in a data
    file is a typo or a new club, and both need a human, not a silent pass.
    """
    raw = str(name).strip()
    if raw in TEAMS:
        return raw

    text = raw.lower()
    for sponsor in _SPONSORS:  # leading title sponsor, e.g. "Vodacom Bulls"
        if text.startswith(sponsor + " "):
            text = text[len(sponsor) + 1:]
    for suffix in _SUFFIXES:  # trailing descriptor, e.g. "Leinster Rugby"
        if text.endswith(" " + suffix):
            text = text[: -len(suffix) - 1]

    key = _slug(text)
    if key in ALIASES:
        return ALIASES[key]
    for team in TEAMS:
        if key == _slug(team):
            return team
    # Last resort: a unique club whose canonical name appears inside the string
    # ("Emirates Lions XV", "Ulster A" style oddities).
    hits = {t for t in TEAMS if _slug(t) in key}
    if len(hits) == 1:
        return hits.pop()
    raise KeyError(f"unrecognised URC team: {name!r}")


def is_long_haul(home: str, away: str) -> bool:
    """True when the away side crosses between Europe and South Africa."""
    return (canonical(home) in SOUTH_AFRICAN) != (canonical(away) in SOUTH_AFRICAN)
