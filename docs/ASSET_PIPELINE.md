# Minions of Mirth → Godot Asset Pipeline

Goal: convert the original Torque Game Engine assets under `MoMReborn/` into
Godot-native formats, starting with the city of **Trinst**, and build up the
`minions-port/` Godot project. Maximize work done in the cloud (headless Godot
render-verification + headless Blender), so converted output can be reviewed by
screenshot before it lands on a desktop.

## Source engine & formats (verified on disk)

Minions of Mirth runs on the **Torque Game Engine**. Asset inventory (371 MB, 6175 files):

| Asset | Format | Version | Count | Conversion target |
|---|---|---|---|---|
| Models | `.dts` | **24** | 378 | glTF (`.glb`) |
| Animations | `.dsq` | — | 807 | glTF animation tracks |
| Interiors (buildings) | `.dif` | **44** | 192 | glTF (`.glb`) — version higher than stock TGE, validate per-file |
| Terrain | `.ter` | **4** | 17 | Terrain3D heightmap + control map |
| Textures | `.jpg`/`.png` | — | 2808 | copied (Godot-native) |
| Audio | `.ogg` | — | 1291 | copied (Godot-native) |
| Particles | datablocks in `.cs.dso` | — | — | `GPUParticles3D` + process material |
| Zone layout | `.mis` (text) | — | 17 | Godot scene `.tscn` / placement JSON |
| Material lists | `.dml` | — | 10 | newline list of texture basenames |

### Zone ↔ mission mapping
**Trinst = `data/missions/city.mis`** (its `MissionInfo.name` is literally
"The City of Trinst"). The Trinst Sewer System = `sewer.mis`.

`city.mis` object counts: 1 TerrainBlock, 97 InteriorInstance, 211 TSStatic,
146 ParticleEmitterNode, 140 sgUniversalStaticLight, 32 AudioEmitter, 1 WaterBlock,
Sky/Sun, foliage/grass/shape replicators, plus 374 rpgSpawnPoint + 151 rpgWayPoint
(gameplay markers, already handled server-side).

### Coordinate system
Torque is **Z-up, right-handed**; Godot is **Y-up**. All converters share one
transform (see `tools/`). Scale is in meters in both.

## Cloud toolchain (proven working)

Run once per fresh container (root, Ubuntu 24.04):

```bash
tools/cloud_setup.sh
```

This installs:
- **Godot 4.6** editor binary (`/usr/local/bin/godot`), rendering **Forward+ via
  software Vulkan (Mesa lavapipe) under Xvfb** — confirmed rendering + screenshots.
- **Blender 5.0** as the `bpy` Python module (headless mesh conversion).
- Pillow + numpy.

### Verifying any asset's look & scale in Godot
```bash
tools/render.sh path/to/asset.glb  out.png  [orbit_deg]
```
Loads the asset in `tools/asset_viewer/`, frames it, adds a 1 m grid + a **1.8 m
human-height reference capsule**, prints the asset's real-world AABB size, and
screenshots it. Use this to catch scale/orientation problems immediately.

## Build phases

- **Phase 0 — Cloud toolchain (done).** Godot render + Blender headless + asset viewer.
- **Phase 1 — Walkable Trinst slice.** `city.ter` → Terrain3D; `city.mis` → scene
  with the coordinate transform; sky/sun/fog; a few landmark interiors + statics;
  player capsule + collision. Verify scale in-engine.
- **Phase 2 — Fill in.** All 211 statics, 97 interiors, 146 particles, 32 audio
  emitters, foliage, 140 lights.
- **Phase 3 — Generalize.** Turn the converters into a reusable pipeline for the
  other 16 zones, wired to existing spawn data.

## Tools

| Path | Purpose |
|---|---|
| `tools/cloud_setup.sh` | Reproducible cloud toolchain bring-up |
| `tools/render.sh` | Headless screenshot of a .glb/.tscn (scale check) |
| `tools/asset_viewer/` | Godot project used by `render.sh` |
| `tools/dts/dts_reader.py` | Pure-Python DTS v24 reader (nodes/objects/meshes/materials) — **working** |
| `tools/dts/dts_to_gltf.py` | DTS → `.glb` (Z-up→Y-up, node-transform baking) — **working** |
| `tools/mom_asset_audit.py` | Existing asset inventory / `.mis` reference scanner |

## Converter status

- **DTS models + textures → glTF: working** (`tools/dts/`). Parse → `.glb` with
  embedded textures, validated by Godot render on props/architecture/trees/a
  character. Pending: skinned-mesh base geometry + `.dsq` animations.
- **Terrain → mesh + heightmap: working** (`tools/ter/`). `.ter` v4 → verification
  `.glb` + 16-bit PNG. Pending: Terrain3D region import + splat/control map.
- **Mission → placement manifest: working** (`tools/mis/`). `.mis` → Godot-space
  transforms for statics/interiors/lights/audio/particles/sun/sky/water.
- **Zone assembly: working** (`tools/build_trinst.py`, `tools/trinst_preview/`).
  Trinst assembled in Godot: terrain + 189/211 statics aligned at correct scale.
- **DIF interiors (buildings): blocked / needs RE.** MoM `.dif` are **version 44**
  (stock Torque is 0–14), so existing importers (RandomityGuy `io_dif`/`hxDIF`)
  won't read them directly. Structure confirmed (Torque interior: NULL/ORIGIN/
  TRIGGER markers, texture names, embedded PNG preview) but the v44 field layout
  must be reverse-engineered. This is the next major converter.
- **Not started:** particles (`.dso` datablocks), positional audio, foliage alpha
  compositing, skinned-character animation, wiring the zone into `minions-port`
  with a player controller + collision.

## Pipeline (end to end)

```bash
tools/cloud_setup.sh                 # one-time: Godot 4.6 + Blender + libs
python3 tools/build_trinst.py        # parse mission, convert terrain + shapes
# preview the assembled zone (aerial|ground|top):
SCENE=/tmp/trinst_build/scene.json OUT=/tmp/trinst.png CAM=ground \
  godot --path tools/trinst_preview --rendering-driver vulkan   # under xvfb-run
```
