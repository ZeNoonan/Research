"""Independent checks of the built VaR page, recomputed from the raw data.

index.html carries its numbers as JSON between ``/*__DATA__*/`` and
``/*__END_DATA__*/``. This file recomputes every one of them from
``data/NASDAQCOM.csv`` and reports any that disagree:

1. the page: it is template.html with only the data dropped in, it loads
   nothing from anywhere else, and it quotes the article's three tests;
2. the source data: one row per weekday, in order, a blank only where the
   market was shut, no move too large to be real, and the row counts and
   dates the page states;
3. the series: every prediction day, each day's dollar loss, and the VaR
   each of the three methods set for it;
4. the breaks: the days each method's VaR was exceeded;
5. the three backtests of each method: counts, expectations, every p-value
   and every PASS / FAIL / borderline call;
6. the two recalibrated variants, rebuilt from the parameter the page states;
7. the prose: every figure in the commentary, and each thing it claims;
8. the written report, whose scorecard must say what the page says;
9. the method itself, where the answer is known: on simulated returns with
   nothing to cluster, the historical-simulation rule must break on 1% of
   days, and the usual spreadsheet percentile must not.

Independence is the point. This file never imports ``var_backtest.py`` or
``build_site.py`` and uses only the standard library: its own CSV reader, its
own rolling window, its own chi-square, binomial, Student-t and permutation
tests. A check that reuses the pipeline's code repeats the pipeline's
mistakes. The first version of this project took its 1% loss point from
numpy's percentile, which sits a day less extreme than the article's rule
and overstated one method's failure; a check built on the same call would
have agreed with it. Check 9 is here because of that.

Run after every build:

    python3 test_pipeline.py              # check the page
    python3 test_pipeline.py --self-test  # plant faults in a copy of the
                                          # page; confirm each one is caught

Exit status 0 means every check passed. With ``--self-test`` it means every
planted fault was caught.
"""

from __future__ import annotations

import argparse
import bisect
import copy
import csv
import json
import math
import random
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
CSV_PATH = HERE / "data" / "NASDAQCOM.csv"
PAGE_PATH = HERE / "index.html"
TEMPLATE_PATH = HERE / "template.html"
REPORT_PATH = HERE / "results" / "backtest_report.md"

# The article's parameters, stated here and not read from the pipeline.
PORTFOLIO = 1_000_000.0
VAR_LEVEL = 0.01            # a 99% VaR: one break expected in a hundred days
WINDOW = 750                # "three years" of trading days
DECAY = 0.94                # RiskMetrics
Z = 2.33                    # the article's figure for the Gaussian 1% point
ALPHA = 0.05                # a test passes at p >= ALPHA
BORDERLINE = (0.01, 0.10)   # p in here: another tolerance, another verdict
SETTINGS = {
    "portfolio": 1_000_000, "var_level": VAR_LEVEL, "window": WINDOW, "decay": DECAY,
    "z": Z, "alpha": ALPHA, "borderline": list(BORDERLINE),
}
ARTICLE_TESTS = (
    "The actual fraction of VaR break days is 1 percent, within statistical tolerance;",
    "The VaR breaks are randomly distributed in time;",
    "The VaR breaks are independent of the level of VaR.",
)
PAGES_URL = "https://zenoonan.github.io/Research/VAR/"

EPOCH = date(1970, 1, 1)
CHECK_DRAWS, CHECK_SEED = 20_000, 424242          # this file's own permutation test
IDEAL_SERIES, IDEAL_DAYS, IDEAL_SEED = 20, 13_968, 2009
DATA_RE = re.compile(r"/\*__DATA__\*/(.*?)/\*__END_DATA__\*/", re.S)
NUMBER_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?%?")
REPORT_ROW_RE = re.compile(
    r"^\| (A2|B2|A|B|C)\. [^|]*\| (\d+) / (\d+) exp\. \| ([^|]*?) \| ([^|]*?) \| ([^|]*?) \|$", re.M)


# ---------------------------------------------------------------------------
# Collecting results
# ---------------------------------------------------------------------------

def short(value):
    text = repr(value)
    return text if len(text) <= 70 else text[:67] + "..."

class Checks:
    """Every check is counted; a failed one leaves a line saying what differs."""

    def __init__(self):
        self.failures = []
        self.sections = []          # [name, checks run]

    def start(self, name):
        self.sections.append([name, 0])

    def ok(self, good, message):
        self.sections[-1][1] += 1
        if not good:
            self.failures.append(f"{self.sections[-1][0]}: {message}")
        return bool(good)

    def eq(self, what, page, mine):
        return self.ok(page == mine, f"{what}: page has {short(page)}, recomputed {short(mine)}")

    def close(self, what, page, mine, rel=1e-6, tol=0.0):
        good = (isinstance(page, (int, float)) and not isinstance(page, bool)
                and math.isfinite(page)
                and abs(page - mine) <= max(tol, rel * max(abs(page), abs(mine))))
        return self.ok(good, f"{what}: page has {short(page)}, recomputed {short(mine)}")

    @property
    def count(self):
        return sum(n for _, n in self.sections)


# ---------------------------------------------------------------------------
# The statistics, written out here from their definitions
# ---------------------------------------------------------------------------

def chi2_tail_1df(x):
    """P(chi-square with one degree of freedom > x)."""
    return math.erfc(math.sqrt(max(x, 0.0) / 2.0))

def log_likelihood(hits, trials, p):
    """Binomial log likelihood, with 0 log 0 = 0."""
    misses = trials - hits
    return (hits * math.log(p) if hits else 0.0) + (misses * math.log(1.0 - p) if misses else 0.0)

def kupiec_p(days, breaks, p):
    """Kupiec's proportion-of-failures test: is the break rate p?"""
    ratio = 2.0 * (log_likelihood(breaks, days, breaks / days) - log_likelihood(breaks, days, p))
    return chi2_tail_1df(ratio)

def christoffersen_p(flags):
    """Christoffersen's independence test: is a break likelier the day after a break?"""
    after_quiet = [0, 0]        # [no break, break] on days following a quiet day
    after_break = [0, 0]
    for yesterday, today in zip(flags, flags[1:]):
        (after_break if yesterday else after_quiet)[1 if today else 0] += 1
    quiet_days, break_days = sum(after_quiet), sum(after_break)
    pooled = (after_quiet[1] + after_break[1]) / (quiet_days + break_days)
    separate = (log_likelihood(after_quiet[1], quiet_days, after_quiet[1] / quiet_days)
                + log_likelihood(after_break[1], break_days, after_break[1] / break_days))
    together = log_likelihood(after_quiet[1] + after_break[1], quiet_days + break_days, pooled)
    return chi2_tail_1df(2.0 * (separate - together))

def binomial_two_sided(hits, trials, p):
    """Exact binomial test: the total probability of every outcome no likelier
    than the one seen."""
    def log_pmf(k):
        return (math.lgamma(trials + 1) - math.lgamma(k + 1) - math.lgamma(trials - k + 1)
                + k * math.log(p) + (trials - k) * math.log1p(-p))
    limit = log_pmf(hits) + 1e-7            # a whisker of slack for ties
    return min(1.0, math.fsum(math.exp(log_pmf(k)) for k in range(trials + 1) if log_pmf(k) <= limit))

def incomplete_beta(a, b, x):
    """Regularised incomplete beta function, by its continued fraction."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    if x > (a + 1.0) / (a + b + 2.0):
        return 1.0 - incomplete_beta(b, a, 1.0 - x)
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log1p(-x)) / a
    tiny = 1e-300
    c, d = 1.0, 1.0 - (a + b) * x / (a + 1.0)
    d = 1.0 / (d if abs(d) > tiny else tiny)
    total = d
    for m in range(1, 500):
        for numerator in (m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m)),
                          -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))):
            d = 1.0 + numerator * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + numerator / c
            c = c if abs(c) > tiny else tiny
            total *= d * c
        if abs(d * c - 1.0) < 1e-15:
            break
    return front * total

def welch_p(first, second):
    """Welch's t-test, two-sided: do two samples share a mean?"""
    def mean_var(values):
        m = math.fsum(values) / len(values)
        return m, math.fsum((v - m) ** 2 for v in values) / (len(values) - 1)
    (m1, v1), (m2, v2) = mean_var(first), mean_var(second)
    e1, e2 = v1 / len(first), v2 / len(second)
    t = (m1 - m2) / math.sqrt(e1 + e2)
    freedom = (e1 + e2) ** 2 / (e1 ** 2 / (len(first) - 1) + e2 ** 2 / (len(second) - 1))
    return incomplete_beta(freedom / 2.0, 0.5, freedom / (freedom + t * t))

def permutation_p(values, size, observed_total, draws, seed):
    """Is `observed_total` an ordinary total for `size` values drawn at random?"""
    rng = random.Random(seed)
    low = high = 0
    for _ in range(draws):
        total = sum(rng.sample(values, size))
        low += total <= observed_total
        high += total >= observed_total
    return min(1.0, 2.0 * min(low, high) / draws)

def mc_noise(p, draws):
    """Standard error of a two-sided Monte Carlo p-value."""
    tail = min(max(p, 2.0 / draws), 1.0) / 2.0
    return 2.0 * math.sqrt(tail * (1.0 - tail) / draws)


# ---------------------------------------------------------------------------
# The three VaR methods, written out here from the article
# ---------------------------------------------------------------------------

def article_position(p):
    """Where the p-th percentile sits in a sorted window, counting from 0.

    A new day is equally likely to rank anywhere among the window's n days
    and itself, so it is worse than the k-th worst with probability
    k / (n + 1). For that to be p, k = p x (n + 1): rank 7.51 for 1% of 750.
    """
    return p * (WINDOW + 1) - 1.0

def spreadsheet_position(p):
    """The same percentile as Excel's PERCENTILE or numpy's default has it."""
    return p * (WINDOW - 1)

def window_quantile(returns, position):
    """For each day after the first WINDOW, the value at `position` (counted
    from 0, fractions interpolated) in the sorted WINDOW returns before it."""
    position = min(max(position, 0.0), WINDOW - 1.0)
    below = min(int(position), WINDOW - 2)
    share = position - below
    window = sorted(returns[:WINDOW])
    out = []
    for t in range(WINDOW, len(returns)):
        out.append(window[below] + share * (window[below + 1] - window[below]))
        del window[bisect.bisect_left(window, returns[t - WINDOW])]
        bisect.insort(window, returns[t])
    return out

def ewma_sigma(returns, decay=DECAY):
    """RiskMetrics volatility for each prediction day, seeded with the sample
    variance of the first WINDOW returns."""
    seed = returns[:WINDOW]
    mean = math.fsum(seed) / WINDOW
    variance = math.fsum((r - mean) ** 2 for r in seed) / (WINDOW - 1)
    out = []
    for t in range(WINDOW, len(returns)):
        out.append(math.sqrt(variance))
        variance = decay * variance + (1.0 - decay) * returns[t] ** 2
    return out

def brown_var(returns, loss, after_break=2.0):
    """Brown's rule: start from Z x the three-year standard deviation; after
    a break double the estimate, otherwise move 6% of the way back to it."""
    out = []
    for i, t in enumerate(range(WINDOW, len(returns))):
        if i % 250 == 0:                    # exact sums now and then; running sums drift
            total = math.fsum(returns[t - WINDOW:t])
            squares = math.fsum(r * r for r in returns[t - WINDOW:t])
        simple = Z * math.sqrt((squares - total * total / WINDOW) / (WINDOW - 1)) * PORTFOLIO
        if i == 0:
            estimate = simple
        elif loss[i - 1] > out[-1]:
            estimate = after_break * out[-1]
        else:
            estimate = DECAY * out[-1] + (1.0 - DECAY) * simple
        out.append(estimate)
        total += returns[t] - returns[t - WINDOW]
        squares += returns[t] ** 2 - returns[t - WINDOW] ** 2
    return out

def backtest(var, loss, draws=CHECK_DRAWS):
    """The article's three tests on one VaR series."""
    days = len(var)
    flags = [lost > limit for lost, limit in zip(loss, var)]
    breaks = [i for i, hit in enumerate(flags) if hit]
    count = len(breaks)
    rate = count / days
    gaps = [b - a for a, b in zip(breaks, breaks[1:])]
    within10_chance = 1.0 - (1.0 - rate) ** 10
    next_day = sum(g == 1 for g in gaps)
    within10 = sum(g <= 10 for g in gaps)
    on_breaks = [var[i] for i in breaks]
    off_breaks = [limit for limit, hit in zip(var, flags) if not hit]
    return {
        "breaks": breaks,
        "count": count,
        "rate": rate,
        "z": (count - VAR_LEVEL * days) / math.sqrt(days * VAR_LEVEL * (1.0 - VAR_LEVEL)),
        "kupiec_p": kupiec_p(days, count, VAR_LEVEL),
        "next_day": next_day,
        "next_day_expected": len(gaps) * rate,
        "next_day_p": binomial_two_sided(next_day, len(gaps), rate),
        "within10": within10,
        "within10_expected": len(gaps) * within10_chance,
        "within10_p": binomial_two_sided(within10, len(gaps), within10_chance),
        "christoffersen_p": christoffersen_p(flags),
        "avg_var": math.fsum(var) / days,
        "avg_var_breaks": math.fsum(on_breaks) / count,
        "welch_p": welch_p(on_breaks, off_breaks),
        "perm_p": permutation_p(var, count, math.fsum(on_breaks), draws, CHECK_SEED),
    }


# ---------------------------------------------------------------------------
# 2. The source data
# ---------------------------------------------------------------------------

def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    return rows[0], rows[1:]

def next_weekday(day):
    return day + timedelta(days=3 if day.weekday() == 4 else 1)

def check_source(ck, header, rows, source):
    """Checks the file, and returns its closes as (day, value)."""
    ck.start("source data")
    ck.eq("CSV header", header, ["observation_date", "NASDAQCOM"])
    closes, problems = [], []
    blank = run = longest = 0
    previous = None
    for line, row in enumerate(rows, start=2):
        try:
            day = date.fromisoformat(row[0])
            text = row[1].strip()
        except (ValueError, IndexError):
            problems.append(f"line {line}: cannot read {row!r}")
            continue
        if day.weekday() > 4:
            problems.append(f"line {line}: {day} is at a weekend")
        elif previous is not None and day != next_weekday(previous):
            problems.append(f"line {line}: {day} does not follow {previous}")
        previous = day
        if text in ("", "."):               # FRED leaves a holiday blank
            blank += 1
            run += 1
            longest = max(longest, run)
            continue
        run = 0
        try:
            value = float(text)
        except ValueError:
            problems.append(f"line {line}: {text!r} is not a number")
            continue
        if not value > 0:
            problems.append(f"line {line}: a close of {value}")
        closes.append((day, value))
    ck.ok(not problems, "; ".join(problems[:3]) + (f"; and {len(problems) - 3} more" if len(problems) > 3 else ""))
    ck.ok(longest <= 5, f"{longest} blank weekdays in a row, longer than any market closure")
    if len(closes) > 1:
        move, when = max((abs(b[1] / a[1] - 1.0), b[0]) for a, b in zip(closes, closes[1:]))
        ck.ok(move < 0.20, f"a {move:.1%} move on {when}: check the file for a typo")
    ck.eq("source.series", source.get("series"), "NASDAQCOM")
    ck.eq("source.rows", source.get("rows"), len(rows))
    ck.eq("source.blank", source.get("blank"), blank)
    ck.eq("source.closes", source.get("closes"), len(closes))
    if closes:
        ck.eq("source.first_close", source.get("first_close"), closes[0][0].isoformat())
        ck.eq("source.last_close", source.get("last_close"), closes[-1][0].isoformat())
    return closes


# ---------------------------------------------------------------------------
# Recomputing everything once from the closes
# ---------------------------------------------------------------------------

def recompute(closes):
    days = [day for day, _ in closes]
    prices = [value for _, value in closes]
    returns = [prices[j + 1] / prices[j] - 1.0 for j in range(len(prices) - 1)]
    loss = [-PORTFOLIO * r for r in returns[WINDOW:]]
    sigma = ewma_sigma(returns)
    series = {
        "A": [-PORTFOLIO * q for q in window_quantile(returns, article_position(VAR_LEVEL))],
        "B": [Z * s * PORTFOLIO for s in sigma],
        "C": brown_var(returns, loss),
    }
    return {
        "returns": returns,
        "sigma": sigma,
        "days": [(day - EPOCH).days for day in days[1 + WINDOW:]],
        "first": days[1 + WINDOW].isoformat(),
        "last": days[-1].isoformat(),
        "loss": loss,
        "series": series,
        "tests": {key: backtest(var, loss) for key, var in series.items()},
        "recalibrated": {},             # filled as the page's parameters are met
    }

def recalibrated(truth, key, parameter):
    """A2 or B2, rebuilt from the parameter the page states."""
    cache = truth["recalibrated"]
    if (key, parameter) not in cache:
        if key == "A2":
            quantile = window_quantile(truth["returns"], article_position(parameter / 100.0))
            var = [-PORTFOLIO * q for q in quantile]
        else:
            var = [parameter * s * PORTFOLIO for s in truth["sigma"]]
        cache[(key, parameter)] = backtest(var, truth["loss"])
    return cache[(key, parameter)]


# ---------------------------------------------------------------------------
# 1. The page itself
# ---------------------------------------------------------------------------

def check_shell(ck, html, template):
    ck.start("page")
    blocks = DATA_RE.findall(html)
    ck.ok(len(blocks) == 1, f"{len(blocks)} data blocks in index.html; there must be exactly one")
    emptied = DATA_RE.sub(lambda _: "/*__DATA__*/null/*__END_DATA__*/", html)
    ck.ok(emptied == template,
          "index.html is not template.html with the data dropped in: rebuild with build_site.py")
    ck.ok("{{" not in html, "an unfilled {{PLACEHOLDER}} is left in the page")
    ck.ok(f'<link rel="canonical" href="{PAGES_URL}">' in html, "the canonical link is missing or wrong")
    ck.ok('name="viewport"' in html, "no viewport meta tag: the page would not fit a phone")
    outside = re.findall(r"<script[^>]*\ssrc=|<link[^>]*stylesheet|<img[^>]*\ssrc=|<iframe|@import|url\(", html)
    ck.ok(not outside, f"the page loads something from outside itself: {outside[:3]}")
    for sentence in ARTICLE_TESTS:
        ck.ok(f"<li>{sentence}</li>" in html, f"the article's test is not quoted exactly: {sentence!r}")


# ---------------------------------------------------------------------------
# 3-6. The numbers
# ---------------------------------------------------------------------------

def check_series(ck, truth, data):
    ck.start("series")
    n = len(truth["loss"])
    expected = VAR_LEVEL * n
    for key, value in SETTINGS.items():
        ck.eq(f"settings.{key}", data["settings"].get(key), value)
    ck.ok(data["settings"].get("perm_draws", 0) >= 20_000,
          "fewer than 20,000 permutation draws: the Test 3 p-value would move with the seed")
    ck.eq("n", data.get("n"), n)
    ck.eq("first", data.get("first"), truth["first"])
    ck.eq("last", data.get("last"), truth["last"])
    ck.close("expected", data.get("expected"), expected, rel=1e-12)
    ck.eq("target", data.get("target"), round(expected))
    ck.eq("days", data.get("days"), truth["days"])
    compare_dollars(ck, "loss", data.get("loss"), truth["loss"], truth)
    ck.eq("method keys", [m.get("key") for m in data["methods"]], ["A", "B", "C"])
    for method in data["methods"]:
        key = method.get("key")
        if key in truth["series"]:
            compare_dollars(ck, f"{key} VaR", method.get("var"), truth["series"][key], truth)

def compare_dollars(ck, what, page, mine, truth):
    """The page rounds to whole dollars; anything further out is a difference."""
    if not isinstance(page, list) or len(page) != len(mine):
        ck.ok(False, f"{what}: page has {len(page) if isinstance(page, list) else 'no'} values, recomputed {len(mine)}")
        return
    wrong = [i for i, (p, m) in enumerate(zip(page, mine)) if not abs(p - m) <= 0.5 + 1e-6]
    if wrong:
        first = wrong[0]
        day = EPOCH + timedelta(days=truth["days"][first])
        ck.ok(False, f"{what}: {len(wrong):,} of {len(mine):,} days differ, first on {day} "
                     f"(page {page[first]:,}, recomputed {mine[first]:,.2f})")
    else:
        ck.ok(True, "")

def check_method(ck, key, page, mine, data):
    """One method's breaks and three backtests against this file's own."""
    t1, t2, t3 = page.get("t1", {}), page.get("t2", {}), page.get("t3", {})
    ck.eq(f"{key} break days", page.get("breaks"), mine["breaks"])
    ck.eq(f"{key} t1.breaks", t1.get("breaks"), mine["count"])
    ck.close(f"{key} t1.rate", t1.get("rate"), mine["rate"])
    ck.close(f"{key} t1.z", t1.get("z"), mine["z"], tol=1e-9)
    ck.close(f"{key} t1.p (Kupiec)", t1.get("p"), mine["kupiec_p"])
    ck.eq(f"{key} t2.next_day", t2.get("next_day"), mine["next_day"])
    ck.close(f"{key} t2.next_day_expected", t2.get("next_day_expected"), mine["next_day_expected"])
    ck.close(f"{key} t2.next_day_p", t2.get("next_day_p"), mine["next_day_p"])
    ck.eq(f"{key} t2.within10", t2.get("within10"), mine["within10"])
    ck.close(f"{key} t2.within10_expected", t2.get("within10_expected"), mine["within10_expected"])
    ck.close(f"{key} t2.within10_p", t2.get("within10_p"), mine["within10_p"])
    ck.close(f"{key} t2.christoffersen_p", t2.get("christoffersen_p"), mine["christoffersen_p"])
    ck.close(f"{key} t3.avg_var", t3.get("avg_var"), mine["avg_var"])
    ck.close(f"{key} t3.avg_var_breaks", t3.get("avg_var_breaks"), mine["avg_var_breaks"])
    ck.close(f"{key} t3.ratio", t3.get("ratio"), mine["avg_var_breaks"] / mine["avg_var"])
    ck.close(f"{key} t3.welch_p", t3.get("welch_p"), mine["welch_p"])

    # The permutation p-value is a Monte Carlo estimate, so it is checked
    # against this file's own estimate, to within the noise of the two.
    perm = t3.get("perm_p")
    draws = data["settings"].get("perm_draws", 1)
    if not isinstance(perm, (int, float)) or isinstance(perm, bool):
        ck.ok(False, f"{key} t3.perm_p: page has {short(perm)}")
        return None
    slack = 5.0 * math.hypot(mc_noise(perm, draws), mc_noise(mine["perm_p"], CHECK_DRAWS))
    ck.ok(abs(perm - mine["perm_p"]) <= slack,
          f"{key} t3.perm_p: page has {perm:.5f}, this file's own permutation test {mine['perm_p']:.5f} "
          f"(more than {slack:.5f} apart)")
    for edge in (BORDERLINE[0], ALPHA, BORDERLINE[1]):
        ck.ok(abs(perm - edge) > 5.0 * mc_noise(perm, draws),
              f"{key} t3.perm_p = {perm:.5f} is within Monte Carlo noise of {edge}: "
              "the verdict would depend on the seed")

    deciding = [mine["kupiec_p"], min(mine["christoffersen_p"], mine["within10_p"]), perm]
    calls = []
    verdicts = page.get("verdicts") or []
    ck.eq(f"{key} number of verdicts", len(verdicts), 3)
    for i, p in enumerate(deciding):
        call = {"pass": p >= ALPHA, "borderline": BORDERLINE[0] <= p < BORDERLINE[1], "p": p}
        calls.append(call)
        if i < len(verdicts):
            ck.eq(f"{key} Test {i + 1} pass", verdicts[i].get("pass"), call["pass"])
            ck.eq(f"{key} Test {i + 1} borderline", verdicts[i].get("borderline"), call["borderline"])
            ck.close(f"{key} Test {i + 1} deciding p", verdicts[i].get("p"), p)
    return calls

def check_tests(ck, truth, data):
    """Returns each method's verdicts as this file calls them, and the
    recomputed statistics they came from."""
    ck.start("backtests")
    calls, used = {}, {}
    for method in data["methods"]:
        key = method.get("key")
        if key in truth["tests"]:
            used[key] = truth["tests"][key]
            calls[key] = check_method(ck, key, method, used[key], data)

    ck.start("recalibrated")
    target = round(VAR_LEVEL * len(truth["loss"]))
    ck.eq("recalibrated keys", [m.get("key") for m in data["recalibrated"]], ["A2", "B2"])
    for method, unit in zip(data["recalibrated"], (" pct", "σ")):
        key, parameter = method.get("key"), method.get("parameter")
        if key not in ("A2", "B2") or not isinstance(parameter, float) or not 0.05 < parameter < 12:
            ck.ok(False, f"{key}: no usable parameter ({short(parameter)})")
            continue
        mine = recalibrated(truth, key, parameter)
        ck.ok(mine["count"] == target,
              f"{key}: with the stated parameter {parameter:.4f} there are {mine['count']} breaks, not the {target} aimed for")
        ck.eq(f"{key} spec", method.get("spec"), f"{parameter:.2f}{unit}")
        ck.ok(f" {parameter:.2f} " in str(method.get("description")) and f" {target}." in str(method.get("description")),
              f"{key}: the description does not give {parameter:.2f} and {target}")
        used[key] = mine
        calls[key] = check_method(ck, key, method, mine, data)
    return calls, used


# ---------------------------------------------------------------------------
# 7-8. The words
# ---------------------------------------------------------------------------

def percent_below(tests):
    return f"{1.0 - tests['avg_var_breaks'] / tests['avg_var']:.0%}"

def check_prose(ck, truth, data, calls):
    ck.start("prose")
    a, b, c = (truth["tests"][key] for key in "ABC")
    expected = f"{VAR_LEVEL * len(truth['loss']):.0f}"
    perm_c = next((m["t3"]["perm_p"] for m in data["methods"] if m.get("key") == "C"), float("nan"))
    figures = [
        [str(a["count"]), expected, f"{a['kupiec_p']:.3f}", str(a["next_day"]),
         f"{a['next_day_expected']:.0f}", str(a["within10"]), f"{a['within10_expected']:.0f}"],
        [f"{b['count'] / (VAR_LEVEL * len(truth['loss'])):.1f}", str(b["count"]),
         percent_below(a), percent_below(b)],
        [str(c["count"]), expected, str(c["next_day"]), f"{c['next_day_expected']:.1f}",
         str(c["within10"]), f"{c['within10_expected']:.0f}",
         "2", f"{min(c['christoffersen_p'], c['within10_p']):.3f}",        # "Test 2"
         "3", percent_below(c), f"{perm_c:.3f}",                           # "Test 3"
         "500"],                                                           # "S&P 500"
    ]
    commentary = data.get("commentary") or []
    ck.eq("paragraphs of commentary", len(commentary), len(figures))
    for i, (text, want) in enumerate(zip(commentary, figures), start=1):
        ck.eq(f"figures in paragraph {i}", NUMBER_RE.findall(str(text)), want)

    # What the commentary says in words has to hold as well.
    def verdict(key, test):
        return (calls.get(key) or [{}] * 3)[test - 1]
    def decisive_fail(key, test):
        v = verdict(key, test)
        return v.get("pass") is False and v.get("borderline") is False
    claims = {
        "A passes Test 1, but only just": verdict("A", 1).get("pass") and verdict("A", 1).get("borderline"),
        "A fails Tests 2 and 3 decisively": decisive_fail("A", 2) and decisive_fail("A", 3),
        "B fails all three tests decisively": all(decisive_fail("B", t) for t in (1, 2, 3)),
        "C passes Test 1 comfortably": verdict("C", 1).get("pass") and not verdict("C", 1).get("borderline"),
        "C passes Test 2 narrowly": verdict("C", 2).get("pass") and verdict("C", 2).get("borderline"),
        "C fails Test 3 narrowly": verdict("C", 3).get("pass") is False and verdict("C", 3).get("borderline"),
        "every method's VaR is lower on its break days": all(t["avg_var_breaks"] < t["avg_var"] for t in (a, b, c)),
        "the recalibrated variants pass Test 1 and fail Tests 2 and 3": all(
            verdict(key, 1).get("pass") and verdict(key, 2).get("pass") is False
            and verdict(key, 3).get("pass") is False for key in ("A2", "B2")),
    }
    for claim, holds in claims.items():
        ck.ok(holds, f"the commentary says {claim!r}, and that is no longer so")
    note = str(data.get("recalibrated_note"))
    ck.ok("pass Test 1 by construction and still fail the other two" in note,
          "the note on the recalibrated variants has changed: check it against the verdicts")

def check_report(ck, truth, report, calls, used):
    ck.start("report")
    expected = f"{VAR_LEVEL * len(truth['loss']):.0f}"
    rows = {m.group(1): m.groups()[1:] for m in REPORT_ROW_RE.finditer(report)}
    ck.eq("scorecard rows in the report", sorted(rows), sorted(calls))
    for key, verdicts in calls.items():
        if key not in rows or not verdicts:
            continue
        mine = used[key]
        want = (str(mine["count"]), expected) + tuple(
            ("PASS" if v["pass"] else "FAIL") + (" (borderline)" if v["borderline"] else "") for v in verdicts)
        ck.eq(f"report row {key}", rows[key], want)


# ---------------------------------------------------------------------------
# 9. The method, where the answer is known
# ---------------------------------------------------------------------------

def check_ideal_conditions(ck):
    """Independent fat-tailed returns have nothing to cluster, so a 1% VaR
    must break on 1% of days. This is what the article means by saying
    historical simulation "should guarantee that all three tests are met"."""
    ck.start("ideal conditions")
    rng = random.Random(IDEAL_SEED)
    article = spreadsheet = predictions = 0
    for _ in range(IDEAL_SERIES):
        returns = [0.01 * rng.gauss(0.0, 1.0) / math.sqrt(rng.gammavariate(2.0, 0.5))
                   for _ in range(IDEAL_DAYS)]          # Student-t, four degrees of freedom
        today = returns[WINDOW:]
        article += sum(r < q for r, q in zip(today, window_quantile(returns, article_position(VAR_LEVEL))))
        spreadsheet += sum(r < q for r, q in zip(today, window_quantile(returns, spreadsheet_position(VAR_LEVEL))))
        predictions += len(today)
    noise = math.sqrt(VAR_LEVEL * (1.0 - VAR_LEVEL) / predictions)
    article_rate, spreadsheet_rate = article / predictions, spreadsheet / predictions
    ck.ok(abs(article_rate - VAR_LEVEL) <= 4.0 * noise,
          f"the article's rule breaks on {article_rate:.3%} of simulated days, not 1% (noise {noise:.3%})")
    ck.ok(spreadsheet_rate - VAR_LEVEL >= 3.0 * noise,
          f"the spreadsheet percentile breaks on {spreadsheet_rate:.3%} of simulated days: "
          "it was expected to break too often")
    return predictions, article_rate, spreadsheet_rate


# ---------------------------------------------------------------------------
# Running the checks
# ---------------------------------------------------------------------------

class Case:
    """What is checked: the raw file, the page and its data, and the report."""

    def __init__(self):
        self.header, self.rows = read_csv(CSV_PATH)
        self.html = PAGE_PATH.read_text(encoding="utf-8")
        self.template = TEMPLATE_PATH.read_text(encoding="utf-8")
        self.report = REPORT_PATH.read_text(encoding="utf-8")
        block = DATA_RE.search(self.html)
        if block is None:
            sys.exit("index.html has no data block. Build it first: python3 build_site.py")
        self.data = json.loads(block.group(1).replace("<\\/", "</"))

    def copy(self):
        twin = copy.copy(self)
        twin.rows = [list(row) for row in self.rows]
        twin.data = copy.deepcopy(self.data)
        return twin

def check_case(case, truth):
    """Every check that compares the page with the recomputation."""
    ck = Checks()
    check_shell(ck, case.html, case.template)
    check_source(ck, case.header, case.rows, case.data.get("source", {}))
    check_series(ck, truth, case.data)
    calls, used = check_tests(ck, truth, case.data)
    check_prose(ck, truth, case.data, calls)
    check_report(ck, truth, case.report, calls, used)
    return ck

def load():
    case = Case()
    ck = Checks()
    closes = check_source(ck, case.header, case.rows, case.data.get("source", {}))
    if len(closes) <= WINDOW + 1:
        sys.exit("data/NASDAQCOM.csv could not be read: " + "; ".join(ck.failures))
    return case, recompute(closes)

def run():
    started = time.time()
    case, truth = load()
    ck = check_case(case, truth)
    predictions, article_rate, spreadsheet_rate = check_ideal_conditions(ck)

    n = len(truth["loss"])
    print(f"VaR page: {n:,} predictions, {truth['first']} to {truth['last']}, "
          f"{VAR_LEVEL * n:.0f} breaks expected")
    for key, tests in truth["tests"].items():
        print(f"  {key}: {tests['count']} breaks recomputed; "
              f"p = {tests['kupiec_p']:.3g}, "
              f"{min(tests['christoffersen_p'], tests['within10_p']):.3g}, {tests['perm_p']:.3g}")
    print(f"  on {predictions:,} simulated ideal days the article's rule breaks on "
          f"{article_rate:.3%}, the spreadsheet percentile on {spreadsheet_rate:.3%}")
    print()
    for name, count in ck.sections:
        print(f"  {name:<18} {count:>4} checks")
    print()
    if ck.failures:
        for failure in ck.failures:
            print("FAIL  " + failure)
        print(f"\n{len(ck.failures)} of {ck.count} checks failed ({time.time() - started:.0f}s)")
        return 1
    print(f"All checks passed ({ck.count} checks, {time.time() - started:.0f}s)")
    return 0


# ---------------------------------------------------------------------------
# --self-test: faults planted on purpose
# ---------------------------------------------------------------------------

def method(case, key):
    return next(m for m in case.data["methods"] + case.data["recalibrated"] if m["key"] == key)

def whole_dollars(series):
    return [round(v) for v in series]

def fault_spreadsheet_percentile(case, truth):
    """A's VaR taken from the spreadsheet percentile, as this project first did"""
    quantile = window_quantile(truth["returns"], spreadsheet_position(VAR_LEVEL))
    method(case, "A")["var"] = whole_dollars(-PORTFOLIO * q for q in quantile)

def fault_look_ahead(case, truth):
    """B's VaR a day early: each day judged against a VaR that had seen it"""
    var = method(case, "B")["var"]
    method(case, "B")["var"] = var[1:] + var[-1:]

def fault_decay(case, truth):
    """B's volatility decayed at 0.97 instead of 0.94"""
    method(case, "B")["var"] = whole_dollars(Z * s * PORTFOLIO for s in ewma_sigma(truth["returns"], 0.97))

def fault_not_doubled(case, truth):
    """C's VaR raised by half after a break instead of doubled"""
    method(case, "C")["var"] = whole_dollars(brown_var(truth["returns"], truth["loss"], 1.5))

def fault_series_swapped(case, truth):
    """B's and C's VaR series the wrong way round"""
    b, c = method(case, "B"), method(case, "C")
    b["var"], c["var"] = c["var"], b["var"]

def fault_break_dropped(case, truth):
    """one of C's break days missing from its list"""
    del method(case, "C")["breaks"][40]

def fault_break_count(case, truth):
    """A's break count one too high"""
    method(case, "A")["t1"]["breaks"] += 1

def fault_one_sided_p(case, truth):
    """A's Test 1 p-value from a one-sided z-test, which would fail it"""
    v = method(case, "A")
    v["t1"]["p"] = v["verdicts"][0]["p"] = 0.023
    v["verdicts"][0]["pass"] = False

def fault_p_values_swapped(case, truth):
    """A's two clustering p-values under each other's labels"""
    t2 = method(case, "A")["t2"]
    t2["next_day_p"], t2["within10_p"] = t2["within10_p"], t2["next_day_p"]

def fault_expected_clusters(case, truth):
    """C's expected next-day breaks worked out at 1% instead of its own rate"""
    t2 = method(case, "C")["t2"]
    t2["next_day_expected"] = VAR_LEVEL * (method(case, "C")["t1"]["breaks"] - 1)

def fault_verdict_flipped(case, truth):
    """C marked as passing Test 3"""
    method(case, "C")["verdicts"][2]["pass"] = True

def fault_borderline_dropped(case, truth):
    """A's Test 1 pass shown as a comfortable one"""
    method(case, "A")["verdicts"][0]["borderline"] = False

def fault_level_average(case, truth):
    """B's average VaR on break days given as its average on all days"""
    t3 = method(case, "B")["t3"]
    t3["avg_var_breaks"] = t3["avg_var"]

def fault_permutation_p(case, truth):
    """C's permutation p-value nudged over the line, with a verdict to match"""
    v = method(case, "C")
    v["t3"]["perm_p"] = v["verdicts"][2]["p"] = 0.06
    v["verdicts"][2]["pass"] = True

def fault_expected_breaks(case, truth):
    """breaks expected from every return, warm-up included"""
    case.data["expected"] = VAR_LEVEL * (case.data["n"] + WINDOW)

def fault_loss_sign(case, truth):
    """the largest loss entered as a gain"""
    worst = max(range(len(case.data["loss"])), key=case.data["loss"].__getitem__)
    case.data["loss"][worst] = -case.data["loss"][worst]

def fault_days_late(case, truth):
    """every prediction dated a day late"""
    case.data["days"] = [day + 1 for day in case.data["days"]]

def fault_recalibration_stale(case, truth):
    """A2 still at the 1.00 percentile it was meant to be moved from"""
    method(case, "A2")["parameter"] = 1.0

def fault_prose_figure(case, truth):
    """the commentary quoting the break count from before the percentile fix"""
    case.data["commentary"][0] = case.data["commentary"][0].replace("155", "176")

def fault_holiday_filled(case, truth):
    """a holiday filled in with the previous close, as a day with no move"""
    line = next(i for i, row in enumerate(case.rows)
                if i > 2000 and row[1].strip() == "" and case.rows[i - 1][1].strip())
    case.rows[line][1] = case.rows[line - 1][1]

def fault_date_day_first(case, truth):
    """a date in the file with its day and month the wrong way round"""
    line = next(i for i, row in enumerate(case.rows) if row[0].endswith("-03-04"))
    case.rows[line][0] = case.rows[line][0][:4] + "-04-03"

def fault_price_typo(case, truth):
    """a close in the file with a digit dropped"""
    line = next(i for i, row in enumerate(case.rows) if i > 5000 and row[1].strip())
    case.rows[line][1] = case.rows[line][1][1:]

def fault_stale_page(case, truth):
    """the page left over from an older template"""
    case.html = case.html.replace("<h2 id=\"h-score\">Scorecard</h2>", "<h2 id=\"h-score\">Results</h2>")

def fault_outside_script(case, truth):
    """a script loaded from another site"""
    case.html = case.html.replace("</body>", '<script src="https://cdn.example.com/chart.js"></script></body>')
    case.template = case.template.replace("</body>", '<script src="https://cdn.example.com/chart.js"></script></body>')

def fault_report_stale(case, truth):
    """the written report still showing A as failing Test 1"""
    case.report = case.report.replace("| 155 / 132 exp. | PASS (borderline) |", "| 176 / 132 exp. | FAIL |")

FAULTS = [
    fault_spreadsheet_percentile, fault_look_ahead, fault_decay, fault_not_doubled,
    fault_series_swapped, fault_break_dropped, fault_break_count, fault_one_sided_p,
    fault_p_values_swapped, fault_expected_clusters, fault_verdict_flipped,
    fault_borderline_dropped, fault_level_average, fault_permutation_p,
    fault_expected_breaks, fault_loss_sign, fault_days_late, fault_recalibration_stale,
    fault_prose_figure, fault_holiday_filled, fault_date_day_first, fault_price_typo,
    fault_stale_page, fault_outside_script, fault_report_stale,
]

def self_test():
    started = time.time()
    case, truth = load()
    clean = check_case(case, truth)
    if clean.failures:
        print("The page does not pass as it stands, so planted faults cannot be told apart from real ones:")
        for failure in clean.failures[:10]:
            print("FAIL  " + failure)
        return 1
    missed = 0
    for plant in FAULTS:
        trial = case.copy()
        plant(trial, truth)
        found = check_case(trial, truth).failures
        if found:
            print(f"caught  {plant.__doc__}\n          {found[0][:150]}"
                  + (f"  (+{len(found) - 1} more)" if len(found) > 1 else ""))
        else:
            missed += 1
            print(f"MISSED  {plant.__doc__}")
    print()
    if missed:
        print(f"{missed} of {len(FAULTS)} planted faults were not caught ({time.time() - started:.0f}s)")
        return 1
    print(f"Self-test passed: all {len(FAULTS)} planted faults caught ({time.time() - started:.0f}s)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--self-test", action="store_true",
                        help="plant faults in a copy of the page and confirm each is caught")
    args = parser.parse_args(argv)
    return self_test() if args.self_test else run()


if __name__ == "__main__":
    sys.exit(main())
