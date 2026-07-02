"""Generate a self-contained HTML view of the March Madness factor model.

Reads data/model_2019.json (produced by extract_model.py) and writes
index.html: the Bracket tab's star ratings and pick grid, the live pool
win-probability calculation, the per-team slot-calculation detail and the
write-up of the Variance-difference bug fix. All of the spreadsheet's maths is
re-implemented in the embedded JavaScript, so round points, pool size and
picks are editable in the page. No external assets.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data" / "model_2019.json"
OUT = HERE / "index.html"

CSS = """
:root {
  --bg: #f4f6f8; --card: #ffffff; --ink: #1c2733; --muted: #5f6b76;
  --accent: #134074; --gold: #c9920a; --good: #1e7d46; --bad: #b3372f;
  --border: #dce3ea; --hl: #fdf6e3; --chip: #eef4fb;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  font-size: 15px; line-height: 1.5; }
.wrap { max-width: 1180px; margin: 0 auto; padding: 16px; }
header h1 { margin: 8px 0 2px; font-size: 26px; color: var(--accent); }
header p.sub { margin: 0 0 14px; color: var(--muted); }
.card { background: var(--card); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 16px; margin: 14px 0; }
.card h2 { margin: 0 0 8px; font-size: 18px; color: var(--accent); }
.card h3 { margin: 14px 0 6px; font-size: 15px; }
.cols { display: flex; gap: 14px; flex-wrap: wrap; }
.cols > .card { flex: 1 1 320px; margin: 0; }
.controls label { display: inline-flex; flex-direction: column; gap: 2px;
  font-size: 12px; color: var(--muted); margin: 4px 10px 4px 0; }
.controls input[type=number] { width: 64px; padding: 4px 6px; font-size: 14px;
  border: 1px solid var(--border); border-radius: 6px; }
.controls .row { display: flex; flex-wrap: wrap; align-items: flex-end; }
button { background: var(--accent); color: #fff; border: 0; border-radius: 6px;
  padding: 6px 12px; font-size: 13px; cursor: pointer; }
button.secondary { background: var(--chip); color: var(--accent); }
.mode-toggle { display: inline-flex; border: 1px solid var(--border);
  border-radius: 8px; overflow: hidden; }
.mode-toggle button { border-radius: 0; background: var(--card); color: var(--ink); }
.mode-toggle button.active { background: var(--accent); color: #fff; }
.big { font-size: 30px; font-weight: 700; color: var(--accent); }
.stat { margin-right: 22px; display: inline-block; }
.stat .lbl { font-size: 12px; color: var(--muted); display: block; }
.counts span { display: inline-block; margin-right: 10px; font-size: 13px;
  padding: 1px 8px; border-radius: 10px; background: var(--chip); }
.counts span.bad { background: #fbeae8; color: var(--bad); font-weight: 600; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
.region th, .region td { border-bottom: 1px solid var(--border);
  padding: 3px 6px; text-align: left; white-space: nowrap; }
.region tr.gline td { border-bottom: 2px solid #b9c4cf; }
.region th { background: var(--chip); position: sticky; top: 0; }
.region td.rc { text-align: center; min-width: 86px; }
.region .stars { color: var(--gold); letter-spacing: 1px; font-size: 13px; }
.region .pick { accent-color: var(--accent); }
.region td.seed { color: var(--muted); width: 26px; text-align: right; }
.region tr.detail-row td { background: #f8fafc; white-space: normal; }
.region tr:hover td { background: #f2f7fc; }
.region .teamname { cursor: pointer; font-weight: 600; color: var(--accent); }
.region .changed { outline: 2px dashed var(--gold); outline-offset: -2px; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 980px) { .grid2 { grid-template-columns: 1fr; } }
.detail-table th, .detail-table td { border: 1px solid var(--border);
  padding: 2px 7px; font-size: 12px; text-align: right; }
.detail-table th:first-child, .detail-table td:first-child { text-align: left; }
.factor-cards { display: grid; gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }
.factor-cards .fc { border: 1px solid var(--border); border-radius: 8px;
  padding: 10px 12px; background: #fbfcfe; }
.fc b { color: var(--accent); }
.fc p { margin: 4px 0 0; font-size: 13px; color: var(--muted); }
code { background: var(--chip); padding: 1px 5px; border-radius: 4px;
  font-size: 12.5px; }
.note { font-size: 13px; color: var(--muted); }
.bugbox { border-left: 4px solid var(--gold); }
.flagdiff { font-size: 13px; }
.flagdiff td, .flagdiff th { border-bottom: 1px solid var(--border);
  padding: 2px 8px; text-align: left; }
.ok { color: var(--good); font-weight: 600; }
footer { color: var(--muted); font-size: 12.5px; margin: 20px 0; }
a { color: var(--accent); }
"""

JS = r"""
const MODEL = __DATA__;
const ROUNDS = MODEL.rounds;                  // ["R64",...,"C6"]
const RLABEL = ["Round of 64","Round of 32","Sweet 16","Elite 8","Final 4","Champion"];
const N = 64, BUG_OFFSET = 38;
const REGION_NAMES = ["East","West","South","Midwest"];

const state = {
  mode: "fixed",                              // "fixed" | "published"
  points: MODEL.points.slice(),
  poolSize: MODEL.poolSize,
  picks: MODEL.teams.map(t => t.picks.slice()),
  openDetail: null,
};

/* ---- spreadsheet maths (mirrors extract_model.py, verified vs xlsx) ---- */

// Excel compares numbers only to 15 significant digits
function excelLt(a, b) {
  if (a === b) return false;
  const s = Math.max(Math.abs(a), Math.abs(b));
  if (s && Math.abs(a - b) / s < 1e-14) return false;
  return a < b;
}

function slotCalcs(mode, points) {
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
    const t = T[i], expDiff = [], varOne = [], varDiff = [];
    for (let k = 0; k < 6; k++) {
      const p = t.prob[k], f = t.freq[k], s = S[i][k];
      expDiff.push(points[k] * (p - P0[i][k]));
      varOne.push(p * (1 - p - 2 * f + 2 * s) + s - s * s);
      let sUsed = s;
      if (mode === "published") {            // AL3 references B41: 38 rows down,
        const j = i + BUG_OFFSET;            // empty (=0) past the last team
        sUsed = j < N ? S[j][k] : 0;
      }
      varDiff.push(points[k] ** 2 * ((p - P0[i][k]) * (1 + 2 * sUsed)
        - p * p + P0[i][k] ** 2 - 2 * (p * f - P0F0[i][k])));
    }
    const cumExp = [], cumVar = [];
    let ce = 0, cv = 0;
    for (let k = 0; k < 6; k++) { ce += expDiff[k]; cv += varDiff[k]; cumExp.push(ce); cumVar.push(cv); }
    const ratio = cumExp.map((e, k) => e === 0 ? 0 : cumVar[k] / e);
    const value = ratio.map(r => mode === "published"
      ? ((r === 0 || r > 1) ? 1 : 0)         // as released
      : ((r === 0 || r <= -1) ? 1 : 0));     // paper's rule: var gain >= EV loss
    const bab = [];
    for (let k = 0; k < 6; k++) {
      const p = t.prob[k], f = t.freq[k];
      bab.push(excelLt(P0[i][k] - 0.5, p)
        && excelLt(f / p, P0F0[i][k] / P0[i][k] ** 2) ? 1 : 0);
    }
    out.push({ S: S[i], p0: P0[i], p0f0: P0F0[i], expDiff, cumExp,
               variance: varOne, varDiff, cumVar, ratio, value, bab });
  }
  return out;
}

function factorIndicators() {
  const T = MODEL.teams, medQ = {}, medS = {};
  for (let seed = 1; seed <= 16; seed++) {
    const qs = T.filter(t => t.seed === seed).map(t => t.quality).sort((a, b) => a - b);
    const ss = T.filter(t => t.seed === seed).map(t => t.size).sort((a, b) => a - b);
    medQ[seed] = (qs[1] + qs[2]) / 2;
    medS[seed] = (ss[1] + ss[2]) / 2;
  }
  return { medQ, medS, ind: T.map(t => ({
    quality: t.quality > medQ[t.seed] ? 1 : 0,
    size: t.size > medS[t.seed] ? 1 : 0,
    mom: ((t.seed < 9 && t.mom > 3) || (t.seed > 8 && t.mom < 4)) ? 1 : 0,
  })) };
}

/* normal distribution helpers (Acklam inverse + erfc, ample for display) */
function erfc(x) {
  const z = Math.abs(x), t = 1 / (1 + z / 2);
  const r = t * Math.exp(-z * z - 1.26551223 + t * (1.00002368 + t * (0.37409196
    + t * (0.09678418 + t * (-0.18628806 + t * (0.27886807 + t * (-1.13520398
    + t * (1.48851587 + t * (-0.82215223 + t * 0.17087277)))))))));
  return x >= 0 ? r : 2 - r;
}
function normCdf(x, mu, sigma) { return 0.5 * erfc(-(x - mu) / (sigma * Math.SQRT2)); }
function normInv(p) {
  const a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
             1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00];
  const b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
             6.680131188771972e+01, -1.328068155288572e+01];
  const c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
             -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00];
  const d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
             3.754408661907416e+00];
  const pl = 0.02425;
  let q, x;
  if (p < pl) {
    q = Math.sqrt(-2 * Math.log(p));
    x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
        ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  } else if (p <= 1 - pl) {
    q = p - 0.5; const r = q * q;
    x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q /
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
  } else {
    q = Math.sqrt(-2 * Math.log(1 - p));
    x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
         ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  }
  return x;
}

function winProbability(slots, picks, points, n) {
  const T = MODEL.teams;
  let youMean = 0, fieldMean = 0, youVar = 0, fieldVar = 0;
  for (let i = 0; i < N; i++) for (let k = 0; k < 6; k++) {
    youMean += points[k] * picks[i][k] * T[i].prob[k];
    fieldMean += points[k] * T[i].prob[k] * T[i].freq[k];
    youVar += points[k] ** 2 * picks[i][k] * slots[i].variance[k];
    fieldVar += points[k] ** 2 * T[i].freq[k] * slots[i].variance[k];
  }
  const d10 = youMean - fieldMean, e10 = Math.sqrt(youVar), e11 = Math.sqrt(fieldVar);
  const totalPts = 32 * points[0] + 16 * points[1] + 8 * points[2]
    + 4 * points[3] + 2 * points[4] + points[5];
  let qs = [1 / n];
  for (let j = 0; j < 6; j++) qs.push(Math.min(1, 2 * qs[qs.length - 1]));
  qs.reverse();
  for (let j = 0; j < 6; j++) qs.push(qs[qs.length - 1] / 2);
  qs.push(0);
  const xs = [-totalPts], Fs = [0];
  for (let j = 1; j < 13; j++) {
    const x = d10 + normInv(1 - qs[j]) * e10;
    xs.push(x);
    Fs.push(Math.pow(normCdf(x, 0, e11), n - 1));
  }
  xs.push(totalPts); Fs.push(1);
  let win = 0;
  for (let j = 1; j < 14; j++) win += (qs[j - 1] - qs[j]) * (Fs[j - 1] + Fs[j]) / 2;
  return { youMean, fieldMean, youVar, fieldVar, winProb: win };
}

/* ------------------------------ rendering ------------------------------ */

const FACTORS = factorIndicators();
let slotsFixed, slotsPublished;

function starCount(slots, i, k) {
  const f = FACTORS.ind[i];
  return f.quality + f.size + f.mom + slots[i].value[k] + slots[i].bab[k];
}

function starTitle(slots, i, k) {
  const f = FACTORS.ind[i], parts = [];
  if (f.quality) parts.push("Quality");
  if (f.size) parts.push("Size");
  if (f.mom) parts.push("Momentum");
  if (slots[i].value[k]) parts.push("Value");
  if (slots[i].bab[k]) parts.push("Bet-against-beta");
  return parts.length ? parts.join(" + ") : "no factors";
}

function fmt(x, dp = 3) {
  return (Math.round(x * 10 ** dp) / 10 ** dp).toFixed(dp);
}
function pct(x, dp = 2) { return (100 * x).toFixed(dp) + "%"; }

function recompute() {
  slotsFixed = slotCalcs("fixed", state.points);
  slotsPublished = slotCalcs("published", state.points);
}

function activeSlots() { return state.mode === "fixed" ? slotsFixed : slotsPublished; }

function renderSummary() {
  const wp = winProbability(activeSlots(), state.picks, state.points, state.poolSize);
  document.getElementById("winprob").textContent = pct(wp.winProb);
  document.getElementById("winprob-x").textContent =
    "= " + (wp.winProb * state.poolSize).toFixed(2) +
    "× a random entry in a pool of " + state.poolSize;
  document.getElementById("exp-you").textContent = fmt(wp.youMean, 1);
  document.getElementById("exp-field").textContent = fmt(wp.fieldMean, 1);
  document.getElementById("sd-you").textContent = fmt(Math.sqrt(wp.youVar), 1);
  document.getElementById("sd-field").textContent = fmt(Math.sqrt(wp.fieldVar), 1);

  const want = [32, 16, 8, 4, 2, 1];
  const counts = ROUNDS.map((_, k) =>
    state.picks.reduce((a, p) => a + (p[k] ? 1 : 0), 0));
  document.getElementById("pickcounts").innerHTML = ROUNDS.map((r, k) =>
    `<span class="${counts[k] === want[k] ? "" : "bad"}">${r}: ${counts[k]}/${want[k]}</span>`
  ).join("");
}

function renderBracket() {
  const slots = activeSlots(), other = state.mode === "fixed" ? slotsPublished : slotsFixed;
  const host = document.getElementById("bracket");
  host.innerHTML = "";
  for (let rgn = 0; rgn < 4; rgn++) {
    const div = document.createElement("div");
    div.className = "card";
    let h = `<h2>${REGION_NAMES[rgn]}</h2><table class="region"><thead><tr>` +
      `<th></th><th>Team</th>` + ROUNDS.map(r => `<th>${r}</th>`).join("") +
      `</tr></thead><tbody>`;
    for (let j = 0; j < 16; j++) {
      const i = rgn * 16 + j, t = MODEL.teams[i];
      const gline = j % 2 === 1 ? " gline" : "";
      h += `<tr class="teamrow${gline}" data-i="${i}">` +
        `<td class="seed">${t.seed}</td>` +
        `<td><span class="teamname" data-i="${i}" title="click for slot detail">` +
        `${t.name}${t.note ? "*" : ""}</span></td>`;
      for (let k = 0; k < 6; k++) {
        const n = starCount(slots, i, k);
        const changed = n !== starCount(other, i, k) ? " changed" : "";
        h += `<td class="rc${changed}" title="${starTitle(slots, i, k)}">` +
          `<input type="checkbox" class="pick" data-i="${i}" data-k="${k}"` +
          `${state.picks[i][k] ? " checked" : ""}>` +
          ` <span class="stars">${"★".repeat(n)}</span></td>`;
      }
      h += "</tr>";
      if (state.openDetail === i) h += detailRow(i, slots);
    }
    h += "</tbody></table>";
    div.innerHTML = h;
    host.appendChild(div);
  }
  host.querySelectorAll(".pick").forEach(cb => cb.addEventListener("change", e => {
    const i = +e.target.dataset.i, k = +e.target.dataset.k;
    state.picks[i][k] = e.target.checked ? 1 : 0;
    renderSummary();
  }));
  host.querySelectorAll(".teamname").forEach(el => el.addEventListener("click", e => {
    const i = +e.target.dataset.i;
    state.openDetail = state.openDetail === i ? null : i;
    renderBracket();
  }));
}

function detailRow(i, slots) {
  const t = MODEL.teams[i], f = FACTORS.ind[i], s = slots[i];
  const head = `<b>${t.longName}</b> &mdash; ` +
    `Quality ${fmt(t.quality, 1)} (seed median ${fmt(FACTORS.medQ[t.seed], 1)})` +
    `${f.quality ? " ✓" : ""} &middot; ` +
    `Size ${fmt(t.size, 1)} (median ${fmt(FACTORS.medS[t.seed], 1)})` +
    `${f.size ? " ✓" : ""} &middot; ` +
    `Momentum ${t.mom} of last 5 (${t.seed < 9 ? "top-8 seed wants &gt;3" : "bottom-8 seed wants &lt;4"})` +
    `${f.mom ? " ✓" : ""}` +
    (t.note ? `<br><span class="note">* ${t.note}</span>` : "");
  let tbl = `<table class="detail-table"><tr><th>Round</th><th>p win</th>` +
    `<th>pick freq</th><th>p0 (fav)</th><th>S</th><th>cum ΔEV pts</th>` +
    `<th>cum ΔVar</th><th>ratio</th><th>Value</th><th>BAB</th></tr>`;
  for (let k = 0; k < 6; k++) {
    tbl += `<tr><td>${RLABEL[k]}</td><td>${fmt(t.prob[k])}</td>` +
      `<td>${fmt(t.freq[k])}</td><td>${fmt(s.p0[k])}</td><td>${fmt(s.S[k])}</td>` +
      `<td>${fmt(s.cumExp[k], 2)}</td><td>${fmt(s.cumVar[k], 2)}</td>` +
      `<td>${fmt(s.ratio[k], 2)}</td>` +
      `<td>${s.value[k] ? "★" : ""}</td><td>${s.bab[k] ? "★" : ""}</td></tr>`;
  }
  tbl += "</table>";
  return `<tr class="detail-row"><td colspan="8">${head}${tbl}</td></tr>`;
}

function renderAll() {
  recompute();
  renderBracket();
  renderSummary();
}

/* ------------------------------- controls ------------------------------ */

function initControls() {
  const pts = document.getElementById("points-inputs");
  ROUNDS.forEach((r, k) => {
    const lab = document.createElement("label");
    lab.innerHTML = `${r}<input type="number" min="0" step="1" value="${state.points[k]}" data-k="${k}">`;
    pts.appendChild(lab);
  });
  pts.querySelectorAll("input").forEach(inp => inp.addEventListener("change", e => {
    state.points[+e.target.dataset.k] = +e.target.value || 0;
    renderAll();
  }));
  const pool = document.getElementById("poolsize");
  pool.value = state.poolSize;
  pool.addEventListener("change", e => {
    state.poolSize = Math.max(2, Math.round(+e.target.value || 2));
    e.target.value = state.poolSize;
    renderSummary();
  });
  document.querySelectorAll(".mode-toggle button").forEach(b =>
    b.addEventListener("click", e => {
      state.mode = e.target.dataset.mode;
      document.querySelectorAll(".mode-toggle button").forEach(x =>
        x.classList.toggle("active", x.dataset.mode === state.mode));
      renderAll();
    }));
  document.getElementById("reset-picks").addEventListener("click", () => {
    state.picks = MODEL.teams.map(t => t.picks.slice());
    renderAll();
  });
}

initControls();
renderAll();
"""

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>March Madness 2019 — Factor Bracket Model</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">

<header>
<h1>March Madness 2019 — factor-investing bracket model</h1>
<p class="sub">Aaron Brown&rsquo;s <em>&ldquo;Quants go mad in March&rdquo;</em>
spreadsheet (March&nbsp;18, 2019 version), re-implemented and verified
cell-by-cell, with the Variance-difference bug fixed.
Source: <a href="reference/March_Madness_20190318.xlsx">original workbook</a>,
<a href="March_Madness_20190318_fixed.xlsx">fixed workbook</a>,
<a href="reference/Quants_Mad_March.pdf">the paper</a>.
New: <a href="value_explainer.html"><b>how the Value factor works</b></a> —
a visual walkthrough following Michigan State through the whole
calculation.</p>
</header>

<div class="cols">
<div class="card controls">
<h2>Inputs</h2>
<div class="row" id="points-inputs"><label style="width:100%">Points per round</label></div>
<div class="row">
<label>Effective pool size<input type="number" id="poolsize" min="2" step="1"></label>
<label>Variance-difference formula<span class="mode-toggle">
<button data-mode="fixed" class="active">Fixed</button>
<button data-mode="published">As published</button></span></label>
<label>&nbsp;<button class="secondary" id="reset-picks">Reset picks to sheet defaults</button></label>
</div>
<p class="note">Stars are factor counts (0&ndash;5) per team per round:
Quality + Size + Momentum (team-level) and Value + Bet-against-beta
(slot-level, these react to the round points). Tick a checkbox to pick that
team to win that round; the win probability updates live. Cells outlined in
gold differ between the published and fixed formulas.</p>
</div>
<div class="card">
<h2>Your estimated chance of winning the pool</h2>
<span class="big" id="winprob"></span>
<span class="note" id="winprob-x"></span>
<div style="margin-top:8px">
<span class="stat"><span class="lbl">Expected points — you</span><b id="exp-you"></b></span>
<span class="stat"><span class="lbl">Expected points — field</span><b id="exp-field"></b></span>
<span class="stat"><span class="lbl">Std dev — you vs field</span><b id="sd-you"></b></span>
<span class="stat"><span class="lbl">Std dev — field</span><b id="sd-field"></b></span>
</div>
<h3>Pick counts</h3>
<div class="counts" id="pickcounts"></div>
<p class="note">The Read&nbsp;Me&rsquo;s guidance: a good bracket has an
estimated win probability around 2&ndash;3&times; that of a random entry.
Don&rsquo;t chase the maximum &mdash; the whole point is to exploit
deviations from the probability and frequency assumptions.</p>
</div>
</div>

<div class="card bugbox">
<h2>The Variance-difference anomaly (and what was fixed)</h2>
<p>The <em>Slot calculations</em> tab, columns <code>AL:AQ</code>
(&ldquo;Variance difference&rdquo;), computes the variance gained by picking
team <em>i</em> instead of the slot favorite. The paper&rsquo;s formula is
&Delta;Var&nbsp;=&nbsp;(p&minus;p&#8320;)(1+2S)&nbsp;&minus;&nbsp;p&sup2;+p&#8320;&sup2;&nbsp;&minus;&nbsp;2(pf&nbsp;&minus;&nbsp;p&#8320;f&#8320;),
where S is the slot&rsquo;s expected wins for the average entry &mdash; the
value already computed in column&nbsp;B of the same row.</p>
<p><b>Bug&nbsp;1 (the one you spotted):</b> <code>AL3</code> reads
<code>(1+2*B41)</code> &mdash; the S of the team <em>38 rows further down</em>
&mdash; instead of <code>(1+2*B3)</code>. Filled down, the reference walks off
the data: from row&nbsp;29 onward it points at empty cells, so more than half
the teams were computed with S&nbsp;=&nbsp;0. Fixed to the same-row
<code>B3</code> reference.</p>
<p><b>Bug&nbsp;2 (surfaced by fixing bug&nbsp;1):</b> the Value flag
(<code>BD:BI</code>) tests <code>ratio &gt; 1</code>, where ratio =
cumulative &Delta;Var &divide; cumulative &Delta;EV. But the sheet stores
&Delta;EV as a <em>negative</em> number for non-favorites, so the paper&rsquo;s
rule &mdash; &ldquo;variance gain at least as large as the expected-value
loss&rdquo; &mdash; corresponds to <code>ratio &le; &minus;1</code>. As
published, the flag fired only for picks whose variance <em>loss</em> exceeded
the EV loss: the exact opposite. Fixed to
<code>IF(OR(ratio=0, ratio&le;&minus;1),1,0)</code>.</p>
<p><b>Effect:</b> 100 of 384 Value flags change (98 gained, 2 lost). As
published, the only championship-column Value pick was Duke. Fixed, the
championship Value picks are Duke, Virginia&nbsp;Tech, Michigan&nbsp;State,
Gonzaga, Texas&nbsp;Tech, Michigan, Virginia and Kentucky &mdash; and the 2019
tournament was won by <span class="ok">Virginia</span> over
<span class="ok">Texas&nbsp;Tech</span>, with
<span class="ok">Michigan&nbsp;State</span> also in the Final&nbsp;Four.
Texas&nbsp;Tech becomes the only 5-star champion pick on the board. Use the
&ldquo;As published&rdquo; toggle above to compare; changed cells are outlined
in gold.</p>
</div>

<div class="card">
<h2>The five factors</h2>
<div class="factor-cards">
<div class="fc"><b>Quality</b><p>ESPN Basketball Power Index above the median
of the four teams sharing the seed. High-BPI halves of each seed won 1.35
games per tournament vs 0.58 for low-BPI halves (1986&ndash;2017).</p></div>
<div class="fc"><b>Size</b><p>Recent tournament success (exponentially
weighted) above seed median. Surprisingly, the &ldquo;big&rdquo;, familiar
programs outperform: 24 of 32 champions were top-two in size for their
seed.</p></div>
<div class="fc"><b>Momentum</b><p>Wins in the last five regular-season games.
Good for top-8 seeds (want 4&ndash;5); <em>inverted</em> for bottom-8 seeds
(want &le;3), because weak finishers there earned their bid without an
automatic conference win.</p></div>
<div class="fc"><b>Value</b><p>Slot-level: the pick increases the variance of
your score versus the pool average by at least as much as it costs in
expected points &mdash; or it is the favorite. Every champion since 1985 has
been a Value pick.</p></div>
<div class="fc"><b>Bet against beta</b><p>Slot-level: a non-favorite within
0.5 win probability of the favorite that the field picks <em>less</em> often
relative to its probability. Differentiates your bracket without Gaussian
assumptions.</p></div>
</div>
</div>

<h2 style="margin:18px 0 0">Bracket &amp; star ratings</h2>
<p class="note">Click a team name for its full slot-calculation detail
(probabilities, frequencies, &Delta;EV, &Delta;Var, ratio and flags by
round).</p>
<div class="grid2" id="bracket"></div>

<div class="card">
<h2>Data notes</h2>
<ul class="note">
<li>Probabilities, pick frequencies, factor values, default picks, round
points and pool size all come from the March&nbsp;18, 2019 workbook (ESPN pool
data for frequencies).</li>
<li>Play-in slots (NDS/NCC, FD/PV, Bel/Tem, AS/SJ) carry the average
Quality/Size/Momentum of the two candidate teams, as in the workbook.</li>
<li>* The South 8&nbsp;seed is listed as &ldquo;Mississippi State&rdquo; in
the workbook &mdash; a duplicate of the East 5&nbsp;seed. The actual 2019
South 8&nbsp;seed was Mississippi (Ole&nbsp;Miss); its Quality/Size/Momentum
lookups therefore return Mississippi State&rsquo;s values. Kept as-is, noted
for transparency.</li>
<li>The Python re-implementation (<code>extract_model.py</code>) reproduces
all 4,224 Slot-calculation cells and all 384 star ratings of the published
workbook exactly, and the win-probability block to within Excel&rsquo;s own
NORMSINV precision (&asymp;4&times;10&#8315;&#8312;).</li>
</ul>
</div>

<footer>
Built {today} &middot; <code>python3 extract_model.py &amp;&amp; python3
build_site.py</code> regenerates this page &middot;
<code>fix_workbook.py</code> writes the corrected workbook.
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
    print(f"Wrote {OUT} ({OUT.stat().st_size/1024:.0f} kB)")


if __name__ == "__main__":
    main()
