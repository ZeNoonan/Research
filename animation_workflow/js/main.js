// Page wiring: which step is on screen, the sticky viewport, the step-card controls and the tour.
import { mountSketch } from './sketches.js';

const $ = (id) => document.getElementById(id);
const steps = [...document.querySelectorAll('.step')];
const screen = $('screen');
const sketchEl = $('sketch');
const SKETCH = new Set(['story', 'concept', 'storyboard', 'animatic']);

// The department name and the file being worked on, shown in the viewport's title bar.
const HUD = {
  story: ['Story', 'pip_and_the_firefly_idea.txt'],
  concept: ['Visual development', 'pip_explorations_v03.psd'],
  storyboard: ['Storyboard', 'sq010_boards_v02'],
  animatic: ['Animatic', 'sq010_animatic_v05'],
  modeling: ['Modelling', 'pip_model_v014'],
  surfacing: ['Surfacing', 'pip_look_v009'],
  rigging: ['Rigging', 'pip_rig_v007'],
  layout: ['Layout', 'sq010_sh020_layout_v003'],
  animation: ['Animation', 'sq010_sh020_anim_v023'],
  fx: ['FX', 'sq010_sh020_fx_v011'],
  lighting: ['Lighting', 'sq010_sh020_lgt_v008'],
  rendering: ['Rendering', 'sq010_sh020.1121.exr'],
  compositing: ['Compositing', 'sq010_sh020_comp_v012'],
  final: ['Final', 'pip_and_the_firefly · reel 1'],
};

const CAPTION = {
  story: 'The idea, scribbled in a notebook.',
  concept: 'Design options and the final model sheet.',
  storyboard: 'Six storyboard panels for our shot.',
  animatic: 'The storyboard panels, timed to temporary sound.',
  modeling: 'A grey “clay” model on a turntable.',
  surfacing: 'The same model, now with textures and materials.',
  rigging: 'Bones (yellow) and animation controls (circles).',
  layout: 'Stand-in models, the camera and its view.',
  animation: 'The animated shot, as a quick preview (playblast).',
  fx: 'Particles added: glow, trail, dust and sparkles.',
  lighting: 'Final materials and dusk lighting.',
  rendering: 'One frame, rendered bucket by bucket.',
  compositing: 'The final image, built up from layers.',
  final: 'The finished shot.',
};

let viewer = null;
let current = null;
let cleanup = () => {};
let fadeTimer = 0;
let conceptPage = 'explore';
const seen = new Set();
const mobile = () => matchMedia('(max-width: 900px)').matches;

// ---- Top navigation chips ----
const chips = $('chips');
chips.innerHTML = steps.map((s) => {
  const num = s.querySelector('.num').textContent;
  return `<li><a href="#${s.id}" data-stage="${s.dataset.stage}" data-phase="${s.dataset.phase}"><b>${num}</b><span>${HUD[s.dataset.stage][0]}</span></a></li>`;
}).join('');
const chipLinks = [...chips.querySelectorAll('a')];

// ---- Viewer (three.js), loaded separately so the page still works without WebGL ----
import('./viewer.js')
  .then(({ Viewer }) => {
    viewer = new Viewer(screen);
    const io = new IntersectionObserver(([e]) => viewer.setVisible(e.isIntersecting));
    io.observe(screen);
    if (current && !SKETCH.has(current)) viewer.setStage(current);
    viewer.onFrame = onFrame;
    const tris = $('tri-count');
    if (tris) tris.textContent = viewer.pip.triangles().toLocaleString();
  })
  .catch((err) => {
    console.error(err);
    screen.classList.add('no-gl');
  });

function onFrame() {
  if (current === 'fx') {
    const el = $('fx-count');
    if (el) el.textContent = viewer.fx.count.toLocaleString();
  }
}

// ---- Switching stages ----
function activate(id) {
  if (id === current) return;
  current = id;
  steps.forEach((s) => s.classList.toggle('active', s.dataset.stage === id));
  chipLinks.forEach((a) => {
    const on = a.dataset.stage === id;
    a.classList.toggle('active', on);
    if (on) chips.scrollTo({ left: a.parentElement.offsetLeft - chips.clientWidth / 2 + a.parentElement.clientWidth / 2, behavior: 'smooth' });
  });
  $('hud-dept').textContent = HUD[id][0];
  $('hud-file').textContent = HUD[id][1];
  $('stage-cap').textContent = CAPTION[id];
  screen.dataset.phase = steps.find((s) => s.dataset.stage === id).dataset.phase;
  $('stage').dataset.phase = screen.dataset.phase;

  const fade = $('fade');
  fade.classList.add('on');
  clearTimeout(fadeTimer);
  fadeTimer = setTimeout(() => {
    const is2d = SKETCH.has(id);
    screen.classList.toggle('is2d', is2d);
    cleanup();
    cleanup = is2d ? mountSketch(id, sketchEl, { page: conceptPage }) : () => {};
    if (viewer) viewer.setStage(id);
    else if (!is2d) screen.dataset.stage = id;
    if (id === 'rendering') startFarm(); else stopFarm();
    if (!seen.has(id)) {
      seen.add(id);
      if (id === 'lighting') buildUp('light.', ['key', 'fill', 'rim', 'firefly']);
      if (id === 'compositing') buildUp('layer.', ['sky', 'set', 'pip', 'fx', 'glow', 'grade']);
    }
    fade.classList.remove('on');
  }, 170);
}

function pickStep() {
  const line = innerHeight * (mobile() ? 0.66 : 0.5);
  let best = steps[0];
  for (const s of steps) if (s.getBoundingClientRect().top < line) best = s;
  activate(best.dataset.stage);
}

let ticking = false;
addEventListener('scroll', () => {
  if (ticking) return;
  ticking = true;
  requestAnimationFrame(() => { ticking = false; pickStep(); });
}, { passive: true });
addEventListener('resize', pickStep);
pickStep();

// ---- Controls inside the step cards ----
function setCtl(name, value) {
  if (name === 'concept.page') {
    conceptPage = value;
    if (current === 'concept') { cleanup(); cleanup = mountSketch('concept', sketchEl, { page: value }); }
    return;
  }
  if (name.startsWith('light.')) {
    document.querySelector(`.plan [data-light="${name.slice(6)}"]`)?.classList.toggle('off', !value);
  }
  viewer?.control(name, value);
}

function press(btn, on) {
  btn.setAttribute('aria-pressed', String(on));
}

const stepsEl = $('steps');
stepsEl.addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  const card = b.closest('.step');
  if (card) activate(card.dataset.stage);
  const seg = b.closest('.seg');
  if (seg && b.dataset.v) {
    seg.querySelectorAll('button').forEach((x) => press(x, x === b));
    setCtl(seg.dataset.ctl, b.dataset.v);
  } else if (b.classList.contains('tog')) {
    const on = b.getAttribute('aria-pressed') !== 'true';
    press(b, on);
    setCtl(b.dataset.ctl, on);
  } else if (b.dataset.act === 'rerender') {
    viewer?.startBucket();
    startFarm();
  } else if (b.dataset.act === 'build-comp') {
    buildUp('layer.', ['sky', 'set', 'pip', 'fx', 'glow', 'grade']);
  }
});
stepsEl.addEventListener('input', (e) => {
  const r = e.target;
  if (!r.matches('input[type=range]')) return;
  const card = r.closest('.step');
  if (card) activate(card.dataset.stage);
  setCtl(r.dataset.ctl, parseFloat(r.value));
});

// Turn a set of toggles off, then back on one at a time (lights, comp layers).
let buildTimers = [];
function buildUp(prefix, names) {
  buildTimers.forEach(clearTimeout);
  const btn = (n) => document.querySelector(`[data-ctl="${prefix}${n}"]`);
  names.forEach((n) => { press(btn(n), false); setCtl(prefix + n, false); });
  buildTimers = names.map((n, i) => setTimeout(() => { press(btn(n), true); setCtl(prefix + n, true); }, 700 + i * 750));
}

// ---- Render farm: 144 frames shared across a handful of machines ----
let farmTimer = 0;
function startFarm() {
  const el = $('farm'), stats = $('farm-stats');
  if (!el) return;
  stopFarm();
  el.innerHTML = Array.from({ length: 144 }, () => '<i></i>').join('');
  const cells = [...el.children], machines = 16;
  let next = 0, done = 0, clock = 0;
  const busy = Array.from({ length: machines }, () => null);
  let seed = 7;
  const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  farmTimer = setInterval(() => {
    clock += 0.1;
    busy.forEach((job, m) => {
      if (job && clock >= job.end) {
        cells[job.f].className = 'd';
        done++;
        busy[m] = null;
      }
      if (!busy[m] && next < 144) {
        busy[m] = { f: next, end: clock + 0.35 + rand() * 0.6 };
        cells[next++].className = 'r';
      }
    });
    stats.textContent = `${done} of 144 frames done · ${busy.filter(Boolean).length} of ${machines} machines busy`;
    if (done === 144) clearInterval(farmTimer);
  }, 100);
}
function stopFarm() {
  clearInterval(farmTimer);
}

// ---- Guided tour: scrolls through every step on a timer ----
const TOUR_MS = { animatic: 9000, layout: 9000, animation: 10000, fx: 9000, lighting: 10000, rendering: 9000, compositing: 10000, final: 12000 };
let tour = null;
function startTour() {
  stopTour();
  const pill = $('tour-pill');
  pill.hidden = false;
  let i = 0;
  tour = { timer: 0 };
  const next = () => {
    if (i >= steps.length) return stopTour();
    const s = steps[i++];
    s.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: mobile() ? 'start' : 'center' });
    $('tour-step').textContent = `Tour: ${i} of ${steps.length} · ${HUD[s.dataset.stage][0]}`;
    tour.timer = setTimeout(next, TOUR_MS[s.dataset.stage] ?? 7500);
  };
  next();
  setTimeout(() => {
    if (!tour) return;
    for (const ev of ['wheel', 'touchstart', 'keydown']) addEventListener(ev, stopTour, { once: true, passive: true });
  }, 600);
}
function stopTour() {
  if (!tour) return;
  clearTimeout(tour.timer);
  tour = null;
  $('tour-pill').hidden = true;
}
$('tour-btn').addEventListener('click', startTour);
$('tour-stop').addEventListener('click', stopTour);

// ---- "Everything at once" chart: six shots staggered through the shot departments ----
(function gantt() {
  const el = $('gantt');
  if (!el) return;
  const depts = [['Layout', 'l'], ['Animation', 'a'], ['FX', 'x'], ['Lighting', 'g'], ['Render', 'r'], ['Comp', 'c']];
  const lens = [2, 5, 2, 3, 1, 2];
  let html = '<div class="g-legend">' + depts.map(([n, k]) => `<span class="g-${k}">${n}</span>`).join('') + '</div>';
  for (let s = 0; s < 6; s++) {
    let t = s * 2 + (s % 2);
    html += `<div class="g-row"><b>sh0${(s + 1) * 10}</b><div class="g-bar">`;
    depts.forEach(([, k], d) => {
      const len = lens[d] + ((s + d) % 3 === 0 ? 1 : 0);
      html += `<span class="g-${k}" style="left:${(t / 30) * 100}%;width:${(len / 30) * 100}%"></span>`;
      t += len;
    });
    html += '</div></div>';
  }
  el.innerHTML = html;
})();
