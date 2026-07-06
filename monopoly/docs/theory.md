# The Theory, Reconstructed

*A complete mathematical reconstruction of Aaron Brown's "Monopoly 101"
(Wilmott magazine, January & March 2003). The scanned PDFs lost every
displayed equation, so this document rebuilds the math from the surviving
prose and tables — and verifies each step numerically (see
`../results/validation_report.md`).*

---

## 1. The setting

Monopoly is a fight for survival financed by a central bank. Each player
starts with $1,500; money enters and leaves the table only through the Bank;
rent moves money *between* players. The last solvent player wins.

Brown's program: treat this exactly the way quantitative finance treats a
market. Don't try to solve the game (game theory); **price the assets**
(finance). All strategy questions — what to bid at auction, which group to
develop, what a fair trade looks like — reduce to valuation.

Three quantities drive everything:

| Symbol | Meaning | Units |
|--------|---------|-------|
| ℜᵢ | *Rent roll*: expected rent player i collects per opponent dice roll | $/roll |
| Φ | Expected **net payment from the Bank to the table** per dice roll | $/roll |
| βᵢ | Return on housing investment: rent-roll increase per dollar of development | 1/roll |

## 2. The rent roll and the cash engine Φ

Under the Part I simplification that all 40 squares are equally likely,
a property with rent *r* is landed on once per 40 rolls, so it contributes
*r*/40 to its owner's rent roll.

Every roll of the dice also triggers Bank flows:

- **Go**: the average roll moves 7 squares, so a player passes (or lands on)
  Go 7/40 of the time: +$200 × 7/40 = **+$35.00**
- **Income Tax** (flat $200 option): −$200/40 = **−$5.00**
- **Luxury Tax**: −$75/40 = **−$1.875**
- **Cards**: 6 of 40 squares draw from decks whose 32 cards net **+$485**
  to the player from the Bank: (6/40)·(485/32) = **+$2.273**

$$\Phi_{\text{uniform}} = 35 - 5 - 1.875 + 2.273 = \$30.40 \text{ per roll} $$

**Validated: $30.40, and the card enumeration nets exactly +$485
(Community Chest +$300, Chance +$185).**

### The accounting identity

Let n players have rent rolls ℜ₁…ℜₙ with average ℜ̄. During one *round*
(each player rolls once), player i:

- collects ℜᵢ from each of the (n−1) opponents' rolls,
- pays ℜⱼ to each owner j on her own roll: total Σⱼ≠ᵢ ℜⱼ = nℜ̄ − ℜᵢ,
- collects Φ from the Bank on her own roll.

$$\text{net}_i = (n-1)\Re_i - (n\bar{\Re} - \Re_i) + \Phi
             = n(\Re_i - \bar{\Re}) + \Phi$$

**The safe zone.** Player i bleeds only if her rent roll is more than
**Φ/n below the table average** — $7.60 in a four-player game. This single
line explains most of Monopoly's macro-dynamics:

- **Undeveloped board**: all 28 properties held singly generate $547 of
  total rent → total rent roll $13.68 → four-player average **$3.42**.
  Even a player who owns *nothing* is only $3.42 below average — comfortably
  inside the $7.60 safe zone. *Nobody can ever go bankrupt.* The game floats
  forever on the Bank's money, and undeveloped properties are, strictly,
  worthless (nothing you pay for them changes anyone's fate).
- **Developed board**: all groups hotelled generate $22,790 of rent → total
  rent roll $569.75 → average **$142.44** (the paper prints $144; small
  slip). Now the safe zone is a rounding error. Development is what makes
  Monopoly lethal.
- **House rules kill the game**: paying $300 on Go and stuffing a Free
  Parking pot raises Φ to roughly **$69 per roll**, which widens the safe
  zone to ±$17 and floods the table with cash. That is *why* casual family
  games never end — a point the paper makes qualitatively and we quantify.

### Who must trade?

With no trading and everyone buying whatever they land on, each property's
owner is (approximately) uniform among the n players. Monte Carlo over
150,000 random allocations, developing every completed group to hotels:
the distribution of (own rent roll − average) has a standard deviation of
**≈$28** (paper: $28.63), is strongly right-skewed (skew ≈ +1.9), and a
player finds herself outside the $7.60 safe zone roughly **a third of the
time** (paper: "about 40%"); *at least one* of the four players is outside
it in about half of all games. Hence Brown's dictum: **some players must
trade to survive, so all players must trade to win.**

Our full-rules simulator agrees from the other direction: with no trading,
only 60 of 200 four-player games produced a bankruptcy within 6,000 rolls.

## 3. The lurking exponential

Now let development be continuous: player i can convert wealth into rent
roll at rate βᵢ (dollars of rent roll per dollar invested per roll). With
everything reinvested, ℜᵢ(t) = ℜᵢ⁰ + βᵢWᵢ(t), and the accounting identity
becomes a linear ODE system (time in rounds):

$$\dot W_i = n\Re_i - \sum_j \Re_j + \Phi$$

Summing over players: total wealth grows **linearly**, Ẇ_tot = nΦ — the
Bank drips money in at a constant rate. But the *distribution* of that
wealth is exponential. For player 1 against aggregated opponents (combined
initial rent ℜ̂⁰, combined development rate β̂), substitute and solve:

$$W_1(t) = C\,e^{\lambda t} + (\text{linear terms}), \qquad
\boxed{\lambda = (n-1)\beta_1 + \hat\beta}$$

Every player's wealth is dominated by an exponential term. **C > 0 means
wealth → ∞; C < 0 means wealth hits zero and the player is eliminated.**
There is no steady state, no comfortable middle. This is Brown's "lurking
exponential", and his rewrite of Shakespeare: *"There is an exponential tide
in the affairs of men…"*

### The survival criterion (exact form)

Solving the two-player system explicitly (n = 2, D = W₁ − W₂, S = W₁ + W₂):

- Ṡ = 2Φ ⟹ S = 2Φt
- Ḋ = 2(ℜ₁⁰ − ℜ₂⁰) + 2Φ(β₁ − β₂)t + (β₁+β₂)D

whose solution has exponential coefficient

$$C = \frac{1}{\lambda}\left[2(\Re_1^0 - \Re_2^0) +
      \frac{2\Phi(\beta_1-\beta_2)}{\beta_1+\beta_2}\right],
      \qquad \lambda = \beta_1 + \beta_2 .$$

So **C > 0 exactly when**

$$\Re_1^0 + \frac{\beta_1\,\Phi}{\beta_1+\beta_2} \;>\;
  \Re_2^0 + \frac{\beta_2\,\Phi}{\beta_1+\beta_2}.$$

Read it as: *annuity rent* plus *your share of the Bank's money*, where the
shares β₁/(β₁+β₂) and β₂/(β₁+β₂) sum to exactly 1 — every dollar the Bank
injects ultimately belongs to someone, in proportion to development power.
In our 400-trial numerical test this criterion predicts the ODE winner
**100%** of the time.

Brown's published formula replaces the opponent-specific denominator with a
single game-wide rate β (for n = 2, requiring the players' shares
βᵢ/(βᵢ+β) to sum to 1 forces **β = √(β₁β₂), the geometric mean** — we
verify this algebraically and numerically). That substitution is what makes
the formula usable as a *market* price — one interest rate for the whole
game rather than a different rate per matchup — at the cost of being an
approximation: it picks the same winner as the exact criterion in ~93% of
random trials. The paper does not flag this distinction; our reconstruction
makes it explicit.

## 4. The pricing formula

Since survival is decided by ℜᵢ + βᵢΦ/((n−1)βᵢ + β), value properties by
that measure. It is an annuity (dollars per roll), so divide by the
per-roll market interest rate β — a dollar spent on houses returns β per
roll to the average player, making β the game's opportunity cost of money:

$$\boxed{\;V_i = \frac{1}{\beta}\left(\Re_i +
   \frac{\beta_i\,\Phi}{(n-1)\beta_i + \beta}\right)\;}$$

Two classic models are visible inside it:

- **Gordon growth model** (V = D/(r−g)): capitalize an income stream with
  a growth adjustment, under assumptions everyone knows are false.
- **CAPM**: value splits into two parts with different portfolio behavior —
  rent rolls ℜᵢ *add* across properties, but option values βᵢ do not (you
  develop your best group first; only the maximum matters much).

Special cases worth internalizing:

- **Railroads and utilities cannot be developed** (βᵢ = 0): V = ℜᵢ/β, a
  pure bond. At β = 4% and uniform frequencies this is rent/40/0.04 =
  **0.625 × rent** — the Part I rule of thumb.
- **A fully developed monopoly** has exhausted its option (βᵢ → 0):
  it too becomes a bond. This is why the paper's "End" valuations are
  exactly ℜᵢ(hotel rents)/β — which our reconstruction reproduces.

### First-cut βᵢ (Part I)

Linearize each group: βᵢ = (hotel rent − doubled base rent) / cost of
hotels / 40. This gives 3.16% for the green group (paper: 3.2%), 5.53% for
the light blue (paper: 5.5%), averaging 4.01% across the eight groups
(paper: "about 4%" — $100 of houses adds ≈$160 of rent).

### Interest rates in Monopoly

β is not constant. Early, cash is plentiful relative to opportunities and
rates are **under 1%**; as monopolies form and development accelerates,
rates rise past 4–6%; near a bankruptcy, short rates spike (a desperate
player will pay almost anything for liquidity) and collapse after it.
Part II handles this with a **yield curve**: a rate for the next roll, the
roll after, out to three rounds, then a long rate — the same machinery as
fixed-income exotics. The $10,000-when-developed monopoly discounted at 4%
per roll over the ~157 rolls it takes for all properties to be bought
(coupon collector: 40·H₂₈ ≈ 157) is worth ~$20 at the opening roll: the
same order as the paper's $18, and the reason opening-phase prices look
absurdly low.

## 5. The board is not uniform (Part II)

Squares are not equally likely. Brown builds a 120-state Markov chain —
40 squares × {fresh roll, after one double, after two doubles} — with
square 30 ("Go To Jail", never an end state) repurposed as the jail-turn
counter, tournament jail rules (stay as long as possible; doubles exit;
third turn pay $50 and move), and the card decks folded in as a second
transition matrix.

Its stationary distribution is the famous frequency table: **In Jail 9.39%**
(the most visited state by far), the orange corridor downstream of jail
(St. James 2.68%, Tennessee 2.82%, New York 2.81% — 8.31% for the group),
Illinois 3.00%, and the Chance squares starved down to 0.82–1.04% because
ten of sixteen cards move the token away.

**Our reconstruction matches all 40 published entries to within 0.005
percentage points, and an independent full-rules simulator (1M rolls)
agrees with the chain to Monte Carlo noise.**

With true frequencies:

- ℜᵢ becomes Σ rent(q)·freq(q) over the group (plus, for railroads, the
  two "advance to the nearest railroad, pay double" Chance cards — worth
  an extra $1.79 per roll to the four-railroad owner, which is exactly how
  the paper's ℜ = $23.04 decomposes: $21.24 from landings + $1.79 from the
  card's doubling).
- Φ falls to **$23.62** (paper) / **$23.49** (our replication of the
  paper's convention). The dominant effect is jail: at 9.39% occupancy,
  time in jail suppresses Go collections.
- Repair cards make Φ *state-dependent*: **−$0.29 per house and −$0.96 per
  hotel on the board (÷ n)** — both reproduced exactly. In a fully built
  two-player endgame (32 houses + 12 hotels) Φ drops to **$13.17** (paper) /
  $13.04 (ours). Buildings don't just raise rents; they *shrink the
  communal subsidy*, making the endgame strictly more lethal.

### A correction: Φ under full accounting

The paper's Φ credits $200 for passing Go by dice movement but not for
passes and landings caused by card moves ("Advance to Go", "Take a Ride on
the Reading" from square 36, etc.) — its own uniform-board arithmetic
($35 salary term = dice displacement only) shows the same convention.
Those card-driven collections are worth **$4.40 per roll**. Full accounting
gives **Φ = $27.89** (empty board) and **$17.44** (built endgame), which our
independent simulator confirms empirically ($27.92 over 1M rolls). None of
the paper's qualitative conclusions change, but quantitative users of the
valuation formula should prefer the corrected Φ.

## 6. The valuation table, reproduced

Using the paper's fitted βᵢ (estimated by iterated endgame simulation, not
the naive linearization), Φ = 23.62, n = 4, and the table's interest rates,
every published number reproduces. One subtlety: the header says "1.6%" and
"6%", but the railroad rows — pure annuities, so V = 23.04/V pins the rate —
imply **1.6123%** and **6.031%**; with those, all 40 rent/value entries
match to within $1–2 of rounding.

The economics of the table:

| Situation | What matters | Best groups |
|-----------|--------------|-------------|
| Start (β≈1.6%, nothing built) | Option value βᵢ | Railroads ($1,429!), orange, dark blue |
| End (β≈6%, fully built) | Rent annuity ℜᵢ | Green ($1,604), red/yellow (~$1,450) |
| Maximum over a game | Both, at the right moment | Dark blue ($2,606), orange |

The **railroads** are the great misprized asset: casual players scorn them,
but early — before anyone can afford houses — their $23.04 rent roll is the
largest cash machine on the board and they are worth more than any color
group. Late, they're a mediocre bond. The **light blue** group is a growth
stock: highest fitted β among the cheap groups (7.65%), it converts a small
bankroll into rent faster than anything nearby, but its hotel rents are too
small to win a war of attrition against a rich opponent. The **green** group
is the opposite — fitted β of just 0.77% (a lousy project you fund only when
money is cheap) but the biggest rent annuity in the endgame. The **orange**
group is the rare quality-growth asset: the best fitted β on the board
(11.89%) *and* a top-three annuity, parked on the most-visited corridor.
That is why every serious Monopoly guide says to fight for orange — the
formula derives it.

Our head-to-head duel simulations (two players, one full group each, equal
cash) turn these prices into win rates: at $750 of cash the light blue wins
67% of its matches and green 44%; at $3,000 the light blue collapses to 7%
while green rises to 58%. Orange wins ~70% at *every* cash level.

## 7. The discrete reality behind β (extension)

The constant-β model hides the most famous discontinuity in Monopoly: the
**third house**. Computing the exact per-stage return (Δ rent roll × true
frequencies ÷ cost of one house on each street of the group) shows returns
peak violently at the third house — e.g. orange stage 3 returns over 10%
per roll per dollar, several times its stage-5 (hotel) return. The
linearized βᵢ of Part I is the average of a hump; real play should stop at
the hump's peak (build to 3–4 houses, then start the next group) unless
denying the housing stock to opponents justifies hotels.

## 8. What the game teaches (Brown's morals, made explicit)

1. **Exponential beats polynomial, always.** Any positive exponential
   eventually overtakes any polynomial. "Exponential" does not mean *fast* —
   it means the growth rate is proportional to the level. The decisive
   factors in Monopoly (and, Brown argues, in careers and firms) are the
   *exponentially slow* ones nobody is watching yet: $1 → $2 matters more
   than $1B → $2B if the doubling continues.
2. **There is no safe zone once development exists.** Linear thinking —
   income > expenses, this year ≥ last year — feels safe and is not. Every
   dollar you earn is a line item someone smarter is trying to cut. You
   survive by riding an exponential, not by standing still.
3. **Value = annuity + option.** Almost any asset decomposes into cash it
   throws off now (add across the portfolio) and the right to invest more
   later (only your best option matters). Mispricing comes from ignoring
   one term: casual players see only hotel rents (annuity) and overpay for
   green; quants-in-training see only β and overpay for light blue.
4. **The money supply is a parameter, and it prices everything.** Φ is
   Monopoly's monetary policy. More money in (house rules) → lower rates →
   longer games, inflated asset values, no bankruptcies. Less money
   (buildings taxing the board via repair cards) → tighter, deadlier
   endgames. If you want to understand why cheap money inflates growth
   assets first, the formula shows it: β̂ appears in the denominator of the
   option term — as β falls, high-βᵢ values explode; annuity assets barely move.
5. **Models are for rationality, not accuracy.** The formula's assumptions
   are false and Brown says so cheerfully. Its value is that it gives
   *rational, consistent* answers to questions ("what should I bid for
   Oriental Avenue in this auction?") that intuition cannot answer at all —
   exactly the role of the Gordon model and CAPM in real finance.

---

*See `validation_report.md` for the line-by-line comparison (68 quantities),
and `../analysis/` for all code. Nothing here requires trusting the papers:
every number regenerates from `python3 run_all.py`.*
