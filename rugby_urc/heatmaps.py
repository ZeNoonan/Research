"""Club x round heatmaps for the two running factor columns.

Renders season-to-date cover (STDC) and power rating as one cell per club per
round, on a **diverging** scale: one hue per direction with a neutral grey at
zero, so "which side of nothing is this" is the thing the eye reads first.

The NFL project uses a red-yellow-green ramp here. This one does not: a hue at
the midpoint reads as a third category rather than as zero, and green/red alone
is the least colour-vision-safe pair available. Blue (positive) against red
(negative) through neutral grey carries the same meaning and separates under
every simulated deficiency.

Both modes are supplied, because the page they sit in has a dark theme and a
ramp cannot simply be flipped.
"""

from __future__ import annotations

import pandas as pd

# Diverging poles and the neutral midpoint, per mode.
SCALES = {
    "light": {"neg": (0xE3, 0x49, 0x48), "mid": (0xF0, 0xEF, 0xEC), "pos": (0x2A, 0x78, 0xD6)},
    "dark":  {"neg": (0xE6, 0x67, 0x67), "mid": (0x38, 0x38, 0x35), "pos": (0x39, 0x87, 0xE5)},
}


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def colour(value: float, cap: float, mode: str = "light") -> tuple[str, str]:
    """(background, text) for a cell, scaled against ``cap``.

    Text flips to white once the background is dark enough to need it, so a
    strongly coloured cell stays readable rather than relying on the ramp being
    gentle.
    """
    scale = SCALES[mode]
    if pd.isna(value) or cap <= 0:
        return _hex(scale["mid"]), "inherit"
    t = max(-1.0, min(1.0, float(value) / cap))
    rgb = _lerp(scale["mid"], scale["pos" if t >= 0 else "neg"], abs(t))
    # Rec. 601 luma: good enough to decide black vs white ink.
    luma = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255
    return _hex(rgb), ("#ffffff" if luma < 0.55 else "#0b0b0b")


def club_round_pivot(report: pd.DataFrame, value: str) -> pd.DataFrame:
    """Club x round table of ``home_<value>`` / ``away_<value>``.

    Sorted by each club's season mean so the table reads top-to-bottom as
    strongest to weakest.
    """
    long = pd.concat([
        report[["round", "home", f"home_{value}"]]
            .rename(columns={"home": "club", f"home_{value}": value}),
        report[["round", "away", f"away_{value}"]]
            .rename(columns={"away": "club", f"away_{value}": value}),
    ])
    long = long.dropna(subset=["club", value])
    if long.empty:
        return pd.DataFrame()
    pivot = long.pivot_table(index="club", columns="round", values=value, aggfunc="last")
    return pivot.loc[pivot.mean(axis=1).sort_values(ascending=False).index]


def heatmap_html(pivot: pd.DataFrame, *, decimals: int, caption: str) -> str:
    """A heatmap table, carrying its own light and dark cell colours.

    Each cell ships both modes as custom properties and the stylesheet picks
    one, so the table does not have to be re-rendered when the theme changes.
    """
    if pivot.empty:
        return f'<p class="empty">{caption}: nothing to show yet.</p>'
    cap = float(pd.to_numeric(pivot.stack(), errors="coerce").abs().quantile(0.95)) or 1.0

    head = "".join(f"<th>{int(c)}</th>" for c in pivot.columns)
    rows = []
    for club, series in pivot.iterrows():
        cells = []
        for v in series:
            if pd.isna(v):
                cells.append('<td class="na"></td>')
                continue
            lbg, lfg = colour(v, cap, "light")
            dbg, dfg = colour(v, cap, "dark")
            cells.append(
                f'<td style="--lbg:{lbg};--lfg:{lfg};--dbg:{dbg};--dfg:{dfg}">'
                f'{v:+.{decimals}f}</td>')
        rows.append(f"<tr><th>{club}</th>{''.join(cells)}</tr>")
    return (f'<figure class="heat"><figcaption>{caption}</figcaption>'
            f'<div class="scroll"><table><thead><tr><th>Club</th>{head}</tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table></div></figure>")
