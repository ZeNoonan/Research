"""Build index.html, the GitHub Pages view of the VaR backtest.

    python3 build_site.py

One run does everything: it runs the backtests (var_backtest.run), rewrites
results/backtest_report.md and the PNG charts, and writes index.html, which
is template.html with the results dropped in as JSON between /*__DATA__*/
and /*__END_DATA__*/. The page draws every number and chart from that block,
so what the block says is what the page shows.

Run test_pipeline.py afterwards. It recomputes the block from
data/NASDAQCOM.csv with code of its own; it never imports this file or
var_backtest.py.

The build is deterministic: no timestamps, fixed seed. Building twice gives
the same bytes.
"""

import json
from pathlib import Path

import numpy as np

import var_backtest as vb

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "template.html"
PAGE = HERE / "index.html"
SLOT = "/*__DATA__*/null/*__END_DATA__*/"


def iso(day):
    return f"{day:%Y-%m-%d}"

def dollars(series):
    """Whole dollars: the page needs no more, and it keeps the file small."""
    return np.rint(series).astype(int).tolist()

def method_payload(r, with_series):
    out = {
        "key": r.key,
        "name": r.name,
        "spec": r.spec,
        "description": r.description,
        "breaks": np.flatnonzero(r.breaks).tolist(),   # prediction-day indices
        "t1": {
            "breaks": r.n_breaks,
            "rate": r.n_breaks / r.n_obs,
            "z": r.z_score,
            "p": r.kupiec_p,
        },
        "t2": {
            "next_day": r.next_day_breaks,
            "next_day_expected": r.next_day_expected,
            "next_day_p": r.next_day_p,
            "within10": r.within10_breaks,
            "within10_expected": r.within10_expected,
            "within10_p": r.within10_p,
            "christoffersen_p": r.christoffersen_p,
        },
        "t3": {
            "avg_var": r.avg_var,
            "avg_var_breaks": r.avg_var_on_breaks,
            "ratio": r.ratio,
            "perm_p": r.perm_p,
            "welch_p": r.welch_p,
        },
        "verdicts": [
            {"pass": ok, "borderline": close, "p": p}
            for ok, close, p in zip(r.passes, r.borderline, r.deciding_p)
        ],
    }
    if with_series:
        out["var"] = dollars(r.var)
    return out

def payload(bt):
    prices = bt.prices
    epoch = np.datetime64("1970-01-01", "D")
    days = (bt.dates.values.astype("datetime64[D]") - epoch).astype(int).tolist()
    recalibrated = []
    for r, parameter in zip(bt.recalibrated, (bt.hs_percentile, bt.ewma_multiplier)):
        recalibrated.append(dict(method_payload(r, with_series=False), parameter=parameter))
    return {
        "settings": {
            "portfolio": vb.PORTFOLIO,
            "var_level": vb.VAR_LEVEL,
            "window": vb.WINDOW,
            "decay": vb.DECAY,
            "z": vb.Z_99,
            "alpha": vb.ALPHA,
            "borderline": list(vb.BORDERLINE),
            "perm_draws": vb.PERM_DRAWS,
        },
        "source": {
            "series": "NASDAQCOM",
            "rows": bt.n_rows,
            "blank": bt.n_rows - len(prices),
            "closes": len(prices),
            "first_close": iso(prices.index[0]),
            "last_close": iso(prices.index[-1]),
        },
        "n": len(bt.losses),
        "first": iso(bt.dates[0]),
        "last": iso(bt.dates[-1]),
        "expected": bt.methods[0].expected_breaks,
        "target": bt.target,
        "days": days,                       # days since 1970-01-01, one per prediction
        "loss": dollars(bt.losses),
        "methods": [method_payload(r, with_series=True) for r in bt.methods],
        "recalibrated": recalibrated,
        "commentary": vb.commentary(bt),
        "recalibrated_note": vb.RECALIBRATED_NOTE,
    }

def to_json(data):
    def plain(value):                       # numpy scalars -> Python numbers
        return value.item()
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False, default=plain)
    return text.replace("</", "<\\/")       # never close the <script> early

def main():
    bt = vb.run()
    vb.write_outputs(bt)

    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(SLOT) != 1:
        raise SystemExit(f"template.html must contain {SLOT} exactly once")
    blob = to_json(payload(bt))
    page = template.replace(SLOT, "/*__DATA__*/" + blob + "/*__END_DATA__*/")
    PAGE.write_text(page, encoding="utf-8")

    vb.print_scorecard(bt)
    print(f"\nWrote {PAGE.name} ({len(page.encode('utf-8')) / 1024:.0f} KB), "
          f"results/backtest_report.md and the charts in results/.")
    print("Now run: python3 test_pipeline.py")


if __name__ == "__main__":
    main()
