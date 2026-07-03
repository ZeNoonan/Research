# VAR — Value at Risk backtesting on the NASDAQ Composite

An implementation of the VaR framework in Aaron Brown's *"Forced by the
Sternest Circumstances"* (Wilmott magazine, July 2009), run on the NASDAQ
Composite index (FRED series `NASDAQCOM`, 1971–2026) for a hypothetical
**$1,000,000** portfolio.

The point of the article — and of this project — is not the VaR number
itself but the **checks**. A daily 99% VaR is only a VaR if nobody could
make money betting for or against your break days at 99-to-1 odds. Brown
gives three tests every VaR methodology must pass:

> 1. The actual fraction of VaR break days is 1 percent, within statistical
>    tolerance;
> 2. The VaR breaks are randomly distributed in time;
> 3. The VaR breaks are independent of the level of VaR.

A *break* is a day the portfolio loses more than its VaR.

## The three methods

All three use the article's parameters unchanged — nothing is fitted to this
dataset:

| | Method | Rule |
|---|---|---|
| A | Historical simulation | 1st percentile of the last 3 years (750 trading days) of returns — the "distribution-free" textbook method |
| B | Parametric (RiskMetrics) | EWMA variance: 0.94 × yesterday's variance + 0.06 × today's move²; VaR = 2.33σ |
| C | Brown's "Bayesian" VaR | Start from 2.33 × 3-year standard deviation. After a break, **double** the estimate; otherwise take 0.94 × yesterday's estimate + 0.06 × the simple estimate |

## Results (1974-01-29 to 2026-07-02, 13,218 predictions, 132 breaks expected)

| Method | Breaks | Test 1: frequency | Test 2: random in time | Test 3: independent of level |
|---|---|---|---|---|
| A. Historical simulation (3yr, 1st pct) | 176 | FAIL | FAIL | FAIL |
| B. Parametric EWMA (0.94, 2.33σ) | 269 | FAIL | FAIL | FAIL |
| C. Brown's Bayesian VaR (double on break) | 134 | **PASS** | **PASS** | FAIL (marginal) |

The NASDAQ data reproduces the article's findings almost exactly. The two
textbook methods break far too often, and their breaks cluster heavily —
historical simulation has 19 breaks landing the day after another break
where independence predicts about 2. Recalibrating them to give exactly the
expected break count (the article's "two out of three?" exercise: the 0.69th
percentile, or 2.94σ) fixes Test 1 by construction but they still fail
Tests 2 and 3 — the problem is volatility clustering, not calibration.

Brown's double-on-break rule, with no tuning at all, gives 134 breaks
against 132 expected and passes the randomness-in-time test. One honest
caveat the checks surface: on this NASDAQ series it narrowly fails Test 3 —
its average VaR on break days is about 10% below its overall average VaR
(permutation p ≈ 0.02), where the article's S&P 500 run erred slightly the
other way. A marginal miss rather than the decisive failures of A and B, but
a non-rubber-stamp backtest reports it as a failure all the same.

Full numbers, p-values, and charts: **[results/backtest_report.md](results/backtest_report.md)**

![Cumulative breaks vs the 1% line](results/cumulative_breaks.png)

## How the checks are computed

- **Test 1** — Kupiec proportion-of-failures likelihood-ratio test against a
  1% break probability, plus the plain z-score.
- **Test 2** — the article's own diagnostics (breaks landing the day after a
  break, and within ten days of a break, versus their expectations under
  independence) with binomial p-values, plus the Christoffersen
  independence test on the break sequence.
- **Test 3** — average VaR on break days versus overall average VaR. If
  breaks are independent of the level, break days are a uniformly random
  sample of days, so a 10,000-draw permutation test on the break-day average
  is exact under the null; a Welch t-test is shown alongside.

Pass tolerance is p ≥ 0.05 throughout.

## Running it

```bash
pip install -r requirements.txt
python3 var_backtest.py
```

Regenerates `results/backtest_report.md` and the three charts in
`results/`. Runtime is under a minute.

## Files

```
VAR/
├── README.md               # this file
├── var_backtest.py         # methods, backtests, report and charts
├── requirements.txt
├── data/NASDAQCOM.csv      # FRED NASDAQ Composite, daily closes
└── results/                # generated: report + charts
```

## Data notes

- Source: FRED `NASDAQCOM` (NASDAQ Composite index, daily close),
  1971-02-05 to 2026-07-02.
- Blank observations (market holidays) are dropped, per FRED convention —
  the return across a holiday is treated as an ordinary one-day return.
- Returns are simple daily percentage changes; dollar loss is
  −$1M × return.
- The first 750 trading days seed the 3-year windows, so VaR predictions
  start in January 1974.
