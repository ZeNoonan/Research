// The set (dusk meadow with a rock), the sky, the asset "turntable" studio and the layout camera gizmo.
import * as THREE from 'three';
import { rng } from './textures.js';

function mesh(geo, role, { x = 0, y = 0, z = 0, ry = 0, s = null, cast = true, receive = true } = {}) {
  const m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial());
  m.userData.role = role;
  m.position.set(x, y, z);
  m.rotation.y = ry;
  if (s) Array.isArray(s) ? m.scale.set(s[0], s[1], s[2]) : m.scale.setScalar(s);
  m.castShadow = cast;
  m.receiveShadow = receive;
  return m;
}

// Gentle hills everywhere except the flat "stage" where the action happens.
export function groundHeight(x, z) {
  const r = Math.hypot(x, z + 1);
  const k = THREE.MathUtils.smoothstep(r, 4, 9);
  return k * (0.35 * Math.sin(x * 0.45) * Math.cos(z * 0.38) + 0.25 * Math.sin(x * 0.2 + z * 0.3) + 0.3);
}

function rockGeometry(rTop, rBot, h, seed) {
  const g = new THREE.CylinderGeometry(rTop, rBot, h, 10, 3);
  g.translate(0, h / 2, 0);
  const r = rng(seed), p = g.attributes.position, v = new THREE.Vector3();
  const seen = new Map();
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i);
    const key = `${v.x.toFixed(4)},${v.y.toFixed(4)},${v.z.toFixed(4)}`;
    if (!seen.has(key)) {
      const rad = Math.hypot(v.x, v.z);
      const top = v.y > h - 0.001;
      const jitter = top ? (rad > 0.3 ? -0.04 * r() : 0) : 0;
      const push = rad > 0.01 && !top ? 1 + (r() - 0.5) * 0.18 : 1;
      seen.set(key, [push, jitter, (r() - 0.5) * 0.05]);
    }
    const [push, jitter, dy] = seen.get(key);
    p.setXYZ(i, v.x * push, v.y + jitter + (v.y > 0.001 && v.y < h - 0.001 ? dy : 0), v.z * push);
  }
  g.computeVertexNormals();
  return g;
}

function tree(group, x, z, h, variant) {
  const y = groundHeight(x, z);
  group.add(mesh(new THREE.CylinderGeometry(0.05, 0.09, h * 0.4, 6), 'env.trunk', { x, y: y + h * 0.2, z }));
  for (let i = 0; i < 3; i++) {
    const r = (0.62 - i * 0.15) * h * 0.42;
    const cone = new THREE.ConeGeometry(r, h * 0.42, 7);
    group.add(mesh(cone, i % 2 === variant ? 'env.foliage' : 'env.foliage2', { x, y: y + h * (0.42 + i * 0.2), z, ry: i * 0.7 + x }));
  }
}

function mushroom(group, x, z, h, r, tilt = 0) {
  const g = new THREE.Group();
  g.position.set(x, 0, z);
  g.rotation.z = tilt;
  g.add(mesh(new THREE.CylinderGeometry(r * 0.28, r * 0.38, h, 8), 'env.stem', { y: h / 2 }));
  const cap = new THREE.SphereGeometry(r, 14, 7, 0, Math.PI * 2, 0, Math.PI / 2);
  g.add(mesh(cap, 'env.cap', { y: h - 0.01, s: [1, 0.62, 1] }));
  group.add(g);
}

export function buildSet() {
  const set = new THREE.Group();
  set.name = 'set';

  const groundGeo = new THREE.PlaneGeometry(40, 40, 80, 80);
  groundGeo.rotateX(-Math.PI / 2);
  const gp = groundGeo.attributes.position;
  for (let i = 0; i < gp.count; i++) gp.setY(i, groundHeight(gp.getX(i), gp.getZ(i)));
  groundGeo.computeVertexNormals();
  const ground = mesh(groundGeo, 'env.ground', { cast: false });
  set.add(ground);

  const rocks = new THREE.Group();
  rocks.add(mesh(rockGeometry(0.6, 0.78, 0.62, 4), 'env.rock', { x: -1.5, z: -0.05, ry: 0.3 }));
  rocks.add(mesh(rockGeometry(0.34, 0.5, 0.95, 8), 'env.rock', { x: -2.25, z: -0.75, ry: 1.1, s: [1, 1, 0.9] }));
  const pebble = (x, z, s) => rocks.add(mesh(new THREE.IcosahedronGeometry(0.12, 0), 'env.rock', { x, y: 0.04 * s, z, ry: x * 3, s: [s, s * 0.6, s] }));
  pebble(-0.75, 0.35, 1.0); pebble(-0.55, 0.55, 0.6); pebble(1.35, 0.55, 0.8); pebble(2.1, -0.2, 1.3); pebble(-2.9, 0.4, 1.6);
  set.add(rocks);

  const trees = new THREE.Group();
  [[-5.2, -4.6, 2.9, 0], [-3.4, -6.4, 3.4, 1], [-7.0, -7.2, 3.9, 0], [4.4, -5.4, 3.1, 1], [6.2, -3.9, 2.6, 0],
    [2.6, -8.2, 4.0, 0], [7.6, -7.4, 3.6, 1], [-1.4, -9.6, 4.2, 1], [1.0, -11.0, 3.8, 0], [-8.6, -4.2, 3.0, 1],
    [9.0, -4.8, 2.8, 0], [-5.8, -11.0, 4.3, 1], [5.2, -11.6, 4.1, 1], [-10.5, -8.0, 3.7, 0], [10.6, -9.0, 4.0, 0],
    [-12.5, -3.5, 3.2, 1], [12.4, -4.6, 3.3, 1]]
    .forEach(([x, z, h, v]) => tree(trees, x, z, h, v));
  const bush = (x, z, s) => trees.add(mesh(new THREE.IcosahedronGeometry(0.4, 1), 'env.foliage2', { x, y: groundHeight(x, z) + 0.12 * s, z, s: [s, s * 0.65, s] }));
  bush(2.6, -2.2, 1); bush(-3.6, -2.0, 1.2); bush(1.4, -3.6, 0.8); bush(-0.6, -3.2, 0.7); bush(3.6, -0.8, 0.7);
  set.add(trees);

  const shrooms = new THREE.Group();
  mushroom(shrooms, 1.5, -0.4, 0.2, 0.1, 0.1);
  mushroom(shrooms, 1.66, -0.2, 0.13, 0.07, -0.15);
  mushroom(shrooms, 1.32, -0.62, 0.11, 0.06, 0.2);
  mushroom(shrooms, -0.85, -0.65, 0.15, 0.08, -0.1);
  mushroom(shrooms, -0.7, -0.5, 0.09, 0.05, 0.25);
  mushroom(shrooms, 2.7, 0.4, 0.17, 0.09, 0);
  set.add(shrooms);

  // Grass tufts, scattered as one instanced mesh.
  const r = rng(77), count = 1100;
  const grass = new THREE.InstancedMesh(new THREE.ConeGeometry(0.016, 0.13, 3), new THREE.MeshStandardMaterial(), count);
  grass.userData.role = 'env.grass';
  grass.receiveShadow = true;
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler();
  for (let i = 0; i < count; i++) {
    let x, z;
    do { x = (r() - 0.5) * 16; z = 2.8 - r() * 11; } while (Math.hypot(x + 1.5, z + 0.05) < 0.8);
    const s = 0.6 + r() * 0.9;
    e.set((r() - 0.5) * 0.5, r() * 6, (r() - 0.5) * 0.5);
    q.setFromEuler(e);
    m.compose(new THREE.Vector3(x, groundHeight(x, z) + 0.07 * s, z), q, new THREE.Vector3(s, s, s));
    grass.setMatrixAt(i, m);
  }
  set.add(grass);

  const moon = mesh(new THREE.SphereGeometry(1.5, 24, 16), 'env.moon', { x: -10, y: 9.5, z: -40, cast: false, receive: false });
  set.add(moon);

  return { group: set, ground, rocks, trees, shrooms, grass, moon };
}

const SKY = {
  dusk: ['#0e0c2a', '#4a2f6e', '#e9875c', 0.05],
  clay: ['#55575f', '#7c7e86', '#a3a5ab', 0.0],
  studio: ['#16181f', '#262932', '#383c47', 0.0],
  black: ['#000000', '#000000', '#000000', 0.0],
};

export function buildSky() {
  const mat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    fog: false,
    uniforms: {
      uTop: { value: new THREE.Color() }, uMid: { value: new THREE.Color() }, uBot: { value: new THREE.Color() },
      uGlow: { value: 0 },
    },
    vertexShader: /* glsl */`
      varying vec3 vDir;
      void main() {
        vDir = normalize(position);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: /* glsl */`
      uniform vec3 uTop; uniform vec3 uMid; uniform vec3 uBot; uniform float uGlow;
      varying vec3 vDir;
      void main() {
        float h = vDir.y;
        vec3 c = mix(uBot, uMid, smoothstep(-0.02, 0.22, h));
        c = mix(c, uTop, smoothstep(0.18, 0.75, h));
        // a warm sunset glow behind the right-hand hills
        float sun = pow(max(dot(normalize(vDir), normalize(vec3(0.55, 0.04, -0.83))), 0.0), 12.0);
        c += uGlow * sun * vec3(4.0, 1.6, 0.6);
        gl_FragColor = vec4(c, 1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
  });
  const sky = new THREE.Mesh(new THREE.SphereGeometry(60, 32, 16), mat);
  sky.renderOrder = -10;
  sky.frustumCulled = false;

  const r = rng(99), n = 520, pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const a = r() * Math.PI * 2, h = 0.12 + r() * 0.88;
    const rr = Math.sqrt(1 - h * h);
    pos.set([Math.cos(a) * rr * 55, h * 55, Math.sin(a) * rr * 55], i * 3);
  }
  const sg = new THREE.BufferGeometry();
  sg.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const stars = new THREE.Points(sg, new THREE.PointsMaterial({ color: 0xfff6e0, size: 1.6, sizeAttenuation: false, fog: false, transparent: true, opacity: 0.85 }));
  stars.frustumCulled = false;

  const setLook = (name) => {
    const [t, m, b, glow] = SKY[name] ?? SKY.clay;
    mat.uniforms.uTop.value.set(t);
    mat.uniforms.uMid.value.set(m);
    mat.uniforms.uBot.value.set(b);
    mat.uniforms.uGlow.value = glow;
    stars.visible = name === 'dusk';
  };
  setLook('clay');
  return { sky, stars, setLook };
}

export function buildStudio() {
  const g = new THREE.Group();
  g.name = 'studio';
  const plate = mesh(new THREE.CylinderGeometry(1.25, 1.3, 0.06, 72), 'studio.floor', { y: -0.03, cast: false });
  g.add(plate);
  return g;
}

// A little film camera with a frustum, so you can see what Layout is positioning.
export function buildCameraGizmo() {
  const g = new THREE.Group();
  const dark = new THREE.MeshStandardMaterial({ color: 0x343a48, roughness: 0.6 });
  const accent = new THREE.MeshStandardMaterial({ color: 0xff5e7a, roughness: 0.5 });
  const glass = new THREE.MeshStandardMaterial({ color: 0x1b2a44, roughness: 0.1, metalness: 0.5 });
  const body = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.24, 0.42), dark);
  const lens = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.095, 0.18, 20), dark);
  lens.rotation.x = Math.PI / 2;
  lens.position.z = -0.29;
  const front = new THREE.Mesh(new THREE.CircleGeometry(0.07, 20), glass);
  front.position.z = -0.381;
  front.rotation.y = Math.PI;
  for (const z of [-0.12, 0.14]) {
    const reel = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.05, 24), accent);
    reel.rotation.z = Math.PI / 2;
    reel.position.set(0, 0.24, z);
    g.add(reel);
  }
  g.add(body, lens, front);
  return g;
}
