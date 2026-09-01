# generals.bot — Generals in Ten Minutes

A short, self-contained guide to **[generals.io](https://generals.io)** and the
**[Generals bot competition](https://generals.bot)**, with a **playable
12 × 12 game** on the same page so the rules land by playing them rather than by
reading them.

**➤ Open [`index.html`](index.html) for the guide and the game** — one file, no
dependencies, no build step, works from GitHub Pages or straight off disk.

Live: <https://zenoonan.github.io/Research/generals.bot/>

## What's in it

The page runs top to bottom as: the game in one sentence → the five tile types →
**the playable board** → the three rules (growth, movement, fog) → what happens
each tick, in order → the observation and action a *program* receives → the
reference bot in twenty lines → how the competition ruleset differs.

The game itself is a faithful port of the engine, not an approximation:

- **Growth** — generals and castles +1 on even turns; every owned tile +1 every
  50th turn. Nothing else generates armies.
- **Movement** — one move per turn into an orthogonal neighbour, always leaving
  one army behind; send all-but-one or half (floor division).
- **Combat** — strictly more attackers than defenders takes the tile, with
  `|attackers − defenders|` left standing. Capturing a general ends the game and
  transfers every tile the loser owned.
- **Move order** — chasing beats reinforcing beats the smaller army, resolved
  one move at a time, exactly as `game._determine_move_order` does it.
- **Fog** — you see only the 3 × 3 neighbourhood of each tile you own; castles
  and mountains persist as indistinguishable dark shapes; the opponent's army
  and land totals are never hidden.
- **Competition rules** (toggle on the board) — no neutral castles; build your
  own for `35 + Σ max(0, 14 − 2 × manhattan_distance)` over your own structures;
  deathtouch, where any legal move onto the enemy general wins outright
  regardless of army size.

Two opponents: **Expander**, a move-for-move port of the reference agent that
ships with the engine (score every legal move as `army × 10 if new land × 2 if
enemy land`, take the best), and **Hunter**, which garrisons its own general,
conveys the surplus forward as one advancing stack, and walks it at your crown
the moment it sees it.

## Sources

Every rule, constant and formula was read out of the
[strakam/generals-bots](https://github.com/strakam/generals-bots) JAX engine
rather than from prose:

| Source file | What was taken from it |
|---|---|
| `generals/core/game.py` | growth phase, combat arithmetic, move order, spoils transfer, fog visibility |
| `generals/core/grid.py` | mountain density, castle values, minimum BFS distance between generals |
| `generals/core/action.py` | the 5-integer action and its validity test |
| `generals/core/env.py` | the `mode="competition"` preset — board sizes, 1200-turn cap, thresholds |
| `generals/modifiers/build_castles.py` | build pricing and the build-as-pass rewrite |
| `generals/modifiers/deathtouch.py` | the turn-800 rule and the mutual-touch draw |
| `competition/protocol.py`, `competition/agents/expander_python/` | the stdio frame and the reference agent |

## Scaled down for a phone

The competition plays 18–21 rectangles over 1200 turns with deathtouch at 800.
The board here is 12 × 12 over 500 turns with deathtouch at 330 — the same
proportion of the game, short enough to finish in a few minutes. Every other
constant is the engine's own. The page says so where it matters.

## Contents

```
generals.bot/
├── index.html   # the whole thing: guide, playable game, engine port (~1,270 lines)
└── README.md    # this file
```

Not affiliated with generals.io or the Generals Competition.
