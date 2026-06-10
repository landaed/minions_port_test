extends SceneTree
## Bulk-toggle features on every GENERATED prop material (see
## tools/enhance_materials.gd) without regenerating anything. Lets you compare
## the enhanced look against plain albedo, or tone a feature down globally.
##
## Usage:
##   godot --headless --script res://tools/toggle_material_features.gd -- \
##       [--normal=on|off] [--rough=on|off] [--ao=on|off] \
##       [--normal-scale=K] [--specular=F]
##
## Examples:
##   -- --normal=off                # disable all generated normal maps
##   -- --normal=on --normal-scale=0.7   # re-enable, slightly subtler
##   -- --ao=off --rough=off        # albedo + normal only
##
## Hand-made materials (anything outside assets/trinst/materials/generated/)
## are never touched.

const MATERIAL_DIR := "res://assets/trinst/materials/generated/"

func _initialize() -> void:
	var set_normal := ""
	var set_rough := ""
	var set_ao := ""
	var normal_scale_mul := -1.0
	var specular := -1.0
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--normal="):
			set_normal = arg.get_slice("=", 1)
		elif arg.begins_with("--rough="):
			set_rough = arg.get_slice("=", 1)
		elif arg.begins_with("--ao="):
			set_ao = arg.get_slice("=", 1)
		elif arg.begins_with("--normal-scale="):
			normal_scale_mul = float(arg.get_slice("=", 1))
		elif arg.begins_with("--specular="):
			specular = float(arg.get_slice("=", 1))
	var d := DirAccess.open(MATERIAL_DIR)
	if d == null:
		print("[toggle] no generated materials at %s — run enhance_materials.gd first" % MATERIAL_DIR)
		quit()
		return
	var changed := 0
	for f in d.get_files():
		if f.get_extension() != "tres":
			continue
		var path := MATERIAL_DIR + f
		var mat: StandardMaterial3D = load(path)
		if mat == null:
			continue
		if set_normal == "off":
			mat.normal_enabled = false
		elif set_normal == "on" and mat.normal_texture != null:
			mat.normal_enabled = true
		if normal_scale_mul >= 0.0:
			mat.normal_scale = normal_scale_mul
		if set_rough == "off":
			mat.roughness_texture = null
			# Base roughness scalar stays, so the surface keeps its category look.
		elif set_rough == "on":
			var rough_path := _map_path_for(mat, "_rough.png")
			if ResourceLoader.exists(rough_path):
				mat.roughness_texture = load(rough_path)
		if set_ao == "off":
			mat.ao_enabled = false
		elif set_ao == "on" and mat.ao_texture != null:
			mat.ao_enabled = true
		if specular >= 0.0:
			mat.metallic_specular = specular
		ResourceSaver.save(mat, path)
		changed += 1
	print("[toggle] updated %d generated materials" % changed)
	quit()

func _map_path_for(mat: StandardMaterial3D, suffix: String) -> String:
	if mat.albedo_texture == null or mat.albedo_texture.resource_path.is_empty():
		return ""
	return mat.albedo_texture.resource_path.get_basename() + suffix
