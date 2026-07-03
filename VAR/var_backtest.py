"""VaR backtest based on Aaron Brown's "Forced by the Sternest Circumstances"
(Wilmott magazine, July 2009).

Builds three daily 99% VaR estimators for a $1M position in the NASDAQ
Composite and runs the three backtests the article says every VaR must pass:

  Test 1: the actual fraction of VaR break days is 1%, within statistical
          tolerance;
  Test 2: the VaR breaks are randomly distributed in time;
  Test 3: the VaR breaks are independent of the level of VaR.

Methods (same parameters as the article — no fitting):
  A. Historical simulation — 1st percentile of the last 3 years (750 days).
  B. Parametric (RiskMetrics) — EWMA variance, 0.94 decay, VaR = 2.33 sigma.
  C. Brown's "Bayesian" VaR — start from 2.33 x 3-year standard deviation;
     double after a break; otherwise decay 0.94 x yesterday + 0.06 x simple.

Also reproduces the article's "two out of three?" exercise: recalibrate A and
B to give exactly the expected number of breaks and show they still fail
Tests 2 and 3.

Usage: python3 var_backtest.py
Writes results/backtest_report.md and three PNG charts to results/.
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


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load_returns():
    """Load FRED NASDAQCOM data; blank observations (holidays) are dropped."""
    raw = pd.read_csv(DATA_FILE, parse_dates=["observation_date"])
    raw = raw.dropna(subset=["NASDAQCOM"]).set_index("observation_date")
    returns = raw["NASDAQCOM"].pct_change().dropna()
    return returns


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
    """Historical simulation VaR at the given percentile (in %)."""
    pos = (WINDOW - 1) * percentile / 100.0
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
    name: str
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

def backtest(name, description, var, losses):
    """Run the article's three tests on a VaR series."""
    breaks = losses > var
    r = BacktestResult(name, description, var, breaks)

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
    rng = np.random.default_rng(20090701)
    sims = np.array([
        var[rng.choice(r.n_obs, r.n_breaks, replace=False)].mean()
        for _ in range(10_000)
    ])
    r.perm_p = 2 * min(
        (sims <= r.avg_var_on_breaks).mean(), (sims >= r.avg_var_on_breaks).mean()
    )
    r.welch_p = stats.ttest_ind(var[breaks], var[~breaks], equal_var=False).pvalue
    r.pass3 = r.perm_p >= ALPHA
    return r


# ---------------------------------------------------------------------------
# Calibrated variants (the article's "should we try for two out of three?")
# ---------------------------------------------------------------------------

def calibrate(count_fn, lo, hi, target, tol=1e-7):
    """Bisect a monotone-increasing break-count function to hit target."""
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if count_fn(mid) > target:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def dollars(x):
    return f"${x:,.0f}"

def flag(ok):
    return "PASS" if ok else "FAIL"

def pfmt(p, floor=2e-4):
    """Monte Carlo p-values below the simulation resolution show as a bound."""
    return f"< {floor:g}" if p < floor else f"{p:.2g}"

def scorecard_rows(results):
    rows = []
    for r in results:
        rows.append(
            f"| {r.name} | {r.n_breaks} / {r.expected_breaks:.0f} exp. "
            f"| {flag(r.pass1)} | {flag(r.pass2)} | {flag(r.pass3)} |"
        )
    return rows

def method_section(r):
    verdict = "a usable VaR" if (r.pass1 and r.pass2 and r.pass3) else "not a VaR"
    rate = r.n_breaks / r.n_obs
    return f"""
### {r.name}

{r.description}

**Test 1 — break frequency is 1%: {flag(r.pass1)}**

| Metric | Value |
|---|---|
| Observations | {r.n_obs:,} |
| VaR breaks | {r.n_breaks} |
| Expected breaks (1%) | {r.expected_breaks:.0f} |
| Observed break rate | {rate:.2%} |
| z-score vs 1% | {r.z_score:+.1f} |
| Kupiec POF p-value | {r.kupiec_p:.2g} |

**Test 2 — breaks randomly distributed in time: {flag(r.pass2)}**

| Metric | Observed | Expected if independent | p-value |
|---|---|---|---|
| Breaks the day after a break | {r.next_day_breaks} | {r.next_day_expected:.1f} | {r.next_day_p:.2g} |
| Breaks within 10 days of a break | {r.within10_breaks} | {r.within10_expected:.1f} | {r.within10_p:.2g} |
| Christoffersen independence test | — | — | {r.christoffersen_p:.2g} |

**Test 3 — breaks independent of the VaR level: {flag(r.pass3)}**

| Metric | Value |
|---|---|
| Average VaR | {dollars(r.avg_var)} |
| Average VaR on break days | {dollars(r.avg_var_on_breaks)} |
| Ratio (break days / all days) | {r.avg_var_on_breaks / r.avg_var:.2f} |
| Permutation test p-value (are break days a random sample of days?) | {pfmt(r.perm_p)} |
| Welch t-test p-value (break vs non-break days) | {r.welch_p:.2g} |

**Verdict: {verdict}** — {'passes' if (r.pass1 and r.pass2 and r.pass3) else 'fails'} {'all three tests' if (r.pass1 and r.pass2 and r.pass3) else 'test(s) ' + ', '.join(t for t, ok in zip('123', (r.pass1, r.pass2, r.pass3)) if not ok)}.
"""

def _commentary(main):
    a, b, c = main
    return (
        f"The textbook methods fail the same way they do in the article. "
        f"Historical simulation gives {a.n_breaks} breaks instead of "
        f"{a.expected_breaks:.0f}, and {a.next_day_breaks} of them land the very "
        f"next day after another break where independence would predict about "
        f"{a.next_day_expected:.0f} — volatility clusters, and a 3-year window "
        f"cannot see it. Parametric EWMA is worse on frequency "
        f"({b.n_breaks} breaks) and just as clustered. Both also break "
        f"disproportionately on days when they say things are safe. "
        f"Brown's double-on-break rule — the article's parameters untouched, "
        f"nothing fitted to this data — passes Tests 1 and 2 outright. "
        f"On this NASDAQ series it narrowly fails Test 3: its average VaR on "
        f"break days ({dollars(c.avg_var_on_breaks)}) sits about "
        f"{1 - c.avg_var_on_breaks / c.avg_var:.0%} below its overall average "
        f"({dollars(c.avg_var)}), p = {pfmt(c.perm_p)}. That is a marginal miss "
        f"on the bad side (the article's S&P run erred slightly the other way), "
        f"not the decisive failure of the other two methods — but a "
        f"nonrubber-stamp backtest reports it as a failure all the same."
    )

def write_report(results, calibrated, dates, path):
    main, extra = results, calibrated
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
        f"A *break* is a day the portfolio loses more than its VaR."
        f" Pass/fail tolerance: p ≥ {ALPHA} on the tests shown.",
        "",
        "## Scorecard",
        "",
        "| Method | Breaks (obs/exp) | Test 1: frequency | Test 2: random in time | Test 3: independent of level |",
        "|---|---|---|---|---|",
        *scorecard_rows(main),
        "",
        "### Reading the results",
        "",
        _commentary(main),
        "",
        "![VaR vs daily losses](var_vs_losses.png)",
        "",
        "![Cumulative breaks](cumulative_breaks.png)",
        "",
        "![Break timeline](break_timeline.png)",
        "",
        "## Method detail",
    ]
    for r in main:
        lines.append(method_section(r))
    lines += [
        '## "Should we try for two out of three?" — recalibrated variants',
        "",
        "As in the article, the failing methods can be forced to pass Test 1 by",
        "moving the percentile / sigma multiplier until the break count is exactly",
        "the expected number. They still fail the other tests — the miscalibration",
        "is not the problem, the clustering is.",
        "",
        "| Method | Breaks (obs/exp) | Test 1: frequency | Test 2: random in time | Test 3: independent of level |",
        "|---|---|---|---|---|",
        *scorecard_rows(extra),
    ]
    for r in extra:
        lines.append(method_section(r))
    lines += [
        "",
        "---",
        "*Generated by `var_backtest.py`. Data: FRED NASDAQCOM (blank*",
        "*observations, i.e. market holidays, dropped as missing).*",
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
        ax.set_title(f"{r.name} — {r.n_breaks} breaks "
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
                solid_joinstyle="round", label=r.name)
        ends.append((f"{r.name} ({r.n_breaks})", cum[-1], color))
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
        names.append((y, f"{r.name} ({r.n_breaks})"))
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

def main():
    RESULTS_DIR.mkdir(exist_ok=True)
    returns_s = load_returns()
    returns = returns_s.to_numpy()
    dates = returns_s.index[WINDOW:]          # prediction days
    losses = -PORTFOLIO * returns[WINDOW:]    # dollar loss on each day

    wins = sorted_windows(returns)
    rolling_std = (
        pd.Series(returns).rolling(WINDOW).std().shift(1).to_numpy()[WINDOW:]
    )
    sigma = ewma_sigma(returns)

    # The three methods, article parameters
    var_hs = hs_var(wins, 1.0)
    var_param = Z_99 * sigma * PORTFOLIO
    var_brown = brown_var(losses, Z_99 * rolling_std * PORTFOLIO)

    results = [
        backtest(
            "A. Historical simulation (3yr, 1st pct)",
            "1st percentile of the last 750 daily returns — the "
            '"distribution-free" method in every textbook.',
            var_hs, losses,
        ),
        backtest(
            "B. Parametric EWMA (0.94, 2.33σ)",
            "RiskMetrics: variance = 0.94 x yesterday's variance + 0.06 x "
            "today's move squared; VaR = 2.33 standard deviations.",
            var_param, losses,
        ),
        backtest(
            "C. Brown's Bayesian VaR (double on break)",
            "Start from 2.33 x 3-year standard deviation. After a break, "
            "double the estimate; otherwise 0.94 x yesterday's estimate + "
            "0.06 x the simple estimate.",
            var_brown, losses,
        ),
    ]

    # Recalibrated variants: force Test 1 to pass, as in the article
    target = round(VAR_LEVEL * len(losses))
    pct = calibrate(
        lambda q: int(np.sum(losses > hs_var(wins, q))), 0.05, 3.0, target
    )
    mult = calibrate(
        lambda m: int(np.sum(losses > (-m) * sigma * PORTFOLIO)), -12.0, -Z_99, target
    )
    mult = -mult
    calibrated = [
        backtest(
            f"A2. Historical simulation recalibrated ({pct:.2f} pct)",
            f"Percentile moved from 1.00 to {pct:.2f} so the break count "
            f"is as close as possible to the expected {target}.",
            hs_var(wins, pct), losses,
        ),
        backtest(
            f"B2. Parametric recalibrated ({mult:.2f}σ)",
            f"Sigma multiplier moved from 2.33 to {mult:.2f} so the break "
            f"count is as close as possible to the expected {target}.",
            mult * sigma * PORTFOLIO, losses,
        ),
    ]

    write_report(results, calibrated, dates, RESULTS_DIR / "backtest_report.md")
    make_charts(results, dates, losses)

    # Console scorecard
    print(f"\nVaR backtest — NASDAQ Composite, $1M portfolio, "
          f"{dates[0]:%Y-%m-%d} to {dates[-1]:%Y-%m-%d} "
          f"({len(dates):,} predictions, {target} breaks expected)\n")
    header = (f"{'Method':<46} {'Breaks':>7} {'T1 freq':>8} "
              f"{'T2 time':>8} {'T3 level':>9}")
    print(header)
    print("-" * len(header))
    for r in results + calibrated:
        print(f"{r.name:<46} {r.n_breaks:>7} {flag(r.pass1):>8} "
              f"{flag(r.pass2):>8} {flag(r.pass3):>9}")
    print(f"\nFull detail: {RESULTS_DIR / 'backtest_report.md'}")


if __name__ == "__main__":
    main()
