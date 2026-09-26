"""Scrape turnovers and scores from the URC match centre, a round at a time.

The match centre at stats.unitedrugby.com is a JavaScript page; the numbers on
it come from a JSON feed run by InCrowd Sports with data from RugbyViz. This
reads that feed directly - the same approach as the FPL scraper, which reads
the FPL API rather than the website - so it needs only ``requests``::

    match list:  {FEED}/matches?compId=1068&season=202601&provider=rugbyviz
    one match:   {FEED}/matches/292584?season=202601&provider=rugbyviz

Both endpoints are documented by working code in the public
transientlunatic/Rugby-Data project. What is **not** documented anywhere is
where the team stats sit inside a match response. So rather than hard-code a
guessed path, ``find_stats`` walks the whole response and collects every stat
that carries a home and an away value, and ``turnovers`` picks the turnover
ones out by name. If the feed moves them, the "every stat found" panel and the
raw-JSON download show where they went.

The CSV it writes is in the shape ``import_turnovers.py`` reads, scores
included::

    python import_turnovers.py entry/scraped/urc_202601_round01.csv --season 2026

Run:  streamlit run urc_scraper.py
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pandas as pd
import requests

FEED = "https://rugby-union-feeds.incrowdsports.com/v1"
COMP_ID = 1068          # United Rugby Championship
PROVIDER = "rugbyviz"
DEFAULT_SEASON = "202601"  # the 2026-27 season, as the match-centre URLs spell it
PAUSE = 0.4             # seconds between requests - one round is only 8 calls

OUT = Path(__file__).parent / "entry" / "scraped"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "application/json",
    "Origin": "https://stats.unitedrugby.com",
    "Referer": "https://stats.unitedrugby.com/",
}

# .../match-centre/202601/united-rugby-championship/benetton-...-2026-09-25/292584#tabs-stats
URL_RE = re.compile(r"/match-centre/(\d{6})/(?:[^/?#]+/)*?(\d+)(?:[/?#]|$)")

PLAYED = {"complete", "completed", "finished", "result", "fulltime", "full time",
          "ft", "played", "post", "postmatch", "post-match"}

COLUMNS = ["Date", "Round", "Home Team", "Away Team", "home_score", "away_score",
           "home_turnovers_won", "away_turnovers_won",
           "home_turnovers_lost", "away_turnovers_lost",
           "match_id", "status", "found_as"]


# --- the feed ----------------------------------------------------------------

def parse_match_url(text: str, season: str = DEFAULT_SEASON) -> tuple[str, str]:
    """A match-centre link (or a bare match id) -> (season, match id)."""
    text = text.strip()
    if text.isdigit():
        return season, text
    if m := URL_RE.search(text):
        return m.group(1), m.group(2)
    raise ValueError(f"not a match-centre link or match id: {text!r}")


def fetch_json(url: str) -> dict:
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return response.json()


def fetch_match(match_id: str, season: str) -> dict:
    return fetch_json(f"{FEED}/matches/{match_id}?season={season}&provider={PROVIDER}")


def fetch_fixtures(season: str) -> pd.DataFrame:
    """Every URC match in a season, played or not, one row each."""
    body = fetch_json(f"{FEED}/matches?compId={COMP_ID}&season={season}"
                      f"&provider={PROVIDER}")
    rows = []
    for m in body.get("data", []):
        home, away = m.get("homeTeam") or {}, m.get("awayTeam") or {}
        rows.append({
            "match_id": str(m.get("id")),
            "date": str(m.get("date", ""))[:10],
            "round": m.get("round"),
            "round_type": "league" if m.get("roundTypeId") == 1 else "knockout",
            "status": str(m.get("status") or ""),
            "home": home.get("name"), "away": away.get("name"),
            "home_score": home.get("score"), "away_score": away.get("score"),
        })
    return pd.DataFrame(rows)


def is_played(status: str) -> bool:
    return str(status).strip().lower() in PLAYED


# --- finding the stats without knowing where they are ------------------------

LABEL_KEYS = ("name", "label", "title", "statName", "stat", "key", "type",
              "description", "displayName")
HOME_KEYS = ("home", "homeValue", "home_value", "homeTotal", "homeTeam", "team1")
AWAY_KEYS = ("away", "awayValue", "away_value", "awayTotal", "awayTeam", "team2")
VALUE_KEYS = ("value", "total", "count", "amount")
# Player-level stats share names with team stats ("turnoversWon"), so anything
# under a player is skipped - one player's count must never pass as the team's.
PLAYER_PARTS = ("players", "player", "lineup", "lineups", "squad", "bench",
                "substitutes", "events")
IDENTIFIERS = {"id", "teamid", "playerid", "positionid", "score", "round",
               "roundtypeid", "compid", "season", "attendance", "minute",
               "group", "venueid", "matchid", "shirtnumber", "number",
               "date", "kickoff", "time", "year"}

TURNOVER = re.compile(r"turn\s*-?\s*overs?", re.I)
WON = re.compile(r"\b(won|win|wins|gained|forced|recovered)\b", re.I)
LOST = re.compile(r"\b(conceded|lost|loses|given|against)\b", re.I)


# A string is a stat only when the whole of it is a number, optionally with a
# percent sign or a bracketed note. Matching just the leading digits read the
# year out of "2026-09-25T18:45:00Z" and produced home_date = 2026 on the first
# real run; a kick-off time would have done the same.
NUMERIC = re.compile(r"\s*(-?\d+(?:\.\d+)?)\s*%?\s*(?:\([^)]*\))?\s*")


def number(value) -> float | None:
    """A stat value as a number: 7, 7.0, "7", "54%" and "7 (54%)" all parse;
    "2026-09-25T18:45:00Z", "19:45" and "150/12" do not."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and (m := NUMERIC.fullmatch(value)):
        return float(m.group(1))
    return None


def words(key: str) -> str:
    """``turnoversWon`` / ``turnovers_won`` / ``Turnovers Won`` -> "turnovers won"."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(key))
    return re.sub(r"[\s_\-]+", " ", spaced).strip().lower()


def _side(path: tuple[str, ...]) -> str | None:
    for part in reversed(path):
        p = part.lower()
        if p.startswith("home"):
            return "home"
        if p.startswith("away"):
            return "away"
    return None


def _walk(node, path: tuple[str, ...] = ()):
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from _walk(v, path + (str(k),))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, path + (f"[{i}]",))


def _first_number(d: dict, keys: tuple[str, ...]) -> float | None:
    for k in keys:
        if k in d and (n := number(d[k])) is not None:
            return n
    return None


def find_stats(match: dict) -> dict[str, dict[str, float]]:
    """Every team stat in a match response: ``{label: {"home": x, "away": y}}``.

    Handles the shapes team stats are usually published in, without being told
    which one this feed uses:

    * a list of ``{"name": "Turnovers Won", "home": 7, "away": 5}``
    * per-team dicts, ``homeTeam.stats = {"turnoversWon": 7}``
    * per-team lists, ``homeTeam.stats = [{"label": ..., "value": 7}]``
    * a stat keyed by name, ``{"turnoversWon": {"home": 7, "away": 5}}``

    Labels are normalised to lower-case words, so all four land on the same
    key. Anything beneath a player, the line-ups or the event log is skipped.
    """
    stats: dict[str, dict[str, float]] = {}

    def put(label: str, side: str, value: float | None) -> None:
        if value is not None:
            stats.setdefault(words(label), {}).setdefault(side, value)

    for path, d in _walk(match):
        if any(p.lower() in PLAYER_PARTS for p in path):
            continue
        side = _side(path)

        label = next((d[k] for k in LABEL_KEYS if isinstance(d.get(k), str)), None)
        if label:
            home, away = _first_number(d, HOME_KEYS), _first_number(d, AWAY_KEYS)
            if home is not None or away is not None:
                put(label, "home", home)
                put(label, "away", away)
            elif side:
                put(label, side, _first_number(d, VALUE_KEYS))

        for key, value in d.items():
            if key in LABEL_KEYS + HOME_KEYS + AWAY_KEYS + VALUE_KEYS:
                continue
            if words(key).replace(" ", "") in IDENTIFIERS:
                continue
            if isinstance(value, dict):           # {"turnoversWon": {"home": 7, ...}}
                home, away = (_first_number(value, HOME_KEYS),
                              _first_number(value, AWAY_KEYS))
                if home is not None or away is not None:
                    put(key, "home", home)
                    put(key, "away", away)
            elif side and (n := number(value)) is not None:   # homeTeam.stats.x
                put(key, side, n)

    return stats


def turnovers(stats: dict[str, dict[str, float]]) -> dict:
    """Pick turnovers won and turnovers conceded out of ``find_stats``.

    When several labels qualify ("turnovers won", "ruck turnovers won") the
    plainest wins - fewest words - because the qualified ones are subsets. A
    bare "turnovers" is left alone rather than guessed at: it could mean either.
    """
    def pick(kind: re.Pattern) -> tuple[str | None, dict]:
        hits = [(label, v) for label, v in stats.items()
                if TURNOVER.search(label) and kind.search(label)
                and "home" in v and "away" in v]
        if not hits:
            return None, {}
        return min(hits, key=lambda h: (len(h[0].split()), h[0]))

    won_label, won = pick(WON)
    lost_label, lost = pick(LOST)
    return {
        "home_turnovers_won": won.get("home"), "away_turnovers_won": won.get("away"),
        "home_turnovers_lost": lost.get("home"), "away_turnovers_lost": lost.get("away"),
        "won_label": won_label, "lost_label": lost_label,
        "other_labels": sorted(l for l in stats
                               if TURNOVER.search(l) and l not in (won_label, lost_label)),
    }


def column_name(label: str) -> str:
    """A stat label as a column stem: "Tackles Made" -> "tackles_made"."""
    text = words(label).replace("%", " pct ")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def match_row(body: dict, match_id: str) -> dict:
    """One CSV row from a match response: the model's columns, then every stat.

    The fixed ``COLUMNS`` come first and are what ``import_turnovers.py`` reads.
    Every other stat in the response follows as a ``home_``/``away_`` pair, in
    the order the feed lists them. Two guards: the turnover stats already used
    are not repeated, and an extra stat can never overwrite one of the fixed
    columns - a stat the feed happened to label "Score" must not replace the
    score the model grades on.
    """
    data = body.get("data", body)
    home, away = data.get("homeTeam") or {}, data.get("awayTeam") or {}
    stats = find_stats(data)
    t = turnovers(stats)
    found = " / ".join(x for x in (t["won_label"], t["lost_label"]) if x)
    row = {
        "Date": str(data.get("date", ""))[:10],
        "Round": data.get("round"),
        "Home Team": home.get("name"), "Away Team": away.get("name"),
        "home_score": number(home.get("score")), "away_score": number(away.get("score")),
        **{k: t[k] for k in ("home_turnovers_won", "away_turnovers_won",
                             "home_turnovers_lost", "away_turnovers_lost")},
        "match_id": match_id,
        "status": str(data.get("status") or ""),
        "found_as": found,
    }
    for label, values in stats.items():
        stem = column_name(label)
        if not stem or label in (t["won_label"], t["lost_label"]):
            continue
        for side in ("home", "away"):
            row.setdefault(f"{side}_{stem}", values.get(side))
    return row


def table_columns(rows: list[dict]) -> list[str]:
    """The fixed columns, then every extra stat in first-seen order.

    Matches in one round need not carry identical stat lists, so the union is
    taken; a stat missing from one match is simply blank in its row.
    """
    extra: list[str] = []
    for row in rows:
        extra += [k for k in row if k not in COLUMNS and k not in extra]
    return COLUMNS + extra


def complete(row: dict) -> bool:
    """All four turnover counts present - what the model needs from a match.

    ``pd.notna`` rather than ``is not None``: once a row has been through a
    DataFrame a missing count is NaN, and NaN is not None.
    """
    return all(pd.notna(row.get(k)) for k in ("home_turnovers_won", "away_turnovers_won",
                                                "home_turnovers_lost", "away_turnovers_lost"))


# --- the app -------------------------------------------------------------------

def wide(container, data, **kwargs):
    """``container.dataframe`` at full width, on old Streamlit and new.

    Newer Streamlit takes ``width="stretch"`` and deprecates
    ``use_container_width``; older releases only know the latter and reject a
    string width with ``TypeError: 'str' object cannot be interpreted as an
    integer``. That is raised before anything is drawn, so retrying is safe.
    """
    try:
        return container.dataframe(data, width="stretch", **kwargs)
    except TypeError:
        return container.dataframe(data, use_container_width=True, **kwargs)


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="URC match-centre scraper", layout="wide")
    st.title("🏉 URC match-centre scraper")
    st.caption("Turnovers and scores for the URC report, straight from the feed "
               "behind stats.unitedrugby.com.")

    @st.cache_data(ttl=600, show_spinner=False)
    def cached_match(match_id: str, season: str) -> dict:
        return fetch_match(match_id, season)

    @st.cache_data(ttl=600, show_spinner=False)
    def cached_fixtures(season: str) -> pd.DataFrame:
        return fetch_fixtures(season)

    mode = st.radio("Which matches?", ("A whole round", "Paste match links"),
                    horizontal=True)
    season = st.text_input("Season (as in the match-centre URL)", DEFAULT_SEASON)

    targets: list[tuple[str, str]] = []
    label = "matches"
    if mode == "A whole round":
        try:
            fixtures = cached_fixtures(season)
        except requests.RequestException as exc:
            st.error(f"Could not load the {season} fixture list: {exc}")
            st.stop()
        if fixtures.empty:
            st.warning(f"The feed returned no matches for season {season}.")
            st.stop()
        rounds = sorted(fixtures["round"].dropna().unique())
        played = fixtures[fixtures["status"].map(is_played)]
        latest = played["round"].max() if not played.empty else rounds[0]
        rnd = st.selectbox("Round", rounds, index=rounds.index(latest)
                           if latest in rounds else 0)
        chosen = fixtures[fixtures["round"] == rnd]
        wide(st, chosen[["date", "home", "away", "home_score", "away_score",
                         "status"]], hide_index=True)
        ready = chosen[chosen["status"].map(is_played)]
        if len(ready) < len(chosen):
            st.info(f"{len(chosen) - len(ready)} of {len(chosen)} not marked as played "
                    f"yet - only played matches have stats to fetch.")
        targets = [(m, season) for m in ready["match_id"]]
        label = f"round{int(rnd):02d}"
    else:
        pasted = st.text_area(
            "One match-centre link (or match id) per line",
            "https://stats.unitedrugby.com/match-centre/202601/united-rugby-championship/"
            "benetton-rugby-vs-dragons-rfc-2026-09-25/292584#tabs-stats", height=120)
        for line in filter(str.strip, pasted.splitlines()):
            try:
                s, m = parse_match_url(line, season)
                targets.append((m, s))
            except ValueError as exc:
                st.warning(str(exc))
        label = "pasted"

    if not st.button(f"Fetch stats for {len(targets)} match(es)", type="primary",
                     disabled=not targets):
        st.stop()

    rows, raw = [], {}
    progress = st.progress(0.0)
    for i, (match_id, s) in enumerate(targets, start=1):
        try:
            body = cached_match(match_id, s)
            raw[match_id] = body
            rows.append(match_row(body, match_id))
        except requests.RequestException as exc:
            st.error(f"Match {match_id}: {exc}")
        progress.progress(i / len(targets))
        time.sleep(PAUSE)
    if not rows:
        st.stop()

    table = pd.DataFrame(rows, columns=table_columns(rows))
    extra_stats = (len(table.columns) - len(COLUMNS)) // 2
    missing = table[~table.apply(lambda r: complete(r.to_dict()), axis=1)]
    if missing.empty:
        st.success(f"Turnovers found for all {len(table)} match(es), "
                   f"plus {extra_stats} other stats per match.")
    else:
        st.warning(f"Turnovers incomplete for {len(missing)} match(es): "
                   + ", ".join(f"{r['Home Team']} v {r['Away Team']}"
                               for _, r in missing.iterrows())
                   + ". Open 'Every stat found' below to see what the feed calls "
                     "them, or download the raw JSON and send it over.")
    st.subheader("For the report")
    wide(st, table[COLUMNS], hide_index=True)
    st.subheader(f"Every stat, one row per match ({extra_stats} stats)")
    wide(st, table.drop(columns=["status", "found_as"]), hide_index=True)
    st.caption("Both tables are in the CSV. The extra stats are for your own use; "
               "the report reads only the columns in the first.")

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = label if label != "pasted" else f"to_{table['Date'].max()}"
    out = OUT / f"urc_{season}_{stamp}.csv"
    table.to_csv(out, index=False)
    st.download_button("Download CSV", table.to_csv(index=False), file_name=out.name,
                       mime="text/csv")
    st.caption(f"Also saved to {out}. Load it into the report with:\n\n"
               f"`python import_turnovers.py {out.relative_to(Path(__file__).parent)} "
               f"--season {season[:4]}`")

    with st.expander("Every stat found, per match"):
        for match_id, body in raw.items():
            stats = find_stats(body.get("data", body))
            st.markdown(f"**Match {match_id}** - {len(stats)} stats")
            st.dataframe(pd.DataFrame(
                [{"stat": k, "home": v.get("home"), "away": v.get("away")}
                 for k, v in sorted(stats.items())]), hide_index=True)

    with st.expander("Raw JSON, for when a stat is missing"):
        for match_id, body in raw.items():
            st.download_button(f"match_{match_id}.json", json.dumps(body, indent=2),
                               file_name=f"urc_match_{match_id}.json",
                               mime="application/json", key=f"raw_{match_id}")


if __name__ == "__main__":
    main()
