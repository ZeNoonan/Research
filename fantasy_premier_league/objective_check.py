# Drop into fantasy_premier_league/ and run: python objective_check.py
# Compares the star-maximising squad squad.py builds against a direct
# expected-points optimisation under identical FPL constraints.
"""Star-max squad vs direct expected-points squad, same constraints."""
import pandas as pd, pulp, preseason, squad

rated, unrated = preseason.rate_preseason('data/2026-27/player_listing.csv',
                                          'data/2025-26')
b = rated[rated['eligible'] & ~rated['unavailable']].copy()
# projected season points = xPts/90 * expected minutes / 90
b['xpts_season'] = b['xpts90'] * b['minutes_share'] * 38.0
# Same bench-forward cap squad.py applies, and the same scoreless filler it
# needs to satisfy it - otherwise this stops being a check on the same
# problem. Recomputed here rather than imported, which is the point.
CAP = 4.5
fodder = unrated[(unrated['position'] == 'FWD') & (unrated['price'] <= CAP)
                 & ~unrated['unavailable']].copy()
for col in ('stars', 'xpts90', 'xpts_season', 'owned_pct'):
    if col not in fodder or col in ('stars', 'xpts90', 'xpts_season'):
        fodder[col] = 0.0
b = pd.concat([b, fodder], ignore_index=True)
FORCED = [i for i in b.index
          if b.at[i, 'position'] == 'FWD' and b.at[i, 'price'] > CAP]

SQ = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
XI_MIN = {"GK": 1, "DEF": 3, "MID": 2, "FWD": 1}
XI_MAX = {"GK": 1, "DEF": 5, "MID": 5, "FWD": 3}


def optimise(df, col, bench_weight=0.0, captain=True):
    p = pulp.LpProblem("s", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x{i}", cat="Binary") for i in df.index}   # in 15
    y = {i: pulp.LpVariable(f"y{i}", cat="Binary") for i in df.index}   # in XI
    c = {i: pulp.LpVariable(f"c{i}", cat="Binary") for i in df.index}   # captain
    p += pulp.lpSum(df.at[i, col] * (y[i] + bench_weight * (x[i] - y[i])
                                     + (c[i] if captain else 0))
                    for i in df.index)
    p += pulp.lpSum(x[i] for i in df.index) == 15
    p += pulp.lpSum(y[i] for i in df.index) == 11
    p += pulp.lpSum(c[i] for i in df.index) == (1 if captain else 0)
    p += pulp.lpSum(df.at[i, 'price'] * x[i] for i in df.index) <= 100.0
    for i in df.index:
        p += y[i] <= x[i]
        p += c[i] <= y[i]
    for pos, n in SQ.items():
        m = [i for i in df.index if df.at[i, 'position'] == pos]
        p += pulp.lpSum(x[i] for i in m) == n
        p += pulp.lpSum(y[i] for i in m) <= XI_MAX[pos]
        p += pulp.lpSum(y[i] for i in m) >= XI_MIN[pos]
    for club in df['team'].unique():
        m = [i for i in df.index if df.at[i, 'team'] == club]
        p += pulp.lpSum(x[i] for i in m) <= 3
    for i in FORCED:
        p += x[i] <= y[i]
    p.solve(pulp.PULP_CBC_CMD(msg=0))
    sel = df.loc[[i for i in df.index if x[i].value() > .5]].copy()
    sel['xi'] = [y[i].value() > .5 for i in sel.index]
    sel['capt'] = [c[i].value() > .5 for i in sel.index]
    return sel


def score(sq):
    xi = sq[sq['xi']]
    capt = sq[sq['capt']]['xpts_season'].sum() if sq['capt'].any() else 0
    return xi['xpts_season'].sum() + capt


# the repo's own squad
factor, _ = squad.build('data/2026-27/player_listing.csv', 'data/2025-26')
# build() now supplies xpts_season itself; drop it so this script's own
# independent recomputation is what gets merged in, not a self-check.
factor = factor.drop(columns=['xpts_season'], errors='ignore').merge(
    b[['name', 'xpts_season']], on='name', how='left')
fxi = factor[factor['xi']]
f_capt = fxi.nlargest(1, 'xpts90')['xpts_season'].iloc[0]
print(f"REPO star-max squad : XI {fxi['xpts_season'].sum():.1f} + capt {f_capt:.1f} "
      f"= {fxi['xpts_season'].sum() + f_capt:.1f} projected pts")

ev = optimise(b, 'xpts_season', bench_weight=0.1)
print(f"EV-max squad        : {score(ev):.1f} projected pts")
print(f"\ndifference: {score(ev) - (fxi['xpts_season'].sum() + f_capt):.1f} pts over a season\n")

for _, r in ev.sort_values(['xi', 'position', 'xpts_season'], ascending=[False, True, False]).iterrows():
    m = ' ' if r['xi'] else 'B'
    cap = ' (C)' if r['capt'] else ''
    print(f"  {m} {r['position']:4} {r['name'][:26]:27} {r['team'][:13]:14} "
          f"£{r['price']:>4.1f}m  {int(r['stars'])}*  proj {r['xpts_season']:>5.1f}"
          f"  own {r['owned_pct']:>4.1f}%{cap}")
print(f"\nspend £{ev['price'].sum():.1f}m")
