# Building a single Windows .exe from Linux

This is the recommended way to play on Windows without making the two Godot
editors identical. You build one self-contained `.exe` on the Linux box (where
all the assets already exist on disk) and copy that single file to Windows.

## Why the Windows editor shows "missing" materials / an invisible tower

It is exactly what you suspected: some generated files were never committed.

- The trinst props/buildings get their look from **override materials** in
  `minions-port/assets/trinst/materials/generated/*.tres` (227 of them, all
  committed). Each one references external textures, e.g. for `prefabs_tower1`:
  - `assets/trinst/interiors/prefabs_tower1_1.jpg` (albedo)
  - `assets/trinst/interiors/prefabs_tower1_1_normal.png`
  - `assets/trinst/interiors/prefabs_tower1_1_ao.png`
  - `assets/trinst/interiors/prefabs_tower1_1_rough.png`
- Those textures (227 `.jpg` + 681 `.png`) are produced **on disk** by
  `tools/enhance_materials.gd` (the normal/roughness/AO maps are computed from
  each prop's albedo). They are **not** re-extracted by Godot on import.
- `minions-port/.gitignore` used to ignore every `.jpg/.png` under
  `assets/trinst/interiors/` and `assets/trinst/shapes/`, so **none of them were
  committed**. On your Linux working tree they were present (you ran the bake);
  on a fresh clone (the Windows machine) they are missing — hence the missing
  materials and the invisible `prefabs_tower1`. (The `cull_mode = 2` on those
  materials is "double-sided", so backface culling was a red herring; the real
  cause is the missing texture files.)

The `.gitignore` is now corrected so those textures **can** be tracked.

## Two ways to fix it

### A. Build a single .exe on Linux (recommended — no editor syncing)

When Godot exports, it bundles the **imported resources from this machine's
disk** into the PCK, and `binary_format/embed_pck=true` puts the PCK *inside*
the executable. So the `.exe` you build on Linux already contains every trinst
texture — even the ones git doesn't track — and "just works" on Windows.

1. Install the Windows export templates for **4.6** (must match your editor):
   - Editor: `Editor > Manage Export Templates > Download and Install`, or
   - download `Godot_v4.6-stable_export_templates.tpz` and unzip its contents
     into `~/.local/share/godot/export_templates/4.6.stable/`.
2. Build:
   ```bash
   # godot 4.6 on PATH, or pass GODOT=/path/to/godot
   tools/build_windows_exe.sh
   # -> build/windows/MinionsOfMirth.exe   (one self-contained file)
   ```
   The preset is committed at `minions-port/export_presets.cfg` (Windows
   Desktop, x86_64, embedded PCK). You can also export from the editor UI:
   `Project > Export > Windows Desktop > Export Project`.
3. Copy `MinionsOfMirth.exe` to the Windows machine and run it. It is only the
   **client** — the servers still run wherever you host them; type the server
   `host:port` into the address field at login (see `docs/WINDOWS_SETUP.md`).

Notes:
- The project renders with D3D12 on Windows (`rendering_device/driver.windows
  = "d3d12"`). The preset's "Export D3D12 = Auto" ships the required runtime, so
  the exe needs no extra DLLs. If you ever see a `dxil.dll`/D3D12 error, set
  `Export D3D12 = Yes` in the export options (or remove the d3d12 override to
  fall back to Vulkan).
- Build on the **Linux** box (the one with the baked textures on disk). Building
  on a machine that is itself missing the textures would bundle a broken set.

### B. Commit (or regenerate) the textures so the Windows editor works too

Only needed if you want to open/edit the scene in the editor on Windows.

- From the Linux machine that ran the bake, commit the now-tracked textures:
  ```bash
  git add minions-port/assets/trinst/interiors minions-port/assets/trinst/shapes
  git commit -m "Track baked trinst PBR textures"
  ```
  (With the corrected `.gitignore` this stages only the ~690 baked PBR maps,
  ~35 MB; the albedo is import-regenerated and stays out. If you'd rather keep
  the repo small, use option A instead and skip this.)
- Or, on any clone, regenerate them from the committed `.glb` meshes:
  ```bash
  tools/enhance_materials.sh           # needs godot 4.6 on PATH
  ```
