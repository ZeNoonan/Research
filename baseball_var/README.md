# ⚾ Little League WAR Explorer

An interactive, mobile-friendly site that explains the **WAR / WAA** (Wins Above
Replacement / Wins Above Average) calculations from the GameChanger spreadsheet —
so you can poke at every number on your phone and watch the answer change.

The goal is to **teach the math**, not to rate kids who should be playing for fun.

## What's here

| File | What it is |
|------|------------|
| `index.html` | The whole interactive site — one self-contained file, no internet needed once loaded. Open it on your phone. Includes a plain-English **glossary** explaining every abbreviation for non-baseball readers. |
| `war_model.py` | A Python reference of the same calculations, cell-for-cell with the Excel workbook. Run it to verify the numbers. |

## View it on your phone

It's a single static HTML file, so any of these work:

- **Quickest:** open `index.html` in any browser (double-tap the file, or drag it
  into a browser tab). It runs entirely on-device.
- **GitHub Pages:** if Pages is enabled for this repo, browse to
  `…/baseball_var/index.html` on your phone.
- **Local share:** AirDrop / email the file to yourself and open it.

Your edits (weights, settings, players) are saved in the browser's local
storage, so they survive a refresh. "Reset to sample" restores the defaults.

## How the model works

Every player's **WAR** is built up in seven steps. The site walks through each
one live for any player you pick; here's the summary.

1. **Outs** = `PA − (1B + 2B + 3B + HR + BB)` — plate appearances that didn't reach.
2. **Batting runs** = the linear-weights sum: each event (out, walk, single, …,
   stolen base, caught stealing) times its run value.
3. **Above baseline** = batting runs minus the league's average rate × PA. The
   baseline is the roster's own runs-per-PA, nudged by the offense "replacement gap".
4. **Position runs** = a positional credit/debit (catcher and shortstop earn runs,
   first base and DH pay them back), scaled by `PA ÷ full-season PA`.
5. **Pitching runs** = `(baseline runs allowed per IP − actual) × IP` — runs saved
   versus the baseline (0 for non-pitchers).
6. **RAR** (Runs Above Replacement) = batting + position + pitching runs.
7. **WAR** = `RAR ÷ runs-per-win`, where runs-per-win falls out of the
   Pythagorean win formula at the league's runs-per-game.

### The blue vs gray cells

Just like the workbook: **blue** boxes are inputs you control (weights, settings,
position adjustments, player stats). **Gray** boxes calculate themselves
(the Pythagorean exponent, runs-per-win, and the two auto baselines).

## Important caveats (these are real)

- **There's no true "replacement player" in Little League.** With mandatory-play
  rules and good athletes who never sign up, the MLB baseline doesn't translate.
  We measure against average, or a hypothetical ~30%-win team, and borrow MLB
  parameters.
- **Not comparable to big-league WAR.** MLB players get ~10× the plate
  appearances, so their WAR is ~10× bigger. Compare WAR *per game* or *per PA*.
- **It's fuzzy.** Even over a full MLB career, Baseball Reference and FanGraphs
  disagree. One Little League season magnifies that — treat the number as a
  conversation starter, not a verdict.

## Verify the numbers

```bash
python3 war_model.py
```

Prints the sample roster's derived constants and full WAR breakdown. The Python
and the JavaScript in `index.html` use identical formulas, so they agree.

Sample roster results (default settings):

| Player | Pos | RAR | WAR |
|--------|-----|----:|----:|
| Mateo | SS | +15.75 | +0.93 |
| Liam | C | +10.69 | +0.63 |
| Noah | P | +6.57 | +0.39 |
| Ethan | 1B | −4.07 | −0.24 |
| Lucas | LF | −8.59 | −0.51 |

_All player data is made up — no actual kids were harmed in making this._
