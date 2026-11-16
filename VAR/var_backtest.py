"""VaR backtest based on Aaron Brown's "Forced by the Sternest Circumstances"
(Wilmott magazine, July 2009).

Builds three daily 99% VaR estimators for a $1M position in the NASDAQ
Composite and runs the three backtests the article says every VaR must pass:

  Test 1: the actual fraction of VaR break days is 1%, within statistical
          tolerance;
  Test 2: the VaR breaks are randomly distributed in time;
  Test 3: the VaR breaks are independent of the level of VaR.

Methods (same parameters as the article — no fitting):
  A. Historical simulation — the 1% loss point of the last 3 years (750
     days), placed so a break has exactly a 1% chance on ideal data.
  B. Parametric (RiskMetrics) — EWMA variance, 0.94 decay, VaR = 2.33 sigma.
  C. Brown's "Bayesian" VaR — start from 2.33 x 3-year standard deviation;
     double after a break; otherwise decay 0.94 x yesterday + 0.06 x simple.

Also reproduces the article's "two out of three?" exercise: recalibrate A and
B to give exactly the expected number of breaks and show they still fail
Tests 2 and 3.

Usage:
    python3 var_backtest.py     # results/backtest_report.md + three PNG charts
    python3 build_site.py       # index.html, the GitHub Pages view
    python3 test_pipeline.py    # independent check of every published figure
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import xlogy

HERE = Path(__file__).parent
DATA_FILE = HERE / "data" / "NASDAQCOM.csv"
RESULTS_DIR = HERE / "results"

PORTFOLIO = 1_000_000  # dollars invested in the NASDAQ Composite
VAR_LEVEL = 0.01       # 99% VaR -> 1% expected break frequency
WINDOW = 750           # "three years" of trading days, as in the article
DECAY = 0.94           # RiskMetrics decay factor
Z_99 = 2.33            # 1% point of the Gaussian, as quoted in the article
ALPHA = 0.05           # statistical tolerance for pass/fail
BORDERLINE = (0.01, 0.10)   # p in this band: a 1% or 10% tolerance flips the verdict
PERM_DRAWS = 100_000   # random subsets in the Test 3 permutation test
PERM_SEED = 20090701


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load_prices():
    """FRED NASDAQCOM daily closes, and the number of rows in the file.

    Blank observations are market holidays. They are dropped, so the return
    across a holiday is an ordinary one-day return.
    """
    raw = pd.read_csv(DATA_FILE, parse_dates=["observation_date"])
    prices = raw.dropna(subset=["NASDAQCOM"]).set_index("observation_date")["NASDAQCOM"]
    return prices, len(raw)

def load_returns():
    """Simple daily returns of the index."""
    return load_prices()[0].pct_change().dropna()


# ---------------------------------------------------------------------------
# VaR methods — VaR for day t uses information through day t-1 only.
# All series are in dollars of loss on the $1M portfolio.
# ---------------------------------------------------------------------------

def sorted_windows(returns):
    """Rolling 3-year windows of returns, each sorted ascending.

    Row i holds returns[i : i+WINDOW] sorted, which is the information set
    for the prediction on day i + WINDOW.
    """
    windows = np.lib.stride_tricks.sliding_window_view(returns, WINDOW)
    return np.sort(windows[:-1], axis=1)  # drop last row: nothing to predict

def hs_var(sorted_wins, percentile):
    """Historical simulation VaR at the given percentile (in %).

    The article builds this so a break has exactly the stated probability
    when returns are independent draws from one distribution: a new day is
    equally likely to rank anywhere among the n window days and itself, so
    "worse than the k-th worst of the last n" has probability k / (n + 1)
    (its example: the fifth worst of the last 499 days, for 1%). The
    percentile therefore sits at rank p x (n + 1) counted from the worst
    day — 7.51 for 1% of 750 days — interpolating between the neighbouring
    days when the rank is fractional.

    The usual spreadsheet / numpy percentile puts it at rank p x (n - 1) + 1
    instead (8.49 here), nearly one whole day less extreme. That version
    breaks on 1.12% of days even on ideal data, not 1%.
    """
    rank = percentile / 100.0 * (WINDOW + 1)
    pos = min(max(rank - 1.0, 0.0), WINDOW - 1.0)   # 0-indexed, ascending
    lo = int(np.floor(pos))
    frac = pos - lo
    q = sorted_wins[:, lo] * (1 - frac) + sorted_wins[:, min(lo + 1, WINDOW - 1)] * frac
    return -q * PORTFOLIO

def ewma_sigma(returns):
    """RiskMetrics EWMA volatility path for prediction days WINDOW..N-1.

    Seeded with the variance of the warm-up window so all methods start
    forecasting on the same day.
    """
    n = len(returns)
    var = np.empty(n - WINDOW)
    var[0] = np.var(returns[:WINDOW], ddof=1)
    for t in range(1, n - WINDOW):
        var[t] = DECAY * var[t - 1] + (1 - DECAY) * returns[WINDOW + t - 1] ** 2
    return np.sqrt(var)

def brown_var(losses, simple_estimate):
    """Brown's method: double after a break, otherwise decay toward the
    simple estimate (2.33 x rolling 3-year standard deviation)."""
    n = len(simple_estimate)
    var = np.empty(n)
    var[0] = simple_estimate[0]
    for t in range(1, n):
        if losses[t - 1] > var[t - 1]:
            var[t] = 2.0 * var[t - 1]
        else:
            var[t] = DECAY * var[t - 1] + (1 - DECAY) * simple_estimate[t]
    return var


# ---------------------------------------------------------------------------
# The three backtests
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    key: str            # A, B, C, or A2 / B2 for the recalibrated variants
    name: str           # "Historical simulation"
    spec: str           # "3yr, 1st pct"
    description: str
    var: np.ndarray
    breaks: np.ndarray
    # test 1 — break frequency
    n_obs: int = 0
    n_breaks: int = 0
    expected_breaks: float = 0.0
    z_score: float = 0.0
    kupiec_p: float = 0.0
    pass1: bool = False
    # test 2 — random in time
    next_day_breaks: int = 0
    next_day_expected: float = 0.0
    next_day_p: float = 0.0
    within10_breaks: int = 0
    within10_expected: float = 0.0
    within10_p: float = 0.0
    christoffersen_p: float = 0.0
    pass2: bool = False
    # test 3 — independent of VaR level
    avg_var: float = 0.0
    avg_var_on_breaks: float = 0.0
    perm_p: float = 0.0
    welch_p: float = 0.0
    pass3: bool = False

    @property
    def title(self):
        return f"{self.key}. {self.name} ({self.spec})"

    @property
    def passes(self):
        return (self.pass1, self.pass2, self.pass3)

    @property
    def deciding_p(self):
        """The p-value each test's verdict rests on. Test 2 needs both of its
        p-values to clear the tolerance, so the smaller one decides."""
        return (self.kupiec_p, min(self.christoffersen_p, self.within10_p), self.perm_p)

    @property
    def borderline(self):
        return tuple(BORDERLINE[0] <= p < BORDERLINE[1] for p in self.deciding_p)

    @property
    def ratio(self):
        """Average VaR on break days over average VaR on all days."""
        return self.avg_var_on_breaks / self.avg_var


def kupiec_pof(n, x, p):
    """Kupiec proportion-of-failures likelihood ratio test."""
    if x == 0:
        lr = -2 * n * np.log(1 - p)
    else:
        phat = x / n
        lr = -2 * (
            (n - x) * np.log((1 - p) / (1 - phat)) + x * np.log(p / phat)
        )
    return stats.chi2.sf(lr, df=1)

def christoffersen_independence(breaks):
    """Christoffersen test: is a break more likely right after a break?"""
    prev, curr = breaks[:-1], breaks[1:]
    n00 = np.sum(~prev & ~curr)
    n01 = np.sum(~prev & curr)
    n10 = np.sum(prev & ~curr)
    n11 = np.sum(prev & curr)
    pi = (n01 + n11) / (n00 + n01 + n10 + n11)
    pi0 = n01 / (n00 + n01) if n00 + n01 > 0 else 0.0
    pi1 = n11 / (n10 + n11) if n10 + n11 > 0 else 0.0
    loglik_null = xlogy(n01 + n11, pi) + xlogy(n00 + n10, 1 - pi)
    loglik_alt = (
        xlogy(n01, pi0) + xlogy(n00, 1 - pi0)
        + xlogy(n11, pi1) + xlogy(n10, 1 - pi1)
    )
    lr = -2 * (loglik_null - loglik_alt)
    return stats.chi2.sf(lr, df=1)

def backtest(key, name, spec, description, var, losses):
    """Run the article's three tests on a VaR series."""
    breaks = losses > var
    r = BacktestResult(key, name, spec, description, var, breaks)

    # Test 1: break frequency vs 1%, judged by the Kupiec test.
    r.n_obs = len(breaks)
    r.n_breaks = int(breaks.sum())
    r.expected_breaks = VAR_LEVEL * r.n_obs
    r.z_score = (r.n_breaks - r.expected_breaks) / np.sqrt(
        r.n_obs * VAR_LEVEL * (1 - VAR_LEVEL)
    )
    r.kupiec_p = kupiec_pof(r.n_obs, r.n_breaks, VAR_LEVEL)
    r.pass1 = r.kupiec_p >= ALPHA

    # Test 2: breaks random in time. The article counts breaks that land the
    # day after a break and within ten days of one; expectations here use the
    # method's own observed break rate, so the clustering question is
    # separated from the frequency question of Test 1.
    rate = r.n_breaks / r.n_obs
    gaps = np.diff(np.flatnonzero(breaks))  # trading days between breaks
    r.next_day_breaks = int(np.sum(gaps == 1))
    r.within10_breaks = int(np.sum(gaps <= 10))
    r.next_day_expected = len(gaps) * rate
    r.within10_expected = len(gaps) * (1 - (1 - rate) ** 10)
    r.next_day_p = stats.binomtest(r.next_day_breaks, len(gaps), rate).pvalue
    r.within10_p = stats.binomtest(
        r.within10_breaks, len(gaps), 1 - (1 - rate) ** 10
    ).pvalue
    r.christoffersen_p = christoffersen_independence(breaks)
    r.pass2 = r.christoffersen_p >= ALPHA and r.within10_p >= ALPHA

    # Test 3: breaks independent of the VaR level — average VaR on break
    # days should match the overall average. If breaks are independent of
    # the level, break days are a uniformly random subset of days, so a
    # permutation test on the break-day average VaR is exact under the null.
    r.avg_var = var.mean()
    r.avg_var_on_breaks = var[breaks].mean()
    rng = np.random.default_rng(PERM_SEED)
    sims = np.array([
        var[rng.choice(r.n_obs, r.n_breaks, replace=False)].mean()
        for _ in range(PERM_DRAWS)
    ])
    r.perm_p = min(1.0, 2 * min(
        (sims <= r.avg_var_on_breaks).mean(), (sims >= r.avg_var_on_breaks).mean()
    ))
    r.welch_p = stats.ttest_ind(var[breaks], var[~breaks], equal_var=False).pvalue
    r.pass3 = r.perm_p >= ALPHA
    return r


# ---------------------------------------------------------------------------
# Calibrated variants (the article's "should we try for two out of three?")
# ---------------------------------------------------------------------------

def calibrate(count_fn, lo, hi, target, tol=1e-9):
    """The parameter at the centre of the range that gives exactly `target`
    breaks, for a break count that rises with the parameter.

    The centre rather than an edge: at an edge one day sits a hair's breadth
    from being a break, and the count would turn on rounding.
    """
    def first_above(level):
        a, b = lo, hi
        while b - a > tol:
            mid = (a + b) / 2
            if count_fn(mid) > level:
                b = mid
            else:
                a = mid
        return b
    return (first_above(target - 1) + first_above(target)) / 2


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def dollars(x):
    return f"${x:,.0f}"

def verdict(r, i):
    """PASS or FAIL on test i (0, 1, 2), marked when the call is a close one."""
    return ("PASS" if r.passes[i] else "FAIL") + (" (borderline)" if r.borderline[i] else "")

def pfmt(p):
    """Monte Carlo p-values the draws could not resolve show as a bound."""
    floor = 2 / PERM_DRAWS
    return "< " + format(floor, "f").rstrip("0") if p < floor else f"{p:.2g}"

def scorecard_rows(results):
    return [
        f"| {r.title} | {r.n_breaks} / {r.expected_breaks:.0f} exp. "
        f"| {verdict(r, 0)} | {verdict(r, 1)} | {verdict(r, 2)} |"
        for r in results
    ]

def method_section(r):
    rate = r.n_breaks / r.n_obs
    return f"""
### {r.title}

{r.description}

**Test 1 — break frequency is 1%: {verdict(r, 0)}**

| Metric | Value |
|---|---|
| Observations | {r.n_obs:,} |
| VaR breaks | {r.n_breaks} |
| Expected breaks (1%) | {r.expected_breaks:.0f} |
| Observed break rate | {rate:.2%} |
| z-score vs 1% | {r.z_score:+.1f} |
| Kupiec POF p-value | {r.kupiec_p:.2g} |

**Test 2 — breaks randomly distributed in time: {verdict(r, 1)}**

| Metric | Observed | Expected if independent | p-value |
|---|---|---|---|
| Breaks the day after a break | {r.next_day_breaks} | {r.next_day_expected:.1f} | {r.next_day_p:.2g} |
| Breaks within 10 days of a break | {r.within10_breaks} | {r.within10_expected:.1f} | {r.within10_p:.2g} |
| Christoffersen independence test | — | — | {r.christoffersen_p:.2g} |

**Test 3 — breaks independent of the VaR level: {verdict(r, 2)}**

| Metric | Value |
|---|---|
| Average VaR | {dollars(r.avg_var)} |
| Average VaR on break days | {dollars(r.avg_var_on_breaks)} |
| Ratio (break days / all days) | {r.ratio:.2f} |
| Permutation test p-value (are break days a random sample of days?) | {pfmt(r.perm_p)} |
| Welch t-test p-value (break vs non-break days) | {r.welch_p:.2g} |

**Result:** {' · '.join(f'Test {i + 1} {verdict(r, i)}' for i in range(3))}
"""

def commentary(bt):
    """The reading of the results, in prose, for the report and the web page.

    The wording is specific to these results, so everything it relies on is
    checked first. If new data changes one of these, rewrite the paragraph
    rather than publish a sentence that has stopped being true.
    """
    a, b, c = bt.methods
    relied_on = {
        "A passes Test 1, but only just": a.pass1 and a.borderline[0],
        "A fails Tests 2 and 3 decisively":
            not (a.pass2 or a.pass3 or a.borderline[1] or a.borderline[2]),
        "B fails all three tests decisively": not (any(b.passes) or any(b.borderline)),
        "C passes Test 1 comfortably": c.pass1 and not c.borderline[0],
        "C passes Test 2 narrowly": c.pass2 and c.borderline[1],
        "C fails Test 3 narrowly": not c.pass3 and c.borderline[2],
        "every method's VaR is lower on break days": all(r.ratio < 1 for r in bt.methods),
        "the recalibrated variants hit the target count, pass Test 1 and fail 2 and 3":
            all(r.n_breaks == bt.target and r.pass1 and not (r.pass2 or r.pass3)
                for r in bt.recalibrated),
    }
    stale = [claim for claim, holds in relied_on.items() if not holds]
    if stale:
        raise RuntimeError("commentary() no longer matches the results: " + "; ".join(stale))

    expected = f"{a.expected_breaks:.0f}"
    return [
        f"Historical simulation, built the way the article specifies, gets the "
        f"number of breaks roughly right: {a.n_breaks} against {expected} expected, "
        f"inside tolerance but only just (p = {a.kupiec_p:.3f}). It fails on when "
        f"they come. {a.next_day_breaks} breaks landed the day after another break, "
        f"where independence predicts about {a.next_day_expected:.0f}; "
        f"{a.within10_breaks} came within ten days of one, where it predicts "
        f"{a.within10_expected:.0f}. Volatility clusters, and a three-year window "
        f"cannot see it.",

        f"Parametric EWMA reacts within days but breaks "
        f"{b.n_breaks / b.expected_breaks:.1f} times as often as it should "
        f"({b.n_breaks} breaks), and its breaks still cluster. Both textbook "
        f"methods also break disproportionately on days when they say things are "
        f"safe: VaR on break days averages {1 - a.ratio:.0%} below the overall "
        f"average for historical simulation and {1 - b.ratio:.0%} below for EWMA.",

        f"Brown's double-on-break rule — the article's parameters untouched, "
        f"nothing fitted to this data — has {c.n_breaks} breaks against {expected} "
        f"expected, and most of the clustering is gone: {c.next_day_breaks} "
        f"next-day breaks against {c.next_day_expected:.1f} expected, and "
        f"{c.within10_breaks} within ten days against {c.within10_expected:.0f}. "
        f"That passes Test 2, narrowly (p = {c.deciding_p[1]:.3f}). It does not "
        f"pass Test 3 on this series: its VaR on break days averages "
        f"{1 - c.ratio:.0%} below its overall average (p = {c.perm_p:.3f}), where "
        f"the article's S&P 500 run erred slightly the other way. It is the only "
        f"one of the three that no test rejects decisively — but a nonrubber-stamp "
        f"backtest reports two passes and a narrow fail, not three passes.",
    ]

RECALIBRATED_NOTE = (
    "As in the article, the percentile and the sigma multiplier can be moved "
    "until the break count is exactly the expected number. Both recalibrated "
    "methods then pass Test 1 by construction and still fail the other two — "
    "the break count is not the problem, the clustering is."
)

def write_report(bt, path):
    dates = bt.dates
    lines = [
        "# VaR backtest report — NASDAQ Composite",
        "",
        "Three daily 99% VaR estimators for a **$1,000,000** position in the",
        "NASDAQ Composite (FRED `NASDAQCOM`), scored against the three tests in",
        'Aaron Brown\'s *"Forced by the Sternest Circumstances"* (Wilmott, 2009):',
        "",
        "> 1. The actual fraction of VaR break days is 1 percent, within statistical tolerance;",
        "> 2. The VaR breaks are randomly distributed in time;",
        "> 3. The VaR breaks are independent of the level of VaR.",
        "",
        f"Backtest window: **{dates[0]:%Y-%m-%d} to {dates[-1]:%Y-%m-%d}**"
        f" ({len(dates):,} daily VaR predictions after a {WINDOW}-day warm-up).",
        "A *break* is a day the portfolio loses more than its VaR.",
        "",
        f"A test passes when its p-value is at least {ALPHA}. A verdict is marked",
        f"*borderline* when that p-value lies between {BORDERLINE[0]} and"
        f" {BORDERLINE[1]}: a 1% or a",
        "10% tolerance would have given the other answer.",
        "",
        "## Scorecard",
        "",
        "| Method | Breaks (obs/exp) | Test 1: frequency | Test 2: random in time | Test 3: independent of level |",
        "|---|---|---|---|---|",
        *scorecard_rows(bt.methods),
        "",
        "### Reading the results",
        "",
        "\n\n".join(commentary(bt)),
        "",
        "![VaR vs daily losses](var_vs_losses.png)",
        "",
        "![Cumulative breaks](cumulative_breaks.png)",
        "",
        "![Break timeline](break_timeline.png)",
        "",
        "## Method detail",
    ]
    for r in bt.methods:
        lines.append(method_section(r))
    lines += [
        '## "Should we try for two out of three?" — recalibrated variants',
        "",
        RECALIBRATED_NOTE,
        "",
        "| Method | Breaks (obs/exp) | Test 1: frequency | Test 2: random in time | Test 3: independent of level |",
        "|---|---|---|---|---|",
        *scorecard_rows(bt.recalibrated),
    ]
    for r in bt.recalibrated:
        lines.append(method_section(r))
    lines += [
        "",
        "---",
        "*Generated by `var_backtest.py`. Data: FRED NASDAQCOM (blank observations,*",
        "*i.e. market holidays, dropped as missing). `build_site.py` publishes the*",
        "*same results as a web page, and `test_pipeline.py` recomputes them from the*",
        "*raw data with code of its own.*",
        "",
    ]
    path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Charts (palette and mark specs per the repo's dataviz conventions)
# ---------------------------------------------------------------------------

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
CRITICAL = "#d03b3b"                          # VaR breaks
SERIES = ["#2a78d6", "#1baf7a", "#eda100"]    # HS, parametric, Brown

def style_axis(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.grid(axis="y", color=GRID, linewidth=1, zorder=0)
    ax.tick_params(colors=MUTED, labelsize=9)
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_color(MUTED)

def make_charts(results, dates, losses):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = "sans-serif"
    thousands = lambda x, _: f"{x/1000:,.0f}"
    from matplotlib.ticker import FuncFormatter

    # --- 1. VaR vs daily losses, small multiples -------------------------
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True, sharey=True)
    fig.patch.set_facecolor(SURFACE)
    for ax, r, color in zip(axes, results, SERIES):
        style_axis(ax)
        ax.scatter(dates, losses, s=3, color=MUTED, alpha=0.25, linewidths=0,
                   zorder=2, label="Daily loss")
        ax.plot(dates, r.var, color=color, linewidth=1.4, zorder=3,
                solid_joinstyle="round", label="VaR (99%)")
        bd = r.breaks
        ax.scatter(dates[bd], losses[bd], s=34, color=CRITICAL, zorder=4,
                   edgecolors=SURFACE, linewidths=1.5,
                   label=f"VaR break ({r.n_breaks})")
        ax.set_title(f"{r.title} — {r.n_breaks} breaks "
                     f"(expected {r.expected_breaks:.0f})",
                     loc="left", fontsize=11, color=INK, pad=8)
        ax.yaxis.set_major_formatter(FuncFormatter(thousands))
        leg = ax.legend(loc="upper left", frameon=False, fontsize=8,
                        labelcolor=INK_2)
        leg.set_zorder(5)
    axes[1].set_ylabel("Daily loss on \\$1M portfolio (\\$ thousands)",
                       color=INK_2, fontsize=10)
    fig.suptitle("99% VaR vs realized daily losses — NASDAQ Composite, $1M portfolio",
                 fontsize=13, color=INK, x=0.5, y=0.985)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(RESULTS_DIR / "var_vs_losses.png", dpi=150,
                facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)

    # --- 2. Cumulative breaks vs expected --------------------------------
    fig, ax = plt.subplots(figsize=(11, 5.5))
    fig.patch.set_facecolor(SURFACE)
    style_axis(ax)
    n = len(dates)
    expected = VAR_LEVEL * np.arange(1, n + 1)
    ax.plot(dates, expected, color=BASELINE, linewidth=2, zorder=2,
            label="Expected at 1%")
    ends = [("Expected at 1%", expected[-1], BASELINE)]
    for r, color in zip(results, SERIES):
        cum = np.cumsum(r.breaks)
        ax.plot(dates, cum, color=color, linewidth=2, zorder=3,
                solid_joinstyle="round", label=r.title)
        ends.append((f"{r.title} ({r.n_breaks})", cum[-1], color))
    # direct end labels, nudged apart if they collide
    ends.sort(key=lambda e: e[1])
    min_gap = max(e[1] for e in ends) * 0.045
    ypos = []
    for _, y, _ in ends:
        if ypos and y - ypos[-1] < min_gap:
            y = ypos[-1] + min_gap
        ypos.append(y)
    for (label, _, _), y in zip(ends, ypos):
        ax.annotate(label, (dates[-1], y), xytext=(8, 0),
                    textcoords="offset points", fontsize=9, color=INK_2,
                    va="center")
    ax.set_title("Test 1 & 2 at a glance — cumulative VaR breaks vs the 1% line",
                 loc="left", fontsize=13, color=INK, pad=10)
    ax.set_ylabel("Cumulative VaR breaks", color=INK_2, fontsize=10)
    ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK_2)
    ax.margins(x=0.10)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "cumulative_breaks.png", dpi=150,
                facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)

    # --- 3. Break timeline (clustering is visible) ------------------------
    fig, ax = plt.subplots(figsize=(11, 3.6))
    fig.patch.set_facecolor(SURFACE)
    style_axis(ax)
    ax.grid(False)
    names = []
    for i, (r, color) in enumerate(zip(results, SERIES)):
        y = len(results) - 1 - i
        ax.eventplot(dates[r.breaks], lineoffsets=y, linelengths=0.7,
                     linewidths=1.2, color=color, zorder=3)
        names.append((y, f"{r.title} ({r.n_breaks})"))
    ax.set_yticks([y for y, _ in names])
    ax.set_yticklabels([nm for _, nm in names], fontsize=10, color=INK_2)
    ax.tick_params(axis="y", length=0)
    ax.set_title("Test 2 at a glance — every VaR break day, by method "
                 "(clustered ticks = breaks are not random in time)",
                 loc="left", fontsize=12, color=INK, pad=10)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "break_timeline.png", dpi=150,
                facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

@dataclass
class Backtests:
    """Everything one run produces; the report, the charts and the web page
    are all written from this."""
    prices: pd.Series           # daily closes, blanks dropped
    n_rows: int                 # rows in the CSV, blanks included
    dates: pd.DatetimeIndex     # prediction days
    losses: np.ndarray          # dollar loss on each prediction day
    methods: list               # A, B, C
    recalibrated: list          # A2, B2
    target: int                 # break count the recalibration aims for
    hs_percentile: float        # A2's percentile, in %
    ewma_multiplier: float      # B2's sigma multiplier

def run():
    """Build the three VaR series, the two recalibrated ones, and backtest all."""
    prices, n_rows = load_prices()
    returns_s = prices.pct_change().dropna()
    returns = returns_s.to_numpy()
    dates = returns_s.index[WINDOW:]          # prediction days
    losses = -PORTFOLIO * returns[WINDOW:]    # dollar loss on each day

    wins = sorted_windows(returns)
    rolling_std = (
        pd.Series(returns).rolling(WINDOW).std().shift(1).to_numpy()[WINDOW:]
    )
    sigma = ewma_sigma(returns)

    # The three methods, article parameters
    methods = [
        backtest(
            "A", "Historical simulation", "3yr, 1st pct",
            "The 1% loss point of the last 750 daily returns — the "
            '"distribution-free" method in every textbook. It sits between the '
            "7th and 8th worst days of the window, where a break has exactly a "
            "1% chance if returns are independent draws from one distribution.",
            hs_var(wins, 100 * VAR_LEVEL), losses,
        ),
        backtest(
            "B", "Parametric EWMA", "0.94, 2.33σ",
            "RiskMetrics: variance = 0.94 × yesterday's variance + 0.06 × "
            "today's move squared; VaR = 2.33 standard deviations.",
            Z_99 * sigma * PORTFOLIO, losses,
        ),
        backtest(
            "C", "Brown's Bayesian VaR", "double on break",
            "Start from 2.33 × the 3-year standard deviation. After a break, "
            "double the estimate; otherwise take 0.94 × yesterday's estimate + "
            "0.06 × the simple estimate.",
            brown_var(losses, Z_99 * rolling_std * PORTFOLIO), losses,
        ),
    ]

    # Recalibrated variants: force Test 1 to pass, as in the article
    target = round(VAR_LEVEL * len(losses))
    pct = calibrate(
        lambda q: int(np.sum(losses > hs_var(wins, q))), 0.05, 3.0, target
    )
    mult = -calibrate(   # negated, so the break count rises with the parameter
        lambda m: int(np.sum(losses > -m * sigma * PORTFOLIO)), -12.0, -Z_99, target
    )
    recalibrated = [
        backtest(
            "A2", "Historical simulation recalibrated", f"{pct:.2f} pct",
            f"Percentile moved from 1.00 to {pct:.2f} so the break count is "
            f"the expected {target}.",
            hs_var(wins, pct), losses,
        ),
        backtest(
            "B2", "Parametric recalibrated", f"{mult:.2f}σ",
            f"Sigma multiplier moved from 2.33 to {mult:.2f} so the break "
            f"count is the expected {target}.",
            mult * sigma * PORTFOLIO, losses,
        ),
    ]
    return Backtests(prices, n_rows, dates, losses, methods, recalibrated,
                     target, pct, mult)

def write_outputs(bt):
    """The markdown report and the three PNG charts in results/."""
    RESULTS_DIR.mkdir(exist_ok=True)
    write_report(bt, RESULTS_DIR / "backtest_report.md")
    make_charts(bt.methods, bt.dates, bt.losses)

def print_scorecard(bt):
    dates = bt.dates
    print(f"\nVaR backtest — NASDAQ Composite, $1M portfolio, "
          f"{dates[0]:%Y-%m-%d} to {dates[-1]:%Y-%m-%d} "
          f"({len(dates):,} predictions, {bt.target} breaks expected)\n")
    header = (f"{'Method':<50} {'Breaks':>6}  {'T1 frequency':<18}"
              f"{'T2 timing':<18}{'T3 level':<18}")
    print(header)
    print("-" * len(header))
    for r in bt.methods + bt.recalibrated:
        print(f"{r.title:<50} {r.n_breaks:>6}  {verdict(r, 0):<18}"
              f"{verdict(r, 1):<18}{verdict(r, 2):<18}")

def main():
    bt = run()
    write_outputs(bt)
    print_scorecard(bt)
    print(f"\nFull detail: {RESULTS_DIR / 'backtest_report.md'}")


if __name__ == "__main__":
    main()
