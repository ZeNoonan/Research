"""Generate the team board: attack, defence and net, gameweek by gameweek.

Writes ``teams.html``. The numbers and the ranking rules live in
``teams.py``; this file is the page.

    python build_teams.py
    python build_teams.py --out teams.html
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

import shots as S
import teams as T
from build_site import CSS, esc
from build_shots import EXTRA_CSS

HERE = Path(__file__).parent

SIDE_COPY = {
    "attack": ("Attack", "What a club creates: shots taken, penalty-adjusted "
               "xG and goals scored. Most is best."),
    "defence": ("Defence", "What a club allows: shots conceded, "
                "penalty-adjusted xG conceded and goals conceded. "
                "<b>Fewest is best</b>, so rank 1 is the meanest defence."),
    "net": ("Net &mdash; attack minus defence", "The two combined as a "
            "difference: shots taken minus conceded, xG for minus against, "
            "goals for minus against. A club that outshoots its opponent by "
            "ten ranks above one that edges it by two."),
}

MEASURE_FMT = {"shots": "{:+.0f}", "xg": "{:+.2f}", "goals": "{:+.0f}"}

TEAM_CSS = """
td.gw.rb { background: rgba(179, 55, 47, .10); }
td .opp { display: block; color: var(--muted); font-size: 10px;
  font-weight: 400; line-height: 1.1; white-space: nowrap; }
section.side h2 small { color: var(--muted); font-weight: 400; font-size: 13px; }
@media (prefers-color-scheme: dark) {
  td.gw.rb { background: rgba(239, 122, 114, .14); }
}
"""

# Each section sorts its own tables and switches its own tabs; there is no
# search or filter, since twenty clubs fit on a screen.
TEAM_JS = """
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

function cmp(a, b, i, dir) {
  const va = a.children[i].dataset.v, vb = b.children[i].dataset.v;
  const ea = va === undefined || va === '', eb = vb === undefined || vb === '';
  if (ea || eb) return ea && eb ? 0 : (ea ? 1 : -1);
  const na = parseFloat(va), nb = parseFloat(vb);
  if (!isNaN(na) && !isNaN(nb)) return dir * (na - nb);
  return dir * String(va).localeCompare(String(vb));
}

function sortBy(table, th) {
  const i = $$('th', th.parentNode).indexOf(th);
  const asc = th.dataset.dir !== 'asc';
  $$('th', th.parentNode).forEach(h => h.removeAttribute('data-dir'));
  th.dataset.dir = asc ? 'asc' : 'desc';
  const body = $('tbody', table);
  const rows = $$('tr', body);
  rows.sort((a, b) => cmp(a, b, i, asc ? 1 : -1));
  rows.forEach(r => body.appendChild(r));
  $$('tr', body).forEach((r, n) => { r.children[0].textContent = n + 1; });
}

$$('section.side').forEach(sec => {
  const show = key => {
    $$('.tabs button', sec).forEach(b =>
      b.setAttribute('aria-selected', b.dataset.view === key));
    $$('table.board', sec).forEach(t => { t.hidden = t.dataset.view !== key; });
  };
  $$('.tabs button', sec).forEach(b =>
    b.addEventListener('click', () => show(b.dataset.view)));
  $$('table.board', sec).forEach(t => $$('th:not(.nosort)', t).forEach(th =>
    th.addEventListener('click', () => sortBy(t, th))));
  show('rank');
});
"""


def _rank(v: float) -> str:
    return f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}"


def _tier(rank: float, field: int = 20) -> str:
    if pd.isna(rank):
        return ""
    if rank <= 3:
        return " r1"
    if rank <= 6:
        return " r2"
    if rank > field - 3:
        return " rb"
    return ""


class _Signed:
    """A format that signs a difference but leaves a dead level as plain 0."""

    def __init__(self, spec: str):
        self.spec = spec

    def format(self, v: float) -> str:
        s = self.spec.format(v)
        return s[1:] if s.lstrip("+-").strip("0.") == "" else s


def _fmt(key: str):
    """How a measure's value is printed: differences carry their sign."""
    base = key.split("_")[0]
    if key.endswith("_diff"):
        return _Signed(MEASURE_FMT[base])
    return "{:.2f}" if base == "xg" else "{:.0f}"


def cell_notes(ranked: pd.DataFrame, side: str) -> dict:
    """Tooltip per (club, gameweek): opponent, and every measure with its rank."""
    out = {}
    for r in ranked.itertuples():
        venue = {"H": "home", "A": "away"}.get(r.venue, r.venue)
        parts = []
        for key, name, _ in T.SIDES[side]:
            v, rk = getattr(r, key), getattr(r, f"rank_{key}")
            if pd.isna(v):
                parts.append(f"{name}: not computable (double gameweek)")
            else:
                parts.append(f"{name} {_fmt(key).format(v)} (rank {_rank(rk)})")
        tail = ("" if pd.isna(r.rank_sum)
                else f" · ranks sum to {_rank(r.rank_sum)} of {3 * r.field}")
        out[(r.team, r.gw)] = (f"GW{r.gw} v {r.opponent} ({venue}): "
                               + " · ".join(parts) + tail)
    return out


def _opp(row, g) -> str:
    opp, ven = row.get(f"opp_gw{g}"), row.get(f"venue_gw{g}")
    if pd.isna(opp):
        return ""
    return f'<span class="opp">{esc(opp)} ({esc(ven)})</span>'


def table_html(side: str, table: pd.DataFrame, view: str, gameweeks: list,
               notes: dict, pens: dict) -> str:
    """One view of one side: the composite, or a single measure."""
    if view == "rank":
        table = table.sort_values(["average", "total"])
        heads_tail = ['<th class="num tot">Total</th>',
                      '<th class="num" data-dir="asc">Avg</th>']
    else:
        key, name, direction = next(m for m in T.SIDES[side] if m[0] == view)
        table = table.sort_values(f"{key}_total", ascending=direction < 0)
        arrow = "asc" if direction < 0 else "desc"
        heads_tail = [f'<th class="num tot" data-dir="{arrow}">Season</th>']

    heads = ['<th class="nosort">#</th>', '<th>Club</th>']
    heads += [f'<th class="num">GW{g}</th>' for g in gameweeks]
    heads += heads_tail

    rows = []
    for n, r in enumerate(table.to_dict("records"), 1):
        cells = [f'<td class="rowno">{n}</td>',
                 f'<td data-v="{esc(r["team"])}"><b>{esc(r["team"])}</b></td>']
        for g in gameweeks:
            note = esc(notes.get((r["team"], g), ""))
            if view == "rank":
                v = r[f"gw{g}"]
                if pd.isna(v):
                    cells.append(f'<td class="dnp" data-v="" title="{note}">'
                                 f'&mdash;{_opp(r, g)}</td>')
                    continue
                cells.append(f'<td class="gw{_tier(v)}" data-v="{v:.0f}" '
                             f'title="{note}">{v:.0f}{_opp(r, g)}</td>')
            else:
                v, rk = r[f"{view}_gw{g}"], r[f"{view}_rank_gw{g}"]
                if pd.isna(v):
                    cells.append(f'<td class="dnp" data-v="" title="{note}">'
                                 f'&mdash;{_opp(r, g)}</td>')
                    continue
                pen = " pen" if view.startswith("xg") and pens.get((r["team"], g)) else ""
                cells.append(
                    f'<td class="gw{_tier(rk)}{pen}" data-v="{v:.4f}" title="{note}">'
                    f'{_fmt(view).format(v)} <span class="rk">({_rank(rk)})</span>'
                    f'{_opp(r, g)}</td>')
        if view == "rank":
            cells.append(f'<td class="num tot" data-v="{r["total"]:.0f}">'
                         f'{r["total"]:.0f}</td>')
            cells.append(f'<td class="num" data-v="{r["average"]:.3f}">'
                         f'<b>{r["average"]:.1f}</b></td>')
        else:
            tot = r[f"{view}_total"]
            cells.append(f'<td class="num tot" data-v="{tot:.4f}">'
                         f'<b>{_fmt(view).format(tot)}</b></td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")

    hidden = "" if view == "rank" else " hidden"
    return (f'<table class="board" data-view="{view}"{hidden}>'
            f'<thead><tr>{"".join(heads)}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def side_section(side: str, wk: pd.DataFrame) -> str:
    ranked = T.rank_side(wk, side)
    table = T.board(ranked)
    gws = [int(g) for g in wk.attrs["gameweeks"]]
    notes = cell_notes(ranked, side)
    # The penalty marker follows the side whose xG it came off: a club's own
    # kicks on attack, its opponent's on defence, both on net.
    pk = {("attack",): "pkatt_for", ("defence",): "pkatt_against"}
    if side == "net":
        pens = {(t, g): (a or 0) + (b or 0) for t, g, a, b in
                zip(wk["team"], wk["gw"], wk["pkatt_for"], wk["pkatt_against"])}
    else:
        col = pk[(side,)]
        pens = dict(zip(zip(wk["team"], wk["gw"]), wk[col].fillna(0)))

    title, blurb = SIDE_COPY[side]
    tabs = ['<button data-view="rank" aria-selected="true">Composite ranking</button>']
    tabs += [f'<button data-view="{k}" aria-selected="false">{esc(n)}</button>'
             for k, n, _ in T.SIDES[side]]
    tables = table_html(side, table, "rank", gws, notes, pens) + "".join(
        table_html(side, table, k, gws, notes, pens) for k, _, _ in T.SIDES[side])
    return f"""
<section class="side" id="{side}"><h2>{title}</h2>
<p class="note">{blurb}</p>
<div class="tabs">{''.join(tabs)}</div>
<div class="tablewrap">{tables}</div>
</section>"""


def build(out: Path) -> None:
    wk = T.team_weeks()
    audit = wk.attrs["audit"]
    print(audit)
    gws = [int(g) for g in wk.attrs["gameweeks"]]
    gw_list = ", ".join(f"GW{g}" for g in gws)

    sections = "".join(side_section(s, wk) for s in T.SIDES)

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FPL — team attack and defence by gameweek</title>
<style>{CSS}{EXTRA_CSS}{TEAM_CSS}</style></head><body><div class="wrap">
<header><h1>Team attack &amp; defence &mdash; by gameweek</h1>
<p class="sub">Every club, ranked each gameweek on shots, penalty-adjusted
xG and goals &mdash; for, against, and the difference between the two.</p>
</header>

<div class="banner">Covering <b>{esc(gw_list)}</b> &middot; <b>20</b> clubs
&middot; shots from <b>fbref</b>, expected goals from the <b>FPL API</b>,
goals from the <b>results file</b> the handicap app keeps. Every penalty
attempt costs <b>{S.PENALTY_XG:.2f} xG</b>.
<a href="#attack" style="color:var(--accent2)">Attack</a> &middot;
<a href="#defence" style="color:var(--accent2)">Defence</a> &middot;
<a href="#net" style="color:var(--accent2)">Net</a> &middot;
<a href="shots.html" style="color:var(--accent2)">Player shots board &rarr;</a>
<a href="defcon.html" style="color:var(--accent2)">Defcon board &rarr;</a></div>

<section><h2>Read this first</h2>
<p class="note"><b>Three measures each way.</b> <b>Attack</b> is shots
taken, penalty-adjusted xG and goals scored. <b>Defence</b> is the same three
conceded. <b>Net</b> is attack minus defence &mdash; shot difference, xG
difference and goal difference &mdash; the one view that says who is
winning the matches rather than just busy in them.</p>

<p class="note"><b>How the ranking works.</b> Within a gameweek each measure
is ranked across the twenty clubs &mdash; most is best on attack and net,
<b>fewest is best on defence</b> &mdash; with ties sharing the mean rank.
The three ranks are added and the sum re-ranked 1 to 20: that is the cell on
each <b>Composite ranking</b> tab. The other tabs show the raw number with
its own rank in brackets. Under every cell is the opponent and whether the
club was at home (H) or away (A); hover for the full breakdown.</p>

<p class="note"><b>Avg and Total.</b> The tables open sorted on
<b>Avg</b>, the mean composite rank. Every club has played every gameweek
so far, so Total &mdash; the ranks summed &mdash; puts them in the same
order; the two would only part company after a blank gameweek, when Total
charges the missed week last place and Avg does not.</p>

<p class="note"><b>Where each number comes from.</b> <b>Shots</b> are
fbref's, summed by club inside each cumulative sheet and then differenced
week to week, so a player who changed club leaves his shots with the club
he took them for. <b>xG</b> is FPL's, summed by the club each player
<i>played for in that fixture</i> &mdash; not FPL's club column, which is
where he plays now and would hand the movers' early-season chances to
their new clubs ({wk.attrs['moved_rows']} player-weeks so far, listed in the
audit). <b>Goals</b> come from the results file, not fbref: fbref
counts goals by players, so it misses own goals &mdash;
{wk.attrs['own_goals']} of the {int(wk['goals_for'].sum())} so far, each one
the difference between fbref and the score in its match.</p>

<p class="note"><b>Penalties.</b> The rule the player boards use: every
attempt costs the club that took it 0.75 xG in that gameweek, and so comes
off its opponent's xG conceded too. Weeks it applied are marked with a
small red <b style="color:#b3372f">p</b> on the xG tabs. Goals are left as
scored.</p>

<p class="note"><b>Conceded is the opponent's for.</b> xG and goals are per
match, so that is exact. fbref's shots are only per gameweek, so if an
opponent ever plays twice in one gameweek its weekly shots cannot be split
between the two matches, and that club's shots conceded will show a blank
rather than a wrong number. No club has had a double or a blank yet.</p>

<p class="legend"><span class="key" style="background:rgba(0,160,90,.18)">
</span>top 3 that gameweek &nbsp;
<span class="key" style="background:rgba(0,160,90,.08)"></span>4th&ndash;6th
&nbsp; <span class="key" style="background:rgba(179,55,47,.10)"></span>bottom
3 &nbsp; <b style="color:#b3372f">p</b> penalty taken that week</p>
</section>
{sections}

<section><h2>How the sources were reconciled</h2>
<p class="note">Three sources describe the same fifty matches, so they are
checked against each other before anything is ranked. The verdict comes
first; anything that disagrees is named here rather than quietly used.
Beyond the lines below, the board is conserved: every shot, xG, goal and
penalty counted <i>for</i> one club is counted <i>against</i> its opponent,
and the three differences sum to zero across the league every week.</p>
<pre class="audit">{esc(audit)}</pre>
</section>

<footer>Built {date.today().isoformat()} &middot; shots: fbref &middot;
expected goals: the FPL API &middot; goals: premier_league_handicap
results</footer>
</div><script>{TEAM_JS}</script></body></html>
"""
    out.write_text(page, encoding="utf-8")
    print(f"\nwrote {out} — 20 clubs, {len(gws)} gameweeks")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=HERE / "teams.html", type=Path)
    build(ap.parse_args().out)


if __name__ == "__main__":
    main()
