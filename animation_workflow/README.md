# animation_workflow — How a 3D Animated Film Is Made

An interactive, scroll-driven explainer of a **3D animation studio pipeline**,
written for people who have never seen one. It follows a single six-second shot
(`sq010_sh020`: Pip the little robot leaping to catch a firefly) through all
fourteen steps, from a notebook scribble to the finished frame. A sticky viewport
shows the shot exactly as each department would see it on their screen.

Live: <https://zenoonan.github.io/Research/animation_workflow/>

## What's on the page

| # | Stage | What the viewport shows | Try it |
|---|---|---|---|
| 01 | Story | The idea, handwritten in a notebook | — |
| 02 | Visual development | Three design options, then the model sheet (front / side / back) | switch pages |
| 03 | Storyboard | Six pencil panels for the shot | — |
| 04 | Animatic | The panels timed to temp sound: 6 s × 24 fps = 144 frames | — |
| 05 | Modelling | Grey clay Pip on a turntable, wireframe on | polygon-detail slider, wireframe, drag to orbit |
| 06 | Surfacing | UV test grid → painted colour → full materials, with the flat texture inset | 3-step toggle |
| 07 | Rigging | See-through Pip with bones and animator controls | head / arm / squash / lean sliders |
| 08 | Layout | Stand-in set and characters, the camera and its frustum, plus what the camera sees | work view / through the lens |
| 09 | Animation | The shot as a playblast with keyframes on a timeline and the body's arc | blocking / spline / polish, scrub |
| 10 | FX | Firefly glow and trail, dust, sparkles, background fireflies | raw particles vs rendered |
| 11 | Lighting | Final materials, dusk lighting, shadows and the firefly as a light | key / fill / rim / firefly + plan view |
| 12 | Rendering | The hero frame appearing bucket by bucket, plus render passes and a render-farm grid | beauty / depth / normals / ID mattes |
| 13 | Compositing | The frame built up from layers, with bloom and a colour grade | layer stack toggles |
| 14 | Final | The finished shot, letterboxed, with an end title | the whole pipeline in one frame (slices) |

After the walkthrough come short sections on why it's not really a straight line
(dailies, notes going back upstream, many shots in flight at once, pipeline TDs),
some numbers, and a glossary. A **guided tour** button scrolls through every step
on a timer.

## How it's built

There is no build step and there are no assets. Everything (the robot, the meadow,
the textures, the animation, the particles) is generated in code and rendered live
with [three.js](https://threejs.org) r170, loaded from jsDelivr through an import map.

```
animation_workflow/
├── index.html        page structure and all the explanatory copy
├── css/style.css     layout (sticky viewport + scrolling cards; stacks on phones)
└── js/
    ├── main.js       scroll tracking, nav chips, card controls, render-farm grid, tour
    ├── viewer.js     the 3D viewport: per-stage looks, lights, cameras, post-processing
    ├── pip.js        the robot: primitives, joints/rig, poses, bones and controls
    ├── shot.js       key poses, interpolation (stepped / spline / polish), camera move,
    │                 firefly path, pre-simulated antenna spring
    ├── fx.js         particle systems (all a pure function of shot time, so scrubbing works)
    ├── world.js      the set, sky, turntable studio and layout camera gizmo
    ├── materials.js  "looks": clay, proxy, UV, paint, final, ghost, depth, normal, ID
    ├── textures.js   procedural canvas textures (UV grid, body paint, ground, rock…)
    └── sketches.js   the 2D pre-production artwork as SVG (notebook, sheets, boards, animatic)
```

The key idea is that there is **one scene and one Pip**. Each stage re-dresses it:
every mesh carries a role (`pip.head`, `env.rock`, …) and a "look" maps roles to
materials, so the same geometry can be grey clay, a UV grid, flat proxy colours,
final materials, or a render pass.

If WebGL isn't available, the text and the 2D stages still work and the 3D
viewport shows a short notice.

## Running locally

The page uses ES modules, so it must be served over HTTP (opening the file
directly won't work). From the repository root:

```bash
python3 -m http.server 8000
# then open http://localhost:8000/animation_workflow/
```

## Notes on accuracy

Department names, tools and hand-offs follow the common shape of a feature-film CG
pipeline. Studios differ in the details: some merge layout and animation, call
surfacing "look development", or put rendering inside lighting. File names such as
`sq010_sh020_anim_v023` are illustrative of typical sequence/shot/version naming.
Figures like "a few seconds of animation per animator per week" and "more than a
thousand shots" are rules of thumb, not measurements.
