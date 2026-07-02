"""Generate value_explainer.html — a visual walkthrough of the Value factor.

Follows one team (Michigan State, the 2019 East 2 seed stuck behind Duke)
through the whole 'Slot calculations' Value pipeline of Aaron Brown's
spreadsheet: slots, the favorite baseline, expected points given up, the
variance-difference formula term by term, the cumulative ratio and the
Value/BAB flags — then what the trade is worth at different pool sizes.

Every number on the page is computed here from data/model_2019.json via
extract_model.py (fixed mode, default round points 2/3/5/8/13/21, pool of
100). Charts are inline SVG, self-contained, light/dark aware.

Rebuild: python3 extract_model.py && python3 build_explainer.py
"""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import extract_model as em

HERE = Path(__file__).parent
OUT = HERE / "value_explainer.html"

ROUNDS = em.ROUNDS
RLABEL = ["Round of 64", "Round of 32", "Sweet 16", "Elite 8", "Final 4", "Champion"]

# ---------------------------------------------------------------- model data

wb_f, wb_v = em.load()
MODEL = em.extract(wb_v)
FIX = em.slot_calcs(MODEL, "fixed")
T = MODEL["teams"]
POINTS = MODEL["points"]
MSU = next(i for i, t in enumerate(T) if t["name"] == "Michigan State")
DUKE = 0
UVA = next(i for i, t in enumerate(T) if t["name"] == "Virginia")


def slot_group(i, k):
    size = 2 ** (k + 1)
    g = (i // size) * size
    return list(range(g, g + size))


def favorite(i, k):
    grp = slot_group(i, k)
    return max(grp, key=lambda j: T[j]["prob"][k])


def walkthrough(i):
    """Every intermediate quantity for team i, per round."""
    s, t = FIX[i], T[i]
    rows = []
    for k in range(6):
        fav = favorite(i, k)
        rows.append({
            "round": ROUNDS[k], "rlabel": RLABEL[k], "pts": POINTS[k],
            "p": t["prob"][k], "f": t["freq"][k],
            "fav": T[fav]["name"], "isFav": fav == i,
            "p0": s["p0"][k], "f0": s["p0f0"][k] / s["p0"][k], "S": s["S"][k],
            "dEV": s["expDiff"][k], "dVar": s["varDiff"][k],
            "cumEV": s["cumExp"][k], "cumVar": s["cumVar"][k],
            "ratio": s["ratio"][k], "value": s["value"][k], "bab": s["bab"][k],
            "groupSize": 2 ** (k + 1),
        })
    return rows


WALK = walkthrough(MSU)
E8 = WALK[3]

# E8 variance-difference term decomposition (unit points, before x pts^2)
_p, _p0, _S, _f = E8["p"], E8["p0"], E8["S"], E8["f"]
_p0f0 = _p0 * E8["f0"]
TERM1 = (_p - _p0) * (1 + 2 * _S)      # win less often, weighted by crowd level
TERM2 = _p0 ** 2 - _p ** 2             # second-order probability correction
TERM3 = 2 * (_p0f0 - _p * _f)          # separation from the crowd
TTOT = TERM1 + TERM2 + TERM3
assert abs(TTOT * E8["pts"] ** 2 - E8["dVar"]) < 1e-9

# Champion column: p vs f for the most-picked teams
c6_order = sorted(range(64), key=lambda i: -T[i]["freq"][5])[:9]
C6ROWS = [{"name": T[i]["name"], "p": T[i]["prob"][5], "f": T[i]["freq"][5],
           "value": FIX[i]["value"][5], "i": i} for i in c6_order]

# Frontier scatter (champion column): x = EV given up, y = variance gained
FRONTIER = [{"name": T[i]["name"], "seed": T[i]["seed"],
             "x": -FIX[i]["cumExp"][5], "y": FIX[i]["cumVar"][5],
             "value": FIX[i]["value"][5]} for i in range(64)]
LABELED = {"Duke", "Virginia", "Gonzaga", "North Carolina", "Kentucky",
           "Michigan State", "Michigan", "Texas Tech", "Virginia Tech",
           "Tennessee", "Houston"}

# Brackets for the payoff section --------------------------------------------
BASE = [t["picks"][:] for t in T]
UVA_B = [r[:] for r in BASE]
UVA_B[DUKE][5] = 0
UVA_B[UVA][5] = 1
MSU_B = [r[:] for r in BASE]
for k in range(1, 6):
    for j in slot_group(MSU, k):
        MSU_B[j][k] = 0
    MSU_B[MSU][k] = 1

BRACKETS = [("Sheet default (Duke champion)", BASE, "gray"),
            ("Same bracket, Virginia champion", UVA_B, "blue"),
            ("Same bracket, Michigan St wins it all", MSU_B, "aqua")]

NS = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000]


def winprob(picks, n):
    return em.win_probability({**MODEL, "poolSize": n}, FIX, picks)


CURVES = []
for label, b, color in BRACKETS:
    wp = winprob(b, 100)
    CURVES.append({"label": label, "color": color,
                   "mean": wp["youMean"], "sd": math.sqrt(wp["youVar"]),
                   "mult": [winprob(b, n)["winProb"] * n for n in NS]})
FIELD = winprob(BASE, 100)
FIELD_MEAN, FIELD_SD = FIELD["fieldMean"], math.sqrt(FIELD["fieldVar"])

# crossover pool size where the MSU bracket overtakes the default
def _cross():
    lo, hi = 1000, 2000
    for _ in range(40):
        mid = (lo + hi) / 2
        d = winprob(MSU_B, mid)["winProb"] - winprob(BASE, mid)["winProb"]
        if d > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


CROSS_N = _cross()

# thresholds: deviation needed to top a pool of N (chart E)
TH100 = em.norm_inv(1 - 1 / 100) * FIELD_SD
TH2000 = em.norm_inv(1 - 1 / 2000) * FIELD_SD

DUKE_W, MSU_W = walkthrough(DUKE), walkthrough(MSU)

# ------------------------------------------------------------- svg utilities

FONT = 'system-ui,-apple-system,"Segoe UI",sans-serif'


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def txt(x, y, s, size=11, anchor="start", fill="var(--ink-2)", weight="", extra=""):
    w = f' font-weight="{weight}"' if weight else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" '
            f'text-anchor="{anchor}" fill="{fill}"{w} '
            f'font-family=\'{FONT}\' {extra}>{esc(s)}</text>')


def hline(x1, x2, y, color="var(--grid)", w=1):
    return f'<line x1="{x1:.1f}" x2="{x2:.1f}" y1="{y:.1f}" y2="{y:.1f}" stroke="{color}" stroke-width="{w}"/>'


def vline(x, y1, y2, color="var(--grid)", w=1):
    return f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y1:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{w}"/>'


def hbar(x0, x1, y, h, fill, tip=""):
    """Horizontal bar from x0 to x1: 4px rounded data-end, square baseline."""
    r = min(4.0, abs(x1 - x0))
    tipattr = f' data-tip="{esc(tip)}"' if tip else ""
    if x1 >= x0:
        d = (f"M{x0:.1f},{y:.1f} H{x1 - r:.1f} q{r:.1f},0 {r:.1f},{r:.1f} "
             f"V{y + h - r:.1f} q0,{r:.1f} -{r:.1f},{r:.1f} H{x0:.1f} Z")
    else:
        d = (f"M{x0:.1f},{y:.1f} H{x1 + r:.1f} q-{r:.1f},0 -{r:.1f},{r:.1f} "
             f"V{y + h - r:.1f} q0,{r:.1f} {r:.1f},{r:.1f} H{x0:.1f} Z")
    return f'<path d="{d}" fill="{fill}"{tipattr}/>'


def vbar(x, w, y0, y1, fill, tip=""):
    """Column between baseline y0 and value y1: rounded at the data end."""
    r = min(4.0, abs(y1 - y0))
    tipattr = f' data-tip="{esc(tip)}"' if tip else ""
    if y1 <= y0:  # grows upward
        d = (f"M{x:.1f},{y0:.1f} V{y1 + r:.1f} q0,-{r:.1f} {r:.1f},-{r:.1f} "
             f"H{x + w - r:.1f} q{r:.1f},0 {r:.1f},{r:.1f} V{y0:.1f} Z")
    else:  # grows downward
        d = (f"M{x:.1f},{y0:.1f} V{y1 - r:.1f} q0,{r:.1f} {r:.1f},{r:.1f} "
             f"H{x + w - r:.1f} q{r:.1f},0 {r:.1f},-{r:.1f} V{y0:.1f} Z")
    return f'<path d="{d}" fill="{fill}"{tipattr}/>'


def legend(items, x, y):
    parts, cx = [], x
    for label, color in items:
        parts.append(f'<circle cx="{cx + 5}" cy="{y - 4}" r="5" fill="{color}"/>')
        parts.append(txt(cx + 15, y, label, 11.5))
        cx += 15 + len(label) * 6.6 + 22
    return "".join(parts)


def svg(w, h, body, title):
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}" '
            f'style="width:100%;height:auto;display:block">{body}</svg>')


def table_view(headers, rows, summary="Table view"):
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    trs = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>"
                  for r in rows)
    return (f'<details class="tv"><summary>{summary}</summary>'
            f'<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></details>')


def pct(x, dp=1):
    return f"{100 * x:.{dp}f}%"


# ------------------------------------------------------------------- chart A

def chart_a():
    left, right, top = 118, 132, 34
    W = 820
    pw = W - left - right
    bh, pitch = 13, 44
    H = top + pitch * len(C6ROWS) + 30
    xmax = 0.45
    X = lambda v: left + v / xmax * pw
    b = [legend([("win probability (model)", "var(--s-blue)"),
                 ("picked as champion (pools)", "var(--s-aqua)")], left, 16)]
    b.append(txt(W - right + 14, 16, "picked ÷ prob", 10.5, "start", "var(--ink-3)"))
    for gx in [0, .1, .2, .3, .4]:
        b.append(vline(X(gx), top - 6, H - 24))
        b.append(txt(X(gx), H - 10, f"{int(gx * 100)}%", 10.5, "middle", "var(--ink-3)"))
    for r_i, r in enumerate(C6ROWS):
        y = top + r_i * pitch
        name = r["name"]
        b.append(txt(left - 8, y + bh + 2, name, 12, "end", "var(--ink-1)",
                     "600" if name in ("Duke", "Michigan State", "Virginia") else ""))
        b.append(hbar(left, X(r["p"]), y, bh, "var(--s-blue)",
                      f"{name} — win probability {pct(r['p'])}"))
        b.append(txt(X(r["p"]) + 5, y + bh - 2.5, pct(r["p"]), 10.5, "start", "var(--ink-2)"))
        y2 = y + bh + 2  # 2px surface gap between the pair
        b.append(hbar(left, X(r["f"]), y2, bh, "var(--s-aqua)",
                      f"{name} — picked as champion in {pct(r['f'])} of pools"))
        b.append(txt(X(r["f"]) + 5, y2 + bh - 2.5, pct(r["f"]), 10.5, "start", "var(--ink-2)"))
        ratio = r["f"] / r["p"]
        note = f"{ratio:.1f}×"
        b.append(txt(W - right + 14, y + bh + 2, note, 11.5, "start",
                     "var(--ink-2)", "600" if ratio > 1.2 or ratio < 0.8 else ""))
        if r["value"]:
            b.append(txt(W - right + 60, y + bh + 2, "★ value", 10.5, "start", "var(--gold)"))
    body = svg(W, H, "".join(b),
               "Champion column: model win probability vs how often pools pick each team")
    tbl = table_view(
        ["Team", "Win probability", "Picked as champion", "picked ÷ prob", "Value pick"],
        [[r["name"], pct(r["p"]), pct(r["f"]), f"{r['f'] / r['p']:.2f}",
          "yes" if r["value"] else "no"] for r in C6ROWS])
    return body + tbl


# ------------------------------------------------------------------- chart B

def chart_b():
    """Slot anatomy: the 16 East teams; per round, the group MSU must win."""
    W, left = 820, 96
    cell, gap = 42, 3
    grid_w = 16 * cell + 15 * gap
    top = 46
    b = []
    for j in range(16):
        t = T[j]
        x = left + j * (cell + gap)
        hero = j == MSU
        duke = j == DUKE
        fill = "var(--s-aqua)" if hero else ("var(--s-blue)" if duke else "var(--cell)")
        b.append(f'<rect x="{x}" y="{top}" width="{cell}" height="30" rx="4" fill="{fill}"/>')
        ink = "#ffffff" if (hero or duke) else "var(--ink-2)"
        b.append(txt(x + cell / 2, top + 19, t["seed"], 12, "middle", ink, "600"))
        nm = {"Michigan State": "Mich St", "Virginia Tech": "Va Tech",
              "Mississippi State": "Miss St", "Saint Louis": "St Louis"}.get(
                  t["name"], t["name"].split("/")[0])
        b.append(f'<g transform="translate({x + cell / 2:.0f},{top - 6}) rotate(-38)">'
                 + txt(0, 0, nm, 9.5, "start", "var(--ink-3)") + "</g>")
    y = top + 44
    for k in range(6):
        grp = slot_group(MSU, k)
        east = [j for j in grp if j < 16]
        x0 = left + east[0] * (cell + gap)
        x1 = left + east[-1] * (cell + gap) + cell
        fav = favorite(MSU, k)
        b.append(txt(left - 10, y + 11, ROUNDS[k], 11.5, "end", "var(--ink-1)", "600"))
        b.append(f'<rect x="{x0}" y="{y}" width="{x1 - x0}" height="15" rx="4" '
                 f'fill="var(--s-blue)" opacity="0.16"/>')
        b.append(vline(x0, y, y + 15, "var(--s-blue)", 2))
        b.append(vline(x1, y, y + 15, "var(--s-blue)", 2))
        extra = {4: "  + the 16 West teams", 5: "  + the other 48 teams"}.get(k, "")
        lbl = (f"{2 ** (k + 1)} teams · favorite: {T[fav]['name']} "
               f"(p₀ {T[fav]['prob'][k]:.2f}){extra}")
        b.append(txt(grid_w + left + 12, y + 12, lbl, 11, "start", "var(--ink-2)"))
        y += 24
    H = y + 8
    return svg(1240, H, "".join(b),
               "The six slots Michigan State must win, and each slot's favorite")


# ------------------------------------------------------------------- chart C

def chart_c():
    W, left, right = 820, 66, 24
    pw = W - left - right
    col_w, n = 24, 6
    pitch = pw / n
    b = []
    # panel 1: cumulative EV given up (<=0)
    t1, h1 = 30, 120
    ev_min = -8.5
    Y1 = lambda v: t1 + (0 - v) / (0 - ev_min) * h1
    b.append(txt(left, 18, "Expected points given up (cumulative)  — picking Michigan St over each slot favorite",
                 12, "start", "var(--ink-1)", "600"))
    for gv in [0, -4, -8]:
        b.append(hline(left, W - right, Y1(gv)))
        b.append(txt(left - 8, Y1(gv) + 4, f"{gv:+d}" if gv else "0", 10.5, "end", "var(--ink-3)"))
    for k, r in enumerate(WALK):
        x = left + pitch * k + (pitch - col_w) / 2
        if r["cumEV"] < 0:
            b.append(vbar(x, col_w, Y1(0), Y1(r["cumEV"]), "var(--s-red)",
                          f"{r['round']}: {r['cumEV']:+.2f} points vs favorite"))
            b.append(txt(x + col_w / 2, Y1(r["cumEV"]) + 14, f"{r['cumEV']:+.2f}",
                         10.5, "middle", "var(--ink-2)"))
        else:
            b.append(txt(x + col_w / 2, Y1(0) + 14, "0 — favorite", 10, "middle", "var(--ink-3)"))
    # panel 2: cumulative variance gained
    t2 = t1 + h1 + 52
    h2 = 130
    b.append(txt(left, t2 - 12, "Variance gained (cumulative)", 12, "start", "var(--ink-1)", "600"))
    vmax = 70.0
    Y2 = lambda v: t2 + h2 - v / vmax * h2
    for gv in [0, 30, 60]:
        b.append(hline(left, W - right, Y2(gv)))
        b.append(txt(left - 8, Y2(gv) + 4, f"+{gv}" if gv else "0", 10.5, "end", "var(--ink-3)"))
    for k, r in enumerate(WALK):
        x = left + pitch * k + (pitch - col_w) / 2
        if r["cumVar"] > 0:
            b.append(vbar(x, col_w, Y2(0), Y2(r["cumVar"]), "var(--s-blue)",
                          f"{r['round']}: {r['cumVar']:+.2f} variance vs picking the favorite"))
            b.append(txt(x + col_w / 2, Y2(r["cumVar"]) - 6, f"+{r['cumVar']:.1f}",
                         10.5, "middle", "var(--ink-2)"))
    # shared x labels + ratio chips
    yx = t2 + h2 + 20
    for k, r in enumerate(WALK):
        xc = left + pitch * k + pitch / 2
        b.append(txt(xc, yx, r["round"], 11.5, "middle", "var(--ink-1)", "600"))
        chip = "favorite → ★" if r["isFav"] else f"ratio {r['ratio']:.1f} ≤ −1 → ★"
        b.append(txt(xc, yx + 17, chip, 10, "middle",
                     "var(--gold)" if r["value"] else "var(--ink-3)", "600"))
    H = yx + 30
    body = svg(W, H, "".join(b),
               "Michigan State cumulative expected points given up and variance gained, by round")
    tbl = table_view(
        ["Round", "cum ΔEV (pts)", "cum ΔVar", "ratio", "Value?"],
        [[r["round"], f"{r['cumEV']:+.2f}", f"{r['cumVar']:+.2f}",
          "0 (favorite)" if r["isFav"] else f"{r['ratio']:.2f}",
          "★" if r["value"] else "—"] for r in WALK])
    return body + tbl


# ------------------------------------------------------------------- chart D

def chart_d():
    W, left, right = 820, 60, 20
    pw = W - left - right
    labels = [("you win less often", TERM1, "(p−p₀)(1+2S)"),
              ("probability² correction", TERM2, "p₀²−p²"),
              ("you leave the crowd", TERM3, "2(p₀f₀−pf)"),
              ("net, per point²", TTOT, "×8² pts → +23.5")]
    vmax, vmin = 0.85, -0.65
    top, ph = 30, 190
    Y = lambda v: top + (vmax - v) / (vmax - vmin) * ph
    n = len(labels)
    pitch = pw / n
    col_w = 24
    b = []
    for gv in [-0.6, -0.3, 0, 0.3, 0.6]:
        b.append(hline(left, W - right, Y(gv), "var(--grid)" if gv else "var(--axis)"))
        b.append(txt(left - 8, Y(gv) + 4, f"{gv:+.1f}" if gv else "0", 10.5, "end", "var(--ink-3)"))
    run = 0.0
    for j, (name, v, formula) in enumerate(labels):
        x = left + pitch * j + (pitch - col_w) / 2
        total = j == n - 1
        y0, y1 = (Y(0), Y(v)) if total else (Y(run), Y(run + v))
        fill = "var(--ink-3)" if total else ("var(--s-blue)" if v > 0 else "var(--s-red)")
        b.append(vbar(x, col_w, y0, y1, fill, f"{name}: {v:+.3f}"))
        vy = min(y0, y1) - 7 if (v > 0 or total) else max(y0, y1) + 15
        b.append(txt(x + col_w / 2, vy, f"{v:+.3f}", 11, "middle", "var(--ink-1)", "600"))
        if not total:
            run += v
            nx = left + pitch * (j + 1) + (pitch - col_w) / 2
            b.append(hline(x + col_w, nx, Y(run), "var(--axis)"))
        yb = top + ph + 20
        b.append(txt(x + col_w / 2, yb, name, 11, "middle", "var(--ink-1)"))
        b.append(txt(x + col_w / 2, yb + 15, formula, 10, "middle", "var(--ink-3)"))
    H = top + ph + 52
    body = svg(W, H, "".join(b),
               "Waterfall: the three terms of Michigan State's Elite-8 variance difference")
    tbl = table_view(["Term", "Formula", "Value"],
                     [[n_, f_, f"{v:+.4f}"] for n_, v, f_ in labels])
    return body + tbl


# ------------------------------------------------------------------- chart E

def chart_e():
    W, left, right = 820, 56, 20
    pw = W - left - right
    top, ph = 46, 190
    x_lo, x_hi = -60, 75
    X = lambda v: left + (v - x_lo) / (x_hi - x_lo) * pw
    chalk = CURVES[0]
    hero = CURVES[2]
    ymax = 1 / (min(chalk["sd"], hero["sd"]) * math.sqrt(2 * math.pi)) * 1.06
    Y = lambda d: top + ph - d / ymax * ph

    def norm_pdf(x, mu, sd):
        return math.exp(-((x - mu) ** 2) / (2 * sd * sd)) / (sd * math.sqrt(2 * math.pi))

    def curve_path(mu, sd, close_from=None):
        pts = []
        steps = 160
        for s_i in range(steps + 1):
            xv = x_lo + (x_hi - x_lo) * s_i / steps
            if close_from is not None and xv < close_from:
                continue
            pts.append((X(xv), Y(norm_pdf(xv, mu, sd))))
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        if close_from is not None:
            d += f" L{X(x_hi):.1f},{Y(0):.1f} L{X(close_from):.1f},{Y(0):.1f} Z"
        return d

    b = [legend([("sheet default (Duke champion)", "var(--ink-3)"),
                 ("Michigan St wins it all", "var(--s-aqua)")], left, 18)]
    for gv in [-50, -25, 0, 25, 50, 75]:
        b.append(vline(X(gv), top, top + ph))
        b.append(txt(X(gv), top + ph + 16, f"{gv:+d}" if gv else "0", 10.5, "middle", "var(--ink-3)"))
    b.append(txt(left + pw / 2, top + ph + 34,
                 "final score, in points above or below the pool average", 11, "middle", "var(--ink-3)"))
    # shaded tails beyond the 2,000-pool threshold
    b.append(f'<path d="{curve_path(chalk["mean"] - FIELD_MEAN, chalk["sd"], TH2000)}" '
             f'fill="var(--ink-3)" opacity="0.13"/>')
    b.append(f'<path d="{curve_path(hero["mean"] - FIELD_MEAN, hero["sd"], TH2000)}" '
             f'fill="var(--s-aqua)" opacity="0.20"/>')
    b.append(f'<path d="{curve_path(chalk["mean"] - FIELD_MEAN, chalk["sd"])}" fill="none" '
             f'stroke="var(--ink-3)" stroke-width="2" stroke-linejoin="round"/>')
    b.append(f'<path d="{curve_path(hero["mean"] - FIELD_MEAN, hero["sd"])}" fill="none" '
             f'stroke="var(--s-aqua)" stroke-width="2" stroke-linejoin="round"/>')
    for thv, lbl in [(TH100, f"≈ top of a 100-entry pool (+{TH100:.0f})"),
                     (TH2000, f"≈ top of a 2,000-entry pool (+{TH2000:.0f})")]:
        b.append(vline(X(thv), top - 4, top + ph, "var(--axis)", 1))
        b.append(txt(X(thv) - 5, top + 6, lbl, 10.5, "end", "var(--ink-2)"))
    H = top + ph + 44
    body = svg(W, H, "".join(b),
               "Score-deviation distributions: default bracket vs the Michigan State bracket")
    rows = []
    for c in (chalk, hero):
        mu = c["mean"] - FIELD_MEAN
        rows.append([c["label"], f"{mu:+.2f}", f"{c['sd']:.2f}",
                     pct((1 - em.norm_cdf(TH100, mu, c["sd"])), 2),
                     pct((1 - em.norm_cdf(TH2000, mu, c["sd"])), 3)])
    tbl = table_view(["Bracket", "mean vs field", "std dev",
                      f"P(> +{TH100:.0f})", f"P(> +{TH2000:.0f})"], rows)
    return body + tbl


# ------------------------------------------------------------------- chart F

def chart_f():
    W, left, right = 820, 56, 200
    pw = W - left - right
    top, ph = 40, 220
    X = lambda n: left + (math.log10(n) - 1) / 4 * pw
    ymax = 12.0
    Y = lambda v: top + ph - v / ymax * ph
    colors = {"gray": "var(--ink-3)", "blue": "var(--s-blue)", "aqua": "var(--s-aqua)"}
    b = [legend([("sheet default (Duke champion)", "var(--ink-3)"),
                 ("Virginia champion", "var(--s-blue)"),
                 ("Michigan St wins it all", "var(--s-aqua)")], left, 16)]
    for gv in [0, 2, 4, 6, 8, 10, 12]:
        b.append(hline(left, W - right, Y(gv), "var(--axis)" if gv == 1 else "var(--grid)"))
        b.append(txt(left - 8, Y(gv) + 4, f"{gv}×", 10.5, "end", "var(--ink-3)"))
    b.append(hline(left, W - right, Y(1), "var(--axis)"))
    b.append(txt(left + 4, Y(1) - 5, "1× = a random entry", 10, "start", "var(--ink-3)"))
    for n in [10, 100, 1000, 10000, 100000]:
        b.append(vline(X(n), top + ph, top + ph + 5, "var(--axis)"))
        lbl = f"{n:,}".replace(",000,000", "M").replace(",000", "k" if n >= 1000 else ",000")
        b.append(txt(X(n), top + ph + 18, lbl, 10.5, "middle", "var(--ink-3)"))
    b.append(txt(left + pw / 2, top + ph + 36, "pool size (entries, log scale)",
                 11, "middle", "var(--ink-3)"))
    for c in CURVES:
        col = colors[c["color"]]
        pts = [(X(n), Y(m)) for n, m in zip(NS, c["mult"])]
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        b.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2" '
                 f'stroke-linejoin="round" stroke-linecap="round"/>')
        for (x, y), n, m in zip(pts, NS, c["mult"]):
            b.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="transparent" '
                     f'data-tip="{esc(c["label"])} — pool of {n:,}: {m:.2f}× a random entry"/>')
        ex, ey = pts[-1]
        b.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="4.5" fill="{col}" '
                 f'stroke="var(--surface)" stroke-width="2"/>')
        short = {"gray": "default (Duke)", "blue": "Virginia champion",
                 "aqua": "Michigan St run"}[c["color"]]
        b.append(txt(ex + 10, ey + 4, f"{short}  {c['mult'][-1]:.1f}×",
                     11, "start", "var(--ink-1)"))
    cx = X(CROSS_N)
    cy = Y([m for n, m in zip(NS, CURVES[0]["mult"]) if n == 1000][0])
    b.append(vline(cx, cy - 36, cy + 8, "var(--axis)"))
    b.append(txt(cx, cy - 42, f"≈{CROSS_N:,.0f} entries: the Michigan St bracket", 10.5, "middle", "var(--ink-2)"))
    b.append(txt(cx, cy - 30, "overtakes the default", 10.5, "middle", "var(--ink-2)"))
    H = top + ph + 50
    body = svg(W, H, "".join(b),
               "Estimated pool-win edge vs pool size for the three brackets")
    tbl = table_view(["Pool size"] + [c["label"] for c in CURVES],
                     [[f"{n:,}"] + [f"{c['mult'][j]:.2f}×" for c in CURVES]
                      for j, n in enumerate(NS)])
    return body + tbl


# ------------------------------------------------------------------- chart G

def chart_g():
    W, left, right, top = 820, 62, 24, 30
    pw, ph = W - left - right, 300
    x_lo, x_hi = -1.0, 17.0
    y_lo, y_hi = -45.0, 95.0
    X = lambda v: left + (v - x_lo) / (x_hi - x_lo) * pw
    Y = lambda v: top + (y_hi - v) / (y_hi - y_lo) * ph
    b = [legend([("value pick (★)", "var(--s-blue)"), ("not a value pick", "var(--cell-strong)")],
                left, 16)]
    for gv in [-40, -20, 0, 20, 40, 60, 80]:
        b.append(hline(left, W - right, Y(gv), "var(--axis)" if gv == 0 else "var(--grid)"))
        b.append(txt(left - 8, Y(gv) + 4, f"{gv:+d}" if gv else "0", 10.5, "end", "var(--ink-3)"))
    for gv in [0, 4, 8, 12, 16]:
        b.append(txt(X(gv), top + ph + 16, str(gv), 10.5, "middle", "var(--ink-3)"))
    b.append(txt(left + pw / 2, top + ph + 34,
                 "expected points given up vs the all-favorites pick (champion column, cumulative)",
                 11, "middle", "var(--ink-3)"))
    b.append(txt(16, top + ph / 2, "", 11))
    b.append(f'<g transform="translate(16,{top + ph / 2:.0f}) rotate(-90)">'
             + txt(0, 0, "variance gained (cumulative)", 11, "middle", "var(--ink-3)") + "</g>")
    # the rule: variance gained >= points given up  (ratio <= -1 boundary)
    bx1, by1 = x_hi, x_hi
    b.append(f'<path d="M{X(0):.1f},{Y(0):.1f} L{X(bx1):.1f},{Y(by1):.1f}" '
             f'stroke="var(--gold)" stroke-width="1.5" stroke-dasharray="none"/>')
    b.append(txt(X(12.3), Y(12.3) - 8, "boundary: gain = give-up", 10.5, "start", "var(--gold)"))
    b.append(txt(X(8), Y(60), "value territory", 12, "middle", "var(--s-blue)", "600"))
    lab_off = {"Duke": (10, 4), "Virginia": (10, 2), "Gonzaga": (10, 4),
               "North Carolina": (10, 12), "Kentucky": (10, -4),
               "Michigan State": (10, 4), "Michigan": (10, 10),
               "Texas Tech": (10, -2), "Virginia Tech": (10, 4),
               "Tennessee": (8, 14), "Houston": (10, 4)}
    for r in sorted(FRONTIER, key=lambda r: r["value"]):
        x, y = X(r["x"]), Y(r["y"])
        col = "var(--s-blue)" if r["value"] else "var(--cell-strong)"
        rad = 5.5 if r["name"] in LABELED else 4
        b.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad}" fill="{col}" '
                 f'stroke="var(--surface)" stroke-width="2" '
                 f'data-tip="{esc(r["name"])} ({r["seed"]} seed): gives up {r["x"]:.1f} pts, '
                 f'variance {r["y"]:+.1f}"/>')
        if r["name"] in LABELED:
            dx, dy = lab_off[r["name"]]
            nm = "Michigan St" if r["name"] == "Michigan State" else r["name"]
            b.append(txt(x + dx, y + dy, nm, 10.5, "start", "var(--ink-2)",
                         "600" if r["name"] == "Michigan State" else ""))
    H = top + ph + 46
    body = svg(W, H, "".join(b),
               "All 64 teams in the champion column: expected points given up vs variance gained")
    rows = sorted(FRONTIER, key=lambda r: -r["y"])
    tbl = table_view(["Team", "Seed", "Points given up", "Variance gained", "Value pick"],
                     [[r["name"], r["seed"], f"{r['x']:.2f}", f"{r['y']:+.2f}",
                       "★" if r["value"] else "—"] for r in rows[:20]],
                     "Table view (top 20 by variance gained)")
    return body + tbl


# ---------------------------------------------------------------------- page

CSS = """
:root {
  --surface: #fcfcfb; --page: #f9f9f7;
  --ink-1: #0b0b0b; --ink-2: #52514e; --ink-3: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --cell: #eceae4; --cell-strong: #c9c7bf;
  --s-blue: #2a78d6; --s-aqua: #1baf7a; --s-red: #e34948;
  --gold: #a17708; --card-border: rgba(11,11,11,0.10);
}
@media (prefers-color-scheme: dark) {
  :root {
    --surface: #1a1a19; --page: #0d0d0d;
    --ink-1: #ffffff; --ink-2: #c3c2b7; --ink-3: #898781;
    --grid: #2c2c2a; --axis: #383835; --cell: #262624; --cell-strong: #4a4a46;
    --s-blue: #3987e5; --s-aqua: #199e70; --s-red: #e66767;
    --gold: #d3a12c; --card-border: rgba(255,255,255,0.10);
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink-1);
  font-family: system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size: 16px; line-height: 1.65; }
.wrap { max-width: 900px; margin: 0 auto; padding: 20px 18px 60px; }
header h1 { font-size: 28px; line-height: 1.25; margin: 14px 0 6px; }
header .sub { color: var(--ink-2); margin: 0 0 8px; }
a { color: var(--s-blue); }
h2 { font-size: 21px; margin: 44px 0 10px; }
h2 .kicker { display:block; font-size: 12px; letter-spacing: 1.2px;
  text-transform: uppercase; color: var(--ink-3); margin-bottom: 4px; }
p, li { color: var(--ink-2); }
strong, b { color: var(--ink-1); }
.card { background: var(--surface); border: 1px solid var(--card-border);
  border-radius: 12px; padding: 18px 20px 12px; margin: 18px 0; }
.card figcaption { font-size: 13px; color: var(--ink-3); margin: 8px 0 4px; }
figure { margin: 0; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px,1fr));
  gap: 12px; margin: 18px 0; }
.tile { background: var(--surface); border: 1px solid var(--card-border);
  border-radius: 12px; padding: 12px 16px; }
.tile .lbl { font-size: 12.5px; color: var(--ink-3); }
.tile .val { font-size: 26px; font-weight: 650; color: var(--ink-1); line-height: 1.3; }
.tile .note { font-size: 12px; color: var(--ink-3); }
.formula { background: var(--surface); border: 1px solid var(--card-border);
  border-radius: 12px; padding: 18px; margin: 16px 0; overflow-x: auto; }
.formula .eq { font-size: 19px; text-align: center; color: var(--ink-1);
  font-family: Georgia, 'Times New Roman', serif; font-style: italic; white-space: nowrap; }
.terms { display: flex; justify-content: center; gap: 26px; flex-wrap: wrap;
  margin-top: 12px; text-align: center; }
.terms div { font-size: 12.5px; color: var(--ink-3); max-width: 170px; }
.terms b { display: block; font-size: 15px; color: var(--ink-1);
  font-variant-numeric: tabular-nums; }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; margin: 6px 0; }
th, td { padding: 5px 10px; border-bottom: 1px solid var(--grid); text-align: right;
  font-variant-numeric: tabular-nums; color: var(--ink-2); }
th { color: var(--ink-3); font-weight: 600; font-size: 12px; }
th:first-child, td:first-child { text-align: left; }
td:first-child { color: var(--ink-1); }
.tv summary { font-size: 12.5px; color: var(--ink-3); cursor: pointer; margin: 6px 0; }
.walk td.flag { color: var(--gold); font-weight: 650; text-align: center; }
.callout { border-left: 3px solid var(--s-blue); padding: 2px 0 2px 16px; margin: 18px 0; }
.callout.gold { border-color: var(--gold); }
.callout p { margin: 6px 0; }
.takeaways li { margin: 10px 0; }
#tip { position: fixed; pointer-events: none; background: var(--ink-1);
  color: var(--surface); padding: 5px 10px; border-radius: 6px; font-size: 12.5px;
  max-width: 300px; opacity: 0; transition: opacity .12s; z-index: 10; }
footer { margin-top: 48px; color: var(--ink-3); font-size: 13px;
  border-top: 1px solid var(--grid); padding-top: 14px; }
.scroll-x { overflow-x: auto; }
.scroll-x svg { min-width: 760px; }
code { background: var(--cell); border-radius: 4px; padding: 1px 5px; font-size: 13px; }
"""

JS = """
const tip = document.createElement('div'); tip.id = 'tip';
document.body.appendChild(tip);
document.querySelectorAll('[data-tip]').forEach(el => {
  el.addEventListener('mousemove', e => {
    tip.textContent = el.dataset.tip;
    tip.style.opacity = 1;
    const w = tip.offsetWidth;
    tip.style.left = Math.min(window.innerWidth - w - 12, e.clientX + 14) + 'px';
    tip.style.top = (e.clientY + 16) + 'px';
  });
  el.addEventListener('mouseleave', () => tip.style.opacity = 0);
});
"""


def walkthrough_table():
    head = ["Round", "MSU p", "MSU f", "Favorite", "p₀", "f₀", "S",
            "ΔEV", "ΔVar", "cum ΔEV", "cum ΔVar", "ratio", "Value", "BAB"]
    rows = []
    for r in WALK:
        ratio_cell = "0" if r["isFav"] else f"{r['ratio']:.2f}"
        rows.append(
            f"<tr><td>{r['round']} <span style='color:var(--ink-3)'>(×{r['pts']} pts)</span></td>"
            f"<td>{r['p']:.3f}</td><td>{r['f']:.3f}</td>"
            f"<td>{esc(r['fav'])}</td><td>{r['p0']:.3f}</td><td>{r['f0']:.3f}</td>"
            f"<td>{r['S']:.3f}</td>"
            f"<td>{r['dEV']:+.2f}</td><td>{r['dVar']:+.2f}</td>"
            f"<td>{r['cumEV']:+.2f}</td><td>{r['cumVar']:+.2f}</td>"
            f"<td>{ratio_cell}</td>"
            f"<td class='flag'>{'★' if r['value'] else '—'}</td>"
            f"<td class='flag'>{'★' if r['bab'] else '—'}</td></tr>")
    return ("<div class='scroll-x'><table class='walk'><thead><tr>"
            + "".join(f"<th>{h}</th>" for h in head)
            + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")


def build():
    e8 = E8
    duke_c6, msu_c6 = T[DUKE], T[MSU]
    chalk, uva_c, msu_c = CURVES
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>How the Value factor works — a walkthrough</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

<header>
<p class="sub"><a href="index.html">← back to the 2019 model</a></p>
<h1>How the Value factor works</h1>
<p class="sub">A walkthrough of the trickiest column in Aaron Brown&rsquo;s
bracket model, following one team — <b>Michigan State, the 2019 East
2&nbsp;seed, drawn into Duke&rsquo;s region</b> — from raw probabilities all
the way to its Value stars. Every number is computed from the fixed model
(round points 2/3/5/8/13/21, pool of 100).</p>
</header>

<div class="tiles">
<div class="tile"><div class="lbl">Michigan St to win it all: expected cost</div>
<div class="val">−7.47 pts</div><div class="note">vs picking Duke each time</div></div>
<div class="tile"><div class="lbl">Variance gained by the same picks</div>
<div class="val">+64.9</div><div class="note">score spread vs the pool average</div></div>
<div class="tile"><div class="lbl">The Value test</div>
<div class="val">ratio −8.7</div><div class="note">≤ −1 → a Value pick in every round</div></div>
<div class="tile"><div class="lbl">What actually happened in 2019</div>
<div class="val">Final Four</div><div class="note">MSU beat Duke in the Elite 8</div></div>
</div>

<h2><span class="kicker">Part 1</span>The game you&rsquo;re actually playing</h2>
<p>A bracket pool pays the <b>top</b> of the standings, not the middle. Picking
every favorite maximises your <em>expected</em> score — and lands you 60th–80th
percentile: good, never first. To finish first out of {MODEL['poolSize']} you
need your score to <em>land far above the pool average</em>, and that means you
need <b>variance</b> — deliberate, cheap variance.</p>
<p>The two curves below are the model&rsquo;s estimate of where your score lands
relative to the pool average, for the sheet&rsquo;s default all-chalk bracket
and for the same bracket with Michigan State picked to win it all. The MSU
bracket&rsquo;s centre is lower (it costs expected points) but its tails are
fatter — and pools are won in the right tail.</p>
<div class="card"><figure>{chart_e()}
<figcaption>Gaussian score-deviation estimates from the model&rsquo;s own
mean/variance machinery. Shaded: the region beyond what it typically takes to
top a 2,000-entry pool. The fatter aqua tail is the whole point.</figcaption>
</figure></div>

<h2><span class="kicker">Part 2</span>The crowd&rsquo;s map — probability vs pick frequency</h2>
<p>Value exists because the crowd&rsquo;s picks don&rsquo;t match the
probabilities. In 2019 the crowd was drunk on Zion-era Duke:
<b>{pct(duke_c6['freq'][5])} of pools</b> picked Duke as champion against a
model probability of <b>{pct(duke_c6['prob'][5])}</b> — backed at
{duke_c6['freq'][5] / duke_c6['prob'][5]:.1f}&times; its probability. That
over-backing had to come from somewhere: Virginia
(picked at 0.4&times; its probability), Gonzaga (0.5&times;) and Michigan State
({msu_c6['freq'][5] / msu_c6['prob'][5]:.1f}&times;) were all left
under-owned. North Carolina shows the opposite: a brand the crowd
<em>over</em>-backed — no value there.</p>
<div class="card"><figure>{chart_a()}
<figcaption>Champion column: model win probability (blue) vs share of pools
picking each team as champion (aqua). The right column is the pick-to-probability
multiple; ★ marks the model&rsquo;s champion-column Value picks.</figcaption>
</figure></div>

<h2><span class="kicker">Part 3</span>Slots, not teams</h2>
<p>The spreadsheet doesn&rsquo;t evaluate &ldquo;Michigan State&rdquo; — it
evaluates <b>63 independent decisions called slots</b>: each round-cell of your
bracket. In the round of 64 a slot has 2 candidate teams; each later round
doubles the candidates until the champion slot has all 64. For every slot, the
baseline is the <b>favorite</b> — the most likely winner, which for MSU&rsquo;s
first three slots is MSU itself, and from the Elite&nbsp;8 onward is Duke.</p>
<div class="card"><figure><div class="scroll-x">{chart_b()}</div>
<figcaption>Michigan State&rsquo;s six slots. Aqua = MSU, blue = Duke, band =
the teams competing for that slot. Two numbers describe each slot&rsquo;s
crowd: the favorite&rsquo;s probability p₀ and S — the average entry&rsquo;s
expected wins from that slot (S&nbsp;=&nbsp;Σ&nbsp;p·f over its teams).</figcaption>
</figure></div>
<p>Picking MSU in a slot where MSU is the favorite costs nothing — the Value
flag is automatic (the sheet shows ratio&nbsp;0). The real question starts at
the Elite&nbsp;8: MSU&rsquo;s probability of reaching the Final Four is
{e8['p']:.2f} against Duke&rsquo;s {e8['p0']:.2f}, and the slot is worth
{e8['pts']} points. Picking MSU there <b>gives up
{e8['pts']}&nbsp;&times;&nbsp;({e8['p']:.2f}&nbsp;−&nbsp;{e8['p0']:.2f})&nbsp;=
{e8['dEV']:+.2f} expected points</b>. What do you get back?</p>

<h2><span class="kicker">Part 4</span>The variance-difference formula, term by term</h2>
<p>What you get back is <em>variance against the field</em>. The score that
decides the pool isn&rsquo;t yours — it&rsquo;s yours <em>minus everyone
else&rsquo;s average</em>. Whenever you and the crowd pick the same team, that
game cancels out of the comparison; whenever you differ, the game swings the
gap both ways. The spreadsheet&rsquo;s AL:AQ columns compute how much the
spread of that gap grows when you pick team&nbsp;<i>i</i> instead of the
favorite:</p>
<div class="formula">
<div class="eq">ΔVar&nbsp;=&nbsp;pts²&nbsp;·&nbsp;[&nbsp;(p−p₀)(1+2S)&nbsp;+&nbsp;(p₀²−p²)&nbsp;+&nbsp;2(p₀f₀−pf)&nbsp;]</div>
<div class="terms">
<div><b>{TERM1:+.3f}</b>you win this slot less often, so it wobbles your total
less — a variance <em>loss</em></div>
<div><b>{TERM2:+.3f}</b>the squared-probability correction from Bernoulli
variance p(1−p)</div>
<div><b>{TERM3:+.3f}</b>the crowd term: the favorite moves with the field
(f₀&nbsp;{e8['f0']:.2f}); your pick moves against it (f&nbsp;{e8['f']:.2f})</div>
<div><b>= {TTOT:+.3f}</b>per point² — times {e8['pts']}² = <b>{e8['dVar']:+.1f}</b>
for the Elite-8 slot</div>
</div>
</div>
<p>Plugged in for MSU&rsquo;s Elite&nbsp;8 slot (p&nbsp;=&nbsp;{e8['p']:.2f},
f&nbsp;=&nbsp;{e8['f']:.2f}, p₀&nbsp;=&nbsp;{e8['p0']:.2f},
f₀&nbsp;=&nbsp;{e8['f0']:.2f}, S&nbsp;=&nbsp;{e8['S']:.3f}):</p>
<div class="card"><figure>{chart_d()}
<figcaption>The decomposition as a waterfall. The first two terms are the price
of backing a less likely winner. The third — being on a different team from
{pct(e8['f0'], 0)} of the field — dwarfs them.</figcaption>
</figure></div>
<div class="callout">
<p><b>The one-sentence intuition:</b> when {pct(e8['f0'], 0)} of the pool rides
Duke and Duke loses, all those brackets sink <em>together</em> — and your MSU
bracket rockets past the whole group at once. Variance against the field is
cheap precisely where the crowd is most concentrated.</p>
</div>
<details class="tv"><summary>Where the formula comes from (derivation sketch)</summary>
<p>Give each slot 1 point. Your slot score is a Bernoulli X<sub>i</sub> with
P(X<sub>i</sub>=1)&nbsp;=&nbsp;p<sub>i</sub>; the field&rsquo;s average score on
the slot is A&nbsp;=&nbsp;Σ<sub>j</sub>&nbsp;f<sub>j</sub>X<sub>j</sub> with
E[A]&nbsp;=&nbsp;S. Working out Var(X<sub>i</sub>&nbsp;−&nbsp;A) — noting the
X<sub>j</sub> of one slot are mutually exclusive, and
Cov(X<sub>i</sub>,&nbsp;A)&nbsp;=&nbsp;p<sub>i</sub>f<sub>i</sub>&nbsp;−&nbsp;p<sub>i</sub>S
— gives the paper&rsquo;s expression
p<sub>i</sub>(2S+1−p<sub>i</sub>−2f<sub>i</sub>)&nbsp;−&nbsp;S²&nbsp;+&nbsp;S.
Subtract the same expression for the favorite (p₀,&nbsp;f₀) and the −S²+S parts
cancel, leaving exactly the three terms above. Points multiply variance by
pts².</p></details>

<h2><span class="kicker">Part 5</span>Accumulate, divide, test: the ratio rule</h2>
<p>A champion pick implies winning six slots, so the sheet accumulates both
sides across rounds: <b>cumulative expected points given up</b> and
<b>cumulative variance gained</b>, then divides them. The rule
(&ldquo;lower limit of 1 on the ratio&rdquo; in the paper): a pick earns the
Value flag when it&rsquo;s the favorite, or when <b>variance gained ≥ points
given up</b> — with the sheet&rsquo;s sign convention (given-up points are
stored negative), a ratio ≤&nbsp;−1.</p>
<div class="card"><figure>{chart_c()}
<figcaption>Michigan State by round. Through the Sweet&nbsp;16 they are the
favorite (nothing given up, ratio 0 — automatic ★). From the Elite&nbsp;8 the
trade begins: about 2.5 points a round for 16–25 variance a round. The ratio
never comes near the −1 boundary.</figcaption>
</figure></div>
<p>The full ledger, every intermediate quantity the spreadsheet computes:</p>
{walkthrough_table()}
<p class="note" style="color:var(--ink-3);font-size:13px">f₀ is the pick
frequency of the slot favorite; S is the crowd&rsquo;s expected wins from the
slot; ΔEV and ΔVar are point-weighted. BAB (bet-against-beta) is the sibling
slot flag: a non-favorite within 0.5 probability of the favorite that the
crowd backs at a lower frequency-to-probability multiple — MSU qualifies from
the Elite&nbsp;8 on too ({e8['f']:.2f}/{e8['p']:.2f}&nbsp;=&nbsp;{e8['f'] / e8['p']:.2f}
vs Duke&rsquo;s {e8['f0']:.2f}/{e8['p0']:.2f}&nbsp;=&nbsp;{e8['f0'] / e8['p0']:.2f}).</p>

<h2><span class="kicker">Part 6</span>The whole field on one map</h2>
<p>Run the same two cumulative numbers for all 64 teams in the champion column
and the definition becomes a picture: a team is a champion-column Value pick
when it sits <b>above the gain&nbsp;=&nbsp;give-up line</b>. Virginia is the
standout — a co-favorite by probability, abandoned by the crowd, so it buys
{FRONTIER[UVA]['y']:.0f} variance for {FRONTIER[UVA]['x']:.1f} points. North
Carolina and Houston sit low: the crowd already over-backs them, so deviating
to them buys little spread or even <em>reduces</em> it.</p>
<div class="card"><figure>{chart_g()}
<figcaption>Champion column, one dot per team. Blue = the eight Value picks
(Duke at the origin is the favorite case). Gold line: variance gained equals
expected points given up (ratio&nbsp;=&nbsp;−1).</figcaption>
</figure></div>
<div class="callout gold">
<p><b>Value ≠ longshot.</b> The eight champion Value picks of 2019 were Duke,
Virginia, Gonzaga, Kentucky, Michigan St, Michigan, Texas Tech and Virginia
Tech — favorites and second favorites the crowd under-owned, not 12 seeds.
Longshots fail the test from both sides: tiny p buys almost no variance, and
still costs the full EV gap. The 2019 title game was Virginia&nbsp;–
Texas&nbsp;Tech, with MSU in the Final Four.</p>
</div>

<h2><span class="kicker">Part 7</span>Does the trade actually pay?</h2>
<p>Honesty first: under the model&rsquo;s own assumptions, in a
100-entry pool, the default Duke bracket still edges the MSU bracket
({chalk['mult'][3]:.2f}&times; vs {msu_c['mult'][3]:.2f}&times; a random
entry) — 7½ points of expected value is a lot to give back. But variance
scales with pool size, because the winning score climbs as the field grows.
Two things follow. First, the near-free value pick — swapping the champion cell
to Virginia costs 0.41 points for +51 variance — <b>beats chalk at every pool
size</b>. Second, the expensive MSU version overtakes chalk once the pool
passes roughly <b>{CROSS_N:,.0f} entries</b>.</p>
<div class="card"><figure>{chart_f()}
<figcaption>The model&rsquo;s estimated chance of winning, expressed as a
multiple of a random entry&rsquo;s 1/N, across pool sizes. Hover the points for
exact values.</figcaption>
</figure></div>
<p>And remember the Read&nbsp;Me&rsquo;s warning: these curves assume the
probability and frequency tables are exactly right. The entire reason Value
picks exist is that you believe the crowd&rsquo;s frequencies are wrong in
knowable ways — so treat the estimate as a compass, not a payout table. The
paper&rsquo;s strongest empirical claim stands separately:
<b>all 32 tournament champions to that point had been Value picks</b>.</p>

<h2><span class="kicker">Part 8</span>What to remember</h2>
<ul class="takeaways">
<li><b>Pools pay position, not points.</b> Expected value gets you to the 70th
percentile; variance against the field is what gets you to 1st.</li>
<li><b>The favorite is always a Value pick</b> (ratio 0). Value is about which
<em>deviations</em> from chalk are efficiently priced.</li>
<li><b>The crowd term drives everything.</b> ΔVar is dominated by
2(p₀f₀&nbsp;−&nbsp;pf): deviation is cheapest exactly where the field is most
herded (Duke&nbsp;2019 at {pct(duke_c6['freq'][5], 0)} champion ownership).</li>
<li><b>Second favorites, not longshots.</b> A value pick needs real win
probability and low crowd ownership. UNC (brand-inflated) failed; Virginia
(brand-deflated co-favorite) was the trade of the year.</li>
<li><b>Pool size sets the variance budget.</b> Small pool → shade toward chalk;
big pool → every efficient variance trade you can find. The MSU-style deep run
only pays past ~{CROSS_N / 1000:.0f}k entries; the Virginia-style free swap pays
everywhere.</li>
<li><b>Caveats:</b> the machinery is Gaussian and treats slots as independent;
in &ldquo;must-win&rdquo; situations (huge pools, top-heavy scoring) the metric
shades toward p/f; and none of it accounts for rivals using the same sheet.
Also: this page uses the <a href="index.html">fixed</a> formulas — as published,
the reference bug (S from 38 rows down) and the reversed ratio test meant the
Value column flagged almost none of this.</li>
</ul>

<footer>
Generated {date.today().isoformat()} by <code>build_explainer.py</code> from the
verified re-implementation (<code>extract_model.py</code>) of the March&nbsp;18,
2019 workbook · <a href="index.html">the interactive model</a> ·
<a href="reference/Quants_Mad_March.pdf">Aaron Brown&rsquo;s paper</a>
</footer>

</div>
<script>{JS}</script>
</body>
</html>
"""
    OUT.write_text(html)
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1024:.0f} kB)")


if __name__ == "__main__":
    build()
