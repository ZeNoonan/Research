"""
Little League WAR / WAA model — a Python reference of the GameChanger spreadsheet.

This mirrors the Excel workbook cell-for-cell so the interactive site
(index.html) and any analysis stay in sync. Run it directly to print the
sample roster and confirm the numbers.

Cell map (vs the original sheet):
    B2..B9   linear-weight values
    B11..B16 league settings + derived constants
    A18:B27  position adjustment table
    B28      baseline offense rate (auto)
    B29      baseline runs-allowed per IP (auto)
    cols A..S per player: name,pos,PA,1B,2B,3B,HR,BB+HBP,SB,CS,IP,R,
                          Outs,BatRuns,BatRAB,PosRuns,PitchRAB,RAR,WAR
"""

from dataclasses import dataclass

# --- B2:B9  linear weights (runs per event) ---------------------------------
WEIGHTS = {
    "out": -0.1,     # B2
    "bbhbp": 0.3,    # B3
    "single": 0.45,  # B4
    "double": 0.75,  # B5
    "triple": 1.0,   # B6
    "hr": 1.4,       # B7
    "sb": 0.2,       # B8
    "cs": -0.4,      # B9
}

# --- B11:B14  settings ------------------------------------------------------
SETTINGS = {
    "r": 10.0,        # B11 runs per team per game
    "gap_off": 0.05,  # B12 replacement gap, offense (runs/PA)
    "gap_pit": 0.15,  # B13 replacement gap, pitching (runs/IP)
    "full_pa": 50.0,  # B14 full-season PA
}

# --- A18:B27  position adjustment (runs per full season) --------------------
POS_ADJ = {
    "C": 9, "SS": 6, "CF": 5, "2B": 3, "3B": 2,
    "LF": -5, "RF": -4, "1B": -7, "DH": -8, "P": 0,
}


@dataclass
class Player:
    name: str
    pos: str
    PA: int
    b1: int   # 1B
    b2: int   # 2B
    b3: int   # 3B
    hr: int
    bb: int   # BB + HBP
    sb: int
    cs: int
    ip: float = 0.0
    r: int = 0  # runs allowed while pitching


# --- sample made-up GameChanger roster (no real kids were harmed) -----------
SAMPLE = [
    Player("Mateo", "SS", 52, 12, 5, 1, 3, 14, 9, 2, 0, 0),
    Player("Liam",  "C",  48, 10, 3, 0, 1, 12, 3, 1, 0, 0),
    Player("Ethan", "1B", 47, 9,  4, 0, 2, 8,  1, 0, 0, 0),
    Player("Noah",  "P",  46, 9,  2, 0, 2, 10, 4, 1, 30, 18),
    Player("Lucas", "LF", 42, 6,  1, 0, 0, 6,  2, 1, 0, 0),
]


def outs(p: Player) -> int:
    """col M: PA minus times reached (hits + walks), floored at 0."""
    return max(0, p.PA - (p.b1 + p.b2 + p.b3 + p.hr + p.bb))


def bat_runs(p: Player, w=WEIGHTS) -> float:
    """col N: linear-weights batting runs."""
    return (
        w["out"] * outs(p)
        + w["bbhbp"] * p.bb
        + w["single"] * p.b1
        + w["double"] * p.b2
        + w["triple"] * p.b3
        + w["hr"] * p.hr
        + w["sb"] * p.sb
        + w["cs"] * p.cs
    )


def constants(s=SETTINGS):
    """B15 Pythag exponent and B16 runs per win."""
    x = (2 * s["r"]) ** 0.287
    rpw = 4 * s["r"] / x if x else 0.0
    return x, rpw


def baselines(players, s=SETTINGS):
    """B28 baseline offense rate and B29 baseline RA per IP."""
    sum_pa = sum(p.PA for p in players)
    sum_br = sum(bat_runs(p) for p in players)
    sum_ip = sum(p.ip for p in players)
    sum_r = sum(p.r for p in players)
    base_off = (sum_br / sum_pa - s["gap_off"]) if sum_pa else 0.0
    base_ra = (sum_r / sum_ip + s["gap_pit"]) if sum_ip else 0.0
    return base_off, base_ra


def evaluate(players, s=SETTINGS, pos_adj=POS_ADJ):
    """Return a list of per-player result dicts (cols M..S)."""
    x, rpw = constants(s)
    base_off, base_ra = baselines(players, s)
    rows = []
    for p in players:
        n = bat_runs(p)                                   # col N
        bat_rab = n - base_off * p.PA                     # col O
        adj = pos_adj.get(p.pos, 0)
        pos_runs = adj * p.PA / s["full_pa"] if s["full_pa"] else 0.0  # col P
        pitch_rab = (base_ra - p.r / p.ip) * p.ip if p.ip else 0.0     # col Q
        rar = bat_rab + pos_runs + pitch_rab              # col R
        war = rar / rpw if rpw else 0.0                   # col S
        rows.append({
            "name": p.name, "pos": p.pos, "outs": outs(p), "bat_runs": n,
            "bat_rab": bat_rab, "pos_runs": pos_runs, "pitch_rab": pitch_rab,
            "rar": rar, "war": war,
        })
    return rows, {"x": x, "rpw": rpw, "base_off": base_off, "base_ra": base_ra}


def _print_report(players=SAMPLE):
    rows, c = evaluate(players)
    print("Derived constants")
    print(f"  Pythag exponent x   = {c['x']:.3f}")
    print(f"  Runs per win (RPW)  = {c['rpw']:.2f}")
    print(f"  Baseline offense    = {c['base_off']:.3f} runs/PA")
    print(f"  Baseline RA per IP  = {c['base_ra']:.3f} runs/IP\n")
    hdr = f"{'Name':8}{'Pos':4}{'Outs':>5}{'BatR':>7}{'BatRAB':>8}{'PosR':>7}{'PitchR':>8}{'RAR':>8}{'WAR':>7}"
    print(hdr)
    print("-" * len(hdr))
    for r in sorted(rows, key=lambda x: -x["war"]):
        print(f"{r['name']:8}{r['pos']:4}{r['outs']:>5}{r['bat_runs']:>7.2f}"
              f"{r['bat_rab']:>8.2f}{r['pos_runs']:>7.2f}{r['pitch_rab']:>8.2f}"
              f"{r['rar']:>8.2f}{r['war']:>7.3f}")


if __name__ == "__main__":
    _print_report()
