// The 3D viewport. One scene, one Pip; each pipeline stage re-dresses it (materials, lights,
// camera, playback, overlays) so you watch the same shot change as it moves down the pipeline.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { MaterialLibrary } from './materials.js';
import { Pip, REST_POSE } from './pip.js';
import { buildSet, buildSky, buildStudio, buildCameraGizmo } from './world.js';
import { SHOT, KEYS, FRAMES, evalPose, frameOf, shotCamera, ShotCache, SHOT_HFOV } from './shot.js';
import { FX } from './fx.js';

const $ = (id) => document.getElementById(id);

const GradeShader = {
  uniforms: { tDiffuse: { value: null }, uAmount: { value: 1 }, uTime: { value: 0 }, uRes: { value: new THREE.Vector2(1, 1) } },
  vertexShader: /* glsl */`varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
  fragmentShader: /* glsl */`
    uniform sampler2D tDiffuse; uniform float uAmount; uniform float uTime; uniform vec2 uRes;
    varying vec2 vUv;
    void main() {
      vec3 col = texture2D(tDiffuse, vUv).rgb;
      float l = dot(col, vec3(0.299, 0.587, 0.114));
      vec3 g = col;
      g = mix(g, g * vec3(0.9, 0.97, 1.12) + vec3(0.0, 0.006, 0.025), 1.0 - l);
      g = mix(g, g * vec3(1.08, 1.0, 0.88), l);
      g = (g - 0.5) * 1.07 + 0.5;
      vec2 d = vUv - 0.5; d.x *= uRes.x / uRes.y;
      g *= mix(0.5, 1.0, smoothstep(0.98, 0.32, length(d)));
      float n = fract(sin(dot(vUv * uRes + uTime * 61.0, vec2(12.9898, 78.233))) * 43758.5453);
      g += (n - 0.5) * 0.03;
      gl_FragColor = vec4(mix(col, g, uAmount), 1.0);
    }`,
};

// What each department's viewport looks like.
const STAGES = {
  modeling: { set: 'studio', looks: { pip: 'clay' }, lights: 'studio', cam: 'turntable', motion: 'turntable' },
  surfacing: { set: 'studio', looks: { pip: 'final' }, lights: 'studio', cam: 'turntable', motion: 'turntable' },
  rigging: { set: 'studio', looks: { pip: 'ghost' }, lights: 'studio', cam: 'turntable', motion: 'rig' },
  layout: { set: 'shot', looks: { pip: 'proxy', env: 'proxy', fx: 'proxy' }, lights: 'viewport', cam: 'work', motion: 'shot', anim: 'blocking', fx: 'proxy', timeline: true },
  animation: { set: 'shot', looks: { pip: 'final', env: 'clay', fx: 'clay' }, lights: 'viewport', cam: 'shot', motion: 'shot', anim: 'polish', fx: 'proxy', timeline: true },
  fx: { set: 'shot', looks: { pip: 'final', env: 'clay', fx: 'final' }, lights: 'fxview', cam: 'shot', motion: 'shot', anim: 'polish', fx: 'full', timeline: true },
  lighting: { set: 'shot', looks: { pip: 'final', env: 'final', fx: 'final' }, lights: 'dusk', cam: 'shot', motion: 'shot', anim: 'polish', fx: 'full', timeline: true },
  rendering: { set: 'shot', looks: { pip: 'final', env: 'final', fx: 'final' }, lights: 'dusk', cam: 'shot', motion: 'frozen', anim: 'polish', fx: 'full', post: true },
  compositing: { set: 'shot', looks: { pip: 'final', env: 'final', fx: 'final' }, lights: 'dusk', cam: 'shot', motion: 'shot', anim: 'polish', fx: 'full', post: true, timeline: true },
  final: { set: 'shot', looks: { pip: 'final', env: 'final', fx: 'final' }, lights: 'dusk', cam: 'shot', motion: 'shot', anim: 'polish', fx: 'full', post: true, letterbox: true },
};

const LIGHTS = {
  studio: { amb: 0.15, hemi: [0xdde6ff, 0x3a3a44, 1.0], key: [0xffffff, 2.6, [2.5, 4, 3]], rim: [0xbfd4ff, 2.2, [-2.5, 2.5, -3]], env: ['studio', 0.55], fog: null, sky: 'studio' },
  viewport: { amb: 0.2, hemi: [0xe8eeff, 0x55555c, 1.25], key: [0xffffff, 1.9, [3, 6, 5]], rim: [0xffffff, 0, [0, 1, 0]], env: ['studio', 0.35], fog: null, sky: 'clay' },
  fxview: { amb: 0.12, hemi: [0xc8d0ff, 0x2a2a30, 0.7], key: [0xffffff, 1.1, [3, 6, 5]], rim: [0x9fb4ff, 0.8, [-3, 2, -5]], env: ['studio', 0.2], fog: null, sky: 'studio' },
  dusk: { amb: 0.05, hemi: [0x7563b8, 0x16262a, 0.75], key: [0xa9bcff, 1.25, [-5, 7, 4]], rim: [0xff9152, 3.2, [6, 2.2, -6]], env: ['dusk', 0.4], fog: [0x3b2a52, 9, 34], sky: 'dusk' },
};

export const HERO_T = 5.0;

export class Viewer {
  constructor(screen) {
    this.screen = screen;
    this.canvas = $('gl');
    const renderer = new THREE.WebGLRenderer({ canvas: this.canvas, antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer = renderer;

    this.scene = new THREE.Scene();
    this.lib = new MaterialLibrary();
    this.pip = new Pip();
    this.set = buildSet();
    this.studio = buildStudio();
    const sky = buildSky();
    this.sky = sky;
    this.fx = new FX(this.lib);
    this.camGizmo = buildCameraGizmo();
    this.scene.add(this.pip.root, this.pip.rigViz, this.set.group, this.studio, sky.sky, sky.stars, this.fx.group, this.fx.body, this.fx.proxy, this.fx.light, this.camGizmo);

    // Blob shadow under Pip in the turntable studio.
    const blob = new THREE.Mesh(new THREE.PlaneGeometry(0.9, 0.9), new THREE.MeshBasicMaterial({ map: this.lib.tex.glow, color: 0x000000, transparent: true, opacity: 0.35, depthWrite: false }));
    blob.rotation.x = -Math.PI / 2;
    blob.position.y = 0.002;
    this.studio.add(blob);

    this.makeLights();
    this.makeCameras();
    this.makeEnvironments();
    this.makePost();

    this.caches = {};
    this.state = { stage: null, cfg: null, t: 0, playing: true, speed: 1, anim: 'polish', is2d: true };
    this.opts = { wire: true, detail: 3, surface: 'final', layoutView: 'work', trail: true, fxRaw: false, pass: 'beauty', slices: false, rigUser: null };
    this.lightsOn = { key: true, fill: true, rim: true, firefly: true };
    this.layers = { sky: true, set: true, pip: true, fx: true, glow: true, grade: true };
    this.rigPose = { ...REST_POSE };
    this.tmp = { pose: {}, v: new THREE.Vector3() };

    this.makeTrail();
    this.buildTimeline();
    this.resize();
    new ResizeObserver(() => this.resize()).observe(screen);
    this.clock = new THREE.Clock();
    this.visible = true;
    this.loop = this.loop.bind(this);
    renderer.setAnimationLoop(this.loop);
  }

  makeLights() {
    const L = {
      amb: new THREE.AmbientLight(0xffffff, 0.1),
      hemi: new THREE.HemisphereLight(0xffffff, 0x444444, 1),
      key: new THREE.DirectionalLight(0xffffff, 2),
      rim: new THREE.DirectionalLight(0xffffff, 1),
    };
    L.key.castShadow = true;
    L.key.shadow.mapSize.set(2048, 2048);
    const sc = L.key.shadow.camera;
    sc.left = -4; sc.right = 4; sc.top = 4; sc.bottom = -4; sc.near = 0.5; sc.far = 30;
    L.key.shadow.bias = -0.0004;
    L.key.shadow.normalBias = 0.02;
    this.scene.add(L.amb, L.hemi, L.key, L.rim);
    this.L = L;
  }

  makeCameras() {
    this.shotCam = new THREE.PerspectiveCamera(30, 16 / 9, 0.1, 200);
    this.workCam = new THREE.PerspectiveCamera(40, 16 / 9, 0.1, 200);
    this.workCam.position.set(7.8, 5.2, 9.6);
    this.workCam.lookAt(-0.6, 0.4, 2.6);
    this.turnCam = new THREE.PerspectiveCamera(30, 16 / 9, 0.05, 200);
    this.turnCam.position.set(1.4, 1.2, 3.55);
    this.controls = new OrbitControls(this.turnCam, this.canvas);
    this.controls.target.set(0, 0.68, 0);
    this.controls.enableZoom = false;
    this.controls.enablePan = false;
    this.controls.enableDamping = true;
    this.controls.minPolarAngle = 0.35;
    this.controls.maxPolarAngle = 1.75;
    this.controls.enabled = false;
    this.controls.update();
    // On touch screens the viewport must not swallow page scrolling.
    if (!matchMedia('(pointer: fine)').matches) this.canvas.style.touchAction = 'pan-y';
    // Short-range twin of the shot camera, so its frustum drawing stays a readable size.
    this.helperCam = new THREE.PerspectiveCamera(30, 16 / 9, 0.4, 6.4);
    this.camHelper = new THREE.CameraHelper(this.helperCam);
    this.camHelper.setColors(new THREE.Color(0xffd84a), new THREE.Color(0xff5e7a), new THREE.Color(0x4fd8ff), new THREE.Color(0xffffff), new THREE.Color(0x777777));
    this.scene.add(this.camHelper);
  }

  makeEnvironments() {
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    this.envs = { studio: pmrem.fromScene(new RoomEnvironment(), 0.04).texture };
    const s = new THREE.Scene();
    const sky = buildSky();
    sky.setLook('dusk');
    s.add(sky.sky);
    this.envs.dusk = pmrem.fromScene(s, 0.02).texture;
    pmrem.dispose();
  }

  makePost() {
    const composer = new EffectComposer(this.renderer);
    this.renderPass = new RenderPass(this.scene, this.shotCam);
    this.bloom = new UnrealBloomPass(new THREE.Vector2(512, 512), 0.6, 0.5, 0.86);
    this.grade = new ShaderPass(GradeShader);
    composer.addPass(this.renderPass);
    composer.addPass(this.bloom);
    composer.addPass(new OutputPass());
    composer.addPass(this.grade);
    this.composer = composer;
  }

  makeTrail() {
    const n = FRAMES + 1;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    this.trailLine = new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0xff5e7a, transparent: true, opacity: 0.85, depthTest: false }));
    this.trailDots = new THREE.Points(g, new THREE.PointsMaterial({ color: 0xffe08a, size: 4, sizeAttenuation: false, depthTest: false }));
    this.trailLine.renderOrder = this.trailDots.renderOrder = 998;
    this.trailLine.frustumCulled = this.trailDots.frustumCulled = false;
    this.trail = new THREE.Group();
    this.trail.add(this.trailLine, this.trailDots);
    this.scene.add(this.trail);
    this.trailMode = null;
  }

  updateTrail(mode) {
    if (this.trailMode === mode) return;
    this.trailMode = mode;
    const pos = this.trail.children[0].geometry.attributes.position;
    const pose = {}, v = new THREE.Vector3();
    const saved = this.pip.root.position.clone();
    for (let f = 0; f <= FRAMES; f++) {
      evalPose(f / SHOT.fps, mode, pose);
      this.pip.applyPose(pose, { antenna: false });
      this.pip.root.updateMatrixWorld(true);
      this.pip.cog.getWorldPosition(v);
      pos.setXYZ(f, v.x, v.y + 0.12, v.z);
    }
    pos.needsUpdate = true;
    this.pip.root.position.copy(saved);
    this.trailLine.visible = mode !== 'blocking';
  }

  cache(mode) {
    if (!this.caches[mode]) this.caches[mode] = new ShotCache(this.pip, mode);
    return this.caches[mode];
  }

  // ---- Timeline (HTML under the viewport) ----
  buildTimeline() {
    const keys = $('tl-keys');
    keys.innerHTML = KEYS.map((k) => `<i style="left:${(k.t / SHOT.len) * 100}%" title="${k.label || 'key'}"></i>`).join('');
    const track = $('tl-track');
    let dragging = false;
    const seek = (e) => {
      const r = track.getBoundingClientRect();
      this.state.t = THREE.MathUtils.clamp((e.clientX - r.left) / r.width, 0, 1) * SHOT.len;
      this.setPlaying(false);
    };
    track.addEventListener('pointerdown', (e) => { dragging = true; track.setPointerCapture(e.pointerId); seek(e); });
    track.addEventListener('pointermove', (e) => dragging && seek(e));
    track.addEventListener('pointerup', () => { dragging = false; });
    $('tl-play').addEventListener('click', () => this.setPlaying(!this.state.playing));
  }

  setPlaying(on) {
    this.state.playing = on;
    const b = $('tl-play');
    b.textContent = on ? '❚❚' : '▶';
    b.setAttribute('aria-label', on ? 'Pause' : 'Play');
  }

  resize() {
    const w = this.screen.clientWidth, h = this.screen.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.composer.setSize(w, h);
    this.composer.setPixelRatio(this.renderer.getPixelRatio());
    this.bloom.resolution.set(w, h);
    this.grade.uniforms.uRes.value.set(w, h);
    for (const c of [this.shotCam, this.workCam, this.turnCam, this.helperCam]) {
      c.aspect = w / h;
      c.updateProjectionMatrix();
    }
    const vf = 2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(SHOT_HFOV) / 2) / (w / h));
    this.shotCam.fov = this.helperCam.fov = THREE.MathUtils.radToDeg(vf);
    this.shotCam.updateProjectionMatrix();
    this.helperCam.updateProjectionMatrix();
    this.size = { w, h };
  }

  // ---- Stage switching ----
  setStage(id) {
    const cfg = STAGES[id];
    this.state.stage = id;
    this.state.is2d = !cfg;
    this.screen.dataset.stage = id;
    if (id !== 'rendering') this.stopBucket();
    if (!cfg) return;
    this.state.cfg = cfg;
    if (cfg.anim) this.state.anim = id === 'animation' ? this.opts.animMode || 'polish' : cfg.anim;
    if (id === 'rendering') { this.state.t = HERO_T; }
    if (cfg.motion === 'shot' && !this.state.playing) this.setPlaying(true);
    this.pip.root.rotation.set(0, 0, 0);
    if (cfg.cam === 'turntable') {
      this.turnCam.position.set(1.4, 1.2, 3.55);
      this.controls.target.set(0, 0.68, 0);
      this.controls.update();
      this.spin = 0;
    }
    this.controls.enabled = cfg.cam === 'turntable' && matchMedia('(pointer: fine)').matches;
    this.canvas.style.cursor = this.controls.enabled ? 'grab' : '';
    this.applyLooks();
    $('timeline').hidden = !cfg.timeline;
    if (id === 'rendering') this.startBucket();
  }

  applyLooks() {
    const cfg = this.state.cfg, id = this.state.stage, o = this.opts;
    const studio = cfg.set === 'studio';
    this.set.group.visible = !studio;
    this.studio.visible = studio;

    let looks = { ...cfg.looks, studio: 'final' };
    this.lib.flatClay = id === 'modeling' && o.detail <= 1;
    if (id === 'surfacing') looks.pip = o.surface;
    if (id === 'rendering' && o.pass !== 'beauty') looks = { pip: o.pass, env: o.pass, fx: o.pass };
    this.lib.apply(this.scene, looks);
    this.pip.setWire(id === 'modeling' && o.wire);
    this.pip.setRigViz(id === 'rigging');

    const passMode = id === 'rendering' && o.pass !== 'beauty';
    const lights = LIGHTS[cfg.lights];
    this.applyLights(lights);
    if (passMode) this.scene.fog = null;
    this.sky.setLook(passMode ? 'black' : lights.sky);
    this.sky.stars.visible = lights.sky === 'dusk' && !passMode;

    this.fx.setLevel(passMode ? 'off' : cfg.fx || 'off');
    if (passMode) this.fx.body.visible = true;
    this.fx.setRaw(id === 'fx' && o.fxRaw);
    this.camGizmo.visible = this.camHelper.visible = id === 'layout' && o.layoutView === 'work';
    this.trail.visible = id === 'animation' && o.trail;
    if (this.trail.visible) this.updateTrail(this.state.anim);
    this.set.grass.visible = cfg.looks.env === 'final';

    if (id === 'compositing') {
      const L = this.layers;
      this.sky.sky.visible = L.sky;
      this.sky.stars.visible = L.sky;
      this.set.group.visible = L.set;
      this.pip.root.visible = L.pip;
      this.fx.group.visible = this.fx.body.visible = L.fx;
      this.bloom.enabled = L.glow;
      this.grade.uniforms.uAmount.value = L.grade ? 1 : 0;
    } else {
      this.sky.sky.visible = true;
      this.pip.root.visible = true;
      this.bloom.enabled = true;
      this.grade.uniforms.uAmount.value = 1;
    }
    this.scene.background = id === 'compositing' && !this.layers.sky ? this.black || (this.black = new THREE.Color(0x000000)) : null;
    this.updateHud();
  }

  applyLights(s) {
    const L = this.L, on = this.state.stage === 'lighting' || this.state.stage === 'compositing' || this.state.stage === 'final' || this.state.stage === 'rendering' ? this.lightsOn : { key: true, fill: true, rim: true, firefly: true };
    L.amb.intensity = s.amb;
    L.hemi.color.set(s.hemi[0]);
    L.hemi.groundColor.set(s.hemi[1]);
    L.hemi.intensity = s.hemi[2] * (on.fill ? 1 : 0);
    L.key.color.set(s.key[0]);
    L.key.intensity = s.key[1] * (on.key ? 1 : 0);
    L.key.position.set(...s.key[2]);
    L.rim.color.set(s.rim[0]);
    L.rim.intensity = s.rim[1] * (on.rim ? 1 : 0);
    L.rim.position.set(...s.rim[2]);
    this.fireflyLight = s === LIGHTS.dusk && on.firefly;
    this.scene.environment = this.envs[s.env[0]];
    this.scene.environmentIntensity = s.env[1] * (s === LIGHTS.dusk ? (on.fill ? 1 : 0.25) : 1);
    if (s.fog && !s.fogObj) s.fogObj = new THREE.Fog(s.fog[0], s.fog[1], s.fog[2]);
    this.scene.fog = s.fog ? s.fogObj : null;
    const studio = this.state.cfg.set === 'studio';
    L.key.shadow.camera.left = studio ? -1.5 : -4;
    L.key.shadow.camera.right = studio ? 1.5 : 4;
    L.key.shadow.camera.top = studio ? 2 : 4;
    L.key.shadow.camera.bottom = studio ? -1.5 : -4;
    L.key.shadow.camera.updateProjectionMatrix();
  }

  // ---- Controls from the step cards ----
  control(name, value) {
    const o = this.opts;
    switch (name) {
      case 'wire': o.wire = value; break;
      case 'detail': {
        o.detail = value;
        const tris = this.pip.setDetail([6, 10, 18, 40, 72][value]);
        const el = $('tri-count');
        if (el) el.textContent = tris.toLocaleString();
        break;
      }
      case 'surface': o.surface = value; break;
      case 'layoutView': o.layoutView = value; break;
      case 'animMode': o.animMode = value; this.state.anim = value; break;
      case 'trail': o.trail = value; break;
      case 'fxView': o.fxRaw = value === 'raw'; break;
      case 'pass': o.pass = value; this.stopBucket(); break;
      case 'slices': o.slices = value; break;
      default:
        if (name.startsWith('light.')) this.lightsOn[name.slice(6)] = value;
        else if (name.startsWith('layer.')) this.layers[name.slice(6)] = value;
        else if (name.startsWith('rig.')) {
          o.rigUser = o.rigUser || {};
          o.rigUser[name.slice(4)] = value;
        }
    }
    if (this.state.cfg) this.applyLooks();
  }

  updateHud() {
    const id = this.state.stage, o = this.opts;
    const inset = $('inset');
    inset.hidden = !(id === 'surfacing' && o.surface !== 'final');
    if (!inset.hidden) {
      const src = o.surface === 'uv' ? this.lib.tex.checker.image : this.lib.tex.torso.image;
      const c = $('inset-canvas'), g = c.getContext('2d'), half = c.width / 2;
      // Shown with the seam moved to the sides, so the "07" on the back reads in one piece.
      g.drawImage(src, 0, 0, c.width, c.height);
      if (o.surface === 'paint') {
        g.drawImage(src, src.width / 2, 0, src.width / 2, src.height, 0, 0, half, c.height);
        g.drawImage(src, 0, 0, src.width / 2, src.height, half, 0, half, c.height);
      }
      $('inset-label').textContent = o.surface === 'uv' ? 'UV test grid (flat)' : 'Body paint, unwrapped flat';
    }
    $('pip-frame').hidden = !(id === 'layout' && o.layoutView === 'work');
    const pass = $('pass-label');
    pass.hidden = id !== 'rendering';
    pass.textContent = { beauty: 'Beauty — the full image', depth: 'Depth pass — distance from camera', normal: 'Normals pass — which way surfaces face', id: 'ID mattes — one flat colour per object' }[o.pass];
    $('slices').hidden = !(id === 'final' && o.slices);
  }

  // ---- Per frame ----
  loop() {
    const dt = Math.min(this.clock.getDelta(), 0.05);
    if (this.state.is2d || !this.visible || !this.state.cfg) return;
    const cfg = this.state.cfg, st = this.state, id = st.stage;

    if (cfg.motion === 'shot' && st.playing) {
      st.t += dt * st.speed;
      if (st.t > SHOT.len + SHOT.hold) st.t = 0;
    }
    const t = Math.min(st.t, SHOT.len);

    if (cfg.motion === 'turntable' || cfg.motion === 'rig') {
      this.spin = (this.spin || 0) + dt * (cfg.motion === 'rig' ? 0.25 : 0.45);
      const pose = cfg.motion === 'rig' ? this.rigDemo(this.clock.elapsedTime) : { ...REST_POSE };
      pose.ry = Math.sin(this.spin) * (cfg.motion === 'rig' ? 0.5 : 0) + (cfg.motion === 'rig' ? 0.3 : this.spin);
      this.pip.applyPose(pose);
      if (this.controls.enabled) this.controls.update();
    } else {
      const cache = this.cache(st.anim);
      const pose = evalPose(t, st.anim, this.tmp.pose);
      const [ax, az] = cache.antennaAt(t);
      pose.antX = ax;
      pose.antZ = az;
      this.pip.applyPose(pose);
      this.fx.update(t, cache, this.fireflyLight);
      shotCamera(t, this.shotCam);
    }
    this.pip.root.updateMatrixWorld(true);
    this.pip.updateRigViz();

    const cam = cfg.cam === 'turntable' ? this.turnCam : cfg.cam === 'work' && this.opts.layoutView === 'work' ? this.workCam : this.shotCam;
    this.fx.setScale(this.renderer.domElement.height / (2 * Math.tan(THREE.MathUtils.degToRad(cam.fov) / 2)));

    if (id === 'layout') {
      this.helperCam.position.copy(this.shotCam.position);
      this.helperCam.quaternion.copy(this.shotCam.quaternion);
      this.helperCam.updateMatrixWorld(true);
      this.camHelper.update();
      this.camGizmo.position.copy(this.shotCam.position);
      this.camGizmo.quaternion.copy(this.shotCam.quaternion);
    }

    this.render(cam, cfg);
    this.updateTimeline(t);
    if (this.bucket) this.stepBucket();
    this.screen.classList.toggle('show-title', id === 'final' && st.t > SHOT.len - 0.3);
    this.onFrame?.();
  }

  // ---- "Bucket" rendering: the frame appears tile by tile, the way production renderers show it ----
  startBucket() {
    const ov = $('bucket');
    ov.classList.remove('done');
    ov.hidden = false;
    this.bucket = { pending: true };
  }

  stepBucket() {
    const b = this.bucket, ov = $('bucket'), { w, h } = this.size;
    if (b.pending) {
      ov.width = w;
      ov.height = h;
      const img = document.createElement('canvas');
      img.width = w;
      img.height = h;
      img.getContext('2d').drawImage(this.canvas, 0, 0, w, h);
      const s = Math.max(32, Math.round(w / 14)), tiles = [];
      for (let y = 0; y < h; y += s) for (let x = 0; x < w; x += s) {
        const dx = x + s / 2 - w / 2, dy = y + s / 2 - h / 2;
        tiles.push({ x, y, d: Math.hypot(dx, dy) + Math.atan2(dy, dx) * 2 });
      }
      tiles.sort((a, c) => a.d - c.d);
      Object.assign(b, { pending: false, img, tiles, s, start: performance.now(), drawn: 0 });
      const g = ov.getContext('2d');
      g.fillStyle = '#0b0c10';
      g.fillRect(0, 0, w, h);
      return;
    }
    const g = ov.getContext('2d'), threads = 6, dur = 3800;
    const k = Math.min(1, (performance.now() - b.start) / dur);
    const done = Math.floor(k * b.tiles.length);
    for (; b.drawn < done; b.drawn++) {
      const tl = b.tiles[b.drawn];
      g.drawImage(b.img, tl.x, tl.y, b.s, b.s, tl.x, tl.y, b.s, b.s);
    }
    // Brackets around the tiles being worked on right now (one per CPU "thread").
    g.save();
    for (let i = done; i < Math.min(done + threads, b.tiles.length); i++) {
      const tl = b.tiles[i], s = b.s, c = s * 0.25;
      g.fillStyle = '#0b0c10';
      g.fillRect(tl.x, tl.y, s, s);
      const prog = (k * b.tiles.length) - done;
      g.globalAlpha = 0.25 + 0.5 * prog;
      g.drawImage(b.img, tl.x, tl.y, s, s * prog, tl.x, tl.y, s, s * prog);
      g.globalAlpha = 1;
      g.strokeStyle = '#ffd84a';
      g.lineWidth = 2;
      g.beginPath();
      for (const [x, y, dx, dy] of [[tl.x, tl.y, 1, 1], [tl.x + s, tl.y, -1, 1], [tl.x, tl.y + s, 1, -1], [tl.x + s, tl.y + s, -1, -1]]) {
        g.moveTo(x + dx * c, y); g.lineTo(x, y); g.lineTo(x, y + dy * c);
      }
      g.stroke();
    }
    g.restore();
    const label = $('bucket-label');
    if (label) label.textContent = k < 1 ? `Rendering frame ${frameOf(HERO_T)} — ${Math.round(k * 100)}%` : '';
    if (k >= 1) {
      g.drawImage(b.img, 0, 0);
      this.bucket = null;
      ov.classList.add('done');
      setTimeout(() => { if (!this.bucket) ov.hidden = true; }, 700);
    }
  }

  stopBucket() {
    this.bucket = null;
    $('bucket').hidden = true;
    const label = $('bucket-label');
    if (label) label.textContent = '';
  }

  render(cam, cfg) {
    const r = this.renderer, { w, h } = this.size;
    r.setScissorTest(false);
    r.setViewport(0, 0, w, h);
    const usePost = cfg.post && !(this.state.stage === 'rendering' && this.opts.pass !== 'beauty');
    if (usePost) {
      this.renderPass.camera = cam;
      this.grade.uniforms.uTime.value = this.clock.elapsedTime % 10;
      this.composer.render();
    } else {
      r.render(this.scene, cam);
    }

    if (this.state.stage === 'layout' && this.opts.layoutView === 'work') {
      // Picture-in-picture: what the shot camera sees.
      const iw = Math.round(w * 0.34), ih = Math.round(iw * h / w), m = Math.round(w * 0.02);
      this.camGizmo.visible = this.camHelper.visible = false;
      r.setScissorTest(true);
      r.setScissor(w - iw - m, m, iw, ih);
      r.setViewport(w - iw - m, m, iw, ih);
      r.render(this.scene, this.shotCam);
      r.setScissorTest(false);
      r.setViewport(0, 0, w, h);
      this.camGizmo.visible = this.camHelper.visible = true;
      const f = $('pip-frame').style;
      f.width = `${(iw / w) * 100}%`;
      f.height = `${(ih / h) * 100}%`;
      f.right = f.bottom = `${(m / w) * 100}%`;
    }

    if (this.state.stage === 'final' && this.opts.slices) this.renderSlices(cam);
  }

  // The finished frame cut into strips, each strip shown as an earlier department saw it.
  renderSlices(cam) {
    const r = this.renderer, { w, h } = this.size;
    const strips = [
      { looks: { pip: 'clay', env: 'clay', fx: 'clay' }, lights: 'viewport', fx: 'proxy' },
      { looks: { pip: 'proxy', env: 'proxy', fx: 'proxy' }, lights: 'viewport', fx: 'proxy' },
      { looks: { pip: 'final', env: 'clay', fx: 'final' }, lights: 'viewport', fx: 'full' },
      { looks: { pip: 'final', env: 'final', fx: 'final' }, lights: 'dusk', fx: 'full' },
    ];
    const sw = w / 5;
    r.autoClear = false;
    r.setScissorTest(true);
    strips.forEach((s, i) => {
      this.lib.apply(this.scene, { ...s.looks, studio: 'final' });
      this.applyLights(LIGHTS[s.lights]);
      this.sky.setLook(LIGHTS[s.lights].sky);
      this.sky.stars.visible = s.lights === 'dusk';
      this.fx.setLevel(s.fx);
      this.set.grass.visible = s.looks.env === 'final';
      r.setScissor(Math.round(i * sw), 0, Math.ceil(sw), h);
      r.clear();
      r.render(this.scene, cam);
    });
    r.setScissorTest(false);
    r.autoClear = true;
    this.applyLooks();
  }

  updateTimeline(t) {
    if ($('timeline').hidden) return;
    $('tl-head').style.left = `${(t / SHOT.len) * 100}%`;
    $('tl-frame').textContent = frameOf(t);
  }

  rigDemo(time) {
    const p = { ...REST_POSE }, u = this.opts.rigUser;
    if (u) {
      p.headYaw = (u.head ?? 0) * 0.9;
      p.armLUp = 0.12 + Math.max(0, u.arm ?? 0) * 2.6;
      p.armLFwd = (u.arm ?? 0) < 0 ? -(u.arm) * 1.6 : 0;
      p.sq = (u.squash ?? 0) * 0.45;
      p.lean = (u.lean ?? 0) * 0.5;
      p.headPitch = -(u.lean ?? 0) * 0.3;
      return p;
    }
    const c = time % 8;
    p.headYaw = Math.sin(time * 0.9) * 0.55;
    p.headPitch = Math.sin(time * 0.7) * 0.15;
    const wave = THREE.MathUtils.smoothstep(c, 0.5, 1.2) * (1 - THREE.MathUtils.smoothstep(c, 3.2, 3.9));
    p.armLUp = 0.12 + wave * (2.4 + Math.sin(time * 9) * 0.3);
    const sq = THREE.MathUtils.smoothstep(c, 4.2, 4.6) * (1 - THREE.MathUtils.smoothstep(c, 6.4, 7));
    p.sq = sq * Math.sin(time * 4.5) * 0.4;
    p.lean = sq * 0.12;
    p.armRUp = 0.12 + sq * 0.5;
    return p;
  }

  setVisible(v) { this.visible = v; }
}
