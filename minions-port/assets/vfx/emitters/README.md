# Spell VFX override prefabs

Drop a Godot scene (`.tscn`) in this folder to **replace the code-generated
particle preset** for a spell effect with one you build and edit visually in the
editor. If no prefab matches, `world/vfx.gd` falls back to its built-in
`CPUParticles3D` presets, so this is purely additive — nothing breaks if the
folder is empty.

## How a prefab is matched

When the server asks the client to play an emitter (e.g. `CastingEmitter`,
`ChimneyFire`, `SpellBeginEmitter`), `VFX.emitter()` looks here first, most- to
least-specific:

1. `:<emittername>.tscn` — exact match, lowercased. e.g. `castingemitter.tscn`
2. `<keyword>.tscn` — one of `casting`, `begin`, `smoke`, `fire`. e.g. a single
   `casting.tscn` overrides every `*Casting*` emitter.

The instanced scene is parented to the casting character at a small offset and
auto-freed after the effect's duration.

## Authoring one

1. In the editor: `Scene > New Scene`, root = `GPUParticles3D` (or any `Node3D`).
2. Build the effect: set a `ParticleProcessMaterial` (or a custom shader — see
   below), a draw pass mesh/material, sub-emitters, lights, tweens, whatever.
3. Save it here as e.g. `casting.tscn`.

### Adding a custom shader

- On the particle's **draw pass material**, use a `ShaderMaterial` with a
  `shader_type spatial;` shader (billboarded quads), or
- On the **process** stage, use a `ShaderMaterial` with `shader_type particles;`
  for fully GPU-driven motion.
- Keep reusable `.gdshader` files in `minions-port/shaders/` (there's already a
  `water.gdshader` there to copy from).

### Optional: react to the server's texture/lifetime

If your prefab's root script defines:

```gdscript
func configure(texture_name: String, duration: float) -> void:
    # texture_name is the legacy particle sprite name (see assets/vfx/particles/),
    # duration is in seconds. Wire these into your material/emitter as you like.
```

`VFX.emitter()` will call it right after instancing, so one prefab can still use
the per-spell texture the server picked.
