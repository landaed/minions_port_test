# Testing Cheats, Class Starting Spells, Icons, Equipment & Combat Visuals

This documents the systems added for in-game testing and gameplay polish:
the cheat tools, class-correct starting abilities/spells, original icon art,
equipment that shows on character models, and skill/spell animations with
particle effects and sounds.

## 1. Cheat tools (toggleable)

**Server gate:** the world server only honors cheats when `MOM_ENABLE_CHEATS=1`
is set in its environment. `./run_servers.sh` exports it **by default** for the
local test stack; start with `./run_servers.sh --no-cheats` (or export
`MOM_ENABLE_CHEATS=0`) to play without them. Implementation:
`mud/world/cheats.py`, exposed as `PlayerAvatar.perspective_cheat` and proxied
via the `{"type": "cheat", "action": ..., "params": {...}}` WebSocket message.

**Client:** press **F8** in-game to toggle the cheat window. It offers:

| Action | UI | Server behavior |
|---|---|---|
| Give XP | amount + button | `Character.gainXP(amount, clamp=False)` (exact amount, same path as XP certificates) |
| Set level | spinbox + button | repeated `gainLevel(0)` to the target primary level (engine can only level up) |
| Full heal | button | restores party health/mana/stamina, clears skill reuse + recast timers |
| Raise all skills | points + button | deterministic `checkSkillRaise(name, 0, 0)` loops |
| Give platinum | amount + button | `player.platinum += n` |
| Give item | search box → list → count + Give | full item DB search (`list_items`); `player.giveItem` + auto-equip when it lands on a worn slot |
| Learn spell | search box → list → Learn | full spell DB search (`list_spells`); creates a `CharacterSpell` in the next free slot |
| Learn all class spells | button | every `SpellClass` entry for your classes up to your level (`max_level` param to override) |

Results stream back as `cheat_result` messages: shown in the window status
line and the combat log. Mutating actions auto-refresh inventory + spellbook.

Headless regression test: `python3 tools/proxy_cheat_test.py` (creates a fresh
Wizard, verifies starting spells, runs every cheat action).

## 2. Class starting abilities & spells

In the original game a fresh character got class-appropriate spell **scrolls**
in inventory (see the `starting_gear` table) and had to click each one onto a
spellbook slot; the default hotbar was just Attack + Kick (per
`mud/client/gui/defaultMacros.py`), so "only Kick regardless of class" really
was original behavior for melee classes — but casters were supposed to have
scrolls to scribe, which the port was silently losing (see §6).

Now, at creation:

- `Character.autoScribeStartingSpells()` (called from
  `PlayerAvatar.newCharacter`) scribes those StartingGear scrolls directly into
  the spellbook, consuming them — a new Wizard spawns with Flying Cinder,
  Arcane Bonds, Icy Touch, Fire Shock, Magic Missile, Frost Touch and
  Lightning Spark memorized; a Cleric with Minor Heal etc.
- The hotbar auto-fills (until the player customizes it) with **active skills
  first, then memorized spells**, each with its proper icon
  (`Hotbar.default_fill_from_skills`).
- The ability list streamed to the client is the character's real *active*
  skills only — passive weapon proficiencies no longer pad the bar, and an
  empty list (fresh caster) is respected instead of falling back to
  placeholder names.

## 3. Icons

All spell, ability and item icons now resolve to the original game art:

- Copied `data/ui/icons/` (spell sheets `spells01–07.jpg`, `gemicons01–03.jpg`,
  loose status icons) into `minions-port/assets/ui/icons/`.
- `UIC.spell_icon()` decodes every original reference style:
  `SPELLICON_<sheet>_<index>` → 40 px cell `(index%6, index/6)` of
  `spells0<sheet>.jpg` (the exact decode the original `itemInfoWnd.py` used),
  loose names → `spellicons/<name>.jpg` then `icons/<name>.jpg`
  (with `.alpha.jpg` mask compositing).
- Active skills carry their icon from the original `skillinfo.py` table
  (loaded by file path server-side — the legacy client package can't be
  imported wholesale).
- Item icons (`item_proto.bitmap` → `assets/ui/items/...`) already worked;
  coverage verified at 100% of the 393 referenced bitmaps.

## 4. Equipment on character models

- **Armor** was already streamed as per-part texture indices
  (`compute_appearance`); the caches (`mob._godot_tex`) are now invalidated on
  equip/unequip so a gear change updates your look immediately.
- **Weapons / shields / helmets:** all 79 equipment shapes were converted
  DTS → GLB (`tools/build_equipment.py` → `minions-port/assets/equipment/`,
  texture overrides under `assets/equipment/textures/`). The entity snapshot
  now streams a `mounts` dict per entity — `{"0": {model, material}, ...}` for
  primary hand / off hand / shield / head — computed with the legacy
  `SimMobInfo` MOUNT0..3 rules (two-handers hide the off-hand/shield unless
  Power Wield). `CharacterRig.apply_mounts` instantiates the GLB under a
  `BoneAttachment3D` on the skeleton's `Mount0..Mount3` bones (preserved by
  the DTS pipeline in every character GLB) and applies the material texture
  override when set.
- Mob loot auto-equip (`mob.aiEquipItem`) was a dead no-op (§6), so NPCs now
  actually wield the weapons they drop.

## 5. Skill/spell animations, particles, sounds

**Animations.** All 61 character GLBs were rebuilt with the full original
animation set (24 clips on humanoids): kick1/kick2, spellcast/spellcast2,
spellprepare (looping wind-up), pain1/pain2, bowattack, shieldblock,
2hslash/2hthrust/1hthrust, plus the dance/point/agree/disagree/bow/wave
emotes (`tools/build_characters.py`).

**Event channel.** The legacy engine sent `playAnimation`, `newParticleSystem`,
`triggerParticleNodes`, `spawnExplosion`, `newSpellEffect`, `itemParticleNode`
and 3D `playSound` calls to the Torque zone client; the headless
`StubSimAvatar` was swallowing them. It now captures them in a ring buffer
(`stubsim._capture_vfx_call`) which `getVisibleEntities` drains per player
(snapshot shape is now `{"entities": [...], "events": [...]}`) and the proxy
forwards inside `entity_snapshot.events`.

**Client playback** (`gameplay_view.apply_vfx_events` + `world/vfx.gd`):

- `anim` events → `CharacterRig.play_overlay()` with the original clip when
  the rig has it and sensible fallbacks otherwise (`ANIM_FALLBACKS`): Kick
  plays `kick1`, Flying Tiger `kick2`, casts `spellcast`, the server's
  per-swing `_attack` keeps the generic swing, shield blocks flinch, etc.
  Overlays suppress the locomotion state machine until done (movement cancels).
- `particles` / `particle_nodes` → CPUParticles3D presets picked from the
  legacy emitter name (fire / smoke / casting swirl / begin burst) textured
  with the original particle art (`assets/vfx/particles/`, alpha-masked).
- `explosion` → burst + light flash, tinted per explosion family
  (water/ground/target).
- `spell_effect` (SimpleZodiacN…) → the iconic rotating **zodiac casting ring**
  (`assets/vfx/zodiacs/zode_symbols.png`).
- `item_particle` → persistent emitter pinned to the weapon mount (flaming
  blades).
- `sound3d` events + the per-player `play_sound` message → positional /
  UI playback of the original `.ogg` sfx (copied to `assets/sound/sfx`,
  case-insensitive lookup because the server lowercases paths).
- `begin_casting` → looping `spellprepare` on your avatar + a **cast bar**
  above the hotbar; the release (spellcast anim, ring, begin-particles,
  explosion) arrives via the zone events above.
- Hit reactions: any entity (and your own avatar) whose health drops plays
  `pain1`/`pain2`, rate-limited.

## 6. Py2 → Py3 lazy `map()` bug sweep

`map(f, xs)` as a statement does nothing in Python 3 (lazy iterator). 15 such
sites were silently dead, including:

- `Character.backupItems` — **every new character lost its entire starting
  gear** at creation export (this is why fresh characters fought unarmed and
  casters had no scrolls to scribe).
- `Mob.initLoot` — mobs never equipped their loot weapons.
- `Player.backupItems` — bank items and party inventories were never backed up
  on save.
- pet equip/unequip paths, vendor stock cleanup, zone mob cleanup,
  aggro/xpDamage/recastTimer dict cleanup, process cancellation on stat loss.

All are now real loops.

## 7. Verifying

```bash
./run_servers.sh --setup          # cheats enabled by default
python3 tools/proxy_cheat_test.py # headless: starting spells + all cheat actions

# full visual tour (login → create → spawn → combat → cheats → casting):
MOM_SHOT_DIR=/tmp/shots xvfb-run -a godot --path minions-port \
    --script res://tools/autotest_driver.gd
# class-specific run:  MOM_AT_CLASS=Wizard ... (same command)
```

The autotest now also exercises the cheat window (search/give item, set level,
learn class spells) and captures the cast bar / casting visuals.
