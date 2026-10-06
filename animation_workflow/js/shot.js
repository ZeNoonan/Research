// Shot sq010_sh020: "Pip leaps for a firefly". Key poses, interpolation, camera move and the
// firefly's flight path. Everything is a pure function of time so the timeline can be scrubbed.
import * as THREE from 'three';
import { REST_POSE } from './pip.js';

export const SHOT = { len: 6.0, fps: 24, first: 1001, hold: 1.0 };
export const FRAMES = Math.round(SHOT.len * SHOT.fps);

const FIELDS = Object.keys(REST_POSE).filter((k) => !['blink', 'antX', 'antZ'].includes(k));

// Each key only lists what changed; missing values carry over from the previous key.
// tan: per-field [incoming, outgoing] slopes where the animator "broke" the tangents.
const RAW_KEYS = [
  { t: 0.0, label: 'Idle', x: -1.45, y: 0.62, z: 0, ry: 0.15, headPitch: 0.25, headYaw: -0.3, headRoll: 0.05, armLUp: 0.14, armRUp: 0.14, armLFwd: 0.05, armRFwd: 0.05 },
  { t: 0.75, headYaw: -0.05, headPitch: 0.32, headRoll: -0.05 },
  { t: 1.25, label: 'Notice', headYaw: 0.6, headPitch: 0.42, headRoll: 0.12, eyeSize: 1.38, sq: -0.08, ry: 0.35, armLUp: 0.32, armRUp: 0.32 },
  { t: 1.95, label: 'Anticipation', sq: 0.38, lean: 0.35, headPitch: 0.5, headYaw: 0.35, headRoll: 0, armLFwd: -0.9, armRFwd: -0.9, armLUp: 0.35, armRUp: 0.35, ry: 0.6, eyeSize: 1.2 },
  { t: 2.3, label: 'Take-off', x: -1.2, y: 0.8, sq: -0.4, lean: 0.05, headPitch: 0.35, armLFwd: 2.3, armRFwd: 2.3, armLUp: 0.1, armRUp: 0.1, ry: 0.75, tan: { y: [null, 2.4] } },
  { t: 2.75, label: 'Catch!', x: -0.35, y: 1.3, sq: -0.05, lean: -0.1, headPitch: 0.05, headYaw: 0.12, armLFwd: 1.75, armRFwd: 1.75, armLUp: -0.5, armRUp: -0.5, legTuck: 0.8, ry: 0.8 },
  { t: 3.1, x: 0.35, y: 0.62, sq: -0.22, lean: 0.12, headPitch: -0.15, armLFwd: 1.5, armRFwd: 1.5, armLUp: -0.6, armRUp: -0.6, legTuck: 0.2, ry: 0.65 },
  { t: 3.29, x: 0.72, y: 0.04, sq: -0.25, legTuck: 0.0 },
  { t: 3.33, label: 'Land', x: 0.75, y: 0, sq: 0.48, lean: 0.35, headPitch: -0.35, headYaw: 0.05, armLFwd: 1.25, armRFwd: 1.25, armLUp: -0.55, armRUp: -0.55, ry: 0.5, eyeSize: 1.0, tan: { y: [-3.6, 0], x: [1.0, 0] } },
  { t: 3.62, sq: -0.1, lean: -0.06, headPitch: -0.1 },
  { t: 4.0, label: 'Look', sq: 0.02, lean: 0.12, headPitch: -0.5, headYaw: 0, armLFwd: 1.45, armRFwd: 1.45, armLUp: -0.62, armRUp: -0.62, ry: 0.35 },
  { t: 4.5, label: 'Open hands', armLUp: 0.25, armRUp: 0.25, armLFwd: 1.55, armRFwd: 1.55, headPitch: -0.4, eyeSize: 1.25, sq: -0.04 },
  { t: 5.15, label: 'Let go', headPitch: 0.55, headYaw: 0.12, headRoll: 0.08, armLFwd: 2.0, armRFwd: 1.7, armLUp: 0.45, armRUp: 0.35, sq: -0.06, happy: 1, eyeSize: 1.1 },
  { t: 6.0, headPitch: 0.7, headRoll: 0.16, sq: 0.04, armLFwd: 0.6, armRFwd: 0.5, armLUp: 0.3, armRUp: 0.3, lean: -0.08 },
];

export const KEYS = (() => {
  let prev = { ...REST_POSE };
  return RAW_KEYS.map((k) => {
    const full = { ...prev };
    for (const f of FIELDS) if (k[f] !== undefined) full[f] = k[f];
    prev = full;
    return { t: k.t, label: k.label, pose: full, tan: k.tan || {} };
  });
})();

// Auto tangents (like Maya's "auto"): flat at peaks/valleys and holds, smooth elsewhere.
const SLOPES = (() => {
  const out = KEYS.map(() => ({}));
  for (const f of FIELDS) {
    for (let i = 0; i < KEYS.length; i++) {
      const p = KEYS[i].pose[f];
      const a = i > 0 ? (p - KEYS[i - 1].pose[f]) / (KEYS[i].t - KEYS[i - 1].t) : 0;
      const b = i < KEYS.length - 1 ? (KEYS[i + 1].pose[f] - p) / (KEYS[i + 1].t - KEYS[i].t) : 0;
      let m = a * b <= 0 ? 0 : (a + b) / 2;
      const o = KEYS[i].tan[f];
      out[i][f] = [o && o[0] != null ? o[0] : m, o && o[1] != null ? o[1] : m];
    }
  }
  return out;
})();

function hermite(p0, m0, p1, m1, h, s) {
  const s2 = s * s, s3 = s2 * s;
  return (2 * s3 - 3 * s2 + 1) * p0 + (s3 - 2 * s2 + s) * h * m0 + (-2 * s3 + 3 * s2) * p1 + (s3 - s2) * h * m1;
}

function keyIndex(t) {
  let i = 0;
  while (i < KEYS.length - 1 && KEYS[i + 1].t <= t) i++;
  return i;
}

const bump = (t, c, w) => Math.max(0, 1 - Math.abs(t - c) / w);

// mode: 'blocking' (stepped key poses), 'spline' (smooth in-betweens), 'polish' (+ overlap, blinks, breathing)
export function evalPose(t, mode, out = {}) {
  t = THREE.MathUtils.clamp(t, 0, SHOT.len);
  const i = keyIndex(t);
  const k0 = KEYS[i], k1 = KEYS[Math.min(i + 1, KEYS.length - 1)];
  if (mode === 'blocking' || k0 === k1) {
    Object.assign(out, REST_POSE, k0.pose);
  } else {
    const h = k1.t - k0.t, s = (t - k0.t) / h;
    Object.assign(out, REST_POSE);
    for (const f of FIELDS) out[f] = hermite(k0.pose[f], SLOPES[i][f][1], k1.pose[f], SLOPES[i + 1][f][0], h, s);
  }
  out.blink = 0;
  if (mode === 'polish') {
    out.blink = Math.max(bump(t, 0.62, 0.07), bump(t, 4.04, 0.08), bump(t, 5.66, 0.07));
    const grounded = (t < 1.8 ? 1 : 0) + THREE.MathUtils.smoothstep(t, 4.1, 4.6);
    out.sq += 0.018 * Math.sin(t * 3.1) * Math.min(1, grounded);
    out.headRoll += 0.02 * Math.sin(t * 1.7 + 0.5);
  }
  return out;
}

export function frameOf(t) {
  return SHOT.first + Math.min(FRAMES - 1, Math.floor(t * SHOT.fps));
}

const ease = (x) => 0.5 - 0.5 * Math.cos(Math.PI * THREE.MathUtils.clamp(x, 0, 1));
const CAM_A = { pos: new THREE.Vector3(-0.4, 1.1, 7.7), at: new THREE.Vector3(-0.35, 1.38, 0) };
const CAM_B = { pos: new THREE.Vector3(0.45, 1.0, 6.0), at: new THREE.Vector3(0.6, 1.3, 0) };
export const SHOT_HFOV = 50;

// The camera move Layout designed: a slow drift right that pushes in for the emotional ending.
export function shotCamera(t, cam) {
  const k = ease(t / SHOT.len);
  cam.position.lerpVectors(CAM_A.pos, CAM_B.pos, k);
  const at = new THREE.Vector3().lerpVectors(CAM_A.at, CAM_B.at, k);
  cam.lookAt(at);
  return at;
}

// Pre-simulated data for one interpolation mode: hand and foot positions over time, and the
// antenna spring (secondary motion) which only "polish" mode adds.
export class ShotCache {
  constructor(pip, mode) {
    this.mode = mode;
    this.rate = 96;
    const n = Math.ceil((SHOT.len + SHOT.hold) * this.rate) + 2;
    this.n = n;
    this.hands = new Float32Array(n * 3);
    this.feet = new Float32Array(n * 3);
    this.ant = new Float32Array(n * 2);
    const pose = {}, v = new THREE.Vector3(), a = new THREE.Vector3(), b = new THREE.Vector3();
    const rest = new Float32Array(n * 3), quats = [];
    const q = new THREE.Quaternion();
    for (let i = 0; i < n; i++) {
      const t = i / this.rate;
      evalPose(t, mode, pose);
      pip.applyPose(pose, { antenna: false });
      pip.root.updateMatrixWorld(true);
      pip.handsMid(v);
      this.hands.set([v.x, v.y, v.z], i * 3);
      pip.footL.getWorldPosition(a);
      pip.footR.getWorldPosition(b);
      a.add(b).multiplyScalar(0.5);
      this.feet.set([a.x, a.y - 0.05, a.z], i * 3);
      pip.antBase.getWorldPosition(a);
      pip.antBase.getWorldQuaternion(q);
      b.set(0, 0.24, 0).applyQuaternion(q).add(a);
      rest.set([b.x, b.y, b.z], i * 3);
      quats.push(q.clone());
    }
    if (mode === 'polish') this.simulateAntenna(rest, quats);
  }

  simulateAntenna(rest, quats) {
    const k = 230, c = 7.5, sub = 5, dt = 1 / (this.rate * sub);
    const p = new THREE.Vector3(rest[0], rest[1], rest[2]), vel = new THREE.Vector3();
    const r = new THREE.Vector3(), r0 = new THREE.Vector3(), r1 = new THREE.Vector3(), acc = new THREE.Vector3();
    const local = new THREE.Vector3(), inv = new THREE.Quaternion();
    for (let i = 0; i < this.n; i++) {
      r0.fromArray(rest, i * 3);
      r1.fromArray(rest, Math.min(i + 1, this.n - 1) * 3);
      for (let s = 0; s < sub; s++) {
        r.lerpVectors(r0, r1, s / sub);
        acc.subVectors(r, p).multiplyScalar(k).addScaledVector(vel, -c);
        vel.addScaledVector(acc, dt);
        p.addScaledVector(vel, dt);
      }
      local.subVectors(p, r0).applyQuaternion(inv.copy(quats[i]).invert());
      this.ant[i * 2] = THREE.MathUtils.clamp(local.x, -0.14, 0.14);
      this.ant[i * 2 + 1] = THREE.MathUtils.clamp(local.z, -0.14, 0.14);
    }
  }

  sample(arr, dim, t, out) {
    const f = THREE.MathUtils.clamp(t, 0, (this.n - 1) / this.rate) * this.rate;
    const i = Math.min(Math.floor(f), this.n - 2), s = f - i;
    for (let d = 0; d < dim; d++) out[d] = arr[i * dim + d] * (1 - s) + arr[(i + 1) * dim + d] * s;
    return out;
  }

  handsAt(t, v) {
    const o = this.sample(this.hands, 3, t, [0, 0, 0]);
    return v.set(o[0], o[1], o[2]);
  }

  feetAt(t, v) {
    const o = this.sample(this.feet, 3, t, [0, 0, 0]);
    return v.set(o[0], o[1], o[2]);
  }

  antennaAt(t) {
    if (this.mode !== 'polish') return [0, 0];
    return this.sample(this.ant, 2, t, [0, 0]);
  }
}

// ---- The firefly ------------------------------------------------------------------------
export const CATCH_T = 2.75, RELEASE_T = 4.55, LAND_T = 3.33, TAKEOFF_T = 2.3;
const FREE = new THREE.CatmullRomCurve3([
  new THREE.Vector3(3.4, 1.95, -0.9), new THREE.Vector3(1.8, 1.35, -0.4), new THREE.Vector3(0.7, 1.68, -0.1),
  new THREE.Vector3(-0.05, 1.42, 0.18), new THREE.Vector3(-0.3, 1.25, 0.3),
]);
const FREE_END = 2.45;

function wobble(t, v, amt = 1) {
  return v.set(0.05 * Math.sin(7.3 * t), 0.07 * Math.sin(5.1 * t + 1), 0.04 * Math.cos(6.2 * t)).multiplyScalar(amt);
}

export function fireflyAt(t, cache, out) {
  const w = new THREE.Vector3(), h = new THREE.Vector3();
  if (t < CATCH_T) {
    FREE.getPoint(THREE.MathUtils.clamp(t / FREE_END, 0, 1), out).add(wobble(t, w));
    const k = THREE.MathUtils.smoothstep(t, 2.3, CATCH_T);
    if (k > 0) out.lerp(cache.handsAt(t, h).add(w.set(0, 0.03, 0.03)), k);
    return out;
  }
  if (t < RELEASE_T) return cache.handsAt(t, out).add(w.set(0, 0.03, 0.03));
  const d = t - RELEASE_T, e = Math.pow(d, 1.35);
  cache.handsAt(RELEASE_T, out).add(w.set(0, 0.03, 0.03));
  out.x += 0.32 * e;
  out.y += 0.78 * e;
  out.z -= 0.2 * e;
  return out.add(wobble(t, w, Math.min(1, d * 1.5)));
}

// How brightly it glows: hidden in Pip's hands, then a big flare when the hands open.
export function fireflyGlow(t) {
  if (t < CATCH_T - 0.05) return 1;
  if (t < 4.42) return THREE.MathUtils.lerp(1, 0.32, THREE.MathUtils.smoothstep(t, CATCH_T - 0.05, CATCH_T + 0.1));
  if (t < 4.75) return THREE.MathUtils.lerp(0.32, 1.5, THREE.MathUtils.smoothstep(t, 4.42, 4.75));
  return THREE.MathUtils.lerp(1.5, 1.0, THREE.MathUtils.smoothstep(t, 4.75, 5.6));
}
