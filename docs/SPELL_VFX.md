# Spell-casting particle effects: how they work and how to edit them

## Short answer

They are **not prefabs** (yet) — they're generated in code at runtime by
`minions-port/world/vfx.gd`. The original engine described each spell's visuals
as named emitter datablocks; the port maps those names to `CPUParticles3D`
presets. You now have **two** ways to customise them:

1. Tweak the presets in `world/vfx.gd` (quick, global).
2. **Author an override prefab** in `minions-port/assets/vfx/emitters/` and edit
   it visually in the editor, shaders and all (new — see that folder's README).
   `VFX.emitter()` uses your prefab if present and falls back to the code preset
   otherwise.

## The pipeline, end to end

1. **Original spell data** (`mud/world/spell.py`) carries particle fields on each
   `SpellProto`: `particleCasting`, `particleBegin`, `particleTick`,
   `particleTextureCasting`, `explosionBegin`, plus `SpellParticleNode` rows.
2. **Casting a spell** calls the legacy client RPCs (`newParticleSystem`,
   `spawnExplosion`, `newSpellEffect`, `triggerParticleNodes`, `itemParticleNode`).
3. **The headless server intercepts them** in
   `mud/world/stubsim.py:_capture_vfx_call()` and turns each into a small JSON
   event, e.g. `{"event":"particles","sim_id":123,"emitter":"CastingEmitter",
   "texture":"plasma","duration":1.5}`, queued on `vfx_events`.
4. **The proxy/client forward them**: `ClientProxy.py` streams the events into the
   Godot client; `control.gd` hands them to `gameplay_view.gd:apply_vfx_events()`.
5. **The client plays them** (`gameplay_view.gd`): it finds the target's node and
   calls into `VFX`:
   - `"particles"` → `VFX.emitter()` (casting swirl, fire, smoke, sparkle, ...)
   - `"explosion"` → `VFX.explosion()` (impact burst + light flash)
   - `"spell_effect"` → `VFX.casting_ring()` (the zodiac circle under the caster)
   - `"casting"` on/off → `VFX.stop_emitters(node,"casting")` to end the wind-up

## What `VFX.emitter()` builds (`world/vfx.gd`)

A `CPUParticles3D` whose parameters are picked by substring of the emitter name:

| Name contains | Look | Key params |
|---|---|---|
| `fire`    | orange rising flame | amount 36, vel 1.2–2.2 |
| `smoke`   | slow grey billows   | amount 14, lifetime 1.6 |
| `casting` | blue inward swirl    | amount 30, sphere emission r=0.7 |
| `begin`   | outward burst        | amount 40, spread 180°, explosive |
| *(else)*  | gentle sparkle       | amount 24 |

The material is a runtime `StandardMaterial3D`: additive blend, unshaded,
billboarded; albedo is the sprite at
`assets/vfx/particles/<texture>.jpg` (with an optional `<texture>.alpha.jpg`
mask, else luminance is used as alpha). `explosion()` and `casting_ring()` work
the same way (`casting_ring` uses `assets/vfx/zodiacs/zode_symbols.png`).

## Editing recipes

- **Retune an existing look globally:** edit the preset block in
  `world/vfx.gd:emitter()` (colors, `amount`, `lifetime`, velocities, emission
  shape). Same for `explosion()` / `casting_ring()`.
- **Swap a sprite:** drop a new `name.jpg` (+ optional `name.alpha.jpg`) into
  `assets/vfx/particles/`; the server's texture name selects it.
- **Build a bespoke effect in the editor (recommended for new/fancy VFX):** make
  `assets/vfx/emitters/<name>.tscn` (e.g. `casting.tscn`). Use `GPUParticles3D`,
  sub-emitters, lights, tweens — anything. Optional `configure(texture_name,
  duration)` on its root lets it honour the server's per-spell texture.
- **Add a shader:** put a `.gdshader` in `minions-port/shaders/` (there's a
  `water.gdshader` to crib from) and assign a `ShaderMaterial` in your override
  prefab — either a `spatial` shader on the draw-pass material or a `particles`
  shader on the process material.

## File map

| Concern | File |
|---|---|
| Particle/explosion/ring engine | `minions-port/world/vfx.gd` |
| Override prefabs (new) | `minions-port/assets/vfx/emitters/` |
| Client event handler | `minions-port/gameplay_view.gd` → `apply_vfx_events()` |
| Event dispatch | `minions-port/control.gd` |
| Server → event capture | `mud/world/stubsim.py` → `_capture_vfx_call()` |
| Spell particle data | `mud/world/spell.py` (`SpellProto`, `SpellParticleNode`) |
| Sprites | `minions-port/assets/vfx/particles/` |
| Reusable shaders | `minions-port/shaders/` |
