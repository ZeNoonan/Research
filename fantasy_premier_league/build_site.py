"""Generate a self-contained, mobile-friendly HTML view of the weekly picks.

Rates the season in ``data/<season>/`` and writes ``index.html``: the factor
explainer, the 4/5-star pick lists by position and the captain shortlist.
No external assets (same treatment as ``nfl_report/``), so the page can be
served from GitHub Pages or opened as a file. Rerun after adding gameweek
files:

    python build_site.py [--data data/2026-27]
"""

from __future__ import annotations

import argparse
import html
from datetime import date
from pathlib import Path

import model
from weekly_report import POSITION_NAMES, fmt_selected

HERE = Path(__file__).parent
PER_POSITION = 12  # rows shown per position section

CSS = """
:root {
  --bg: #f4f6f8; --card: #ffffff; --ink: #1c2733; --muted: #5f6b76;
  --accent: #38003c; --accent2: #00ff85; --border: #dce3ea; --star: #b58900;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  -webkit-text-size-adjust: 100%; }
.wrap { max-width: 980px; margin: 0 auto; padding: 16px; }
header h1 { font-size: 24px; margin: 8px 0 4px; }
header p.sub { color: var(--muted); margin: 0 0 16px; font-size: 14px; }
.banner { background: var(--accent); color: #fff; border-radius: 10px;
  padding: 12px 14px; font-size: 14px; margin-bottom: 16px; }
.banner b { color: var(--accent2); }
section { background: var(--card); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px; margin-bottom: 16px; }
section h2 { font-size: 18px; margin: 0 0 10px; }
.tablewrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border);
  white-space: nowrap; }
th { color: var(--muted); font-weight: 600; font-size: 12px;
  text-transform: uppercase; letter-spacing: .04em; }
td.num, th.num { text-align: right; }
.stars { color: var(--star); letter-spacing: 1px; }
.letters { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: #eef4fb; border-radius: 6px; padding: 1px 6px; font-size: 12px; }
p.note, li { color: var(--muted); font-size: 14px; }
code { background: #eef1f4; border-radius: 4px; padding: 1px 5px; font-size: 13px; }
footer { color: var(--muted); font-size: 12px; margin: 20px 0; text-align: center; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #14181c; --card: #1d232a; --ink: #e6ebf0; --muted: #98a4af;
    --border: #313a44; --star: #e0b64a; }
  .letters { background: #26303a; }
  code { background: #26303a; }
}
"""

FACTOR_ROWS = [
    ("Q", "Quality", "Model expected points per 90 — rebuilt from the FPL "
     "scoring rules and the player's underlying per-90 numbers (xG, xA, xGC, "
     "defensive contributions, saves) — above the position median."),
    ("V", "Value", "Expected points per 90 per £million above the position "
     "median. Points per pound funds the rest of the squad."),
    ("F", "Form", "Points over the last 5 gameweeks above the position "
     "median. Momentum."),
    ("J", "Justice", "Under-rewarded over the last 6 gameweeks: attackers "
     "whose xGI beats their actual returns, defenders/keepers who conceded "
     "more than their xGC. Luck mean-reverts; the unlucky are cheap."),
    ("C", "Crowd", "Ownership percentile below quality percentile within the "
     "position — the field underweights the player (bet against beta)."),
]


def esc(x) -> str:
    return html.escape(str(x))


def picks_table(block) -> str:
    rows = []
    for r in block.itertuples():
        rows.append(
            f"<tr><td><span class='stars'>{'★' * r.stars}</span></td>"
            f"<td>{esc(r.name)}</td><td>{esc(r.team)}</td>"
            f"<td class='num'>£{r.price:.1f}m</td>"
            f"<td><span class='letters'>{esc(r.factor_letters)}</span></td>"
            f"<td class='num'>{r.xpts90:.1f}</td>"
            f"<td class='num'>{fmt_selected(r.selected)}</td></tr>")
    head = ("<tr><th>Stars</th><th>Player</th><th>Team</th>"
            "<th class='num'>Price</th><th>Factors</th>"
            "<th class='num'>xPts/90</th><th class='num'>Owned</th></tr>")
    return f"<div class='tablewrap'><table>{head}{''.join(rows)}</table></div>"


def build(data_dir: Path, out: Path) -> None:
    rated = model.rate_season(data_dir)
    picks = model.recommendations(rated, min_stars=4)
    through = int(rated["through_gw"].iloc[0])
    used = int(rated["gws_used"].iloc[0])
    season = data_dir.name

    thin = ""
    if used < model.MINUTES_WINDOW:
        thin = (" Only <b>%d</b> gameweek%s of evidence is loaded, so the "
                "form and justice windows are thin — treat these ratings as "
                "provisional." % (used, "s" if used != 1 else ""))

    sections = []
    for pos in model.POSITIONS:
        block = picks[picks["position"] == pos].head(PER_POSITION)
        body = (picks_table(block) if not block.empty
                else "<p class='note'>No players at 4+ stars.</p>")
        sections.append(f"<section><h2>{POSITION_NAMES[pos]}</h2>{body}</section>")

    captains = picks[picks["position"].isin(("MID", "FWD"))].nlargest(3, "xpts90")
    cap = ", ".join(f"{esc(r.name)} ({esc(r.team)})" for r in captains.itertuples())

    factor_rows = "".join(
        f"<tr><td><span class='letters'>{l}</span></td><td><b>{n}</b></td>"
        f"<td style='white-space:normal'>{d}</td></tr>"
        for l, n, d in FACTOR_ROWS)

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FPL five-factor picks — {esc(season)} through GW{through}</title>
<style>{CSS}</style></head><body><div class="wrap">
<header><h1>FPL five-factor picks</h1>
<p class="sub">An additive binary-factor model for weekly Fantasy Premier
League picks — one star per factor, judged against position peers, in the
family of <code>march_madness/</code> and <code>nfl_report/</code>.</p></header>
<div class="banner">Season <b>{esc(season)}</b>, rated through
<b>GW{through}</b>. {int(rated['eligible'].sum())} players pass the minutes
gate; 4★ and 5★ picks below (top {PER_POSITION} per position).{thin}</div>
<section><h2>The five factors</h2>
<div class="tablewrap"><table>{factor_rows}</table></div>
<p class="note">Eligibility gate: 45+ minutes per gameweek averaged over the
last {model.MINUTES_WINDOW} gameweeks — no factor can rescue a player who
doesn't play.</p></section>
{''.join(sections)}
<section><h2>Captain shortlist</h2>
<p class="note">{cap or 'No 4★+ attackers yet.'}</p></section>
<section><h2>Refresh</h2>
<p class="note"><code>python fetch_data.py</code> after a gameweek finishes,
then <code>python weekly_report.py</code> for the terminal view and
<code>python build_site.py</code> to regenerate this page. The full rated
table for every player is written to <code>reports/</code>.</p></section>
<footer>Generated {date.today().isoformat()} · fantasy_premier_league ·
five-factor model</footer>
</div></body></html>"""
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({len(picks)} picks, through GW{through})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=HERE / "data" / "2025-26")
    ap.add_argument("--out", default=HERE / "index.html")
    args = ap.parse_args()
    build(Path(args.data), Path(args.out))


if __name__ == "__main__":
    main()
