"""Team x week heatmaps for the season-to-date cover and power factors.

For one season's report, build a pivot of one value per team per week:

* **STDC** — each team's season-to-date cover entering that week (the value the
  model uses; positive = "fat", a team that has been covering; negative =
  "hungry"). This is the same number shown in the game table.
* **Power** — each team's power rating that week.

Each pivot renders as a static HTML heatmap (one ``<td>`` per cell, coloured on
a red-yellow-green diverging scale centred at zero), teams sorted by their
season mean so the table reads strong-to-weak top to bottom. No JavaScript.
"""

from __future__ import annotations

import pandas as pd

# Red-Yellow-Green diverging anchors (ColorBrewer RdYlGn 3-class).
_NEG = (0xD7, 0x30, 0x27)   # red    -> most negative
_MID = (0xFF, 0xFF, 0xBF)   # pale   -> zero
_POS = (0x1A, 0x98, 0x50)   # green  -> most positive


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> str:
    t = max(0.0, min(1.0, t))
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def colour(value: float, cap: float) -> str:
    """Diverging colour for ``value`` on a symmetric scale ``[-cap, +cap]``."""
    if pd.isna(value) or cap == 0:
        return "#ffffff"
    if value >= 0:
        return _lerp(_MID, _POS, value / cap)
    return _lerp(_MID, _NEG, -value / cap)


def team_week_pivot(report: pd.DataFrame, value: str) -> pd.DataFrame:
    """Pivot teams (rows) x week (cols) for ``value`` in {'stdc', 'power'}."""
    long = pd.concat([
        report[["week", "home", f"home_{value}"]]
        .rename(columns={"home": "team", f"home_{value}": value}),
        report[["week", "away", f"away_{value}"]]
        .rename(columns={"away": "team", f"away_{value}": value}),
    ])
    pivot = long.pivot_table(index="team", columns="week", values=value, aggfunc="first")
    order = pivot.mean(axis=1, skipna=True).sort_values(ascending=False).index
    return pivot.loc[order]


def heatmap_html(pivot: pd.DataFrame, *, decimals: int) -> str:
    """Render a team x week pivot as a coloured HTML table."""
    weeks = list(pivot.columns)
    cap = float(pivot.abs().max().max()) or 1.0
    head = "".join(f"<th>{w}</th>" for w in weeks)

    body = []
    for team, row in pivot.iterrows():
        cells = [f'<td class="l">{team}</td>']
        for w in weeks:
            v = row[w]
            if pd.isna(v):
                cells.append('<td class="hm na"></td>')
            else:
                txt = f"{v:.{decimals}f}" if decimals else f"{int(round(v))}"
                cells.append(
                    f'<td class="hm" style="background:{colour(v, cap)}">{txt}</td>')
        body.append(f"<tr>{''.join(cells)}</tr>")

    return (
        '<div class="tablewrap"><table class="heat">'
        f'<thead><tr><th class="l">Team</th>{head}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )
