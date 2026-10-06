// "Looks": the same meshes dressed differently for each department.
// Every mesh carries userData.role (e.g. "pip.head", "env.rock"); a look maps role -> material.
import * as THREE from 'three';
import * as T from './textures.js';

const CLAY = {
  'pip.visor': 0x9a9aa1, 'pip.eye': 0x6a6a71, 'pip.bulb': 0xb0b0b6,
  'env.ground': 0x8a8b91, 'env.rock': 0xa2a3a9, 'env.foliage': 0x9a9ba1, 'env.foliage2': 0xa5a6ac,
  'env.moon': 0xc8c8cc, 'fx.firefly': 0xffd84a,
};

const PROXY = {
  pip: 0xe0a47c, 'pip.visor': 0x6d564b, 'pip.eye': 0x6d564b,
  'env.ground': 0x7b8782, 'env.rock': 0x8d95a8, 'env.trunk': 0x8c8478, 'env.foliage': 0x7d978d,
  'env.foliage2': 0x86a094, 'env.cap': 0xa18fc0, 'env.stem': 0xa9a4a0, 'env.grass': 0x7b8782,
  'env.moon': 0xc9c9c9, 'fx.firefly': 0xffd84a,
};

const ID = {
  pip: 0xff4d4d, 'env.ground': 0x4d7dff, 'env.grass': 0x4d7dff, 'env.rock': 0x4dff88,
  'env.trunk': 0xffd84d, 'env.foliage': 0xffd84d, 'env.foliage2': 0xffd84d,
  'env.cap': 0xd94dff, 'env.stem': 0xd94dff, 'env.moon': 0x4dffff, 'fx.firefly': 0xffffff,
  'studio.floor': 0x333333,
};

// Linear "distance from camera" pass: white is near, black is far.
function depthMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: { uNear: { value: 2.5 }, uFar: { value: 16 } },
    vertexShader: /* glsl */`
      varying float vDepth;
      void main() {
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vDepth = -mv.z;
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */`
      uniform float uNear; uniform float uFar; varying float vDepth;
      void main() {
        float d = 1.0 - smoothstep(uNear, uFar, vDepth);
        gl_FragColor = vec4(vec3(d * d), 1.0);
      }`,
  });
}

export class MaterialLibrary {
  constructor() {
    this.tex = {
      checker: T.toTexture(T.checkerCanvas()),
      torso: T.toTexture(T.torsoCanvas()),
      head: T.toTexture(T.headCanvas()),
      belly: T.toTexture(T.bellyCanvas()),
      metal: T.toTexture(T.metalCanvas()),
      rubber: T.toTexture(T.rubberCanvas()),
      ground: T.toTexture(T.groundCanvas(), { repeat: [9, 9] }),
      rock: T.toTexture(T.rockCanvas(), { repeat: [2, 1] }),
      floor: T.toTexture(T.studioFloorCanvas()),
      glow: T.toTexture(T.glowCanvas()),
    };
    this.cache = new Map();
    this.flatClay = false;
  }

  get(look, role) {
    const key = `${look}|${role}|${this.flatClay && look === 'clay' ? 'f' : ''}`;
    let m = this.cache.get(key);
    if (!m) {
      m = this.create(look, role);
      this.cache.set(key, m);
    }
    return m;
  }

  create(look, role) {
    const group = role.split('.')[0];
    const std = (o) => new THREE.MeshStandardMaterial(o);
    if (role === 'studio.floor') return std({ map: this.tex.floor, roughness: 0.95 });
    switch (look) {
      case 'clay':
        return std({ color: CLAY[role] ?? 0xc3c3c8, roughness: 0.8, flatShading: this.flatClay });
      case 'proxy':
        return std({ color: PROXY[role] ?? PROXY[group] ?? 0x9a9ea6, roughness: 0.95, flatShading: true });
      case 'uv':
        return group === 'pip' ? std({ map: this.tex.checker, roughness: 0.75 }) : this.get('clay', role);
      case 'paint':
        return group === 'pip' ? this.paint(role) : this.get('clay', role);
      case 'final':
        return this.final(role);
      case 'ghost':
        return group === 'pip'
          ? std({ color: 0x8fb6dd, roughness: 0.4, transparent: true, opacity: 0.32, depthWrite: false })
          : this.get('clay', role);
      case 'depth':
        return depthMaterial();
      case 'normal':
        return new THREE.MeshNormalMaterial();
      case 'id':
        return new THREE.MeshBasicMaterial({ color: ID[role] ?? ID[group] ?? 0x777777 });
      default:
        return this.get('clay', role);
    }
  }

  // Colour only: the textures are on, but every surface is matte with no shine.
  paint(role) {
    const t = this.tex;
    const maps = { 'pip.shell': t.torso, 'pip.head': t.head, 'pip.belly': t.belly, 'pip.metal': t.metal, 'pip.rubber': t.rubber };
    const flat = { 'pip.arm': 0xee7a3a, 'pip.cream': 0xf1e8da, 'pip.visor': 0x1a2033, 'pip.eye': 0x63f3ff, 'pip.bulb': 0xff5e7a };
    if (maps[role]) return new THREE.MeshStandardMaterial({ map: maps[role], roughness: 1, metalness: 0 });
    return new THREE.MeshStandardMaterial({ color: flat[role] ?? 0xcccccc, roughness: 1, metalness: 0 });
  }

  final(role) {
    const t = this.tex;
    const phys = (o) => new THREE.MeshPhysicalMaterial(o);
    const std = (o) => new THREE.MeshStandardMaterial(o);
    switch (role) {
      case 'pip.shell': return phys({ map: t.torso, roughness: 0.42, clearcoat: 0.6, clearcoatRoughness: 0.25 });
      case 'pip.arm': return phys({ color: 0xee7a3a, roughness: 0.42, clearcoat: 0.5, clearcoatRoughness: 0.3 });
      case 'pip.head': return phys({ map: t.head, roughness: 0.4, clearcoat: 0.55, clearcoatRoughness: 0.25 });
      case 'pip.belly': return phys({ map: t.belly, roughness: 0.5, clearcoat: 0.3 });
      case 'pip.cream': return std({ color: 0xf1e8da, roughness: 0.55 });
      case 'pip.visor': return phys({ color: 0x10162a, roughness: 0.12, metalness: 0.2, clearcoat: 1, clearcoatRoughness: 0.04 });
      case 'pip.eye': return std({ color: 0x63f3ff, emissive: 0x63f3ff, emissiveIntensity: 2.4 });
      case 'pip.metal': return std({ map: t.metal, color: 0xc4ccd6, metalness: 0.85, roughness: 0.32 });
      case 'pip.rubber': return std({ map: t.rubber, roughness: 0.92 });
      case 'pip.bulb': return std({ color: 0xff5e7a, emissive: 0xff5e7a, emissiveIntensity: 2.2 });
      case 'env.ground': return std({ map: t.ground, roughness: 1 });
      case 'env.rock': return std({ map: t.rock, color: 0x9aa0b8, roughness: 0.95, flatShading: true });
      case 'env.trunk': return std({ color: 0x4a3328, roughness: 1, flatShading: true });
      case 'env.foliage': return std({ color: 0x1b4a4a, roughness: 0.9, flatShading: true });
      case 'env.foliage2': return std({ color: 0x27604f, roughness: 0.9, flatShading: true });
      case 'env.grass': return std({ color: 0x4f8a66, roughness: 1 });
      case 'env.cap': return std({ color: 0x31e3c4, emissive: 0x2ad6b8, emissiveIntensity: 1.1, roughness: 0.6 });
      case 'env.stem': return std({ color: 0xd6cfc0, roughness: 0.8 });
      case 'env.moon': return std({ color: 0xfff1d6, emissive: 0xfff1d6, emissiveIntensity: 2.2, fog: false });
      case 'fx.firefly': return std({ color: 0xfff3a0, emissive: 0xfff09a, emissiveIntensity: 6 });
      default: return std({ color: 0xcccccc, roughness: 0.8 });
    }
  }

  // looks = { pip: 'final', env: 'clay', fx: 'final', studio: 'final' }
  apply(root, looks) {
    root.traverse((o) => {
      const role = o.userData.role;
      if (!role) return;
      const group = role.split('.')[0];
      const look = looks[group] ?? looks.default ?? 'clay';
      o.material = this.get(look, role);
    });
  }
}
