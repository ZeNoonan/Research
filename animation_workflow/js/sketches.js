// Pre-production artwork, drawn as SVG: the story notebook, concept sheets, storyboards and the
// animatic. These stages happen before anything is built in 3D, so they are deliberately 2D.

const INK = '#2c2a28';
const COL = {
  shell: '#ee7a3a', cream: '#f1e8da', visor: '#1a2033', eye: '#63f3ff', metal: '#a9b2bd',
  rubber: '#2f3441', bulb: '#ff5e7a', line: '#3b2a24',
};
const PENCIL = {
  shell: '#fbf8f2', cream: '#fbf8f2', visor: '#d8d2c8', eye: '#4a4744', metal: '#ebe6dd',
  rubber: '#cfc9bf', bulb: '#fbf8f2', line: INK,
};

// Pip, drawn with its feet at (0, 0). Angles in degrees.
// arms: 0 = hanging down, 90 = out sideways, 180 = straight up, negative = across the body.
export function pip(o = {}) {
  const {
    x = 0, y = 0, s = 1, lean = 0, sq = 0, head = 0, armA = 12, armB = 12, eyes = 'open',
    view = 'front', style = 'pencil', tuck = 0,
  } = o;
  const c = style === 'color' ? COL : PENCIL;
  const sw = style === 'color' ? 2.6 : 2.2;
  const L = `stroke="${c.line}" stroke-width="${sw}" stroke-linejoin="round" stroke-linecap="round"`;
  const sx = 1 + sq * 0.25, sy = 1 - sq * 0.35;
  const lift = tuck * 10;

  const arm = (sxp, dir, deg) => {
    const r = (deg * Math.PI) / 180, len = 34;
    const ex = sxp + dir * Math.sin(r) * len, ey = -60 + Math.cos(r) * len;
    return `<line x1="${sxp}" y1="-60" x2="${ex}" y2="${ey}" stroke="${c.line}" stroke-width="11" stroke-linecap="round"/>
      <line x1="${sxp}" y1="-60" x2="${ex}" y2="${ey}" stroke="${view === 'back' || style === 'color' ? c.shell : '#fbf8f2'}" stroke-width="6.5" stroke-linecap="round"/>
      <circle cx="${ex}" cy="${ey}" r="7.5" fill="${c.cream}" ${L}/>`;
  };

  let body = '';
  if (view === 'side') {
    body += `<rect x="-4" y="${-24 + lift}" width="8" height="15" fill="${c.metal}" ${L}/>
      <ellipse cx="6" cy="${-6 + lift}" rx="16" ry="7" fill="${c.rubber}" ${L}/>
      ${armA < 0 ? arm(2, 1, armA) : ''}
      <path d="M0,-20 C27,-20 30,-52 22,-64 C16,-74 -16,-74 -22,-64 C-30,-52 -27,-20 0,-20 Z" fill="${c.shell}" ${L}/>
      <ellipse cx="21" cy="-42" rx="6" ry="12" fill="${c.cream}" ${L}/>
      <rect x="-8" y="-78" width="16" height="9" fill="${c.metal}" ${L}/>`;
  } else {
    body += `<rect x="${-17}" y="${-24 + lift}" width="8" height="15" fill="${c.metal}" ${L}/>
      <rect x="9" y="${-24 + lift}" width="8" height="15" fill="${c.metal}" ${L}/>
      <ellipse cx="-13" cy="${-6 + lift}" rx="12" ry="7" fill="${c.rubber}" ${L}/>
      <ellipse cx="13" cy="${-6 + lift}" rx="12" ry="7" fill="${c.rubber}" ${L}/>
      <path d="M0,-20 C32,-20 35,-52 25,-64 C18,-74 -18,-74 -25,-64 C-35,-52 -32,-20 0,-20 Z" fill="${c.shell}" ${L}/>`;
    if (view === 'front') {
      body += `<ellipse cx="0" cy="-42" rx="15" ry="12" fill="${c.cream}" ${L}/>`;
      if (style === 'color') body += `<circle cx="-6" cy="-45" r="2.4" fill="#ff5e7a"/><circle cx="0" cy="-45" r="2.4" fill="#ffd25e"/><circle cx="6" cy="-45" r="2.4" fill="#5ee08f"/>`;
      else body += `<circle cx="-6" cy="-45" r="1.8" fill="${INK}"/><circle cx="0" cy="-45" r="1.8" fill="${INK}"/><circle cx="6" cy="-45" r="1.8" fill="${INK}"/>`;
    } else if (style === 'color') {
      body += `<text x="0" y="-36" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" font-weight="900" font-size="17" fill="${COL.cream}">07</text>`;
    }
    body += `<rect x="-8" y="-78" width="16" height="9" fill="${c.metal}" ${L}/>`;
  }
  if (view !== 'side') body += arm(-27, -1, armA) + arm(27, 1, armB);
  else if (armA >= 0) body += arm(2, 1, armA);

  let hd = '';
  if (view === 'side') {
    hd += `<path d="M-2,-147 Q-4,-162 -7,-173" fill="none" stroke="${c.line}" stroke-width="5" stroke-linecap="round"/>
      <path d="M-2,-147 Q-4,-162 -7,-173" fill="none" stroke="${c.metal}" stroke-width="2.5" stroke-linecap="round"/>
      <circle cx="-7.5" cy="-177" r="6.5" fill="${c.bulb}" ${L}/>
      <circle cx="0" cy="-110" r="38" fill="${c.cream}" ${L}/>
      <path d="M8,-129 Q38,-127 37,-109 Q38,-90 8,-89 Q20,-109 8,-129 Z" fill="${c.visor}" ${L}/>
      ${eyeShape(27, eyes, c, 0.8)}
      <circle cx="-4" cy="-108" r="9" fill="${c.metal}" ${L}/><circle cx="-4" cy="-108" r="4.5" fill="${c.shell}" ${L}/>`;
  } else {
    hd += `<path d="M0,-147 Q1,-162 3,-173" fill="none" stroke="${c.line}" stroke-width="5" stroke-linecap="round"/>
      <path d="M0,-147 Q1,-162 3,-173" fill="none" stroke="${c.metal}" stroke-width="2.5" stroke-linecap="round"/>
      <circle cx="3.5" cy="-177" r="6.5" fill="${c.bulb}" ${L}/>
      <rect x="-45" y="-119" width="10" height="18" rx="3" fill="${c.metal}" ${L}/>
      <rect x="35" y="-119" width="10" height="18" rx="3" fill="${c.metal}" ${L}/>
      <circle cx="0" cy="-110" r="38" fill="${c.cream}" ${L}/>`;
    if (style === 'color') hd += `<path d="M-6,-147.4 Q0,-148.6 6,-147.4 L6,-133 L-6,-133 Z" fill="${COL.shell}"/>`;
    if (view === 'front') {
      hd += `<rect x="-29" y="-129" width="58" height="41" rx="18" fill="${c.visor}" ${L}/>
        ${eyeShape(-11, eyes, c)}${eyeShape(11, eyes, c)}`;
    } else {
      hd += `<path d="M0,-148 L0,-72" stroke="${c.line}" stroke-width="1.2" opacity=".6"/>`;
    }
  }

  return `<g transform="translate(${x},${y}) scale(${s}) rotate(${lean}) scale(${sx},${sy})">
    ${body}<g transform="rotate(${head} 0 -72)">${hd}</g></g>`;
}

function eyeShape(cx, kind, c, k = 1) {
  if (kind === 'happy') return `<path d="M${cx - 6 * k},-104 Q${cx},-117 ${cx + 6 * k},-104" fill="none" stroke="${c.eye}" stroke-width="4" stroke-linecap="round"/>`;
  if (kind === 'closed') return `<path d="M${cx - 6 * k},-108 L${cx + 6 * k},-108" stroke="${c.eye}" stroke-width="3.5" stroke-linecap="round"/>`;
  const w = (kind === 'wide' ? 12 : 9) * k, h = kind === 'wide' ? 22 : 17;
  let s = `<rect x="${cx - w / 2}" y="${-109 - h / 2}" width="${w}" height="${h}" rx="${w / 2}" fill="${c.eye}"/>`;
  if (kind === 'wide') s += `<circle cx="${cx + w * 0.15}" cy="-114" r="2.6" fill="#fff"/>`;
  return s;
}

const firefly = (x, y, r = 3, rays = true) => `
  <circle cx="${x}" cy="${y}" r="${r * 3.2}" fill="#ffe27a" opacity=".35"/>
  <circle cx="${x}" cy="${y}" r="${r}" fill="#f5c400" stroke="${INK}" stroke-width="1"/>
  ${rays ? [0, 60, 120, 180, 240, 300].map((a) => {
    const r1 = r * 2.2, r2 = r * 3.6, q = (a * Math.PI) / 180;
    return `<line x1="${x + Math.cos(q) * r1}" y1="${y + Math.sin(q) * r1}" x2="${x + Math.cos(q) * r2}" y2="${y + Math.sin(q) * r2}" stroke="${INK}" stroke-width="1" stroke-linecap="round"/>`;
  }).join('') : ''}`;

const dust = (x, y, s = 1) => `<g fill="#fbf8f2" stroke="${INK}" stroke-width="1.4">
  <circle cx="${x}" cy="${y}" r="${7 * s}"/><circle cx="${x + 9 * s}" cy="${y - 4 * s}" r="${6 * s}"/><circle cx="${x - 9 * s}" cy="${y - 3 * s}" r="${5 * s}"/></g>`;

// ---- Storyboard panels for shot sq010_sh020 (320 x 180 each) ----
export const PANELS = [
  {
    dur: 1.2, label: 'Dusk. Pip stands on a rock, gazing at the sky.', sfx: '♪ soft evening music · crickets',
    art: () => `
      <circle cx="58" cy="36" r="13" fill="none" stroke="${INK}" stroke-width="1.6"/>
      <path d="M0,104 Q60,88 120,102 T240,96 T320,102" fill="none" stroke="${INK}" stroke-width="1.2" opacity=".55"/>
      ${[[248, 104, 16], [272, 96, 20], [296, 106, 14], [26, 108, 14]].map(([x, y, h]) => `<path d="M${x - h / 2.4},${y} L${x},${y - h * 1.6} L${x + h / 2.4},${y} Z" fill="#fbf8f2" stroke="${INK}" stroke-width="1.3"/>`).join('')}
      <path d="M0,134 Q80,128 160,135 T320,131" fill="none" stroke="${INK}" stroke-width="1.8"/>
      <path d="M38,134 L50,103 L94,99 L110,134" fill="#fbf8f2" stroke="${INK}" stroke-width="1.8" stroke-linejoin="round"/>
      ${pip({ x: 72, y: 101, s: 0.2, head: -10 })}
      <path d="M330,30 Q300,70 268,52" fill="none" stroke="${INK}" stroke-width="1" stroke-dasharray="3 4"/>
      ${firefly(266, 52, 2.4)}
      <text x="230" y="168" font-size="11" class="note">slow push in →</text>`,
  },
  {
    dur: 0.7, label: 'A firefly drifts by. Pip notices: eyes go wide!', sfx: 'SFX: tiny "bweep?"',
    art: () => `
      <path d="M0,170 L120,170 L150,180" fill="none" stroke="${INK}" stroke-width="1.8"/>
      ${pip({ x: 90, y: 172, s: 0.62, head: 12, eyes: 'wide', armA: 30, armB: 30 })}
      <text x="128" y="44" font-size="30" font-weight="700" class="note">!</text>
      ${firefly(236, 64, 3.5)}
      <path d="M300,20 Q270,40 240,62" fill="none" stroke="${INK}" stroke-width="1" stroke-dasharray="3 4"/>`,
  },
  {
    dur: 0.4, label: 'Anticipation: Pip crouches, arms swing back…', sfx: 'SFX: servo whirr',
    art: () => `
      <path d="M0,150 L170,150 L190,180" fill="none" stroke="${INK}" stroke-width="1.8"/>
      ${pip({ x: 120, y: 150, s: 0.5, view: 'side', sq: 0.4, lean: 10, armA: -45, head: -6 })}
      <path d="M90,156 Q120,163 150,156" fill="none" stroke="${INK}" stroke-width="1.2"/>
      <path d="M96,162 Q120,168 144,162" fill="none" stroke="${INK}" stroke-width="1"/>
      ${firefly(262, 52, 3)}
      <text x="200" y="120" font-size="12" class="note">squash!</text>`,
  },
  {
    dur: 1.0, label: 'LEAP! Pip arcs up and grabs the firefly.', sfx: 'SFX: boing!',
    art: () => `
      <path d="M0,142 L60,142 L74,180" fill="none" stroke="${INK}" stroke-width="1.8"/>
      <path d="M74,180 Q200,160 320,166" fill="none" stroke="${INK}" stroke-width="1.4"/>
      <path d="M58,128 Q150,10 262,152" fill="none" stroke="#c0392b" stroke-width="1.6" stroke-dasharray="5 5"/>
      ${pip({ x: 150, y: 108, s: 0.38, view: 'side', sq: -0.3, lean: 22, armA: 120, tuck: 0.8 })}
      ${firefly(190, 56, 2.6, false)}
      <path d="M110,96 L96,104 M112,108 L98,116 M114,120 L100,128" stroke="${INK}" stroke-width="1.2" stroke-linecap="round"/>
      <text x="230" y="56" font-size="12" class="note">arc!</text>`,
  },
  {
    dur: 1.0, label: 'THUD. Pip lands (squash!) holding it in cupped hands.', sfx: 'SFX: thud + puff of dust',
    art: () => `
      <path d="M0,152 Q160,146 320,154" fill="none" stroke="${INK}" stroke-width="1.8"/>
      ${pip({ x: 196, y: 152, s: 0.48, sq: 0.45, eyes: 'closed', armA: -55, armB: -55 })}
      ${dust(160, 148, 1.1)}${dust(236, 147, 1.2)}${dust(134, 150, 0.7)}
      <text x="88" y="70" font-size="20" font-weight="700" class="note">THUD</text>`,
  },
  {
    dur: 1.7, label: 'Pip opens its hands… the firefly glows and floats away.', sfx: '♪ music swells',
    art: () => `
      ${pip({ x: 150, y: 250, s: 0.86, head: -10, eyes: 'happy', armA: 125, armB: 125 })}
      ${firefly(212, 30, 4)}
      <path d="M190,74 Q200,52 210,36" fill="none" stroke="${INK}" stroke-width="1" stroke-dasharray="3 4"/>
      <text x="246" y="70" font-size="13" class="note">✦</text><text x="176" y="20" font-size="10" class="note">✦</text>
      <text x="236" y="150" font-size="12" class="note">push in</text>`,
  },
];

const svg = (vb, inner, cls = '') => `<svg viewBox="${vb}" class="${cls}" preserveAspectRatio="xMidYMid meet" aria-hidden="true">${inner}</svg>`;

export function panelSVG(i) {
  return svg('0 0 320 180', `<g filter="url(#pencil)">${PANELS[i].art()}</g>`, 'panel-art');
}

// ---- Stage views ----
function storyView() {
  const lines = [
    ['h', 'Idea #7 — “Pip &amp; the Firefly”'],
    ['', 'A tiny robot who has only ever known machines…'],
    ['', 'One evening, a firefly drifts past. Pip has never seen one!'],
    ['', 'Pip <u>leaps</u> to catch it — then gently lets it go.'],
    ['n', 'Feeling: wonder ✶ (it’s not about keeping things)'],
    ['n', 'Shot 20 = the big leap!! ↘'],
  ];
  return `<div class="notebook">
    <div class="nb-lines">${lines.map(([k, t], i) => `<p class="hand ${k}" style="--d:${i * 0.45}s">${t}</p>`).join('')}</div>
    <div class="nb-doodle">${svg('0 0 200 200', `<g filter="url(#pencil)">
      ${pip({ x: 82, y: 186, s: 0.82, head: -14, eyes: 'wide', armA: 40, armB: 150 })}
      <path d="M120,40 C150,10 190,40 170,60 C150,80 140,50 165,35" fill="none" stroke="${INK}" stroke-width="1.2" stroke-dasharray="3 4"/>
      ${firefly(166, 34, 3)}</g>`)}</div>
  </div>`;
}

function exploreView() {
  const boxy = `<g transform="translate(95,300)">
      <rect x="-16" y="-34" width="10" height="34" fill="#fbf8f2" stroke="${INK}" stroke-width="2"/><rect x="6" y="-34" width="10" height="34" fill="#fbf8f2" stroke="${INK}" stroke-width="2"/>
      <rect x="-30" y="-110" width="60" height="78" rx="4" fill="#fbf8f2" stroke="${INK}" stroke-width="2"/>
      <rect x="-44" y="-102" width="12" height="48" fill="#fbf8f2" stroke="${INK}" stroke-width="2"/><rect x="32" y="-102" width="12" height="48" fill="#fbf8f2" stroke="${INK}" stroke-width="2"/>
      <rect x="-36" y="-172" width="72" height="58" rx="3" fill="#fbf8f2" stroke="${INK}" stroke-width="2"/>
      <circle cx="-14" cy="-146" r="8" fill="none" stroke="${INK}" stroke-width="2"/><circle cx="14" cy="-146" r="8" fill="none" stroke="${INK}" stroke-width="2"/>
      <path d="M-14,-126 L14,-126" stroke="${INK}" stroke-width="2"/>
      <path d="M-20,-172 L-26,-196 M20,-172 L26,-196" stroke="${INK}" stroke-width="2"/><circle cx="-26" cy="-199" r="4" fill="${INK}"/><circle cx="26" cy="-199" r="4" fill="${INK}"/></g>`;
  const lanky = `<g transform="translate(250,300)">
      <path d="M-6,-92 L-16,0 M6,-92 L16,0" stroke="${INK}" stroke-width="3" stroke-linecap="round"/>
      <rect x="-12" y="-170" width="24" height="82" rx="10" fill="#fbf8f2" stroke="${INK}" stroke-width="2"/>
      <path d="M-12,-160 Q-40,-120 -34,-80 M12,-160 Q40,-120 34,-80" fill="none" stroke="${INK}" stroke-width="2.5" stroke-linecap="round"/>
      <ellipse cx="0" cy="-192" rx="17" ry="22" fill="#fbf8f2" stroke="${INK}" stroke-width="2"/>
      <rect x="-12" y="-196" width="24" height="5" rx="2" fill="${INK}"/>
      <path d="M0,-214 L0,-232" stroke="${INK}" stroke-width="2"/></g>`;
  const round = pip({ x: 410, y: 300, s: 1.0, eyes: 'open', armA: 20, armB: 30 });
  const sw = ['shell', 'cream', 'visor', 'eye', 'bulb', 'metal'];
  return svg('0 0 640 360', `
    <g filter="url(#pencil)">${boxy}${lanky}${round}</g>
    <text x="95" y="346" text-anchor="middle" class="note">A · “too cold?”</text>
    <text x="250" y="346" text-anchor="middle" class="note">B · “a bit spooky”</text>
    <text x="410" y="346" text-anchor="middle" class="note">C · round + bouncy!</text>
    <ellipse cx="410" cy="204" rx="90" ry="120" fill="none" stroke="#d64545" stroke-width="3.5" filter="url(#pencil2)"/>
    <text x="478" y="78" class="note red" transform="rotate(-8 478 78)">YES! ✓</text>
    <g transform="translate(530,130)">
      <text x="0" y="-12" class="note small">palette</text>
      ${sw.map((k, i) => `<rect x="${(i % 2) * 40}" y="${Math.floor(i / 2) * 40}" width="34" height="34" rx="6" fill="${COL[k]}" stroke="${INK}" stroke-width="1.2"/>`).join('')}
    </g>
    <text x="526" y="268" class="note small">big head = cute</text>
    <text x="526" y="290" class="note small">screen face</text>
    <text x="526" y="308" class="note small">shows feelings</text>
    <text x="526" y="330" class="note small">wobbly antenna!</text>`, 'sheet');
}

function sheetView() {
  const guides = [300, 228, 148, 122].map((y) => `<line x1="20" x2="620" y1="${y}" y2="${y}" stroke="#7aa7d9" stroke-width="1" stroke-dasharray="6 5"/>`).join('');
  return svg('0 0 640 360', `
    ${guides}
    <text x="24" y="296" class="note small blue">ground</text>
    <text x="24" y="224" class="note small blue">shoulders</text>
    <text x="24" y="144" class="note small blue">eye line</text>
    ${pip({ x: 180, y: 300, s: 1.05, style: 'color', armA: 14, armB: 14 })}
    ${pip({ x: 340, y: 300, s: 1.05, style: 'color', view: 'side', armA: 8 })}
    ${pip({ x: 500, y: 300, s: 1.05, style: 'color', view: 'back', armA: 14, armB: 14 })}
    <text x="180" y="340" text-anchor="middle" class="note">FRONT</text>
    <text x="340" y="340" text-anchor="middle" class="note">SIDE</text>
    <text x="500" y="340" text-anchor="middle" class="note">BACK</text>
    <text x="620" y="40" text-anchor="end" class="note">PIP — model sheet v3</text>`, 'sheet');
}

function boardView() {
  return `<div class="boards">${PANELS.map((p, i) => `
    <figure class="board" style="--d:${i * 0.18}s">
      <div class="board-frame">${panelSVG(i)}<span class="board-no">${i + 1}</span></div>
      <figcaption>${p.label}</figcaption>
    </figure>`).join('')}</div>`;
}

function animaticView() {
  const total = PANELS.reduce((s, p) => s + p.dur, 0);
  return `<div class="animatic">
    <div class="am-screen">${PANELS.map((p, i) => `<div class="am-panel" data-i="${i}">${panelSVG(i)}</div>`).join('')}
      <div class="am-sfx" id="am-sfx"></div>
      <div class="am-tc" id="am-tc">sq010_sh020 · 00:00</div>
    </div>
    <div class="am-track">${PANELS.map((p, i) => `<span style="flex:${p.dur}" data-i="${i}">${i + 1}<small>${p.dur.toFixed(1)}s</small></span>`).join('')}<i id="am-head"></i></div>
    <div class="am-total">Total: ${total.toFixed(1)} s × 24 frames per second = <b>${Math.round(total * 24)} frames</b></div>
  </div>`;
}

// Mount the artwork for a stage; returns a cleanup function.
export function mountSketch(id, el, opts = {}) {
  let raf = 0;
  if (id === 'story') el.innerHTML = storyView();
  else if (id === 'concept') el.innerHTML = opts.page === 'sheet' ? sheetView() : exploreView();
  else if (id === 'storyboard') el.innerHTML = boardView();
  else if (id === 'animatic') {
    el.innerHTML = animaticView();
    const panels = [...el.querySelectorAll('.am-panel')], blocks = [...el.querySelectorAll('.am-track span')];
    const head = el.querySelector('#am-head'), sfx = el.querySelector('#am-sfx'), tc = el.querySelector('#am-tc');
    const total = PANELS.reduce((s, p) => s + p.dur, 0);
    const t0 = performance.now();
    let cur = -1;
    const tick = () => {
      const t = ((performance.now() - t0) / 1000) % (total + 0.6);
      let acc = 0, i = 0;
      while (i < PANELS.length - 1 && t >= acc + PANELS[i].dur) acc += PANELS[i++].dur;
      if (i !== cur) {
        cur = i;
        panels.forEach((p, k) => p.classList.toggle('on', k === i));
        blocks.forEach((b, k) => b.classList.toggle('on', k === i));
        sfx.textContent = PANELS[i].sfx;
      }
      const tt = Math.min(t, total);
      head.style.left = `${(tt / total) * 100}%`;
      tc.textContent = `sq010_sh020 · ${tt.toFixed(1).padStart(4, '0')}s · frame ${1001 + Math.min(143, Math.floor(tt * 24))}`;
      raf = requestAnimationFrame(tick);
    };
    tick();
  } else {
    el.innerHTML = '';
  }
  return () => cancelAnimationFrame(raf);
}
