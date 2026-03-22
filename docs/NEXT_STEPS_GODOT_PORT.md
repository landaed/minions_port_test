# Next Steps for the Godot Port

## What is blocking "Enter World" right now?

Your current login flow already proves that the **PB/login/account/character-selection half** of the stack works.

What is *not* working yet is the **post-login gameplay bridge**:

1. The Godot client sends `enter_world` to the proxy.
2. The proxy forwards `PlayerAvatar.enterWorld(...)` to the original world server.
3. The world server builds `RootInfo`, selects a zone, and calls back into the client mind with `setRootInfo(...)`.
4. Your proxy currently only converts that into a status event for the UI.
5. The Godot UI then stops at "waiting for zone transfer / gameplay protocol bridge" because there is no renderer/gameplay runtime consuming the world state yet.

In other words: **you do not need to start with art import first**. You need the first playable gameplay bridge first.

## Recommended order of work

### Phase 1 — Make `setRootInfo` actually drive Godot
Before importing Trinst assets, make the Godot client able to:

- receive `root_info`,
- deserialize enough of the PB payload to understand:
  - player stats,
  - party members,
  - zone/instance identifiers,
  - spawn state,
- transition from the login UI into a separate in-game scene.

Even a graybox test scene is enough at this stage.

### Phase 2 — Decide how you will replace Torque zone networking
You have two broad choices:

#### Option A: Reuse original zone simulation temporarily
- Keep the Python/Torque server logic authoritative.
- Reverse-engineer or bridge the old zone protocol enough for Godot.
- Faster for validation, but ugly and legacy-heavy.

#### Option B: Replace zone runtime with your own Godot-friendly protocol
- Keep master/world/account/character systems.
- Rebuild moment-to-moment gameplay transport in a new protocol.
- More work up front, but cleaner long term.

Given your current progress, **Option B is probably the better destination**, but you can still use pieces of the original Python world logic as a reference/authority source.

### Phase 3 — Only then import Trinst assets
Art import becomes worthwhile once you can already:

- load a zone scene,
- spawn a player capsule,
- place static geometry,
- move around,
- display NPCs/objects as placeholders.

If you import assets before that, you risk burning time on visuals before the runtime contract is stable.

## What the asset automation in this repo can do

Use:

```bash
python3 tools/mom_asset_audit.py --mission field
```

This script will:

- scan the extracted MoM asset tree,
- count file types,
- parse Torque `.mis` mission files,
- extract references to terrain, interiors, shapes, textures, and other assets,
- emit a JSON manifest at `docs/generated/mom_asset_manifest.json`.

This is useful because the old Torque content is spread across several proprietary formats (`.dts`, `.dif`, `.ter`, `.dsq`, `.dml`, etc.), and you need a clean inventory before building converters.

## What I can realistically automate for you

I can help a lot with **pipeline glue**, but not magically solve every proprietary format by myself.

### I can do
- Build inventory/export scripts like the one added here.
- Parse `.mis` mission files and generate structured placement manifests.
- Write importers/converters for formats once you provide the format details or sample files.
- Generate Godot scene/JSON/CSV data from parsed mission placement.
- Build a graybox Trinst loader that places placeholders for interiors, static props, and terrain chunks.
- Help create a staged asset pipeline:
  - textures/audio copied directly,
  - models routed through Blender/Assimp if supported,
  - mission placements translated into Godot transforms.
- Help reverse-engineer how Trinst maps to the mission file names in your extracted data.

### You probably need to do yourself
- Provide the legally obtained original client/game asset install.
- Validate licensing/copyright boundaries for reused assets.
- Run Blender or other GUI-based conversion tools when proprietary formats need interactive fixes.
- Manually verify scale/orientation/material correctness.
- Decide whether to preserve exact old visuals or do a reinterpretation.
- Test the gameplay feel in Godot and decide how faithful the port should be.

## Practical milestone I recommend next

Do **not** begin with a full "convert everything" effort.

Instead, do this next:

1. Add a Godot gameplay scene separate from the login screen.
2. Extend the proxy so `root_info` includes the minimum fields Godot needs to know which zone was entered.
3. Build a graybox zone loader for the starting area.
4. Use `tools/mom_asset_audit.py` to identify which mission/terrain/interior files correspond to that zone.
5. Import only the first zone's terrain + a few landmark assets.
6. Keep all NPCs/props as placeholders until movement and replication work.

If you want, my next step can be one of these:

1. **Gameplay-first:** wire the proxy/Godot client so `enter_world` opens an in-game scene and displays parsed root info.
2. **Asset-first:** extend the asset audit script into a real mission-to-Godot scene exporter.
3. **Protocol-first:** inspect the old client/zone handoff and design the minimal replacement gameplay protocol.
