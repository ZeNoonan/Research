# Security Trading Game — Rouge et Noir

Recreation of the security from **Aaron Brown's "Rouge et Noir"** (*Wilmott*
magazine, September 2013): roll a hidden die `D`, put `D` black and `6 − D`
red chips in a hat, and auction — six times, one draw per round — a security
that pays **$100 if the next chip out is black**.

**➤ Open [`index.html`](index.html) for the interactive site** (works from
GitHub Pages or a local file — fully self-contained, no dependencies).

The point of the page is the thing that's hard to get from the article alone:
**how the payoff/fair value in every state is actually calculated.** Every one
of the 21 states is clickable and shows the full five-step Bayes calculation
in exact fractions — which die rolls survive, the hypergeometric likelihood of
what you've seen, the posterior, the chips left in the hat, and the weighted
average. A three-chip warm-up version (coin flip instead of die) demonstrates
the key concepts first, because it's small enough to hold in your head — and
because it cleanly isolates the two forces that make the probabilities so
treacherous:

- **learning** — a black draw is evidence the hat holds more blacks (value ↑);
- **depletion** — a black draw removes a black chip from the hat (value ↓).

## Contents

```
security_trading_game/
├── index.html          # interactive explainer: rules, warm-up game, clickable
│                       #   state-by-state calculations, GARP results, takeaways
├── rouge_et_noir.py    # exact verification (stdlib only): Bayes closed form vs
│                       #   brute-force enumeration, article Table 1, rule-of-
│                       #   succession identity — run `python3 rouge_et_noir.py`
├── FINDINGS.md         # write-up: Brown's findings, takeaways, what the
│                       #   security resembles
├── papers/             # the source article PDF
└── README.md           # this file
```

## Headline numbers

- Fair value before any draw: **$58.33** (= 100 × 3.5/6).
- Actual game (die rolled 1; draws Red–Black–Red–Red–Red–Red): fair value
  fell $58.33 → $28.57, while the mean bid rose to ≈$87 — bids moved
  *opposite* to value in every round after the first.
- Hidden pattern: with at least one black seen, the value is exactly
  **Laplace's rule of succession**, `$100 × (B+1)/(B+R+2)`; the all-red
  column breaks it (the die guarantees one black) and actually *rises*
  toward $100 as reds accumulate.

## Verify the math

```bash
python3 rouge_et_noir.py
```

Recomputes all 21 states two independent ways (Bayes/hypergeometric and
exhaustive enumeration of every die roll × chip ordering), checks all values
against the article's published Table 1, and proves the rule-of-succession
identity — all in exact rational arithmetic.

## Source

Aaron Brown, "Rouge et Noir: How to turn the most sober risk professional
into a rabid rogue trader in a few easy moves", *Wilmott*, September 2013,
pp. 14–16. See [`FINDINGS.md`](FINDINGS.md) for the discussion of results.
