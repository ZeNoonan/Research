// Procedural textures, painted on <canvas> so the site needs no image files.
import * as THREE from 'three';

// Small deterministic RNG so every visit paints identical textures.
export function rng(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function canvas(w, h) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  return c;
}

function speckle(g, w, h, rand, count, colors, rMin, rMax, alpha) {
  for (let i = 0; i < count; i++) {
    g.globalAlpha = alpha * (0.4 + rand() * 0.6);
    g.fillStyle = colors[(rand() * colors.length) | 0];
    g.beginPath();
    g.arc(rand() * w, rand() * h, rMin + rand() * (rMax - rMin), 0, Math.PI * 2);
    g.fill();
  }
  g.globalAlpha = 1;
}

export function toTexture(c, { srgb = true, repeat = null } = {}) {
  const t = new THREE.CanvasTexture(c);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  if (repeat) {
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.repeat.set(repeat[0], repeat[1]);
  }
  t.anisotropy = 4;
  return t;
}

// The classic "UV test grid": every square is labelled so stretching is obvious.
export function checkerCanvas() {
  const c = canvas(512, 512), g = c.getContext('2d'), n = 8, s = 64;
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.font = 'bold 22px system-ui, sans-serif';
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      const hue = (x * 45 + y * 12) % 360;
      const light = (x + y) % 2 === 0;
      g.fillStyle = light ? `hsl(${hue} 70% 66%)` : `hsl(${hue} 35% 26%)`;
      g.fillRect(x * s, y * s, s, s);
      g.fillStyle = light ? '#15151c' : '#f4f4f8';
      g.fillText(String.fromCharCode(65 + x) + (n - y), x * s + s / 2, y * s + s / 2);
    }
  }
  g.strokeStyle = 'rgba(255,255,255,.55)';
  g.lineWidth = 2;
  for (let i = 0; i <= n; i++) {
    g.beginPath(); g.moveTo(i * s, 0); g.lineTo(i * s, 512); g.stroke();
    g.beginPath(); g.moveTo(0, i * s); g.lineTo(512, i * s); g.stroke();
  }
  return c;
}

// Torso: LatheGeometry UVs, u wraps around (u = 0 is the back), v runs bottom to top.
export function torsoCanvas() {
  const w = 512, h = 256, c = canvas(w, h), g = c.getContext('2d'), r = rng(7);
  const grd = g.createLinearGradient(0, 0, 0, h);
  grd.addColorStop(0, '#f8995a');
  grd.addColorStop(0.55, '#ee7a3a');
  grd.addColorStop(1, '#d8652c');
  g.fillStyle = grd;
  g.fillRect(0, 0, w, h);
  speckle(g, w, h, r, 2200, ['#fbb07a', '#d4602a', '#e46f34'], 0.6, 2.2, 0.35);

  g.strokeStyle = 'rgba(110,40,12,.55)';
  g.lineWidth = 2;
  g.beginPath(); g.moveTo(0, 64); g.lineTo(w, 64); g.stroke();

  g.fillStyle = '#c4562a';
  g.fillRect(0, 196, w, 22);
  g.fillStyle = 'rgba(255,220,190,.35)';
  g.fillRect(0, 196, w, 2);
  for (let x = 8; x < w; x += 32) {
    g.fillStyle = '#6e2f15';
    g.beginPath(); g.arc(x, 207, 3.4, 0, 7); g.fill();
    g.fillStyle = 'rgba(255,230,200,.7)';
    g.beginPath(); g.arc(x - 1, 206, 1.3, 0, 7); g.fill();
  }

  // Stencilled "07" on the back; drawn at both edges so it wraps over the seam.
  g.fillStyle = 'rgba(248,238,224,.93)';
  g.font = '900 54px "Arial Black", Arial, sans-serif';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  for (const x of [0, w]) {
    g.save();
    g.translate(x, 128);
    g.scale(1, 1.6);
    g.fillText('07', 0, 0);
    g.restore();
  }

  g.strokeStyle = 'rgba(255,236,214,.55)';
  g.lineWidth = 1;
  for (let i = 0; i < 46; i++) {
    const x = r() * w, y = r() * h, a = r() * Math.PI, l = 4 + r() * 14;
    g.beginPath(); g.moveTo(x, y); g.lineTo(x + Math.cos(a) * l, y + Math.sin(a) * l); g.stroke();
  }
  return c;
}

// Head: SphereGeometry UVs, u = 0.25 faces front, v = 1 at the top.
export function headCanvas() {
  const w = 512, h = 256, c = canvas(w, h), g = c.getContext('2d'), r = rng(11);
  const grd = g.createLinearGradient(0, 0, 0, h);
  grd.addColorStop(0, '#fbf6ec');
  grd.addColorStop(0.6, '#efe5d5');
  grd.addColorStop(1, '#d9ccb8');
  g.fillStyle = grd;
  g.fillRect(0, 0, w, h);
  speckle(g, w, h, r, 1600, ['#ffffff', '#e0d3bf', '#d6c8b2'], 0.5, 1.8, 0.3);

  // An orange "racing stripe" over the crown, front to back.
  g.fillStyle = '#ee7a3a';
  for (const x of [128, 384]) g.fillRect(x - 14, 0, 28, 52);
  g.fillStyle = '#ee7a3a';
  g.fillRect(0, 0, w, 8);

  g.strokeStyle = 'rgba(120,100,80,.45)';
  g.lineWidth = 1.5;
  g.beginPath(); g.moveTo(0, 168); g.lineTo(w, 168); g.stroke();
  g.beginPath(); g.moveTo(384, 52); g.lineTo(384, 256); g.stroke();

  g.strokeStyle = 'rgba(130,110,90,.35)';
  g.lineWidth = 1;
  for (let i = 0; i < 30; i++) {
    const x = r() * w, y = 30 + r() * 200, a = r() * Math.PI, l = 3 + r() * 10;
    g.beginPath(); g.moveTo(x, y); g.lineTo(x + Math.cos(a) * l, y + Math.sin(a) * l); g.stroke();
  }
  return c;
}

// Belly panel: a flattened sphere, front of it is u = 0.25.
export function bellyCanvas() {
  const w = 512, h = 256, c = canvas(w, h), g = c.getContext('2d'), r = rng(5);
  g.fillStyle = '#f1e8da';
  g.fillRect(0, 0, w, h);
  speckle(g, w, h, r, 900, ['#ffffff', '#ddd0bc'], 0.5, 1.6, 0.3);
  const btn = [['#ff5e7a', 100], ['#ffd25e', 128], ['#5ee08f', 156]];
  for (const [col, x] of btn) {
    g.fillStyle = '#3a3330';
    g.beginPath(); g.ellipse(x, 104, 11, 16, 0, 0, 7); g.fill();
    g.fillStyle = col;
    g.beginPath(); g.ellipse(x, 103, 8, 12, 0, 0, 7); g.fill();
    g.fillStyle = 'rgba(255,255,255,.7)';
    g.beginPath(); g.ellipse(x - 2, 98, 2.5, 4, 0, 0, 7); g.fill();
  }
  g.strokeStyle = '#8a7c6c';
  g.lineWidth = 3;
  for (let i = 0; i < 3; i++) {
    g.beginPath(); g.moveTo(104, 140 + i * 11); g.lineTo(152, 140 + i * 11); g.stroke();
  }
  return c;
}

export function metalCanvas() {
  const w = 256, h = 256, c = canvas(w, h), g = c.getContext('2d'), r = rng(3);
  g.fillStyle = '#b4bcc6';
  g.fillRect(0, 0, w, h);
  for (let i = 0; i < 500; i++) {
    const y = r() * h;
    g.strokeStyle = r() > 0.5 ? 'rgba(255,255,255,.18)' : 'rgba(60,70,80,.16)';
    g.lineWidth = 0.5 + r();
    g.beginPath(); g.moveTo(r() * w - 60, y); g.lineTo(r() * w + 60, y); g.stroke();
  }
  return c;
}

export function rubberCanvas() {
  const w = 256, h = 256, c = canvas(w, h), g = c.getContext('2d'), r = rng(9);
  g.fillStyle = '#2f3441';
  g.fillRect(0, 0, w, h);
  speckle(g, w, h, r, 1400, ['#3c4252', '#262a35', '#454c5e'], 0.5, 2, 0.6);
  return c;
}

export function groundCanvas() {
  const w = 512, h = 512, c = canvas(w, h), g = c.getContext('2d'), r = rng(21);
  g.fillStyle = '#2d5246';
  g.fillRect(0, 0, w, h);
  speckle(g, w, h, r, 260, ['#365f50', '#24453c', '#3f6c57', '#2a4a41'], 10, 34, 0.45);
  speckle(g, w, h, r, 2600, ['#4b7d62', '#1f3c35', '#5a8a6a'], 0.6, 2.4, 0.5);
  return c;
}

export function rockCanvas() {
  const w = 256, h = 256, c = canvas(w, h), g = c.getContext('2d'), r = rng(31);
  g.fillStyle = '#8b91a5';
  g.fillRect(0, 0, w, h);
  speckle(g, w, h, r, 160, ['#9aa0b4', '#7a8094', '#a6a3b0'], 6, 22, 0.4);
  speckle(g, w, h, r, 1800, ['#6c7184', '#b0b5c4', '#5f6b6a'], 0.5, 2, 0.5);
  return c;
}

export function studioFloorCanvas() {
  const w = 512, h = 512, c = canvas(w, h), g = c.getContext('2d');
  const grd = g.createRadialGradient(256, 256, 20, 256, 256, 256);
  grd.addColorStop(0, '#6d717d');
  grd.addColorStop(1, '#4a4e59');
  g.fillStyle = grd;
  g.fillRect(0, 0, w, h);
  g.strokeStyle = 'rgba(255,255,255,.08)';
  g.lineWidth = 2;
  for (let i = 1; i < 6; i++) {
    g.beginPath(); g.arc(256, 256, i * 42, 0, Math.PI * 2); g.stroke();
  }
  for (let i = 0; i < 12; i++) {
    const a = (i / 12) * Math.PI * 2;
    g.beginPath(); g.moveTo(256, 256); g.lineTo(256 + Math.cos(a) * 256, 256 + Math.sin(a) * 256); g.stroke();
  }
  return c;
}

// Soft round sprite used for glows, particles and blob shadows.
export function glowCanvas(inner = 0.18) {
  const s = 128, c = canvas(s, s), g = c.getContext('2d');
  const grd = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  grd.addColorStop(0, 'rgba(255,255,255,1)');
  grd.addColorStop(inner, 'rgba(255,255,255,.55)');
  grd.addColorStop(0.5, 'rgba(255,255,255,.14)');
  grd.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grd;
  g.fillRect(0, 0, s, s);
  return c;
}
