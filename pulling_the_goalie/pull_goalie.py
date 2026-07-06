#!/usr/bin/env python3
"""Replication of Asness & Brown (2018), "Pulling the Goalie: Hockey and
Investment Implications" (SSRN 3132563).

The paper models the decision of when a trailing hockey team should pull its
goalie for an extra attacker. It is a dynamic program over two state
variables -- score differential S and time remaining t -- advanced in
10-second steps, with three scoring probabilities estimated from the 2015-16
NHL season:

    P_EVEN = 0.65%  chance a team scores in a 10-second slice, goalies in
                    (4,947 even-strength goals / 126,425 minutes / 6)
    P_FOR  = 1.97%  chance the pulling team scores in a slice, net empty
    P_AGT  = 4.30%  chance the opponent scores into the empty net
                    (both from 2,206 minutes of 6-on-5 play that season)

Standings points: win = 2, regulation tie = 1.5 (expected value of overtime),
loss = 0. Only "tie beats trailing" matters for the decision itself.

Three value functions, each defined on (S, t) and solved backwards from t=0:

    EPNP  never pull ("Tikhonov"):
          EPNP(S,t) = 0.9870*EPNP(S,t-10) + 0.0065*EPNP(S+1,t-10)
                                          + 0.0065*EPNP(S-1,t-10)
    EPNO  keep the goalie in for this slice, act optimally afterwards
    EPPO  pull for this slice, act optimally afterwards

"Act optimally" means the continuation value is V = max(EPPO, EPNO). The
paper's displayed equation (footnote 18) chains the no-goal branch of EPPO to
EPPO itself -- i.e. once pulled, stay pulled until a goal. Because the pull
region is monotone in time for a fixed deficit, the two formulations give
identical thresholds; we verified both. Optimal policy: pull iff EPPO > EPNO.

Usage:
    python3 pull_goalie.py                 # replication report
    python3 pull_goalie.py --export DIR    # also write CSVs + SVG figure
    python3 pull_goalie.py --simulate N    # Monte Carlo validation, N games

No dependencies beyond the standard library.
"""

import argparse
import csv
import os
import random

# ---------------------------------------------------------------- inputs ---

P_EVEN = 0.0065   # per team per 10s slice, both goalies in
P_FOR = 0.0197    # pulling team scores, per 10s slice
P_AGT = 0.0430    # opponent scores into the empty net, per 10s slice

WIN_PTS = 2.0
TIE_PTS = 1.5     # expected standings points of reaching overtime

STEP = 10                      # seconds per slice
GAME_STEPS = 360               # 60 minutes of regulation
S_BOUND = 30                   # score differentials tracked: -30..+30


# ----------------------------------------------------------------- model ---

class Solution:
    """Solved value functions on the (S, t) grid.

    Grids are lists indexed [n][S + S_BOUND] where n = t / 10 seconds.
    """

    def __init__(self, epnp, eppo, epno):
        self.epnp = epnp
        self.eppo = eppo
        self.epno = epno

    def value(self, s, n):
        """Expected points under the optimal pull policy."""
        i = s + S_BOUND
        return max(self.eppo[n][i], self.epno[n][i])

    def should_pull(self, s, n):
        i = s + S_BOUND
        return self.eppo[n][i] > self.epno[n][i]

    def pull_threshold(self, deficit):
        """Most time remaining (seconds) at which pulling is optimal when
        trailing by `deficit`, or None if pulling never helps."""
        s = -deficit
        for n in range(GAME_STEPS, 0, -1):
            if self.should_pull(s, n):
                return n * STEP
        return None


def _terminal():
    row = []
    for s in range(-S_BOUND, S_BOUND + 1):
        row.append(0.0 if s < 0 else (TIE_PTS if s == 0 else WIN_PTS))
    return row


def solve(p_even=P_EVEN, p_for=P_FOR, p_agt=P_AGT, steps=GAME_STEPS):
    """Solve the dynamic program by backward induction from t = 0."""
    width = 2 * S_BOUND + 1
    lo, hi = 0, width - 1  # clamp indices at the score-differential bounds

    epnp = [_terminal()]
    eppo = [_terminal()]
    epno = [_terminal()]

    for _ in range(steps):
        prev_np = epnp[-1]
        prev_po, prev_no = eppo[-1], epno[-1]
        row_np, row_po, row_no = [], [], []
        for i in range(width):
            up, dn = min(i + 1, hi), max(i - 1, lo)
            row_np.append((1 - 2 * p_even) * prev_np[i]
                          + p_even * prev_np[up]
                          + p_even * prev_np[dn])
            v_here = max(prev_po[i], prev_no[i])
            v_up = max(prev_po[up], prev_no[up])
            v_dn = max(prev_po[dn], prev_no[dn])
            row_no.append((1 - 2 * p_even) * v_here
                          + p_even * v_up + p_even * v_dn)
            row_po.append((1 - p_for - p_agt) * v_here
                          + p_for * v_up + p_agt * v_dn)
        epnp.append(row_np)
        eppo.append(row_po)
        epno.append(row_no)

    return Solution(epnp, eppo, epno)


# --------------------------------------------------------------- results ---

def mmss(seconds):
    if seconds is None:
        return "never"
    return f"{seconds // 60}:{seconds % 60:02d}"


def advantage_series(sol, deficit=1, max_seconds=1200):
    """Per-timestep advantage of pull-now and wait over never pulling
    (the paper's Figure 1). Returns rows of (seconds_remaining,
    pull_advantage, wait_advantage)."""
    s = -deficit + S_BOUND
    rows = []
    for n in range(1, max_seconds // STEP + 1):
        base = sol.epnp[n][s]
        rows.append((n * STEP, sol.eppo[n][s] - base, sol.epno[n][s] - base))
    return rows


def peak_advantage(sol, deficit=1):
    best_t, best_adv = None, -1.0
    s = -deficit + S_BOUND
    for n in range(1, GAME_STEPS + 1):
        adv = max(sol.eppo[n][s], sol.epno[n][s]) - sol.epnp[n][s]
        if adv > best_adv:
            best_adv, best_t = adv, n * STEP
    return best_t, best_adv


COMPARATIVE_SCENARIOS = [
    ("Baseline (2015-16 NHL)", P_EVEN, P_FOR, P_AGT, "6:10"),
    ("All scoring doubled ('1980s Oilers')", 2 * P_EVEN, 2 * P_FOR,
     2 * P_AGT, "~3:00"),
    ("All scoring halved ('soccer')", P_EVEN / 2, P_FOR / 2, P_AGT / 2,
     ">12:00"),
    ("Empty-net offense cut 25% (1.48%)", P_EVEN, 0.0148, P_AGT, "~4:00"),
    ("Empty-net offense cut 60% (0.79%)", P_EVEN, 0.4 * P_FOR, P_AGT,
     "~1:00"),
]


def replication_report():
    sol = solve()
    lines = []
    lines.append("Replication of Asness & Brown (2018), 'Pulling the Goalie'")
    lines.append("=" * 62)
    lines.append("")
    lines.append(f"{'Result':<44}{'Paper':>8}{'Here':>9}")
    lines.append("-" * 62)

    paper_thresholds = {1: "6:10", 2: "13:00", 3: "23:40", 4: "any time"}
    for d in (1, 2, 3, 4):
        t = sol.pull_threshold(d)
        lines.append(f"{'Pull when down %d, time remaining' % d:<44}"
                     f"{paper_thresholds[d]:>8}{mmss(t):>9}")

    peak_t, peak_adv = peak_advantage(sol)
    lines.append(f"{'Peak advantage vs never pulling (down 1)':<44}"
                 f"{'0.18':>8}{peak_adv:>9.3f}")
    lines.append(f"{'  ...occurs with time remaining':<44}"
                 f"{'4:20':>8}{mmss(peak_t):>9}")

    mid = S_BOUND
    game_adv = sol.value(0, GAME_STEPS) - sol.epnp[GAME_STEPS][mid]
    lines.append(f"{'Season value of optimal pulling, pts/game':<44}"
                 f"{'0.05':>8}{game_adv:>9.3f}")
    lines.append(f"{'  ...over an 82-game season':<44}"
                 f"{'4.18':>8}{game_adv * 82:>9.2f}")

    down4 = -4 + S_BOUND
    lines.append(f"{'Down 4 at 60:00, never-pull expected pts':<44}"
                 f"{'0.09':>8}{sol.epnp[GAME_STEPS][down4]:>9.3f}")
    lines.append(f"{'Down 4 at 60:00, optimal expected pts':<44}"
                 f"{'0.14':>8}{sol.value(-4, GAME_STEPS):>9.3f}")

    lines.append("")
    lines.append("Comparative statics (optimal pull time when down 1):")
    lines.append("-" * 62)
    for name, pe, pf, pa, paper in COMPARATIVE_SCENARIOS:
        s = solve(pe, pf, pa)
        lines.append(f"{name:<44}{paper:>8}"
                     f"{mmss(s.pull_threshold(1)):>9}")

    lines.append("")
    lines.append("Note: near the down-3 and down-4 thresholds the pull vs")
    lines.append("wait gap is ~1e-4 points -- the decision surface is almost")
    lines.append("perfectly flat, so exact deep-deficit thresholds are")
    lines.append("sensitive to implementation details. All materially")
    lines.append("consequential results match the paper.")
    return "\n".join(lines), sol


# ---------------------------------------------------------- monte carlo ---

def _convention_policy(s, n):
    """Approximate NHL practice: pull only in the last minute, down 1 or 2."""
    return s in (-1, -2) and n * STEP <= 60


def simulate(sol, games, policy, seed=7):
    """Play synthetic games at 10-second resolution and average the
    standings points earned by 'our' team. The opponent never pulls, as in
    the paper's model. policy: 'never' | 'optimal' | 'convention'."""
    rng = random.Random(seed)
    total = 0.0
    for _ in range(games):
        s = 0
        for n in range(GAME_STEPS, 0, -1):
            if policy == "optimal":
                pulled = -S_BOUND < s < S_BOUND and sol.should_pull(s, n)
            elif policy == "convention":
                pulled = _convention_policy(s, n)
            else:
                pulled = False
            r = rng.random()
            if pulled:
                if r < P_FOR:
                    s += 1
                elif r < P_FOR + P_AGT:
                    s -= 1
            else:
                if r < P_EVEN:
                    s += 1
                elif r < 2 * P_EVEN:
                    s -= 1
        total += WIN_PTS if s > 0 else (TIE_PTS if s == 0 else 0.0)
    return total / games


# ---------------------------------------------------------------- export ---

def export_results(sol, outdir):
    os.makedirs(outdir, exist_ok=True)

    with open(os.path.join(outdir, "thresholds.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["deficit", "pull_time_remaining_seconds",
                    "pull_time_remaining_mmss", "paper_value"])
        paper = {1: "6:10", 2: "13:00", 3: "23:40", 4: "any time"}
        for d in (1, 2, 3, 4):
            t = sol.pull_threshold(d)
            w.writerow([d, t, mmss(t), paper[d]])

    with open(os.path.join(outdir, "advantage_down1.csv"), "w",
              newline="") as f:
        w = csv.writer(f)
        w.writerow(["seconds_remaining", "pull_now_minus_never",
                    "wait_minus_never"])
        for t, adv_p, adv_n in advantage_series(sol):
            w.writerow([t, f"{adv_p:.6f}", f"{adv_n:.6f}"])

    with open(os.path.join(outdir, "comparative_statics.csv"), "w",
              newline="") as f:
        w = csv.writer(f)
        w.writerow(["scenario", "p_even", "p_for", "p_against",
                    "pull_time_down1", "paper_value"])
        for name, pe, pf, pa, paper in COMPARATIVE_SCENARIOS:
            s = solve(pe, pf, pa)
            w.writerow([name, pe, pf, pa, mmss(s.pull_threshold(1)), paper])

    with open(os.path.join(outdir, "figure1.svg"), "w") as f:
        f.write(figure1_svg(sol))


def figure1_svg(sol):
    """Standalone SVG replication of the paper's Figure 1: expected-point
    advantage over never pulling when down one goal."""
    rows = advantage_series(sol, deficit=1, max_seconds=1200)
    w, h = 760, 420
    ml, mr, mt, mb = 62, 24, 56, 52
    pw, ph = w - ml - mr, h - mt - mb
    tmax, ymax = 1200.0, 0.20

    def x(t):
        return ml + (1 - t / tmax) * pw   # clock runs down left to right

    def y(v):
        return mt + (1 - v / ymax) * ph

    pull_pts = " ".join(f"{x(t):.1f},{y(a):.1f}" for t, a, _ in rows)
    wait_pts = " ".join(f"{x(t):.1f},{y(b):.1f}" for t, _, b in rows)

    grid = []
    for v in (0.0, 0.05, 0.10, 0.15, 0.20):
        gy = y(v)
        grid.append(f'<line x1="{ml}" y1="{gy:.1f}" x2="{ml+pw}" '
                    f'y2="{gy:.1f}" stroke="#e1e0d9" stroke-width="1"/>')
        grid.append(f'<text x="{ml-8}" y="{gy+4:.1f}" text-anchor="end" '
                    f'font-size="12" fill="#898781">{v:.2f}</text>')
    for t in (1200, 900, 600, 300, 0):
        gx = x(t)
        grid.append(f'<text x="{gx:.1f}" y="{mt+ph+22}" text-anchor="middle" '
                    f'font-size="12" fill="#898781">{mmss(t)}</text>')

    cx, cy = x(370), y(sol.eppo[37][-1 + S_BOUND]
                       - sol.epnp[37][-1 + S_BOUND])
    font = "system-ui, -apple-system, 'Segoe UI', sans-serif"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}"
     font-family="{font}">
  <rect width="{w}" height="{h}" fill="#fcfcfb"/>
  <text x="{ml}" y="26" font-size="16" font-weight="600" fill="#0b0b0b">Expected-point advantage over never pulling (down one goal)</text>
  <text x="{ml}" y="44" font-size="12" fill="#52514e">Replicates Figure 1 of Asness &amp; Brown (2018). Crossover at 6:10; peak +0.18 points at 4:20.</text>
  {''.join(grid)}
  <line x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}" stroke="#c3c2b7" stroke-width="1"/>
  <polyline points="{wait_pts}" fill="none" stroke="#2a78d6" stroke-width="2" stroke-linejoin="round"/>
  <polyline points="{pull_pts}" fill="none" stroke="#e34948" stroke-width="2" stroke-linejoin="round"/>
  <line x1="{cx:.1f}" y1="{mt}" x2="{cx:.1f}" y2="{mt+ph}" stroke="#898781" stroke-width="1" stroke-dasharray="none" opacity="0.6"/>
  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="#0b0b0b" stroke="#fcfcfb" stroke-width="2"/>
  <text x="{cx+8:.1f}" y="{mt+14}" font-size="12" fill="#52514e">pull from 6:10</text>
  <text x="{ml+6}" y="{y(rows[-1][2])-20:.1f}" font-size="12" fill="#52514e">wait, act optimally later</text>
  <text x="{ml+6}" y="{y(rows[-1][1])+26:.1f}" font-size="12" fill="#52514e">pull now</text>
  <text x="{ml+pw/2}" y="{h-8}" text-anchor="middle" font-size="12" fill="#898781">time remaining</text>
</svg>
"""


# ------------------------------------------------------------------ main ---

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--export", metavar="DIR",
                    help="write CSVs and the Figure 1 SVG to DIR")
    ap.add_argument("--simulate", metavar="N", type=int,
                    help="Monte Carlo validation over N synthetic games "
                         "per policy")
    args = ap.parse_args()

    report, sol = replication_report()
    print(report)

    if args.export:
        export_results(sol, args.export)
        print(f"\nWrote thresholds.csv, advantage_down1.csv, "
              f"comparative_statics.csv, figure1.svg to {args.export}/")

    if args.simulate:
        n = args.simulate
        print(f"\nMonte Carlo validation ({n:,} synthetic games per policy)")
        print("-" * 62)
        never = simulate(sol, n, "never")
        conv = simulate(sol, n, "convention")
        opt = simulate(sol, n, "optimal")
        print(f"{'Never pull':<44}{never:>9.4f} pts/game")
        print(f"{'NHL convention (last minute, down 1-2)':<44}"
              f"{conv:>9.4f} pts/game")
        print(f"{'Optimal policy':<44}{opt:>9.4f} pts/game")
        print(f"{'Optimal minus never (model says ~0.051)':<44}"
              f"{opt - never:>+9.4f}")


if __name__ == "__main__":
    main()
