# Rouge et Noir — findings and takeaways

A write-up of Aaron Brown's **"Rouge et Noir: How to turn the most sober risk
professional into a rabid rogue trader in a few easy moves"** (*Wilmott*,
September 2013, pp. 14–16 — copy in [`papers/`](papers/)), the experiment he
ran at the 2013 GARP annual convention in New York, and what the security at
the heart of it should remind you of. The interactive companion is
[`index.html`](index.html); every number below is reproduced exactly by
[`rouge_et_noir.py`](rouge_et_noir.py).

## The experiment in one paragraph

Brown rolled a die (result `D`, hidden), put `D` black chips and `6 − D` red
chips in a hat, and ran six rounds of a sealed-bid market on a security paying
**$100 if the next chip drawn is black, $0 if red**. Sixteen teams (96 risk
professionals, four to six per team) bid each round; the median bid set the
price, teams above it bought, teams below it sold, and then a chip was drawn
and removed. Co-presenters were Donna Howe, Michael Miller, and Kent Osband.
The problem was calibrated so roughly half the room could price the security
exactly in the time allotted — hard enough to create doubt, easy enough that
every team likely had someone who could do it.

The die came up **D = 1** and the hat delivered
**Red – Black – Red – Red – Red – Red**, so the fair value walked
$58.33 → $46.67 → $50.00 → $40.00 → $33.33 → $28.57.

## What happened, round by round

| Round | State before draw | Fair value | Mean bid (≈) | Draw  | Losing side |
|------:|-------------------|-----------:|-------------:|-------|-------------|
| 1     | nothing seen      | $58.33     | $58          | Red   | buyers      |
| 2     | 0B 1R             | $46.67     | $66          | Black | sellers     |
| 3     | 1B 1R             | $50.00     | $44          | Red   | buyers      |
| 4     | 1B 2R             | $40.00     | $53          | Red   | buyers      |
| 5     | 1B 3R             | $33.33     | $62          | Red   | buyers      |
| 6     | 1B 4R             | $28.57     | $87          | Red   | buyers      |

(Mean bids digitized from the article's Figure 1, accurate to a dollar or two;
fair values are exact.)

## Brown's findings

**1. The crowd was wise for exactly one round.** With no history, the median
bid in round 1 was almost exactly the correct $58.33 — individual teams erred
in both directions and the errors cancelled, the classic Wisdom of Crowds
result Brown had discussed in an earlier column ("Try This at Home, Kids").

**2. After that, the mean bid moved in the *opposite* direction to value in
every round.** The first red draw lowered the security's value; the average
bid rose. The black draw raised the value; the average bid fell. By round 6
the mean bid (≈$87) was three times fair value ($28.57) — the widest gap of
the game, on a round whose math is among the easiest (one step from the rule
of succession, see below).

**3. Splitting bidders by last round's outcome explains it.** Teams that had
*won* money the previous round bid close to fair value and, after round one,
moved their bids in the right direction (or toward the correct price). Teams
that had just *lost* look, in Brown's words, "wildly irrational by contrast."
Membership in the two groups churned randomly — a different set of losers
each round — so this cannot be a skill difference. The same people priced
calmly after a win and flailed after a loss.

**4. The flailing had a precise shape: loss-chasing.** The losing trade was to
buy in rounds 1, 3, 4, 5, 6 and to sell in round 2. Teams that lost money
*buying* bid considerably **more** the next round; the round teams lost money
*selling*, they bid considerably **less** — in both cases repeating the failed
trade harder, ignoring both the level and the direction of fair value. Brown
notes the factor they were reacting to is *doubly* irrelevant: whether you won
was pure luck regardless of bidding skill, and last round's luck says nothing
about next round's. Worse, even if it were relevant, the rational reaction
would be the exact opposite of what losers did. He likens it to lottery
players: a winner rarely feels compelled to replay the same number, but the
longer a number loses, the more determined its player becomes — the
superstition that a desired event which failed to occur is "due."

**5. It took almost nothing to trigger.** These were quantitative risk
managers, anonymous, at a friendly conference, playing for fake money, solving
a mildly complicated math problem within many participants' abilities. Group
membership plus a little competition sufficed: *"Simply by putting people in
groups and introducing some competition, we were able to induce behavior more
often associated with rogue traders than sober risk professionals. If we can
do that, imagine what the markets and real money and frenetic trading rooms
can do to impressionable junior traders."*

**6. Brown's own caveats.** He offers it as anecdote, not science:
participants self-selected, may have known the effects, no controls, no
blinding. "Change the rules a little, get a different group, and you could get
entirely different results. The point is you do get results. People do not
behave randomly or rationally and you don't have to poke them very hard to
discover that."

## Takeaways

- **Losses switch off arithmetic.** The ability to price the security never
  left the room; the willingness to use it did, selectively, among those who
  had just lost. Risk process has to be built for the moment *after* a loss,
  because that is when people stop following it. (This is also the practical
  case for the trading-desk rule of cutting size after drawdowns — not because
  the edge changed, but because the trader did.)
- **P&L is not information.** In this game — and more often than traders
  admit, in real ones — outcomes are luck layered on top of decision quality.
  Evaluating decisions by their outcome trains exactly the loss-chasing the
  experiment exposed.
- **Crowds are wise until they start keeping score.** Aggregation works when
  errors are independent. One round of shared wins and losses correlated the
  errors, and the "crowd" became a mood.
- **Complexity wasn't the trigger — competition was.** The worst pricing came
  on nearly the easiest math. Making people smarter is not a defense;
  structure (position limits, forced flat after losses, pre-committed pricing)
  is.
- **There was no game-theory excuse.** With a median-price mechanism, your bid
  can't improve your price, only pick your side — so bidding your honest
  expected value is optimal regardless of what others do. Participants had no
  strategic reason to shade bids; everything in Figures 1–2 is behavior.

## What the security should remind you of

**A binary option / prediction-market contract.** A $100-or-nothing payoff on
an event is a digital option, an Arrow–Debreu state claim, or literally a
prediction-market contract (Iowa Electronic Markets, Kalshi, Polymarket). The
fair bid *is* the event probability times $100, re-marked as information
arrives — the game is six rounds of marking a binary to market.

**Laplace's rule of succession.** The neatest thing the article leaves
implicit: once at least one black has been drawn (`B ≥ 1`), the security's
exact value is

```
value = $100 × (B + 1) / (B + R + 2)
```

— Laplace's 1774 rule of succession, the formula for the probability the sun
rises tomorrow after rising `n` days straight. A uniform die over hat
compositions plus draws without replacement produces *identical* predictive
probabilities to the textbook Beta(1,1) coin — the finite-urn shadow of de
Finetti's theorem, and first cousin to Pólya's urn. The `B = 0` column is the
lone exception, because the die has no zero face: the hat is *guaranteed* at
least one black chip. (`rouge_et_noir.py` verifies the identity exactly in all
fifteen `B ≥ 1` states, and that a hypothetical 0–6 die would satisfy it
everywhere.)

**Card counting.** Value determined by the depleting composition of a finite
shoe is blackjack; here the shoe's starting composition is itself unknown, so
the player runs a running count and a Bayesian estimate of the deck
simultaneously. The two forces the page calls *learning* and *depletion* are
exactly the two terms a counter tracks.

**Pull-to-par.** The all-red column (`B = 0`) falls, bottoms at $43.75, then
climbs to a certain $100.00 — bad news arriving while the guaranteed payoff
becomes a larger share of a shorter remaining game. That is a distressed bond
pulling to par: survive enough bad periods and proximity to the promised
payment dominates the deteriorating news. It also means that from that column
a red draw *raises* the price — a regime where the naive gambler's-fallacy
reflex ("black is due") happens to point the right way, which is precisely
what makes the wrong habit durable.

**Experimental asset-market bubbles.** A room bidding a known, declining
fundamental to three times its value is the Smith–Suchanek–Williams (1988)
result — bubbles in experimental markets where every trader can compute
fundamental value — compressed into six rounds. Brown's variant adds the
diagnosis: the bubble was carried by the previous round's losers.

**The rogue-trader file.** Loss-chasing — doubling the failed trade to get
back to even — is the signature of Nick Leeson and Jérôme Kerviel, and of
Kahneman & Tversky's break-even effect: people in a loss accept gambles they
would never take otherwise. Coval & Shumway (2005) found the same pattern in
professional CBOT traders, who took significantly more afternoon risk after
morning losses. Brown's contribution is a demonstration of how *little*
pressure is needed: no money, no career risk, no market — just a scoreboard
and a group.

## The pricing, for reference

Value of the security after seeing `B` black and `R` red chips
(`D` uniform on 1–6 a priori; full derivation and every state worked
interactively in [`index.html`](index.html)):

```
P(seen | D)  =  C(D,B) · C(6−D,R) / C(6,B+R)      for max(1,B) ≤ D ≤ 6−R
P(D | seen)  ∝  P(seen | D)                        (uniform prior cancels)
value        =  $100 · Σ_D  P(D | seen) · (D−B)/(6−B−R)
```

The full table (article Table 1, verified by both Bayes and brute-force
enumeration of all die rolls × chip orderings):

```
round 1                          $58.33
round 2                     $46.67   $66.67
round 3                 $43.75   $50.00   $75.00
round 4             $46.67   $40.00   $60.00   $80.00
round 5         $58.33   $33.33   $50.00   $66.67   $83.33
round 6    $100.00   $28.57   $42.86   $57.14   $71.43   $85.71
```

Left edge = all red so far; right edge = all black; a red draw steps left,
a black draw steps right.
