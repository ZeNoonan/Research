# Monopoly as Quantitative Finance

Recreation, validation and extension of **Aaron Brown's "Monopoly 101",
Parts I & II** (Wilmott magazine, January & March 2003) — an "alternative
theory of monopoly economics" that prices the board game's properties with
the toolkit of quantitative finance: annuities, growth options, Markov
chains, interest-rate dynamics and an exponential wealth ODE.

**➤ Open [`index.html`](index.html) for the interactive site** (works from
GitHub Pages or a local file — fully self-contained).

## What was done

1. **Recreated** every computation in the papers from scratch
   (`analysis/`): the board data, the bank-flow Φ, the 120-state Markov
   chain with tournament jail rules and card decks, the wealth ODE, and the
   property pricing formula
   `V = (1/β)[ℜᵢ + βᵢΦ/((n−1)βᵢ + β)]`.
2. **Validated** 68 published quantities — see
   [`results/validation_report.md`](results/validation_report.md).
   Highlights:
   - all 40 long-run square frequencies match to ≤0.005 percentage points;
   - all 40 rent-roll/value entries of the Part II valuation table
     reproduce (the header's "1.6%/6%" rates are really 1.6123%/6.031%,
     pinned by the railroad rows);
   - the repair-card adjustments (−$0.29/house, −$0.96/hotel) match to the
     cent;
   - documented corrections: the paper's Φ omits card-driven Go collections
     (worth $4.40/roll; full accounting gives $27.89, confirmed by
     simulation), and its survival criterion substitutes a geometric-mean
     market rate for the exact opponent-specific rate (93% vs 100%
     agreement with the ODE).
3. **Extended** the work (`analysis/simulator.py`, `analysis/extensions.py`):
   an independent full-rules game simulator (frequencies and Φ cross-checks,
   monopoly-vs-monopoly duels across cash levels, game-length statistics)
   and the exact house-by-house development returns behind the linearized β
   (the "third house" effect).

## Layout

```
monopoly/
├── index.html                  # self-contained interactive site
├── papers/                     # the two source PDFs
├── analysis/
│   ├── board.py                # squares, rents, prices, card decks
│   ├── markov.py               # 120-state chain: frequencies + exact Φ
│   ├── bankflow.py             # uniform-board Φ, house-rule variant
│   ├── part1.py                # rent rolls, safe zone, wealth ODE, MC
│   ├── valuation.py            # the pricing formula + published tables
│   ├── simulator.py            # full-rules Monte Carlo engine + duels
│   ├── extensions.py           # stepwise development ROI, payback
│   └── run_all.py              # regenerate everything
├── docs/
│   └── theory.md               # the math, fully reconstructed + morals
└── results/
    ├── validation_report.md    # 68-line paper-vs-ours comparison
    └── site_data.json          # data consumed by index.html
```

## Reproduce

```bash
pip install numpy
cd analysis && python3 run_all.py     # ~2 minutes
```

Regenerates `results/validation_report.md` and `results/site_data.json`.

## The one-paragraph takeaway

Monopoly's Bank injects Φ ≈ $24–30 per dice roll; rent only moves money
between players. On an undeveloped board nobody can ever go bankrupt (the
biggest possible rent-roll deficit, $3.42, sits inside the Φ/n = $7.60 safe
zone) — so undeveloped properties are worthless and casual "more money"
house rules make the game literally unwinnable. Development converts wealth
into rent-generating capacity at rate βᵢ, which turns wealth dynamics into
a linear ODE whose solutions are exponentials: every player's fortune is
C·e^{λt} + linear terms, and the sign of C — determined by rent annuity
plus a growth option, the game's Gordon-model-plus-CAPM — decides rich or
bankrupt. There is no middle. Value the option when money is scarce (light
blue, railroads early), the annuity when money is plentiful (green late),
and the group that has both on the most-visited corridor — orange — always.
