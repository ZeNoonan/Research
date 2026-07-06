"""Distill results/site_data.json into the compact payload inlined in
index.html (works from file:// so no fetch)."""

import json
from pathlib import Path

import numpy as np

from board import STREETS, GROUPS, RAILROADS, UTILITIES

ROOT = Path(__file__).resolve().parent.parent
d = json.loads((ROOT / "results" / "site_data.json").read_text())

sq_group = {}
for s in STREETS:
    sq_group[s.square] = s.group
for q in RAILROADS:
    sq_group[q] = "rail"
for q in UTILITIES:
    sq_group[q] = "util"

# Overall duel win rate per group per cash level.
duel_overall = {}
duel_pairs = {}
for cash, tbl in d["duels"].items():
    wins = {}
    games = {}
    for ga, row in tbl.items():
        for gb, (wa, wb, dr) in row.items():
            wins[ga] = wins.get(ga, 0) + wa
            wins[gb] = wins.get(gb, 0) + wb
            games[ga] = games.get(ga, 0) + wa + wb + dr
            games[gb] = games.get(gb, 0) + wa + wb + dr
    duel_overall[cash] = {g: round(100 * wins[g] / games[g], 1) for g in wins}
    lg = tbl.get("lightblue", {}).get("green")
    duel_pairs[cash] = {"lightblue_vs_green": lg}

# Rent-roll deficit histogram (bins of $5 from -60 to 120).
sample = np.array(d["rentroll_dist"]["sample"])
edges = np.arange(-60, 125, 5)
hist, _ = np.histogram(sample, bins=edges)
rentroll = {
    "bin_start": -60, "bin_width": 5,
    "counts": hist.tolist(), "n": int(len(sample)),
    "sd": round(d["rentroll_dist"]["sd"], 2),
    "skew": round(d["rentroll_dist"]["skew"], 2),
    "p_below": round(100 * d["rentroll_dist"]["p_below"], 1),
}

# Game length histogram (bins of 250 rolls).
lengths = np.array(d["full_games"]["lengths"])
ledges = np.arange(0, 6250, 250)
lhist, _ = np.histogram(lengths, bins=ledges)

# ODE scenarios: downsample to ~130 points.
scen = []
for s in d["ode_scenarios"]:
    step = max(1, len(s["t"]) // 130)
    scen.append({
        "label": s["label"], "r0": s["r0"], "betas": s["betas"],
        "phi": s["phi"],
        "t": s["t"][::step],
        "paths": [p[::step] for p in s["paths"]],
    })

payload = {
    "freq": {
        "ours": d["frequencies"]["ours"],
        "paper": d["frequencies"]["paper"],
        "names": d["frequencies"]["names"],
        "group": [sq_group.get(q) for q in range(40)],
    },
    "phi": {k: round(v, 4) for k, v in d["phi"].items()},
    "table": [
        {"group": r["group"], "label": r["label"],
         "beta": r["beta_i"],
         "rs": round(r["rent_start"], 2), "vs": round(r["value_start_implied"]),
         "re": round(r["rent_end"], 2), "ve": round(r["value_end_implied"]),
         "paper": r["paper"], "vmax": r["max_value_paper"]}
        for r in d["part2_table"]],
    "naive_betas": {g: round(b, 4) for g, b in d["naive_betas"].items()},
    "duel_overall": duel_overall,
    "duel_pairs": duel_pairs,
    "roi": {g: {"label": v["label"],
                "roi": [round(s["roi"] * 100, 2) for s in v["stages"]],
                "cost": v["stages"][0]["cost"]}
            for g, v in d["house_roi"].items()},
    "payback": {g: round(v["rolls_to_payback"]) for g, v in d["payback"].items()},
    "rentroll": rentroll,
    "games": {"bins": lhist.tolist(), "bin_width": 250,
              "finished": d["full_games"]["finished"],
              "unfinished": d["full_games"]["unfinished"],
              "median": d["full_games"]["median_len"]},
    "ode": scen,
    "validation": d["validation"],
    "meta": d["meta"],
}

out = ROOT / "results" / "payload.json"
out.write_text(json.dumps(payload))
print(f"{out}: {out.stat().st_size/1024:.0f} KB")
