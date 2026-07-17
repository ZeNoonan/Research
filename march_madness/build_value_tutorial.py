"""Generate value_tutorial.html — an in-depth tutorial on the Value factor.

Reads data/model_2019.json (produced by extract_model.py) and writes a
self-contained page that teaches how the Value pick calculation works, from
first principles to the exact workbook columns:

  * why variance — not expected points — wins bracket pools;
  * the quantities (p, f, p0, f0, S) and the slot/group structure;
  * the derivation of E[Y], Var(Y), dEV and dVar, step by step;
  * a two-team toy example small enough to enumerate by hand, with live
    sliders that recompute every number (and verify the closed form against
    direct enumeration);
  * an explorer that traces the full calculation for any 2019 team and round,
    with every substitution shown, in both the fixed and as-published modes;
  * a "value frontier" scatter of all 64 teams against the ratio boundary.

All maths is re-implemented in the embedded JavaScript (the same slot
calculations as index.html, verified against the workbook by
extract_model.py --report). No external assets.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data" / "model_2019.json"
OUT = HERE / "value_tutorial.html"

CSS = """
:root {
  --bg: #f4f6f8; --card: #ffffff; --ink: #1c2733; --muted: #5f6b76;
  --accent: #134074; --gold: #c9920a; --good: #1e7d46; --bad: #b3372f;
  --border: #dce3ea; --hl: #fdf6e3; --chip: #eef4fb;
  --s1: #2a78d6; --s2: #008300; --dim: #898781;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  font-size: 15px; line-height: 1.55; }
.wrap { max-width: 980px; margin: 0 auto; padding: 16px; }
header h1 { margin: 8px 0 2px; font-size: 26px; color: var(--accent); }
header p.sub { margin: 0 0 10px; color: var(--muted); }
.toc { margin: 0 0 14px; }
.toc a { display: inline-block; background: var(--chip); color: var(--accent);
  border-radius: 12px; padding: 2px 10px; margin: 2px 6px 2px 0;
  font-size: 12.5px; text-decoration: none; }
.toc a:hover { background: #dfeafa; }
.card { background: var(--card); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 16px; margin: 14px 0; }
.card h2 { margin: 0 0 8px; font-size: 18px; color: var(--accent); }
.card h3 { margin: 14px 0 6px; font-size: 15px; }
.stepbadge { display: inline-block; background: var(--accent); color: #fff;
  border-radius: 12px; font-size: 12px; padding: 1px 9px;
  vertical-align: 2px; margin-right: 7px; }
.formula { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13.5px; background: var(--chip); border-radius: 8px;
  padding: 9px 12px; margin: 8px 0; overflow-x: auto; white-space: pre; }
.formula b { color: var(--accent); }
.callout { border-left: 4px solid var(--gold); background: var(--hl);
  border-radius: 0 8px 8px 0; padding: 8px 12px; margin: 10px 0;
  font-size: 13.5px; }
.note { font-size: 13px; color: var(--muted); }
code { background: var(--chip); padding: 1px 5px; border-radius: 4px;
  font-size: 12.5px; }
a { color: var(--accent); }
table { border-collapse: collapse; font-size: 13px; }
.num-table th, .num-table td { border: 1px solid var(--border);
  padding: 3px 8px; text-align: right; font-variant-numeric: tabular-nums; }
.num-table th { background: var(--chip); font-weight: 600; }
.num-table th:first-child, .num-table td:first-child { text-align: left; }
.num-table tr.hl-you td { background: var(--hl); }
.num-table tr.hl-fav td { background: var(--chip); }
.num-table tr.sumrow td { border-top: 2px solid #b9c4cf; font-weight: 600; }
.num-table tr.sel td { outline: 2px solid var(--accent); outline-offset: -2px; }
.num-table tr.clickable { cursor: pointer; }
.num-table tr.clickable:hover td { background: #f2f7fc; }
.scrollx { overflow-x: auto; margin: 8px 0; }
.scrolly { max-height: 250px; overflow-y: auto; margin: 8px 0;
  border: 1px solid var(--border); border-radius: 6px; }
.scrolly table { width: 100%; }
.scrolly .num-table th, .scrolly .num-table td { border-left: 0; border-right: 0; }
.scrolly th { position: sticky; top: 0; }
.controls { display: flex; flex-wrap: wrap; gap: 10px 22px;
  align-items: flex-end; margin: 6px 0 10px; }
.controls label { display: flex; flex-direction: column; gap: 2px;
  font-size: 12px; color: var(--muted); }
.controls select { padding: 4px 6px; font-size: 13.5px;
  border: 1px solid var(--border); border-radius: 6px; background: #fff;
  color: var(--ink); max-width: 260px; }
.controls input[type=range] { width: 170px; accent-color: var(--accent); }
.controls .val { font-size: 13.5px; color: var(--ink); font-weight: 600; }
.mode-toggle { display: inline-flex; border: 1px solid var(--border);
  border-radius: 8px; overflow: hidden; }
.mode-toggle button { border: 0; padding: 5px 12px; font-size: 13px;
  cursor: pointer; background: var(--card); color: var(--ink); }
.mode-toggle button.active { background: var(--accent); color: #fff; }
.verdict { border-radius: 8px; padding: 8px 12px; font-size: 14px;
  margin: 10px 0; font-weight: 600; }
.verdict.yes { background: #e8f5ee; color: var(--good); }
.verdict.no { background: #fbeae8; color: var(--bad); }
.verdict .why { font-weight: 400; color: var(--ink); font-size: 13px; }
.tracestep { border: 1px solid var(--border); border-radius: 8px;
  padding: 10px 12px; margin: 10px 0; }
.tracestep h4 { margin: 0 0 6px; font-size: 13.5px; color: var(--accent); }
.chart-wrap { position: relative; margin: 10px 0 4px; }
.chart-wrap svg { display: block; width: 100%; height: auto; }
.viz-tooltip { position: absolute; display: none; z-index: 5;
  background: #fff; border: 1px solid var(--border); border-radius: 6px;
  padding: 6px 9px; font-size: 12px; pointer-events: none;
  box-shadow: 0 2px 8px rgba(28,39,51,.15); max-width: 240px; }
.viz-tooltip b { font-size: 12.5px; }
.viz-tooltip .tt-val { font-weight: 600; font-variant-numeric: tabular-nums; }
.legend { display: flex; flex-wrap: wrap; gap: 4px 18px; margin: 6px 0;
  font-size: 12.5px; color: var(--muted); align-items: center; }
.legend .sw { display: inline-block; width: 12px; height: 12px;
  border-radius: 3px; margin-right: 5px; vertical-align: -2px; }
.legend .dot { display: inline-block; width: 11px; height: 11px;
  border-radius: 50%; margin-right: 5px; vertical-align: -2px;
  border: 2px solid #fff; box-shadow: 0 0 0 1px var(--border); }
.defs { display: grid; gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
.defs .d { border: 1px solid var(--border); border-radius: 8px;
  padding: 9px 12px; background: #fbfcfe; font-size: 13.5px; }
.defs .d b { color: var(--accent); font-family: ui-monospace, SFMono-Regular,
  Menlo, Consolas, monospace; }
.defs .d p { margin: 3px 0 0; color: var(--muted); font-size: 13px; }
ul.fine { padding-left: 20px; font-size: 13.5px; }
ul.fine li { margin: 6px 0; }
footer { color: var(--muted); font-size: 12.5px; margin: 20px 0; }
.star { color: var(--gold); }
svg text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
  Roboto, sans-serif; }
"""

JS = r"""
const MODEL = __DATA__;
const ROUNDS = MODEL.rounds;
const RLABEL = ["Round of 64","Round of 32","Sweet 16","Elite 8","Final 4","Champion"];
const N = 64, BUG_OFFSET = 38;
const POINTS = MODEL.points;

/* ---- slot calculations (same maths as index.html / extract_model.py) ---- */

function slotCalcs(mode) {
  const T = MODEL.teams;
  const S = [], P0 = [], P0F0 = [];
  for (let i = 0; i < N; i++) { S.push([]); P0.push([]); P0F0.push([]); }
  for (let k = 0; k < 6; k++) {
    const size = 2 ** (k + 1);
    for (let g = 0; g < N; g += size) {
      let s = 0, mx = -Infinity;
      for (let i = g; i < g + size; i++) {
        s += T[i].prob[k] * T[i].freq[k];
        if (T[i].prob[k] > mx) mx = T[i].prob[k];
      }
      let fs = 0, fn = 0;
      for (let i = g; i < g + size; i++)
        if (T[i].prob[k] === mx) { fs += T[i].freq[k]; fn++; }
      const pf = fs / fn * mx;
      for (let i = g; i < g + size; i++) { S[i][k] = s; P0[i][k] = mx; P0F0[i][k] = pf; }
    }
  }
  const out = [];
  for (let i = 0; i < N; i++) {
    const t = T[i], expDiff = [], varOne = [], varDiff = [], sUsedArr = [];
    for (let k = 0; k < 6; k++) {
      const p = t.prob[k], f = t.freq[k], s = S[i][k];
      expDiff.push(POINTS[k] * (p - P0[i][k]));
      varOne.push(p * (1 - p - 2 * f + 2 * s) + s - s * s);
      let sUsed = s;
      if (mode === "published") {            // the fill-down bug: S from 38 rows down
        const j = i + BUG_OFFSET;
        sUsed = j < N ? S[j][k] : 0;
      }
      sUsedArr.push(sUsed);
      varDiff.push(POINTS[k] ** 2 * ((p - P0[i][k]) * (1 + 2 * sUsed)
        - p * p + P0[i][k] ** 2 - 2 * (p * f - P0F0[i][k])));
    }
    const cumExp = [], cumVar = [];
    let ce = 0, cv = 0;
    for (let k = 0; k < 6; k++) { ce += expDiff[k]; cv += varDiff[k]; cumExp.push(ce); cumVar.push(cv); }
    const ratio = cumExp.map((e, k) => e === 0 ? 0 : cumVar[k] / e);
    const value = ratio.map(r => mode === "published"
      ? ((r === 0 || r > 1) ? 1 : 0)
      : ((r === 0 || r <= -1) ? 1 : 0));
    out.push({ S: S[i], p0: P0[i], p0f0: P0F0[i], sUsed: sUsedArr, expDiff,
               cumExp, variance: varOne, varDiff, cumVar, ratio, value });
  }
  return out;
}

const SLOTS = { fixed: slotCalcs("fixed"), published: slotCalcs("published") };

const state = {
  mode: "fixed",
  team: Math.max(0, MODEL.teams.findIndex(t => t.name === "Texas Tech")),
  round: 2,
  frontierRound: 5,
};

/* ------------------------------- helpers ------------------------------- */

function fmt(x, dp = 3) {
  const v = Math.round(x * 10 ** dp) / 10 ** dp;
  return (Object.is(v, -0) ? 0 : v).toFixed(dp);
}
function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function groupRange(i, k) {
  const size = 2 ** (k + 1), g = Math.floor(i / size) * size;
  return [g, g + size];
}
function favoritesOf(i, k) {
  const [g, e] = groupRange(i, k), p0 = SLOTS.fixed[i].p0[k], out = [];
  for (let j = g; j < e; j++) if (MODEL.teams[j].prob[k] === p0) out.push(j);
  return out;
}
function setText(id, s) { document.getElementById(id).textContent = s; }

/* ---------------------------- tooltip (shared) -------------------------- */

function makeTooltip(wrap) {
  const tip = document.createElement("div");
  tip.className = "viz-tooltip";
  wrap.appendChild(tip);
  return {
    show(px, py, rows) {                       // rows: [label, value, isHead]
      tip.replaceChildren();
      rows.forEach(([lab, val, head]) => {
        const div = document.createElement("div");
        if (head) { const b = document.createElement("b"); b.textContent = lab; div.appendChild(b); }
        else {
          div.appendChild(document.createTextNode(lab + " "));
          const sp = document.createElement("span");
          sp.className = "tt-val"; sp.textContent = val;
          div.appendChild(sp);
        }
        tip.appendChild(div);
      });
      tip.style.display = "block";
      const W = wrap.clientWidth, tw = tip.offsetWidth;
      tip.style.left = Math.max(0, Math.min(px + 14, W - tw - 4)) + "px";
      tip.style.top = Math.max(0, py - tip.offsetHeight - 10) + "px";
    },
    hide() { tip.style.display = "none"; },
  };
}

/* ------------------------------ toy example ----------------------------- */

const toy = { pA: 0.70, fA: 0.80, pts: 1 };

function toyCompute() {
  const pA = toy.pA, fA = toy.fA, pts = toy.pts;
  const pB = 1 - pA, fB = 1 - fA;
  const S = pA * fA + pB * fB;
  // outcome rows: [prob, swingIfPickA, swingIfPickB] (in units of pts)
  const rows = [
    ["Favorite wins, opponent picked the favorite", pA * fA, 0, -1],
    ["Favorite wins, opponent picked the underdog", pA * fB, +1, 0],
    ["Underdog wins, opponent picked the favorite", pB * fA, 0, +1],
    ["Underdog wins, opponent picked the underdog", pB * fB, -1, 0],
  ];
  function moments(col) {
    let e = 0, e2 = 0;
    rows.forEach(r => { e += r[1] * r[col] * pts; e2 += r[1] * (r[col] * pts) ** 2; });
    return { e, e2, v: e2 - e * e };
  }
  const A = moments(2), B = moments(3);
  const bracket = (pB - pA) * (1 + 2 * S) - pB * pB + pA * pA - 2 * (pB * fB - pA * fA);
  const dEV = pts * (pB - pA);
  const dVar = pts * pts * bracket;
  const ratio = dVar / dEV;
  return { pA, fA, pB, fB, pts, S, rows, A, B, bracket, dEV, dVar, ratio };
}

function toyDistributions(c) {
  // P(swing = -pts / 0 / +pts) for each pick
  return {
    A: [c.pB * c.fB, c.fA, c.pA * c.fB],          // -,0,+
    B: [c.pA * c.fA, c.fB, c.pB * c.fA],
  };
}

function renderToyChart(c) {
  const host = document.getElementById("toy-chart");
  host.querySelectorAll("svg").forEach(e => e.remove());
  const dist = toyDistributions(c);
  const W = 640, H = 250, m = { t: 16, r: 12, b: 40, l: 46 };
  const pw = W - m.l - m.r, ph = H - m.t - m.b;
  const y = v => m.t + ph * (1 - v);
  const cats = ["−" + c.pts + (c.pts === 1 ? " pt" : " pts"), "0",
                "+" + c.pts + (c.pts === 1 ? " pt" : " pts")];
  let s = "";
  for (let g = 0; g <= 4; g++) {                 // gridlines 0..1 by .25
    const v = g / 4, yy = y(v);
    s += `<line x1="${m.l}" y1="${yy}" x2="${W - m.r}" y2="${yy}"
      stroke="${g === 0 ? "#b9c4cf" : "var(--border)"}" stroke-width="1"/>`;
    s += `<text x="${m.l - 7}" y="${yy + 4}" text-anchor="end" font-size="11"
      fill="var(--muted)">${v}</text>`;
  }
  const barW = 22, gap = 2, series = [
    { key: "A", name: "You pick the favorite", color: "var(--s1)", vals: dist.A },
    { key: "B", name: "You pick the underdog", color: "var(--s2)", vals: dist.B },
  ];
  const hits = [];
  for (let ci = 0; ci < 3; ci++) {
    const bandX = m.l + pw * ci / 3, bandW = pw / 3;
    const x0 = bandX + bandW / 2 - barW - gap / 2;
    series.forEach((sr, si) => {
      const v = sr.vals[ci], x = x0 + si * (barW + gap), yy = y(v);
      const h = y(0) - yy;
      if (h > 4)
        s += `<path d="M${x},${y(0)} V${yy + 4} Q${x},${yy} ${x + 4},${yy}
          H${x + barW - 4} Q${x + barW},${yy} ${x + barW},${yy + 4} V${y(0)} Z"
          fill="${sr.color}"/>`;
      else
        s += `<rect x="${x}" y="${yy}" width="${barW}" height="${Math.max(h, 1)}"
          fill="${sr.color}"/>`;
      s += `<text x="${x + barW / 2}" y="${yy - 5}" text-anchor="middle"
        font-size="11" fill="var(--muted)">${fmt(v, 2)}</text>`;
      hits.push({ x: x - 7, w: barW + 14, name: sr.name, cat: cats[ci], v });
    });
    s += `<text x="${bandX + bandW / 2}" y="${H - m.b + 18}" text-anchor="middle"
      font-size="12" fill="var(--muted)">${cats[ci]}</text>`;
  }
  s += `<text x="${m.l - 34}" y="${m.t + ph / 2}" font-size="11" fill="var(--muted)"
    transform="rotate(-90 ${m.l - 34} ${m.t + ph / 2})" text-anchor="middle">probability</text>`;
  s += `<text x="${m.l + pw / 2}" y="${H - 4}" text-anchor="middle" font-size="11"
    fill="var(--muted)">score swing vs one random opponent (this slot only)</text>`;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.innerHTML = s + hits.map((h, idx) =>
    `<rect data-hit="${idx}" x="${h.x}" y="${m.t}" width="${h.w}" height="${ph}"
     fill="transparent"/>`).join("");
  host.appendChild(svg);
  const tt = host._tt || (host._tt = makeTooltip(host));
  svg.querySelectorAll("[data-hit]").forEach(r => {
    const h = hits[+r.dataset.hit];
    r.addEventListener("pointermove", ev => {
      const b = host.getBoundingClientRect();
      tt.show(ev.clientX - b.left, ev.clientY - b.top,
        [[h.name, "", true], ["swing " + h.cat + ":", "", false],
         ["probability", fmt(h.v, 3)]]);
    });
    r.addEventListener("pointerleave", () => tt.hide());
  });
}

function renderToy() {
  const c = toyCompute();
  setText("toy-pA", fmt(c.pA, 2)); setText("toy-fA", fmt(c.fA, 2));
  setText("toy-pts", String(c.pts));
  setText("toy-pB", fmt(c.pB, 2)); setText("toy-fB", fmt(c.fB, 2));

  const enumBody = document.getElementById("toy-enum");
  enumBody.innerHTML = c.rows.map(r =>
    `<tr><td>${r[0]}</td><td>${fmt(r[1], 3)}</td>` +
    `<td>${r[2] === 0 ? "0" : (r[2] > 0 ? "+" : "−") + c.pts}</td>` +
    `<td>${r[3] === 0 ? "0" : (r[3] > 0 ? "+" : "−") + c.pts}</td></tr>`).join("");

  setText("toy-S-sub", `${fmt(c.pA, 2)}×${fmt(c.fA, 2)} + ${fmt(c.pB, 2)}×${fmt(c.fB, 2)}` +
    ` = ${fmt(c.pA * c.fA, 3)} + ${fmt(c.pB * c.fB, 3)} = ${fmt(c.S, 3)}`);

  const mom = document.getElementById("toy-moments");
  mom.innerHTML =
    `<tr><td>E[swing] &nbsp;(= pts·(p − S))</td><td>${fmt(c.A.e, 4)}</td><td>${fmt(c.B.e, 4)}</td></tr>` +
    `<tr><td>E[swing²]</td><td>${fmt(c.A.e2, 4)}</td><td>${fmt(c.B.e2, 4)}</td></tr>` +
    `<tr><td>Var(swing) = E[swing²] − E[swing]²</td><td>${fmt(c.A.v, 4)}</td><td>${fmt(c.B.v, 4)}</td></tr>`;

  setText("toy-dev-sub", `${fmt(c.B.e, 4)} − ${fmt(c.A.e, 4)} = ${fmt(c.dEV, 4)}` +
    `  (same as pts·(p − p₀) = ${c.pts}×(${fmt(c.pB, 2)} − ${fmt(c.pA, 2)}) = ${fmt(c.pts * (c.pB - c.pA), 4)})`);
  setText("toy-dvar-direct", `${fmt(c.B.v, 4)} − ${fmt(c.A.v, 4)} = ${fmt(c.B.v - c.A.v, 4)}`);
  setText("toy-dvar-formula",
    `(${fmt(c.pB, 2)} − ${fmt(c.pA, 2)})×(1 + 2×${fmt(c.S, 3)}) − ${fmt(c.pB, 2)}² + ${fmt(c.pA, 2)}²` +
    ` − 2×(${fmt(c.pB, 2)}×${fmt(c.fB, 2)} − ${fmt(c.pA, 2)}×${fmt(c.fA, 2)})` +
    ` = ${fmt(c.bracket, 4)};  × pts² = ${fmt(c.dVar, 4)}`);
  setText("toy-match", Math.abs((c.B.v - c.A.v) - c.dVar) < 1e-9
    ? "The two routes agree exactly." : "MISMATCH — this should never happen.");

  setText("toy-ratio-sub", `${fmt(c.dVar, 4)} / ${fmt(c.dEV, 4)} = ${fmt(c.ratio, 2)}`);
  const verdict = document.getElementById("toy-verdict");
  const isValue = c.ratio <= -1;
  verdict.className = "verdict " + (isValue ? "yes" : "no");
  verdict.innerHTML = (isValue
    ? `★ Value pick. <span class="why">ratio = ${fmt(c.ratio, 2)} ≤ −1: ` +
      `picking the underdog buys ${fmt(c.dVar, 3)} points² of variance for ` +
      `${fmt(-c.dEV, 3)} points of expected score — variance at a fair price or better.</span>`
    : `Not a Value pick. <span class="why">ratio = ${fmt(c.ratio, 2)} &gt; −1: ` +
      `the underdog costs ${fmt(-c.dEV, 3)} expected points but only adds ` +
      `${fmt(c.dVar, 3)} points² of variance — the variance is too expensive here.</span>`);
  renderToyChart(c);
}

function initToy() {
  [["toy-in-pA", "pA", v => v / 100], ["toy-in-fA", "fA", v => v / 100],
   ["toy-in-pts", "pts", v => v]].forEach(([id, key, cv]) => {
    const el = document.getElementById(id);
    el.addEventListener("input", () => { toy[key] = cv(+el.value); renderToy(); });
  });
}

/* --------------------------- real-board explorer ------------------------ */

function teamLabel(i) {
  const t = MODEL.teams[i];
  return `${t.seed} ${t.longName}${t.note ? " *" : ""}`;
}

function initExplorer() {
  const sel = document.getElementById("ex-team");
  ["East", "West", "South", "Midwest"].forEach(rg => {
    const og = document.createElement("optgroup");
    og.label = rg;
    MODEL.teams.forEach((t, i) => {
      if (t.region !== rg) return;
      const o = document.createElement("option");
      o.value = i; o.textContent = teamLabel(i);
      og.appendChild(o);
    });
    sel.appendChild(og);
  });
  sel.value = state.team;
  sel.addEventListener("change", () => { state.team = +sel.value; renderExplorer(); renderFrontier(); });

  const rsel = document.getElementById("ex-round");
  RLABEL.forEach((r, k) => {
    const o = document.createElement("option");
    o.value = k; o.textContent = `${ROUNDS[k]} — ${r} (${POINTS[k]} pts)`;
    rsel.appendChild(o);
  });
  rsel.value = state.round;
  rsel.addEventListener("change", () => { state.round = +rsel.value; renderExplorer(); });

  document.querySelectorAll("#ex-mode button").forEach(b =>
    b.addEventListener("click", () => {
      state.mode = b.dataset.mode;
      document.querySelectorAll("#ex-mode button").forEach(x =>
        x.classList.toggle("active", x.dataset.mode === state.mode));
      renderExplorer(); renderFrontier();
    }));
}

function renderExplorer() {
  const i = state.team, k = state.round, s = SLOTS[state.mode][i], t = MODEL.teams[i];
  document.getElementById("ex-team").value = i;
  document.getElementById("ex-round").value = k;

  // six-round overview table
  const body = document.getElementById("ex-rounds");
  body.innerHTML = ROUNDS.map((r, kk) =>
    `<tr class="clickable${kk === k ? " sel" : ""}" data-k="${kk}">` +
    `<td>${RLABEL[kk]}</td><td>${POINTS[kk]}</td>` +
    `<td>${fmt(t.prob[kk])}</td><td>${fmt(t.freq[kk])}</td>` +
    `<td>${fmt(s.p0[kk])}</td><td>${fmt(s.S[kk], 4)}</td>` +
    `<td>${fmt(s.expDiff[kk], 3)}</td><td>${fmt(s.varDiff[kk], 3)}</td>` +
    `<td>${fmt(s.cumExp[kk], 3)}</td><td>${fmt(s.cumVar[kk], 3)}</td>` +
    `<td>${fmt(s.ratio[kk], 2)}</td>` +
    `<td>${s.value[kk] ? '<span class="star">★</span>' : ""}</td></tr>`).join("");
  body.querySelectorAll("tr").forEach(tr => tr.addEventListener("click", () => {
    state.round = +tr.dataset.k; renderExplorer();
  }));

  renderTrace(i, k);
}

function renderTrace(i, k) {
  const mode = state.mode, s = SLOTS[mode][i], t = MODEL.teams[i];
  const [g, e] = groupRange(i, k);
  const favs = favoritesOf(i, k);
  const p = t.prob[k], f = t.freq[k], p0 = s.p0[k], p0f0 = s.p0f0[k], S = s.S[k];
  const f0 = p0f0 / p0;
  const pts = POINTS[k];
  const host = document.getElementById("ex-trace");
  const favNames = favs.map(j => esc(MODEL.teams[j].longName)).join(", ");
  const isFav = favs.includes(i);

  let h = `<p class="note" style="margin:8px 0 2px">Step-by-step trace — ` +
    `<b>${esc(t.longName)}</b> (${t.seed} seed, ${esc(t.region)}), ` +
    `<b>${RLABEL[k]}</b> slot, <b>${mode === "fixed" ? "fixed" : "as-published"}</b> formulas. ` +
    `Numbers are rounded for display; the maths uses full precision.</p>`;

  // Step A -- the group
  let rows = "";
  for (let j = g; j < e; j++) {
    const tj = MODEL.teams[j];
    const cls = j === i ? "hl-you" : (favs.includes(j) ? "hl-fav" : "");
    rows += `<tr class="${cls}"><td>${esc(tj.longName)}` +
      `${j === i ? " ← your pick" : ""}${favs.includes(j) ? " (favorite)" : ""}</td>` +
      `<td>${tj.seed}</td><td>${fmt(tj.prob[k])}</td><td>${fmt(tj.freq[k])}</td>` +
      `<td>${fmt(tj.prob[k] * tj.freq[k], 4)}</td></tr>`;
  }
  h += `<div class="tracestep"><h4>A &middot; The slot and its group</h4>
    <p class="note" style="margin:0 0 6px">The ${RLABEL[k]} slot containing
    ${esc(t.name)} is contested by the ${e - g} teams below — exactly one of
    them wins it and scores its backers ${pts} points. Summing p·f down the
    group gives S; the highest p is the favorite, p₀.</p>
    <div class="scrolly"><table class="num-table" style="width:100%">
    <tr><th>Team</th><th>Seed</th><th>p (win this slot)</th><th>f (pool picked)</th><th>p·f</th></tr>
    ${rows}
    <tr class="sumrow"><td colspan="4">S = Σ p·f (expected slot points-rate of a random entry)</td>
    <td>${fmt(S, 4)}</td></tr></table></div>
    <div class="formula">p  = ${fmt(p)}   f  = ${fmt(f)}     (your pick: ${esc(t.name)})
p₀ = ${fmt(p0)}   f₀ = ${fmt(f0)}     (favorite: ${favNames}${favs.length > 1 ? " — tied, f₀ averaged" : ""})
S  = ${fmt(S, 4)}        p₀·f₀ = ${fmt(p0f0, 4)}</div></div>`;

  // Step B -- dEV
  h += `<div class="tracestep"><h4>B &middot; Expected-points difference (ΔEV)</h4>
    <div class="formula">ΔEV = pts · (p − p₀) = ${pts} × (${fmt(p)} − ${fmt(p0)}) = <b>${fmt(s.expDiff[k], 4)}</b></div>
    <p class="note" style="margin:4px 0 0">${isFav
      ? "Zero: this team <i>is</i> the favorite, so picking it costs nothing."
      : "Negative: swapping the favorite for " + esc(t.name) +
        " gives up expected score. The question is what that sacrifice buys."}</p></div>`;

  // Step C -- dVar
  const sUsed = s.sUsed[k];
  let bugNote = "";
  if (mode === "published") {
    const j = i + BUG_OFFSET;
    bugNote = `<p class="callout" style="margin:6px 0 0"><b>Bug 1 in action:</b> the workbook
      does not use this slot's S here. Cell AL${i + 3} reads <code>B${i + 3 + BUG_OFFSET}</code>
      — 38 rows below its own row — so it borrows ` +
      (j < N ? `<b>${esc(MODEL.teams[j].longName)}</b>&rsquo;s S for this round: ${fmt(sUsed, 4)}.`
             : `an <b>empty cell</b> past the last team, which Excel treats as <b>0</b>.`) +
      ` The correct same-row S is ${fmt(S, 4)}.</p>`;
  }
  const term1 = (p - p0) * (1 + 2 * sUsed);
  const term2 = -p * p + p0 * p0;
  const term3 = -2 * (p * f - p0f0);
  const bracket = term1 + term2 + term3;
  h += `<div class="tracestep"><h4>C &middot; Variance difference (ΔVar)</h4>
    <div class="formula">bracket = (p − p₀)(1 + 2S) − p² + p₀² − 2(p·f − p₀·f₀)

  (p − p₀)(1 + 2S)  = (${fmt(p)} − ${fmt(p0)}) × (1 + 2×${fmt(sUsed, 4)}) = ${fmt(term1, 4)}
  − p² + p₀²        = −${fmt(p * p, 4)} + ${fmt(p0 * p0, 4)} = ${fmt(term2, 4)}
  − 2(p·f − p₀·f₀)  = −2 × (${fmt(p * f, 4)} − ${fmt(p0f0, 4)}) = ${fmt(term3, 4)}

bracket = ${fmt(bracket, 4)}
ΔVar = pts² × bracket = ${pts}² × ${fmt(bracket, 4)} = <b>${fmt(s.varDiff[k], 4)}</b></div>` + bugNote;
  // cross-check against the per-team variance column
  const varYou = s.variance[k], varFav = p0 * (1 - p0 - 2 * f0 + 2 * S) + S - S * S;
  const trueBracket = varYou - varFav;
  if (mode === "fixed") {
    h += `<p class="note" style="margin:6px 0 0">Cross-check: the workbook also computes each
      team's own swing variance (columns AF:AK). Var(${esc(t.name)}) = ${fmt(varYou, 4)},
      Var(favorite) = ${fmt(varFav, 4)}; difference = ${fmt(trueBracket, 4)} —
      identical to the bracket above, as the algebra says it must be.</p>`;
  } else {
    h += `<p class="note" style="margin:6px 0 0">Cross-check against columns AF:AK (which use
      the correct same-row S): Var(${esc(t.name)}) − Var(favorite) = ${fmt(trueBracket, 4)},
      but the published bracket above says ${fmt(bracket, 4)}` +
      (Math.abs(trueBracket - bracket) < 1e-12 ? " — they happen to agree here."
        : " — they disagree: that gap is bug 1.") + `</p>`;
  }
  h += `</div>`;

  // Step D -- cumulate
  let cumRows = "";
  for (let kk = 0; kk <= k; kk++)
    cumRows += `<tr><td>${RLABEL[kk]}</td><td>${fmt(s.expDiff[kk], 4)}</td><td>${fmt(s.varDiff[kk], 4)}</td></tr>`;
  cumRows += `<tr class="sumrow"><td>cumulative through ${RLABEL[k]}</td>` +
    `<td>${fmt(s.cumExp[k], 4)}</td><td>${fmt(s.cumVar[k], 4)}</td></tr>`;
  h += `<div class="tracestep"><h4>D &middot; Accumulate rounds 1…${k + 1}</h4>
    <p class="note" style="margin:0 0 6px">Picking ${esc(t.name)} for the ${RLABEL[k]} means
    riding it through every earlier round too, so the round-by-round differences are summed.</p>
    <div class="scrollx"><table class="num-table">
    <tr><th>Round</th><th>ΔEV</th><th>ΔVar</th></tr>${cumRows}</table></div></div>`;

  // Step E -- ratio and verdict
  const ratio = s.ratio[k], val = s.value[k];
  const ratioLine = s.cumExp[k] === 0
    ? `cum ΔEV = 0 (favorite all the way) → ratio is defined as <b>0</b>`
    : `ratio = cum ΔVar / cum ΔEV = ${fmt(s.cumVar[k], 4)} / ${fmt(s.cumExp[k], 4)} = <b>${fmt(ratio, 2)}</b>`;
  const rule = mode === "fixed"
    ? "Value ★ ⇔ ratio = 0 (favorite) or ratio ≤ −1"
    : "published rule: Value ★ ⇔ ratio = 0 or ratio &gt; 1";
  let why;
  if (s.cumExp[k] === 0) why = "Favorite picks get the star automatically — swapping the favorite for itself costs nothing.";
  else if (mode === "fixed") why = val
    ? `cum ΔVar (${fmt(s.cumVar[k], 2)}) ≥ |cum ΔEV| (${fmt(-s.cumExp[k], 2)}): the variance gained at least pays for the expected points given up.`
    : `cum ΔVar (${fmt(s.cumVar[k], 2)}) &lt; |cum ΔEV| (${fmt(-s.cumExp[k], 2)}): not enough variance for the points sacrificed.`;
  else why = val
    ? `ratio &gt; 1 with cum ΔEV negative means cum ΔVar is <i>more negative still</i> — the published test rewards losing variance, which is bug 2.`
    : `the published test wanted ratio &gt; 1; a genuine variance-for-EV trade sits at ratio ≤ −1 and fails it.`;
  h += `<div class="tracestep"><h4>E &middot; The ratio test</h4>
    <div class="formula">${ratioLine}
${rule}</div>
    <div class="verdict ${val ? "yes" : "no"}">${val ? "★ Value pick." : "No Value star."}
    <span class="why">${why}</span></div></div>`;

  host.innerHTML = h;
}

/* ----------------------------- value frontier --------------------------- */

function niceTicks(lo, hi, n = 6) {
  const span = hi - lo || 1, raw = span / n, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map(m => m * mag).find(s => span / s <= n) || 10 * mag;
  const t0 = Math.ceil(lo / step) * step, out = [];
  for (let v = t0; v <= hi + 1e-9; v += step) out.push(Math.abs(v) < 1e-9 ? 0 : v);
  return out;
}

function initFrontier() {
  const rsel = document.getElementById("fr-round");
  RLABEL.forEach((r, k) => {
    const o = document.createElement("option");
    o.value = k; o.textContent = `through ${ROUNDS[k]} — ${r}`;
    rsel.appendChild(o);
  });
  rsel.value = state.frontierRound;
  rsel.addEventListener("change", () => { state.frontierRound = +rsel.value; renderFrontier(); });
}

function renderFrontier() {
  const k = state.frontierRound, mode = state.mode, slots = SLOTS[mode];
  const pts = MODEL.teams.map((t, i) => ({
    i, name: t.longName, seed: t.seed, region: t.region,
    x: slots[i].cumExp[k], y: slots[i].cumVar[k],
    r: slots[i].ratio[k], v: slots[i].value[k],
  }));
  setText("fr-mode-note", mode === "fixed"
    ? "Fixed formulas: the boundary is cum ΔVar = −cum ΔEV (ratio = −1); Value picks sit on or above it, favorites at the origin."
    : "As published: the (buggy) test is ratio > 1, i.e. cum ΔVar below cum ΔEV — the flagged region rewards losing variance.");

  const W = 720, H = 430, m = { t: 18, r: 18, b: 46, l: 62 };
  const pw = W - m.l - m.r, ph = H - m.t - m.b;
  let xmin = Math.min(...pts.map(p => p.x), 0), xmax = Math.max(...pts.map(p => p.x), 0);
  let ymin = Math.min(...pts.map(p => p.y), 0), ymax = Math.max(...pts.map(p => p.y), 0);
  const xpad = (xmax - xmin || 1) * 0.05, ypad = (ymax - ymin || 1) * 0.07;
  xmin -= xpad; xmax += xpad; ymin -= ypad; ymax += ypad;
  const X = v => m.l + pw * (v - xmin) / (xmax - xmin);
  const Y = v => m.t + ph * (1 - (v - ymin) / (ymax - ymin));

  let s = "";
  niceTicks(xmin, xmax).forEach(v => {
    s += `<line x1="${X(v)}" y1="${m.t}" x2="${X(v)}" y2="${m.t + ph}" stroke="var(--border)" stroke-width="1"/>` +
      `<text x="${X(v)}" y="${m.t + ph + 16}" text-anchor="middle" font-size="11" fill="var(--muted)">${fmt(v, 0)}</text>`;
  });
  niceTicks(ymin, ymax).forEach(v => {
    s += `<line x1="${m.l}" y1="${Y(v)}" x2="${m.l + pw}" y2="${Y(v)}" stroke="var(--border)" stroke-width="1"/>` +
      `<text x="${m.l - 7}" y="${Y(v) + 4}" text-anchor="end" font-size="11" fill="var(--muted)">${fmt(v, 0)}</text>`;
  });
  // zero anchors
  if (xmin < 0 && xmax > 0) s += `<line x1="${X(0)}" y1="${m.t}" x2="${X(0)}" y2="${m.t + ph}" stroke="#b9c4cf" stroke-width="1"/>`;
  if (ymin < 0 && ymax > 0) s += `<line x1="${m.l}" y1="${Y(0)}" x2="${m.l + pw}" y2="${Y(0)}" stroke="#b9c4cf" stroke-width="1"/>`;

  // boundary line: fixed y=-x, published y=+x (for x<=0)
  const sign = mode === "fixed" ? -1 : 1;
  const cand = [];
  [[xmin, sign * xmin], [xmax, sign * xmax],
   [sign * ymin, ymin], [sign * ymax, ymax]].forEach(([bx, by]) => {
    if (bx >= xmin - 1e-9 && bx <= xmax + 1e-9 && by >= ymin - 1e-9 && by <= ymax + 1e-9)
      cand.push([bx, by]);
  });
  cand.sort((a, b) => a[0] - b[0]);
  if (cand.length >= 2) {
    const [a, b] = [cand[0], cand[cand.length - 1]];
    s += `<line x1="${X(a[0])}" y1="${Y(a[1])}" x2="${X(b[0])}" y2="${Y(b[1])}"
      stroke="var(--accent)" stroke-width="1.5"/>`;
    const lx = X(a[0]) + 8, ly = Y(a[1]) + (mode === "fixed" ? 14 : -8);
    s += `<text x="${lx}" y="${ly}" font-size="11" fill="var(--accent)">ratio = ${mode === "fixed" ? "−1" : "+1"} boundary</text>`;
  }

  const order = pts.filter(p => !p.v).concat(pts.filter(p => p.v));
  order.forEach(p => {
    const selRing = p.i === state.team
      ? `<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="9" fill="none" stroke="var(--gold)" stroke-width="2"/>` : "";
    s += selRing + `<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="5"
      fill="${p.v ? "var(--s1)" : "var(--dim)"}" stroke="#fff" stroke-width="2"/>`;
  });
  const selP = pts[state.team];
  s += `<text x="${Math.max(m.l + 30, Math.min(X(selP.x), W - m.r - 30))}"
    y="${Math.max(Y(selP.y) - 14, m.t + 10)}" text-anchor="middle"
    font-size="11.5" fill="var(--ink)" font-weight="600">${esc(selP.name)}</text>`;
  s += `<text x="${m.l + pw / 2}" y="${H - 6}" text-anchor="middle" font-size="11.5" fill="var(--muted)">
    cumulative ΔEV through the ${RLABEL[k]} (points; 0 = favorite everywhere)</text>`;
  s += `<text x="${m.l - 46}" y="${m.t + ph / 2}" font-size="11.5" fill="var(--muted)"
    transform="rotate(-90 ${m.l - 46} ${m.t + ph / 2})" text-anchor="middle">cumulative ΔVar (points²)</text>`;

  const host = document.getElementById("fr-chart");
  host.querySelectorAll("svg").forEach(e => e.remove());
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.innerHTML = s;
  host.appendChild(svg);

  const tt = host._tt || (host._tt = makeTooltip(host));
  function nearest(ev) {
    const box = svg.getBoundingClientRect(), sc = W / box.width;
    const mx = (ev.clientX - box.left) * sc, my = (ev.clientY - box.top) * sc;
    let best = null, bd = 24 * sc;
    pts.forEach(p => {
      const d = Math.hypot(X(p.x) - mx, Y(p.y) - my);
      if (d < bd) { bd = d; best = p; }
    });
    return best;
  }
  svg.addEventListener("pointermove", ev => {
    const p = nearest(ev);
    if (!p) { tt.hide(); return; }
    const b = host.getBoundingClientRect();
    tt.show(ev.clientX - b.left, ev.clientY - b.top, [
      [`${p.seed} ${p.name} (${p.region})`, "", true],
      ["cum ΔEV", fmt(p.x, 2)], ["cum ΔVar", fmt(p.y, 2)],
      ["ratio", fmt(p.r, 2)],
      [p.v ? "★ Value pick" : "no Value star", "", false],
    ]);
  });
  svg.addEventListener("pointerleave", () => tt.hide());
  svg.addEventListener("click", ev => {
    const p = nearest(ev);
    if (p) { state.team = p.i; renderExplorer(); renderFrontier(); }
  });

  // table twin
  const tw = document.getElementById("fr-table");
  tw.innerHTML = pts.map(p =>
    `<tr><td>${esc(p.name)}</td><td>${p.seed}</td><td>${esc(p.region)}</td>` +
    `<td>${fmt(p.x, 2)}</td><td>${fmt(p.y, 2)}</td><td>${fmt(p.r, 2)}</td>` +
    `<td>${p.v ? '<span class="star">★</span>' : ""}</td></tr>`).join("");
}

/* -------------------------------- boot ---------------------------------- */

initToy(); renderToy();
initExplorer(); initFrontier();
renderExplorer(); renderFrontier();
"""

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>How the Value factor works — March Madness factor model</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">

<header>
<h1>How the Value factor works</h1>
<p class="sub">A from-first-principles tutorial on the Value pick in Aaron
Brown&rsquo;s <em>&ldquo;Quants go mad in March&rdquo;</em> bracket model
&mdash; every step of the calculation, a toy example you can check by hand,
and a live trace of any 2019 team. Companion to the
<a href="index.html">main model page</a>; sources:
<a href="reference/Quants_Mad_March.pdf">the paper</a>,
<a href="README.md">README</a>.</p>
<nav class="toc">
<a href="#idea">The idea</a>
<a href="#why-variance">Why variance</a>
<a href="#pieces">The pieces</a>
<a href="#step1">Step 1: swing</a>
<a href="#step2">Step 2: &Delta;EV</a>
<a href="#step3">Step 3: &Delta;Var</a>
<a href="#step4">Step 4: the ratio</a>
<a href="#toy">Toy example</a>
<a href="#real">Real 2019 explorer</a>
<a href="#frontier">Value frontier</a>
<a href="#fine-print">Fine print</a>
</nav>
</header>

<div class="card" id="idea">
<h2>The idea in one paragraph</h2>
<p>A bracket pool pays the <em>winner</em>, not the average scorer &mdash; so
the right question is never &ldquo;which picks score the most points on
average?&rdquo; but &ldquo;which picks give me the best chance of finishing
first?&rdquo;. Those are different questions, and <b>variance</b> is the
difference between them. The Value factor awards a star to a pick that
<b>increases the variance of your score against the pool by at least as much
as it costs in expected points</b> &mdash; variance bought at a fair price or
better. The slot favorite gets the star automatically (it costs nothing to
pick). It is the bracket version of the value factor in Fama&ndash;French
investing: don&rsquo;t pay for what&rsquo;s popular, buy what&rsquo;s cheap
per unit of what you actually need &mdash; and what you need in a pool is
variance.</p>
</div>

<div class="card" id="why-variance">
<h2>Why variance wins pools</h2>
<p>Suppose you copy the crowd&rsquo;s favorite in every slot. Your score then
moves almost in lock-step with the pool average: when your teams win,
everyone&rsquo;s teams win. You&rsquo;ll finish mid-pack nearly every year
&mdash; a high expected score, but almost no chance of being <em>first</em>
in a pool of 100, because dozens of near-identical brackets sit ahead of you
on any tiebreak of luck.</p>
<p>To finish first you must be <em>different</em> from the field where being
different is cheap, so that some plausible run of results catapults you past
the crowd. Every deviation from the favorites costs expected points &mdash;
the favorite is, by definition, the most likely winner &mdash; but the right
deviations buy a lot of spread between you and the field for very little
expected cost. The Value factor is exactly that price check, run slot by
slot: <em>how many points of expected score am I paying, and how much
score-variance against the pool am I getting?</em></p>
<p class="note">The same model uses this machinery a second time: the main
page&rsquo;s pool win-probability block treats your score minus the
field&rsquo;s as a Gaussian and integrates it against the best of the other
entries. More variance widens that Gaussian &mdash; and when you need to beat
99 other brackets, the right tail is where wins come from.</p>
</div>

<div class="card" id="pieces">
<h2>The pieces the formula is built from</h2>
<p>The tournament is scored in six rounds with points
<b>2, 3, 5, 8, 13, 21</b> per correct pick (editable on the main page; fixed
here for clarity). For round <i>k</i>, the 64 teams split into
<b>groups of 2<sup>k+1</sup></b>: pairs for the Round of 64, fours for the
Round of 32, eights for the Sweet&nbsp;16 &hellip; all 64 for the Champion
slot. <b>Exactly one team from each group wins that slot</b> and scores its
backers the round&rsquo;s points. Everything below is computed
<em>per slot</em>, always relative to that group of teams.</p>
<div class="defs">
<div class="d"><b>p</b> &mdash; win probability<p>The chance your pick wins
this slot (reaches the round and wins it). Workbook tab
&ldquo;Brackets&nbsp;- prob&rdquo;.</p></div>
<div class="d"><b>f</b> &mdash; pick frequency<p>The share of pool entries
that picked this team for this slot (ESPN &ldquo;Who Picked Whom&rdquo;
data). Tab &ldquo;Brackets&nbsp;- freq&rdquo;.</p></div>
<div class="d"><b>p&#8320;, f&#8320;</b> &mdash; the favorite<p>p&#8320; is
the highest win probability in the group; f&#8320; is that team&rsquo;s pick
frequency (averaged if several teams tie for the top probability).</p></div>
<div class="d"><b>S = &Sigma; p&#8321;f&#8321;</b> &mdash; the field&rsquo;s
slot rate<p>Sum of p&middot;f over the whole group: the probability that a
randomly drawn pool entry scores this slot. Column B of the
&ldquo;Slot calculations&rdquo; tab &mdash; the cell the fill-down bug
mis-references.</p></div>
</div>
<p class="note" style="margin-top:8px">The opponent model throughout: a
random pool entry picks team <i>j</i> in this slot with probability
f<sub>j</sub>. That single random opponent stands in for the whole field,
slot by slot.</p>
</div>

<div class="card" id="step1">
<h2><span class="stepbadge">Step 1</span>Your score swing against a random
opponent</h2>
<p>Fix one slot and compare yourself with one random opponent. Let
X<sub>j</sub> be 1 if team <i>j</i> wins the slot (0 otherwise). You picked
team <i>i</i>; the opponent picked team <i>J</i>, drawn with the pick
frequencies. Your <b>swing</b> on this slot is the score difference</p>
<div class="formula">Y = X<sub>i</sub> − X<sub>J</sub>   ∈  {{−1, 0, +1}}   (in units of the round&rsquo;s points)</div>
<p>Y can only be +1 (your team won, theirs didn&rsquo;t), −1 (theirs
won, yours didn&rsquo;t) or 0 (same pick, or both wrong). Its moments come
straight from enumerating who-wins &times; who-they-picked:</p>
<div class="formula">E[Y]  = p − S
P(Y = +1) = p·(1 − f)          you win, opponent is on someone else
P(Y = −1) = S − p·f            a team the opponent backs wins, and it isn&rsquo;t yours
E[Y²] = P(+1) + P(−1) = p − 2pf + S

Var(Y) = E[Y²] − E[Y]²
       = p − 2pf + S − (p − S)²
       = <b>p(1 − p − 2f + 2S) + S − S²</b></div>
<p class="note">That last line is exactly the workbook&rsquo;s
&ldquo;Variance&rdquo; columns (AF:AK of the Slot calculations tab), one cell
per team per round &mdash; and the quantity the whole Value factor is built
on. Note what pushes it up: a high win probability <i>p</i> paired with a
<em>low</em> pick frequency <i>f</i> (the &minus;2pf term). Being right where
the crowd isn&rsquo;t is what creates spread.</p>
</div>

<div class="card" id="step2">
<h2><span class="stepbadge">Step 2</span>What a non-favorite pick costs:
&Delta;EV</h2>
<p>The baseline pick for any slot is the favorite (probability p&#8320;).
Swapping it for team <i>i</i> changes your expected slot score by</p>
<div class="formula">ΔEV = pts · (p − p₀)      ≤ 0 for every non-favorite</div>
<p>The opponent&rsquo;s side (the &minus;S in E[Y]) is the same whichever
team you pick, so it cancels: the expected cost of a deviation is just the
probability gap times the round&rsquo;s points. This is the workbook&rsquo;s
&ldquo;Expected points difference&rdquo; (columns T:Y), and the sheet stores
it as this <em>negative</em> number &mdash; remember that sign, it decides
the direction of the final inequality.</p>
</div>

<div class="card" id="step3">
<h2><span class="stepbadge">Step 3</span>What the pick buys: &Delta;Var</h2>
<p>Now do the same swap for the variance. Both picks face the same slot, so S
is the same in both expressions and most terms cancel:</p>
<div class="formula">ΔVar/pts² = Var(pick i) − Var(pick favorite)
        = [p − p² − 2pf + 2pS] − [p₀ − p₀² − 2p₀f₀ + 2p₀S]     (S − S² cancels)
        = (p − p₀) − (p² − p₀²) − 2(pf − p₀f₀) + 2S(p − p₀)
        = <b>(p − p₀)(1 + 2S) − p² + p₀² − 2(pf − p₀f₀)</b>

ΔVar = pts² × that bracket        (variance scales with the square of the stakes)</div>
<p>This is the paper&rsquo;s formula and the workbook&rsquo;s
&ldquo;Variance difference&rdquo; columns (AL:AQ). Read the three parts:
the <b>(p&nbsp;&minus;&nbsp;p&#8320;)(1&nbsp;+&nbsp;2S)</b> term is the raw
probability gap amplified by how much the field already scores in this slot;
<b>&minus;p&sup2;&nbsp;+&nbsp;p&#8320;&sup2;</b> trims each side&rsquo;s
self-variance; and <b>&minus;2(pf&nbsp;&minus;&nbsp;p&#8320;f&#8320;)</b> is
the crowding term &mdash; the favorite is usually heavily picked
(p&#8320;f&#8320; large), so stepping away from it <em>adds</em> variance,
while picking an over-backed dark horse subtracts it.</p>
<p class="callout"><b>Where the bug lives:</b> S enters this formula once,
through the cross-term &mdash; and it must be <em>this slot&rsquo;s</em> S,
the value already sitting in column B of the same row. The published workbook
reads it 38 rows down (<code>AL3</code> says <code>B41</code>), so from
row&nbsp;29 onward the reference walks off the data and Excel silently uses
S&nbsp;=&nbsp;0. The explorer below can replay that.</p>
</div>

<div class="card" id="step4">
<h2><span class="stepbadge">Step 4</span>Accumulate the rounds, then take the
ratio</h2>
<p>Picking a team to win round <i>k</i> implies picking it in every earlier
round too, so the workbook sums the round-by-round differences down the
team&rsquo;s path &mdash; cumulative &Delta;EV (columns Z:AE) and cumulative
&Delta;Var (AR:AW) &mdash; and prices one against the other:</p>
<div class="formula">ratio = cum ΔVar / cum ΔEV          (columns AX:BC)

Value ★  ⇔  favorite (cum ΔEV = 0, ratio defined as 0)   or   ratio ≤ −1</div>
<p>Why <b>&le; &minus;1</b>? The rule is &ldquo;variance gained &ge; expected
points lost&rdquo;, i.e. cum&nbsp;&Delta;Var &ge; &minus;cum&nbsp;&Delta;EV.
Divide both sides by cum&nbsp;&Delta;EV &mdash; a <em>negative</em> number
for any non-favorite &mdash; and the inequality flips:
cum&nbsp;&Delta;Var&nbsp;/&nbsp;cum&nbsp;&Delta;EV &le; &minus;1. One point
of expected score must buy at least one point&sup2; of variance; the
threshold is an exchange rate, set to 1 on this points scale.</p>
<p>The published workbook tests <code>ratio &gt; 1</code> instead
(bug&nbsp;2). With a negative denominator, ratio&nbsp;&gt;&nbsp;1 means the
variance change is <em>more negative than the EV change</em> &mdash; the flag
fired for picks that lose variance faster than they lose expected points,
the exact opposite of the paper&rsquo;s stated rule.</p>
</div>

<div class="card" id="toy">
<h2>A toy pool you can check by hand</h2>
<p>One first-round game, worth <b>1 point</b>. The favorite wins with
probability <b>0.70</b>, and the crowd is heavily on it: <b>80%</b> of
entries picked the favorite, 20% the underdog. So for the underdog:
p&nbsp;=&nbsp;0.30, f&nbsp;=&nbsp;0.20, p&#8320;&nbsp;=&nbsp;0.70,
f&#8320;&nbsp;=&nbsp;0.80. Drag the sliders and every number on this card
recomputes.</p>
<div class="controls">
<label>Favorite win probability p&#8320; <span class="val" id="toy-pA"></span>
<input type="range" id="toy-in-pA" min="55" max="95" step="1" value="70"></label>
<label>Share of pool on the favorite f&#8320; <span class="val" id="toy-fA"></span>
<input type="range" id="toy-in-fA" min="5" max="95" step="1" value="80"></label>
<label>Points for this round <span class="val" id="toy-pts"></span>
<input type="range" id="toy-in-pts" min="1" max="21" step="1" value="1"></label>
</div>
<p class="note">Underdog: p = <span id="toy-pB"></span>, f = <span id="toy-fB"></span>
(probabilities and pool shares must each sum to 1 in a 2-team slot).</p>

<h3>Enumerate every case</h3>
<p>Two things are random: who wins the game, and which team your (one,
random) opponent picked. Four combinations cover everything:</p>
<div class="scrollx"><table class="num-table">
<thead><tr><th>Outcome</th><th>probability</th>
<th>your swing if you picked the favorite</th>
<th>your swing if you picked the underdog</th></tr></thead>
<tbody id="toy-enum"></tbody></table></div>
<p class="note">First the field constant:
S = p&#8320;&middot;f&#8320; + p&middot;f =
<span id="toy-S-sub"></span>.</p>

<h3>Moments, both ways</h3>
<div class="scrollx"><table class="num-table">
<thead><tr><th></th><th>you picked the favorite</th><th>you picked the underdog</th></tr></thead>
<tbody id="toy-moments"></tbody></table></div>
<p>Picking the underdog concentrates probability on the <em>extreme</em>
swings (see the chart below): you leap past every favorite-backer when the
underdog wins, and trail them all when it doesn&rsquo;t. Same game, far more
spread.</p>

<h3>&Delta;EV and &Delta;Var, two routes to the same number</h3>
<div class="formula">ΔEV  (underdog − favorite) = <span id="toy-dev-sub"></span>

ΔVar by direct enumeration   = <span id="toy-dvar-direct"></span>
ΔVar by the Step-3 formula:
  bracket = <span id="toy-dvar-formula"></span></div>
<p class="note" id="toy-match"></p>
<div class="formula">ratio = ΔVar / ΔEV = <span id="toy-ratio-sub"></span></div>
<div id="toy-verdict"></div>

<h3>The distribution picture</h3>
<div class="legend">
<span><span class="sw" style="background:var(--s1)"></span>You pick the favorite</span>
<span><span class="sw" style="background:var(--s2)"></span>You pick the underdog</span>
</div>
<div class="chart-wrap" id="toy-chart"></div>
<p class="note">Probability of each score swing against one random opponent.
The favorite pick huddles at 0 (you and the crowd rise and fall together);
the underdog pick moves the mass to the tails &mdash; that <em>is</em> the
variance you&rsquo;re buying. Try dragging the crowd share f&#8320; down and
watch the underdog&rsquo;s star vanish: a dark horse the crowd has already
piled onto separates you from nobody, so it&rsquo;s variance at a bad
price.</p>
</div>

<div class="card" id="real">
<h2>Now the real 2019 board &mdash; trace any team, any round</h2>
<p>Everything below is computed live from the workbook&rsquo;s data with the
exact slot mathematics verified against it cell-by-cell (see the
<a href="index.html">main page</a>). Pick a team and a round, and follow the
five steps; the <b>As published</b> toggle replays both bugs.</p>
<div class="controls">
<label>Team<select id="ex-team"></select></label>
<label>Round<select id="ex-round"></select></label>
<label>Formulas<span class="mode-toggle" id="ex-mode">
<button data-mode="fixed" class="active">Fixed</button>
<button data-mode="published">As published</button></span></label>
</div>

<div class="scrollx"><table class="num-table" style="width:100%">
<thead><tr><th>Round</th><th>pts</th><th>p</th><th>f</th><th>p&#8320;</th>
<th>S</th><th>&Delta;EV</th><th>&Delta;Var</th><th>cum &Delta;EV</th>
<th>cum &Delta;Var</th><th>ratio</th><th>Value</th></tr></thead>
<tbody id="ex-rounds"></tbody></table></div>
<p class="note">Click a row to trace that round below.</p>
<div id="ex-trace"></div>

<h3>Two stories worth tracing</h3>
<p><b>Texas Tech, Sweet&nbsp;16</b> (the default above). Michigan is the
slot favorite (p&#8320;&nbsp;=&nbsp;0.411 vs Texas&nbsp;Tech&rsquo;s 0.340)
and the crowd knows it (57% picked Michigan through, 23% Texas&nbsp;Tech).
The swap costs only 0.355 expected points but buys 6.19 points&sup2; of
variance &mdash; ratio &minus;17.4, a bargain. Ridden all the way to the
Champion slot the ratio is still &minus;2.50, so the fixed model stars
Texas&nbsp;Tech in every round &mdash; the only 5-star champion pick on the
2019 board. Texas&nbsp;Tech reached the final. The published workbook,
S-bug and sign-bug included, drops the star from the Sweet&nbsp;16 onward:
flip the toggle and watch steps C and E change.</p>
<p><b>Virginia, Champion</b>. Duke is the overall favorite
(p&#8320;&nbsp;=&nbsp;0.184 vs Virginia&rsquo;s 0.165) and a colossal 42% of
the pool rode Duke to the title against Virginia&rsquo;s 6.7%. Give up 0.41
expected points, collect 51.4 points&sup2; of variance: ratio &minus;127.
Virginia won the 2019 tournament.</p>
</div>

<div class="card" id="frontier">
<h2>The value frontier &mdash; all 64 teams at once</h2>
<p>Each dot is a team&rsquo;s cumulative &Delta;EV (what riding it costs)
against its cumulative &Delta;Var (what that buys), through the chosen
round. The line is the pricing boundary; the gold ring is the team selected
in the explorer above &mdash; click any dot to trace it.</p>
<div class="controls">
<label>Cumulative through<select id="fr-round"></select></label>
</div>
<div class="legend">
<span><span class="dot" style="background:var(--s1)"></span>Value pick (ratio &le; &minus;1, or the favorite at the origin)</span>
<span><span class="dot" style="background:var(--dim)"></span>No Value star</span>
<span><span class="dot" style="background:#fff;border-color:var(--gold);box-shadow:0 0 0 2px var(--gold)"></span>Selected team</span>
</div>
<div class="chart-wrap" id="fr-chart"></div>
<p class="note" id="fr-mode-note"></p>
<p class="note">Reading the picture: favorites sit at the origin (deviating
from themselves costs and buys nothing &mdash; several dots stack there).
Value picks sit on or above the boundary: lots of variance per point
sacrificed. The far bottom-left is pure sacrifice &mdash; heavy expected-point
losses that <em>reduce</em> your spread against the field (long shots the
crowd somehow backs more than their probability warrants). Hover any dot for
its numbers.</p>
<details><summary class="note" style="cursor:pointer">Table view (same data)</summary>
<div class="scrollx" style="max-height:340px;overflow-y:auto"><table class="num-table" style="width:100%">
<thead><tr><th>Team</th><th>Seed</th><th>Region</th><th>cum &Delta;EV</th>
<th>cum &Delta;Var</th><th>ratio</th><th>Value</th></tr></thead>
<tbody id="fr-table"></tbody></table></div></details>
</div>

<div class="card" id="fine-print">
<h2>Fine print &mdash; the details that keep the calculation honest</h2>
<ul class="fine">
<li><b>The favorite can change round to round.</b> Texas Tech is its own
group&rsquo;s favorite in the first two rounds, then compares against
Michigan (Sweet&nbsp;16), Gonzaga (Elite&nbsp;8) and Duke (Final&nbsp;4 and
Champion). The cumulative sums always price your path against
<em>each round&rsquo;s</em> favorite.</li>
<li><b>Ties for favorite:</b> if several teams share the top probability,
f&#8320; is the average of their pick frequencies (the workbook&rsquo;s
AVERAGEIF), and each of them counts as a favorite (&Delta;EV = 0, automatic
star).</li>
<li><b>The opponent model is an approximation.</b> One random entry drawn
from the pick frequencies, slots treated as independent when variances are
summed across rounds. The workbook makes the same Gaussian-style
approximations in its pool win-probability block; they are excellent for
pricing picks, not exact bracket combinatorics.</li>
<li><b>Units and the exchange rate.</b> &Delta;EV is in points, &Delta;Var in
points&sup2;, so the ratio is in points &mdash; and the &minus;1 threshold is
a modeling choice tied to this points scale (2,&nbsp;3,&nbsp;5,&nbsp;8,
&nbsp;13,&nbsp;21). Rescale the round points and picks move across the
boundary; that&rsquo;s a feature of the workbook, not a bug.</li>
<li><b>&Delta;Var can be negative.</b> An over-picked underdog separates you
from nobody: you pay expected points <em>and</em> lose variance. The frontier
chart&rsquo;s bottom-left shows them.</li>
<li><b>Why favorites star automatically:</b> the factor asks &ldquo;is this
deviation worth it?&rdquo;; not deviating is always worth it, so the
favorite&rsquo;s ratio is defined as 0 and flagged. Per the paper, every
champion from 1985&ndash;2018 was a Value pick; with the fixes, the 2019
champion column stars Duke, Virginia&nbsp;Tech, Michigan&nbsp;State, Gonzaga,
Texas&nbsp;Tech, Michigan, Virginia and Kentucky &mdash; including the actual
champion, Virginia.</li>
<li><b>Data quirk:</b> the workbook lists &ldquo;Mississippi State&rdquo;
twice; the South 8-seed should be Mississippi (Ole&nbsp;Miss). Kept as-is
here and on the main page, flagged with&nbsp;*.</li>
<li><b>The companion slot factor,</b> Bet against beta, uses the same p, f,
p&#8320;, f&#8320; ingredients without the Gaussian machinery &mdash; see the
<a href="index.html">main page</a>.</li>
</ul>
</div>

<footer>
Built {today} &middot; <code>python3 build_value_tutorial.py</code>
regenerates this page from <code>data/model_2019.json</code> &middot;
companion to <a href="index.html">index.html</a> &middot; slot mathematics
identical to <code>extract_model.py</code>, verified against the workbook.
</footer>

</div>
<script>{js}</script>
</body>
</html>
"""


def main():
    data = json.loads(DATA.read_text())
    js = JS.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    OUT.write_text(HTML.format(css=CSS, js=js, today=date.today().isoformat()))
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1024:.0f} kB)")


if __name__ == "__main__":
    main()
