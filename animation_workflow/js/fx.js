// FX: firefly glow and trail, landing dust, release sparkles and background fireflies.
// Like the animation, every particle is a pure function of shot time, so scrubbing works.
import * as THREE from 'three';
import { rng } from './textures.js';
import { fireflyAt, fireflyGlow, CATCH_T, RELEASE_T, LAND_T, TAKEOFF_T } from './shot.js';

const VERT = /* glsl */`
  attribute float aSize; attribute float aAlpha; attribute vec3 aColor;
  uniform float uScale; uniform float uRaw;
  varying vec3 vColor; varying float vAlpha;
  void main() {
    vColor = aColor; vAlpha = aAlpha;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mv;
    gl_PointSize = mix(aSize * uScale / -mv.z, 5.0, uRaw);
  }`;

const FRAG = /* glsl */`
  uniform sampler2D uMap; uniform float uRaw;
  varying vec3 vColor; varying float vAlpha;
  void main() {
    if (vAlpha < 0.004) discard;
    if (uRaw > 0.5) {
      gl_FragColor = vec4(mix(vColor, vec3(1.0), 0.35), 1.0);
    } else {
      gl_FragColor = vec4(vColor, texture2D(uMap, gl_PointCoord).a * vAlpha);
    }
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }`;

class Particles {
  constructor(max, map, blending) {
    this.max = max;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(max * 3), 3));
    g.setAttribute('aColor', new THREE.BufferAttribute(new Float32Array(max * 3), 3));
    g.setAttribute('aAlpha', new THREE.BufferAttribute(new Float32Array(max), 1));
    g.setAttribute('aSize', new THREE.BufferAttribute(new Float32Array(max), 1));
    this.uniforms = { uMap: { value: map }, uScale: { value: 500 }, uRaw: { value: 0 } };
    const m = new THREE.ShaderMaterial({
      uniforms: this.uniforms, vertexShader: VERT, fragmentShader: FRAG,
      transparent: true, depthWrite: false, blending,
    });
    this.points = new THREE.Points(g, m);
    this.points.frustumCulled = false;
    this.n = 0;
  }

  begin() { this.n = 0; }

  push(p, color, alpha, size) {
    if (this.n >= this.max || alpha <= 0.004) return;
    const a = this.points.geometry.attributes, i = this.n++;
    a.position.setXYZ(i, p.x, p.y, p.z);
    a.aColor.setXYZ(i, color[0], color[1], color[2]);
    a.aAlpha.setX(i, alpha);
    a.aSize.setX(i, size);
  }

  end() {
    const g = this.points.geometry;
    g.setDrawRange(0, this.n);
    for (const k of ['position', 'aColor', 'aAlpha', 'aSize']) g.attributes[k].needsUpdate = true;
  }
}

export class FX {
  constructor(lib) {
    const map = lib.tex.glow;
    this.glow = new Particles(4, map, THREE.AdditiveBlending);
    this.trail = new Particles(160, map, THREE.AdditiveBlending);
    this.sparks = new Particles(80, map, THREE.AdditiveBlending);
    this.ambient = new Particles(60, map, THREE.AdditiveBlending);
    this.dust = new Particles(90, map, THREE.NormalBlending);
    this.systems = [this.dust, this.ambient, this.trail, this.sparks, this.glow];
    this.group = new THREE.Group();
    this.group.name = 'fx';
    for (const s of this.systems) this.group.add(s.points);

    this.body = new THREE.Mesh(new THREE.SphereGeometry(0.022, 12, 8), new THREE.MeshStandardMaterial());
    this.body.userData.role = 'fx.firefly';
    this.proxy = new THREE.Mesh(new THREE.SphereGeometry(0.06, 16, 10), new THREE.MeshStandardMaterial({ color: 0xffd84a, roughness: 0.6 }));
    this.light = new THREE.PointLight(0xffcf6b, 0, 4, 2);

    const r = rng(42);
    this.seeds = Array.from({ length: 200 }, () => [r(), r(), r(), r()]);
    this.ambientBase = Array.from({ length: 46 }, () => [
      (r() - 0.5) * 13, 0.3 + r() * 2.6, -1.2 - r() * 7, r() * 6.28, 0.6 + r() * 1.2,
    ]);
    this.level = 'off';
    this.count = 0;
  }

  // level: 'off' | 'proxy' (a stand-in ball, as animators see it) | 'full'
  setLevel(level) {
    this.level = level;
    this.group.visible = level === 'full';
    this.body.visible = level === 'full';
    this.proxy.visible = level === 'proxy';
  }

  setRaw(on) {
    for (const s of this.systems) s.uniforms.uRaw.value = on ? 1 : 0;
  }

  setScale(px) {
    for (const s of this.systems) s.uniforms.uScale.value = px;
  }

  update(t, cache, lightOn) {
    const pos = new THREE.Vector3(), p = new THREE.Vector3();
    fireflyAt(t, cache, pos);
    this.body.position.copy(pos);
    this.proxy.position.copy(pos);
    const glow = fireflyGlow(t);
    this.light.position.copy(pos);
    this.light.intensity = lightOn ? 0.2 * glow : 0;
    if (this.level !== 'full') { this.count = 0; return; }

    // The firefly's own glow: a hot core plus a soft halo.
    this.glow.begin();
    this.glow.push(pos, [1.0, 0.95, 0.6], 0.9 * Math.min(1, glow), 0.08 + 0.03 * glow);
    this.glow.push(pos, [1.0, 0.8, 0.35], 0.3 * glow, 0.16 * glow + 0.1);
    this.glow.end();

    // Trail: a particle born every 1/40 s that drifts down and fades over one second.
    this.trail.begin();
    const rate = 40, life = 1.0;
    const first = Math.max(0, Math.ceil((t - life) * rate));
    for (let k = first; k <= Math.floor(t * rate); k++) {
      const tb = k / rate, age = t - tb, sd = this.seeds[k % 200];
      fireflyAt(tb, cache, p);
      p.x += (sd[0] - 0.5) * 0.25 * age;
      p.y += (sd[1] - 0.6) * 0.18 * age - 0.06 * age;
      p.z += (sd[2] - 0.5) * 0.25 * age;
      const hidden = tb > CATCH_T && tb < RELEASE_T - 0.1 ? 0.2 : 1;
      this.trail.push(p, [1.0, 0.92, 0.45], Math.pow(1 - age / life, 1.6) * 0.75 * hidden, 0.07 * (1 - 0.5 * age));
    }
    this.trail.end();

    // Dust: two bursts, a small one at take-off and a bigger one on landing.
    this.dust.begin();
    const burst = (t0, origin, n, power, offset) => {
      const age = t - t0;
      if (age < 0 || age > 1.6) return;
      for (let i = 0; i < n; i++) {
        const sd = this.seeds[(i + offset) % 200];
        const a = sd[0] * Math.PI * 2, sp = power * (0.5 + sd[1]);
        const travel = (1 - Math.exp(-3.2 * age)) / 3.2;
        p.set(origin.x + Math.cos(a) * sp * travel, origin.y + 0.03 + (0.15 + sd[2] * 0.35) * travel + 0.04 * age, origin.z + Math.sin(a) * sp * travel * 0.8);
        const f = 1 - age / 1.6;
        this.dust.push(p, [0.62, 0.58, 0.66], 0.5 * f * f, 0.12 + age * 0.3 * (0.6 + sd[3]));
      }
    };
    burst(TAKEOFF_T - 0.05, cache.feetAt(TAKEOFF_T - 0.05, new THREE.Vector3()), 14, 0.6, 50);
    burst(LAND_T, cache.feetAt(LAND_T, new THREE.Vector3()), 46, 1.15, 0);
    this.dust.end();

    // Sparkles when Pip opens its hands.
    this.sparks.begin();
    const sAge = t - RELEASE_T + 0.1;
    if (sAge > 0 && sAge < 1.5) {
      const o = fireflyAt(RELEASE_T - 0.1, cache, new THREE.Vector3());
      for (let i = 0; i < 40; i++) {
        const sd = this.seeds[(i + 100) % 200];
        const a = sd[0] * Math.PI * 2, up = 0.4 + sd[1] * 0.8, sp = 0.35 + sd[2] * 0.5;
        p.set(o.x + Math.cos(a) * sp * sAge, o.y + up * sAge - 0.35 * sAge * sAge, o.z + Math.sin(a) * sp * sAge * 0.7);
        const tw = 0.6 + 0.4 * Math.sin(t * 30 + i * 2.1);
        this.sparks.push(p, [1.0, 0.82, 0.4], (1 - sAge / 1.5) * tw, 0.045);
      }
    }
    this.sparks.end();

    // Other fireflies drifting in the background.
    this.ambient.begin();
    for (const [x, y, z, ph, sp] of this.ambientBase) {
      p.set(x + 0.35 * Math.sin(t * 0.5 * sp + ph), y + 0.22 * Math.sin(t * 0.8 * sp + ph * 2), z + 0.3 * Math.cos(t * 0.4 * sp + ph));
      const blink = 0.5 + 0.5 * Math.sin(t * 1.7 * sp + ph * 3);
      this.ambient.push(p, [0.85, 1.0, 0.5], 0.25 + 0.75 * blink * blink, 0.12);
    }
    this.ambient.end();

    this.count = this.systems.reduce((n, s) => n + s.n, 0);
  }
}
