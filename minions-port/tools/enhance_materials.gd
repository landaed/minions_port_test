extends SceneTree
## Offline material enhancement for trinst props/buildings (NO runtime work).
##
## Generates tangent-space normal maps, roughness-variation maps and ambient-
## occlusion maps from each prop's existing albedo texture, then wires them into
## shared StandardMaterial3D .tres resources applied as surface overrides on the
## editable prop scenes (assets/trinst/editable/*.tscn). Per-material scalars
## (normal strength, roughness, specular) are chosen from the legacy Torque
## material name (wood/stone/shingle/...), so the result stays tasteful instead
## of uniformly bumpy. Everything is baked to disk; nothing happens at runtime.
##
## Usage (run from the repo's minions-port directory, servers not required):
##   godot --headless --script res://tools/enhance_materials.gd -- --phase=generate
##   godot --headless --import .            # let Godot import the new textures
##   godot --headless --script res://tools/enhance_materials.gd -- --phase=apply
##
## Or simply:  ../tools/enhance_materials.sh   (runs all three steps)
##
## Other phases / flags:
##   --phase=strip     remove every generated override (back to plain albedo)
##   --force           regenerate maps even if the files already exist
##   --no-normal / --no-rough / --no-ao    skip a feature when generating
##
## Surfaces that already carry a hand-made override (e.g. the two hand-tuned
## tower1 materials) are left untouched. To toggle features on everything that
## was generated, see tools/toggle_material_features.gd.

const EDITABLE_DIR := "res://assets/trinst/editable/"
const MATERIAL_DIR := "res://assets/trinst/materials/generated/"
const TEXTURE_DIRS := ["res://assets/trinst/interiors/", "res://assets/trinst/shapes/"]
const SKIP_SCENES := ["terrain.tscn"]
const MAX_MAP_SIZE := 512

# Map legacy Torque material names to tasteful per-category parameters.
# normal_scale: strength of the generated normal map on the surface.
# roughness: base roughness (the generated map adds +/- variation around it).
# specular: dielectric specular intensity (StandardMaterial3D metallic_specular).
const CATEGORIES := {
	"wood":    {"keys": ["wood", "plank", "bark", "log"],                          "normal_scale": 1.0, "roughness": 0.82, "specular": 0.38},
	"stone":   {"keys": ["stone", "rock", "granite", "pierre", "cement", "brick", "wall", "cobble", "marble", "slate"], "normal_scale": 1.4, "roughness": 0.88, "specular": 0.45},
	"roof":    {"keys": ["shingle", "roof", "thatch"],                             "normal_scale": 1.2, "roughness": 0.9,  "specular": 0.35},
	"ground":  {"keys": ["grass", "dirt", "sand", "gravel", "mud"],                "normal_scale": 0.8, "roughness": 0.95, "specular": 0.25},
	"foliage": {"keys": ["leaf", "tree", "plant", "weed", "fern", "bush"],         "normal_scale": 0.5, "roughness": 0.95, "specular": 0.2},
	"metal":   {"keys": ["metal", "iron", "steel", "gold", "silver", "copper", "chain"], "normal_scale": 0.8, "roughness": 0.55, "specular": 0.6},
	"cloth":   {"keys": ["cloth", "rug", "tent", "canvas", "banner", "curtain"],   "normal_scale": 0.7, "roughness": 0.92, "specular": 0.25},
	"plaster": {"keys": ["drywall", "plaster", "stucco"],                          "normal_scale": 0.7, "roughness": 0.85, "specular": 0.32},
}
const DEFAULT_PARAMS := {"normal_scale": 1.0, "roughness": 0.85, "specular": 0.4}

# Map-generation tuning.
const BUMP_SCALE := 6.0          # heightfield slope strength fed to the sobel pass
const ROUGH_VARIATION := 0.28    # +/- swing of the roughness map around 1.0
const AO_STRENGTH := 0.45        # how dark crevices get in the AO map
const AO_BLUR_RADIUS := 6        # cavity detection radius (pixels at map size)

var force := false
var gen_normal := true
var gen_rough := true
var gen_ao := true

func _initialize() -> void:
	var phase := "generate"
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--phase="):
			phase = arg.get_slice("=", 1)
		elif arg == "--force":
			force = true
		elif arg == "--no-normal":
			gen_normal = false
		elif arg == "--no-rough":
			gen_rough = false
		elif arg == "--no-ao":
			gen_ao = false
	match phase:
		"generate":
			_phase_generate()
		"apply":
			_phase_apply()
		"strip":
			_phase_strip()
		_:
			push_error("Unknown --phase=%s (generate|apply|strip)" % phase)
	quit()

# ---------------------------------------------------------------------------
# Phase 1: bake normal/roughness/AO PNGs next to every prop albedo texture.
# ---------------------------------------------------------------------------
func _phase_generate() -> void:
	var albedos: Array[String] = []
	for dir_path in TEXTURE_DIRS:
		var d := DirAccess.open(dir_path)
		if d == null:
			continue
		for f in d.get_files():
			# Albedo textures extracted from the prop GLBs are plain .jpg files;
			# generated maps are .png so the two sets never collide.
			if f.get_extension().to_lower() == "jpg":
				albedos.append(dir_path + f)
	albedos.sort()
	var made := 0
	var skipped := 0
	for albedo in albedos:
		var n := _generate_maps_for(albedo)
		if n > 0:
			made += n
		else:
			skipped += 1
	print("[enhance] generate done: %d maps written (%d albedos already had maps)" % [made, skipped])

func _generate_maps_for(albedo_path: String) -> int:
	var abs_path := ProjectSettings.globalize_path(albedo_path)
	var base := albedo_path.get_basename()  # res://.../prefabs_tower1_0
	var normal_path := base + "_normal.png"
	var rough_path := base + "_rough.png"
	var ao_path := base + "_ao.png"
	var need_normal := gen_normal and (force or not FileAccess.file_exists(normal_path))
	var need_rough := gen_rough and (force or not FileAccess.file_exists(rough_path))
	var need_ao := gen_ao and (force or not FileAccess.file_exists(ao_path))
	if not (need_normal or need_rough or need_ao):
		return 0
	var img := Image.load_from_file(abs_path)
	if img == null or img.is_empty():
		push_warning("[enhance] could not read " + albedo_path)
		return 0
	img.convert(Image.FORMAT_RGB8)
	if img.get_width() > MAX_MAP_SIZE or img.get_height() > MAX_MAP_SIZE:
		var s := float(MAX_MAP_SIZE) / float(maxi(img.get_width(), img.get_height()))
		img.resize(int(img.get_width() * s), int(img.get_height() * s), Image.INTERPOLATE_LANCZOS)
	var height := _height_from_albedo(img)
	var written := 0
	if need_normal:
		var bump := height.duplicate()
		bump.bump_map_to_normal_map(BUMP_SCALE)
		bump.save_png(ProjectSettings.globalize_path(normal_path))
		written += 1
	if need_rough:
		_roughness_from_height(height).save_png(ProjectSettings.globalize_path(rough_path))
		written += 1
	if need_ao:
		_ao_from_height(height).save_png(ProjectSettings.globalize_path(ao_path))
		written += 1
	if written > 0:
		print("[enhance]   %s -> %d map(s)" % [albedo_path.get_file(), written])
	return written

func _height_from_albedo(img: Image) -> Image:
	# Luminance as a pseudo-heightfield, lightly smoothed so jpeg noise doesn't
	# turn into sandpaper normals.
	var w := img.get_width()
	var h := img.get_height()
	var out := Image.create(w, h, false, Image.FORMAT_RF)
	for y in range(h):
		for x in range(w):
			var c := img.get_pixel(x, y)
			out.set_pixel(x, y, Color(c.r * 0.299 + c.g * 0.587 + c.b * 0.114, 0, 0))
	return _box_blur(out, 1)

func _box_blur(src: Image, radius: int) -> Image:
	if radius <= 0:
		return src
	var w := src.get_width()
	var h := src.get_height()
	var tmp := Image.create(w, h, false, Image.FORMAT_RF)
	var out := Image.create(w, h, false, Image.FORMAT_RF)
	var span := float(radius * 2 + 1)
	for y in range(h):
		var acc := 0.0
		for x in range(-radius, radius + 1):
			acc += src.get_pixel(clampi(x, 0, w - 1), y).r
		for x in range(w):
			tmp.set_pixel(x, y, Color(acc / span, 0, 0))
			var x_add := clampi(x + radius + 1, 0, w - 1)
			var x_sub := clampi(x - radius, 0, w - 1)
			acc += src.get_pixel(x_add, y).r - src.get_pixel(x_sub, y).r
	for x in range(w):
		var acc := 0.0
		for y in range(-radius, radius + 1):
			acc += tmp.get_pixel(x, clampi(y, 0, h - 1)).r
		for y in range(h):
			out.set_pixel(x, y, Color(acc / span, 0, 0))
			var y_add := clampi(y + radius + 1, 0, h - 1)
			var y_sub := clampi(y - radius, 0, h - 1)
			acc += tmp.get_pixel(x, y_add).r - tmp.get_pixel(x, y_sub).r
	return out

func _roughness_from_height(height: Image) -> Image:
	# Brighter (raised/worn) areas read as slightly smoother, darker crevices as
	# rougher. Values stay near 1.0 so the material's roughness scalar keeps
	# control of the base level (final roughness = scalar * texture).
	var w := height.get_width()
	var h := height.get_height()
	var mean := 0.0
	for y in range(h):
		for x in range(w):
			mean += height.get_pixel(x, y).r
	mean /= float(w * h)
	var out := Image.create(w, h, false, Image.FORMAT_L8)
	for y in range(h):
		for x in range(w):
			var v := clampf(1.0 - (height.get_pixel(x, y).r - mean) * ROUGH_VARIATION * 2.0, 0.6, 1.0)
			out.set_pixel(x, y, Color(v, v, v))
	return out

func _ao_from_height(height: Image) -> Image:
	# Cavity AO: pixels below their blurred neighbourhood sit in a recess and
	# get darkened. Subtle by design (floor at 1-AO_STRENGTH).
	var blurred := _box_blur(height, AO_BLUR_RADIUS)
	var w := height.get_width()
	var h := height.get_height()
	var out := Image.create(w, h, false, Image.FORMAT_L8)
	for y in range(h):
		for x in range(w):
			var cavity: float = maxf(0.0, blurred.get_pixel(x, y).r - height.get_pixel(x, y).r)
			var v := clampf(1.0 - cavity * AO_STRENGTH * 4.0, 1.0 - AO_STRENGTH, 1.0)
			out.set_pixel(x, y, Color(v, v, v))
	return out

# ---------------------------------------------------------------------------
# Phase 2: build shared .tres materials and assign them as surface overrides
# on every editable prop scene.
# ---------------------------------------------------------------------------
func _phase_apply() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(MATERIAL_DIR))
	var scenes := _editable_scenes()
	var stats := {"scenes": 0, "surfaces": 0, "kept": 0, "materials": {}}
	for scene_path in scenes:
		var packed: PackedScene = load(scene_path)
		if packed == null:
			push_warning("[enhance] cannot load " + scene_path + " (skipped)")
			continue
		var node := packed.instantiate()
		var changed := _apply_to_node(node, stats)
		if changed:
			var repacked := PackedScene.new()
			if repacked.pack(node) == OK:
				repacked.take_over_path(scene_path)
				ResourceSaver.save(repacked, scene_path)
				stats["scenes"] += 1
			else:
				push_warning("[enhance] failed to repack " + scene_path)
		node.free()
	print("[enhance] apply done: %d scenes updated, %d surfaces enhanced, %d hand-made overrides kept, %d shared materials" % [
		stats["scenes"], stats["surfaces"], stats["kept"], stats["materials"].size()])

func _apply_to_node(node: Node, stats: Dictionary) -> bool:
	var changed := false
	if node is MeshInstance3D and node.mesh != null:
		for s in range(node.mesh.get_surface_count()):
			var existing: Material = node.get_surface_override_material(s)
			if existing != null:
				var gen_dir := existing.resource_path.begins_with(MATERIAL_DIR)
				if not gen_dir and not force:
					stats["kept"] += 1  # hand-made override (e.g. tower1) — leave it
					continue
			var mat: Material = node.mesh.surface_get_material(s)
			if not (mat is BaseMaterial3D):
				continue
			var albedo: Texture2D = mat.albedo_texture
			if albedo == null or albedo.resource_path.is_empty():
				continue
			var enhanced := _material_for(mat, albedo.resource_path, stats)
			if enhanced != null:
				node.set_surface_override_material(s, enhanced)
				stats["surfaces"] += 1
				changed = true
	for child in node.get_children():
		if _apply_to_node(child, stats):
			changed = true
	return changed

func _material_for(src: BaseMaterial3D, albedo_path: String, stats: Dictionary) -> StandardMaterial3D:
	var base := albedo_path.get_basename()
	var mat_path := MATERIAL_DIR + base.get_file() + ".tres"
	var cache: Dictionary = stats["materials"]
	if cache.has(mat_path):
		return cache[mat_path]
	var normal_path := base + "_normal.png"
	var rough_path := base + "_rough.png"
	var ao_path := base + "_ao.png"
	if not ResourceLoader.exists(normal_path) and not ResourceLoader.exists(rough_path) and not ResourceLoader.exists(ao_path):
		return null  # nothing generated for this texture (or not imported yet)
	var params := _params_for_material_name(src.resource_name, albedo_path)
	var mat := StandardMaterial3D.new()
	# Preserve the source look (two-sided cull, alpha mode, vertex colors, ...).
	mat.cull_mode = src.cull_mode
	mat.transparency = src.transparency
	mat.alpha_scissor_threshold = src.alpha_scissor_threshold
	mat.vertex_color_use_as_albedo = src.vertex_color_use_as_albedo
	mat.albedo_color = src.albedo_color
	mat.albedo_texture = src.albedo_texture
	mat.texture_filter = src.texture_filter
	mat.metallic = src.metallic
	mat.metallic_specular = params["specular"]
	mat.roughness = params["roughness"]
	if ResourceLoader.exists(normal_path):
		mat.normal_enabled = true
		mat.normal_texture = load(normal_path)
		mat.normal_scale = params["normal_scale"]
	if ResourceLoader.exists(rough_path):
		mat.roughness_texture = load(rough_path)
	if ResourceLoader.exists(ao_path):
		mat.ao_enabled = true
		mat.ao_texture = load(ao_path)
		mat.ao_light_affect = 0.35
	mat.resource_name = (src.resource_name if not src.resource_name.is_empty() else base.get_file()) + "_enhanced"
	var err := ResourceSaver.save(mat, mat_path)
	if err != OK:
		push_warning("[enhance] failed to save material " + mat_path)
		return null
	# Reload so every scene shares the same on-disk resource (stable ext refs).
	var shared: StandardMaterial3D = load(mat_path)
	cache[mat_path] = shared
	return shared

func _params_for_material_name(mat_name: String, albedo_path: String) -> Dictionary:
	var probe := (mat_name + " " + albedo_path.get_file()).to_lower()
	for cat in CATEGORIES.values():
		for key in cat["keys"]:
			if probe.contains(key):
				return cat
	return DEFAULT_PARAMS

# ---------------------------------------------------------------------------
# Phase 3 (strip): remove generated overrides so props fall back to the plain
# GLB albedo materials. Hand-made overrides are left alone.
# ---------------------------------------------------------------------------
func _phase_strip() -> void:
	var removed := 0
	var scenes_touched := 0
	for scene_path in _editable_scenes():
		var packed: PackedScene = load(scene_path)
		if packed == null:
			continue
		var node := packed.instantiate()
		var n := _strip_node(node)
		if n > 0:
			var repacked := PackedScene.new()
			if repacked.pack(node) == OK:
				repacked.take_over_path(scene_path)
				ResourceSaver.save(repacked, scene_path)
				scenes_touched += 1
				removed += n
		node.free()
	print("[enhance] strip done: removed %d generated overrides from %d scenes" % [removed, scenes_touched])

func _strip_node(node: Node) -> int:
	var n := 0
	if node is MeshInstance3D and node.mesh != null:
		for s in range(node.mesh.get_surface_count()):
			var existing: Material = node.get_surface_override_material(s)
			if existing != null and existing.resource_path.begins_with(MATERIAL_DIR):
				node.set_surface_override_material(s, null)
				n += 1
	for child in node.get_children():
		n += _strip_node(child)
	return n

func _editable_scenes() -> Array[String]:
	var out: Array[String] = []
	var d := DirAccess.open(EDITABLE_DIR)
	if d == null:
		return out
	for f in d.get_files():
		if f.get_extension() == "tscn" and not SKIP_SCENES.has(f):
			out.append(EDITABLE_DIR + f)
	out.sort()
	return out
