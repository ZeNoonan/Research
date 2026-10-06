// Pip, the little robot that travels through the pipeline.
// Built entirely from primitives so the "polygon detail" can be rebuilt live in the Modeling stage.
import * as THREE from 'three';

const V3 = (x, y, z) => new THREE.Vector3(x, y, z);

export const REST_POSE = {
  x: 0, y: 0, z: 0, ry: 0, sq: 0, lean: 0,
  headPitch: 0, headYaw: 0, headRoll: 0,
  armLUp: 0.12, armRUp: 0.12, armLFwd: 0, armRFwd: 0,
  legTuck: 0, eyeSize: 1, happy: 0, blink: 0, antX: 0, antZ: 0,
};

const TORSO_PROFILE = [
  [0.001, 0], [0.13, 0.008], [0.2, 0.05], [0.218, 0.13], [0.206, 0.22],
  [0.17, 0.29], [0.11, 0.338], [0.045, 0.362], [0.001, 0.368],
];

function joint(parent, x, y, z, name) {
  const j = new THREE.Group();
  j.position.set(x, y, z);
  j.name = name || '';
  parent.add(j);
  return j;
}

function torsoGeometry(seg) {
  const curve = new THREE.CatmullRomCurve3(TORSO_PROFILE.map(([r, y]) => V3(r, y, 0)));
  const n = Math.max(4, Math.round(seg / 2.4));
  const pts = curve.getPoints(n).map((p) => new THREE.Vector2(Math.max(p.x, 0.0005), p.y));
  // phiStart = PI puts u = 0 at the back, so the stencilled number sits there.
  return new THREE.LatheGeometry(pts, seg, Math.PI);
}

function circleLine(radius, color, axis = 'y', segments = 48) {
  const pts = [];
  for (let i = 0; i < segments; i++) {
    const a = (i / segments) * Math.PI * 2;
    const c = Math.cos(a) * radius, s = Math.sin(a) * radius;
    pts.push(axis === 'y' ? V3(c, 0, s) : axis === 'z' ? V3(c, s, 0) : V3(0, c, s));
  }
  const g = new THREE.BufferGeometry().setFromPoints(pts);
  const m = new THREE.LineBasicMaterial({ color, depthTest: false, transparent: true });
  const line = new THREE.LineLoop(g, m);
  line.renderOrder = 1000;
  return line;
}

export class Pip {
  constructor() {
    this.root = new THREE.Group();
    this.root.name = 'pip';
    this.squash = joint(this.root, 0, 0, 0, 'squash');
    this.cog = joint(this.squash, 0, 0.17, 0, 'cog');
    this.spine = joint(this.cog, 0, 0, 0, 'spine');
    this.chest = joint(this.spine, 0, 0.27, 0, 'chest');
    this.neck = joint(this.spine, 0, 0.35, 0, 'neck');
    this.neck.rotation.order = 'YXZ';
    this.headC = joint(this.neck, 0, 0.27, 0, 'head');
    this.headTop = joint(this.headC, 0, 0.29, 0, 'headTop');
    this.antBase = joint(this.headC, 0, 0.275, -0.03, 'antenna');
    this.antTip = joint(this.antBase, 0, 0.24, 0, 'antennaTip');
    this.shoulderL = joint(this.spine, 0.185, 0.27, 0.02, 'shoulderL');
    this.shoulderR = joint(this.spine, -0.185, 0.27, 0.02, 'shoulderR');
    this.handL = joint(this.shoulderL, 0, -0.27, 0, 'handL');
    this.handR = joint(this.shoulderR, 0, -0.27, 0, 'handR');
    this.hipL = joint(this.cog, 0.09, 0.02, 0, 'hipL');
    this.hipR = joint(this.cog, -0.09, 0.02, 0, 'hipR');
    this.footL = joint(this.hipL, 0, -0.14, 0.02, 'footL');
    this.footR = joint(this.hipR, 0, -0.14, 0.02, 'footR');

    this.parts = [];
    this.detail = 40;
    this.wireMat = new THREE.MeshBasicMaterial({ color: 0x1e2a3a, wireframe: true, transparent: true, opacity: 0.45 });
    this.wire = false;
    this._antenna = { x: NaN, z: NaN };
    this.build();
    this.buildRigViz();
    this.applyPose(REST_POSE);
  }

  part(parent, role, make, { pos, rot, scale } = {}) {
    const mesh = new THREE.Mesh(make(this.detail), new THREE.MeshStandardMaterial());
    mesh.userData.role = role;
    if (pos) mesh.position.copy(pos);
    if (rot) mesh.rotation.set(rot[0], rot[1], rot[2]);
    if (scale) mesh.scale.copy(scale);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    const wire = new THREE.Mesh(mesh.geometry, this.wireMat);
    wire.visible = false;
    wire.raycast = () => {};
    mesh.add(wire);
    parent.add(mesh);
    this.parts.push({ mesh, wire, make });
    return mesh;
  }

  build() {
    const half = (s) => Math.max(3, Math.round(s / 2));
    const sphere = (r, sx = 1) => (s) => new THREE.SphereGeometry(r, Math.max(5, Math.round(s * sx)), half(s * sx));

    this.part(this.spine, 'pip.shell', torsoGeometry);
    this.part(this.spine, 'pip.belly', sphere(1), { pos: V3(0, 0.155, 0.168), scale: V3(0.125, 0.115, 0.06) });
    this.part(this.neck, 'pip.metal', (s) => new THREE.CylinderGeometry(0.065, 0.08, 0.1, Math.max(5, s), 1), { pos: V3(0, 0.03, 0) });
    this.part(this.headC, 'pip.head', (s) => new THREE.SphereGeometry(0.29, Math.max(5, s), Math.max(3, Math.round(s * 0.75))));
    // Visor: a patch of a slightly larger sphere facing +z.
    const W = 2.05;
    this.part(this.headC, 'pip.visor', (s) => new THREE.SphereGeometry(0.297, Math.max(4, Math.round(s * 0.7)), Math.max(2, Math.round(s * 0.4)), Math.PI / 2 - W / 2, W, 1.02, 1.12));

    for (const side of [1, -1]) {
      this.part(this.headC, 'pip.metal', (s) => new THREE.CylinderGeometry(0.07, 0.07, 0.06, Math.max(5, Math.round(s * 0.6))), { pos: V3(side * 0.282, 0.0, -0.01), rot: [0, 0, Math.PI / 2] });
      this.part(this.headC, 'pip.arm', (s) => new THREE.CylinderGeometry(0.042, 0.042, 0.075, Math.max(5, Math.round(s * 0.5))), { pos: V3(side * 0.29, 0.0, -0.01), rot: [0, 0, Math.PI / 2] });
    }

    // Eyes: a pill for "open" and an arc for "happy", sitting on the visor surface.
    this.eyes = [];
    for (const side of [1, -1]) {
      const theta = 1.5, phi = Math.PI / 2 + side * 0.34;
      const dir = V3(-Math.cos(phi) * Math.sin(theta), Math.cos(theta), Math.sin(phi) * Math.sin(theta)).normalize();
      const eye = new THREE.Group();
      eye.position.copy(dir).multiplyScalar(0.299);
      eye.quaternion.setFromUnitVectors(V3(0, 0, 1), dir);
      this.headC.add(eye);
      const pill = this.part(eye, 'pip.eye', (s) => new THREE.CapsuleGeometry(0.03, 0.05, Math.max(2, Math.round(s / 8)), Math.max(6, Math.round(s / 2))));
      const arc = this.part(eye, 'pip.eye', (s) => new THREE.TorusGeometry(0.036, 0.011, 6, Math.max(8, Math.round(s / 2)), Math.PI));
      arc.position.y = -0.012;
      pill.castShadow = arc.castShadow = false;
      this.eyes.push({ eye, pill, arc });
    }

    // Antenna: a tube re-shaped every frame so it can wobble (secondary motion).
    this.part(this.antBase, 'pip.metal', (s) => new THREE.CylinderGeometry(0.028, 0.042, 0.045, Math.max(5, Math.round(s / 2))), { pos: V3(0, 0.005, 0) });
    this.antennaMesh = this.part(this.antBase, 'pip.metal', () => this.antennaGeometry(0, 0));
    this.bulb = this.part(this.antTip, 'pip.bulb', sphere(0.05, 0.6));

    for (const [sh, hand] of [[this.shoulderL, this.handL], [this.shoulderR, this.handR]]) {
      this.part(sh, 'pip.metal', sphere(0.05, 0.6));
      this.part(sh, 'pip.arm', (s) => new THREE.CapsuleGeometry(0.036, 0.17, Math.max(2, Math.round(s / 8)), Math.max(5, Math.round(s / 2))), { pos: V3(0, -0.12, 0) });
      this.part(hand, 'pip.cream', sphere(0.058, 0.8), { scale: V3(1, 0.92, 1) });
    }
    for (const [hip, foot] of [[this.hipL, this.footL], [this.hipR, this.footR]]) {
      this.part(hip, 'pip.metal', (s) => new THREE.CapsuleGeometry(0.04, 0.06, Math.max(2, Math.round(s / 8)), Math.max(5, Math.round(s / 2))), { pos: V3(0, -0.06, 0) });
      this.part(foot, 'pip.rubber', sphere(1, 0.8), { scale: V3(0.08, 0.05, 0.108) });
    }
  }

  antennaGeometry(bx, bz) {
    const L = 0.24;
    const tip = V3(bx, Math.sqrt(Math.max(0.01, L * L - bx * bx - bz * bz)), bz);
    const curve = new THREE.QuadraticBezierCurve3(V3(0, 0, 0), V3(0, tip.y * 0.55, 0), tip);
    this._tip = tip;
    return new THREE.TubeGeometry(curve, 10, 0.012, 6, false);
  }

  setAntenna(bx, bz) {
    if (Math.abs(bx - this._antenna.x) < 0.0015 && Math.abs(bz - this._antenna.z) < 0.0015) return;
    this._antenna = { x: bx, z: bz };
    const g = this.antennaGeometry(bx, bz);
    this.antennaMesh.geometry.dispose();
    this.antennaMesh.geometry = g;
    this.antennaMesh.children[0].geometry = g;
    this.antTip.position.copy(this._tip);
  }

  // Rebuild every primitive at a new polygon density; returns the triangle count.
  setDetail(seg) {
    this.detail = seg;
    for (const p of this.parts) {
      if (p.mesh === this.antennaMesh) continue;
      p.mesh.geometry.dispose();
      p.mesh.geometry = p.make(seg);
      p.wire.geometry = p.mesh.geometry;
    }
    return this.triangles();
  }

  triangles() {
    let n = 0;
    for (const p of this.parts) {
      const g = p.mesh.geometry;
      n += (g.index ? g.index.count : g.attributes.position.count) / 3;
    }
    return Math.round(n);
  }

  setWire(on) {
    this.wire = on;
    for (const p of this.parts) p.wire.visible = on;
  }

  applyPose(p, { antenna = true } = {}) {
    this.root.position.set(p.x, p.y, p.z);
    this.root.rotation.y = p.ry;
    const sy = 1 - 0.5 * p.sq;
    const sxz = 1 / Math.sqrt(sy);
    this.squash.scale.set(sxz, sy, sxz);
    this.spine.rotation.x = p.lean;
    this.neck.rotation.set(-p.headPitch, p.headYaw, p.headRoll);
    this.shoulderL.rotation.set(-p.armLFwd, 0, p.armLUp);
    this.shoulderR.rotation.set(-p.armRFwd, 0, -p.armRUp);
    this.hipL.rotation.x = this.hipR.rotation.x = -p.legTuck * 0.9;
    this.cog.position.y = 0.17;
    const open = Math.max(0.06, 1 - p.blink);
    for (const { pill, arc } of this.eyes) {
      const h = p.happy;
      pill.scale.set(p.eyeSize, Math.max(0.0001, p.eyeSize * open * (1 - h)), 0.45 * p.eyeSize);
      pill.visible = h < 0.98;
      arc.scale.set(p.eyeSize * h + 0.0001, p.eyeSize * h + 0.0001, 0.6);
      arc.visible = h > 0.02;
    }
    if (antenna) this.setAntenna(p.antX, p.antZ);
  }

  // Bones (yellow lines) and animator controls (coloured curves), as a rigger sees them.
  buildRigViz() {
    this.bonePairs = [
      [this.cog, this.chest], [this.chest, this.neck], [this.neck, this.headC], [this.headC, this.antBase],
      [this.antBase, this.antTip], [this.chest, this.shoulderL], [this.shoulderL, this.handL],
      [this.chest, this.shoulderR], [this.shoulderR, this.handR], [this.cog, this.hipL], [this.hipL, this.footL],
      [this.cog, this.hipR], [this.hipR, this.footR],
    ];
    const joints = [...new Set(this.bonePairs.flat())];
    this.rigJoints = joints;
    const boneGeo = new THREE.BufferGeometry();
    boneGeo.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(this.bonePairs.length * 6), 3));
    this.boneLines = new THREE.LineSegments(boneGeo, new THREE.LineBasicMaterial({ color: 0xffd84a, depthTest: false, transparent: true }));
    this.boneLines.frustumCulled = false;
    this.boneLines.renderOrder = 999;
    const jGeo = new THREE.BufferGeometry();
    jGeo.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(joints.length * 3), 3));
    const dot = document.createElement('canvas');
    dot.width = dot.height = 32;
    const dg = dot.getContext('2d');
    dg.fillStyle = '#fff';
    dg.beginPath(); dg.arc(16, 16, 13, 0, Math.PI * 2); dg.fill();
    this.jointPoints = new THREE.Points(jGeo, new THREE.PointsMaterial({ color: 0xfff1b0, size: 10, sizeAttenuation: false, depthTest: false, transparent: true, map: new THREE.CanvasTexture(dot), alphaTest: 0.5 }));
    this.jointPoints.frustumCulled = false;
    this.jointPoints.renderOrder = 1001;
    this.rigViz = new THREE.Group();
    this.rigViz.add(this.boneLines, this.jointPoints);
    this.rigViz.visible = false;

    const add = (parent, line, y = 0) => { line.position.y = y; parent.add(line); return line; };
    this.ctrlLines = [
      add(this.root, circleLine(0.5, 0xffd84a), 0.01),
      add(this.cog, circleLine(0.3, 0xff9a3c), 0.08),
      add(this.neck, circleLine(0.34, 0x4fd8ff), 0.1),
      add(this.handL, circleLine(0.085, 0x4f8cff, 'x')),
      add(this.handR, circleLine(0.085, 0xff4f6a, 'x')),
      add(this.footL, circleLine(0.11, 0x4f8cff), -0.03),
      add(this.footR, circleLine(0.11, 0xff4f6a), -0.03),
      add(this.antTip, circleLine(0.07, 0xd96bff, 'z')),
    ];
    this.setRigViz(false);
  }

  setRigViz(on) {
    this.rigViz.visible = on;
    for (const l of this.ctrlLines) l.visible = on;
  }

  updateRigViz() {
    if (!this.rigViz.visible) return;
    const a = new THREE.Vector3(), b = new THREE.Vector3();
    const pos = this.boneLines.geometry.attributes.position;
    this.bonePairs.forEach(([p, c], i) => {
      p.getWorldPosition(a);
      c.getWorldPosition(b);
      pos.setXYZ(i * 2, a.x, a.y, a.z);
      pos.setXYZ(i * 2 + 1, b.x, b.y, b.z);
    });
    pos.needsUpdate = true;
    const jp = this.jointPoints.geometry.attributes.position;
    this.rigJoints.forEach((j, i) => {
      j.getWorldPosition(a);
      jp.setXYZ(i, a.x, a.y, a.z);
    });
    jp.needsUpdate = true;
  }

  handsMid(target) {
    const a = new THREE.Vector3(), b = new THREE.Vector3();
    this.handL.getWorldPosition(a);
    this.handR.getWorldPosition(b);
    return target.copy(a).add(b).multiplyScalar(0.5);
  }
}
