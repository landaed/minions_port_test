@tool
extends EditorScript
## Bake the converted Trinst JSON/GLB set into editable Godot scenes.
##
## Run from Godot with FileSystem -> res://tools/bake_trinst_editable.gd -> Run.
## Use this only if your checkout does not already have an editable
## res://world/zones/trinst.tscn scene. It creates:
##   res://assets/trinst/editable/<asset>.tscn  (one inherited wrapper per GLB)
##   res://world/trinst_baked.tscn              (placed editable fallback scene)
##
## Collision is generated once in the editor and saved into those .tscn files, so
## the live loader can instance saved collision instead of calling
## create_trimesh_collision() during gameplay.

const ZONE := "trinst"
const ASSET_ROOT := "res://assets/"
const BAKED_SCENE_PATH := "res://world/trinst_baked.tscn"
const EDITABLE_DIR := "res://assets/trinst/editable/"
const TERRAIN_LAYER := 1 | 4
const WORLD_LAYER := 1

# Match zone_loader.gd: these interiors are visual/decorative and should not
# trap the player at spawn.
const PASSTHROUGH_INTERIORS := ["architecture_bindpoint"]

# Static shapes that should receive saved editor collision. Small alpha-card or
# light fixtures stay decorative by default.
const COLLIDING_STATIC_PREFIXES := [
	"shapes/objects_",
	"shapes/rocks_",
	"shapes/trees_",
]

func _run() -> void:
	bake_zone(ZONE)

func bake_zone(zone: String) -> void:
	var base := ASSET_ROOT + zone + "/"
	var data := _load_json(base + "scene.json")
	if data.is_empty():
		push_error("Missing or invalid " + base + "scene.json")
		return
	_ensure_dir(EDITABLE_DIR)
	_bake_asset_wrappers(zone, data)
	_bake_placed_scene(zone, data)
	get_editor_interface().get_resource_filesystem().scan()
	print("Baked editable %s scene and collider wrappers." % zone)

func _bake_asset_wrappers(zone: String, data: Dictionary) -> void:
	var base := ASSET_ROOT + zone + "/"
	if data.has("terrain_glb"):
		_bake_asset_wrapper(base + str(data["terrain_glb"]), true, TERRAIN_LAYER)
	for item in data.get("statics", []):
		var rel = item.get("glb", null)
		if rel == null:
			continue
		var rel_s := str(rel)
		_bake_asset_wrapper(base + rel_s, _static_should_collide(rel_s), WORLD_LAYER)
	for item in data.get("interiors", []):
		var rel = item.get("glb", null)
		if rel == null:
			continue
		var rel_s := str(rel)
		_bake_asset_wrapper(base + rel_s, not _is_passthrough(rel_s), WORLD_LAYER)

func _bake_asset_wrapper(glb_path: String, with_collision: bool, collision_layer: int) -> void:
	var out_path := _editable_scene_path(glb_path)
	if ResourceLoader.exists(out_path):
		return
	var ps := load(glb_path) as PackedScene
	if ps == null:
		push_warning("Cannot load " + glb_path)
		return
	var root := Node3D.new()
	root.name = _safe_scene_name(glb_path)
	root.set_meta("source_glb", glb_path)
	var inst := ps.instantiate()
	inst.name = "Model"
	root.add_child(inst)
	inst.owner = root
	if with_collision:
		for mi in _mesh_instances(inst):
			mi.create_trimesh_collision()
			for child in mi.get_children():
				if child is StaticBody3D:
					child.owner = root
					child.collision_layer = collision_layer
					child.collision_mask = WORLD_LAYER
					child.set_meta("source_glb", glb_path)
					_make_owned(child, root)
		_add_fallback_floor(root, collision_layer)
	var packed := PackedScene.new()
	var err := packed.pack(root)
	if err != OK:
		push_error("Could not pack " + out_path + ": " + error_string(err))
		return
	err = ResourceSaver.save(packed, out_path)
	if err != OK:
		push_error("Could not save " + out_path + ": " + error_string(err))

func _bake_placed_scene(zone: String, data: Dictionary) -> void:
	var base := ASSET_ROOT + zone + "/"
	var root := Node3D.new()
	root.name = "TrinstBaked"
	root.set_meta("zone", zone)
	if data.has("terrain_glb"):
		var terrain := _instance_editable(base + str(data["terrain_glb"]), "Terrain")
		if terrain:
			var tp = data["terrain"].get("pos", [0.0, 0.0, 0.0])
			terrain.position = Vector3(float(tp[0]), float(tp[1]), float(tp[2]))
			root.add_child(terrain)
			terrain.owner = root
	var statics_root := Node3D.new()
	statics_root.name = "Statics"
	root.add_child(statics_root)
	statics_root.owner = root
	_place_items(statics_root, base, data.get("statics", []))
	var interiors_root := Node3D.new()
	interiors_root.name = "Interiors"
	root.add_child(interiors_root)
	interiors_root.owner = root
	_place_items(interiors_root, base, data.get("interiors", []))
	var packed := PackedScene.new()
	var err := packed.pack(root)
	if err != OK:
		push_error("Could not pack " + BAKED_SCENE_PATH + ": " + error_string(err))
		return
	err = ResourceSaver.save(packed, BAKED_SCENE_PATH)
	if err != OK:
		push_error("Could not save " + BAKED_SCENE_PATH + ": " + error_string(err))

func _place_items(parent: Node3D, base: String, items: Array) -> void:
	var index := 0
	for item in items:
		var rel = item.get("glb", null)
		if rel == null:
			continue
		var node := _instance_editable(base + str(rel), _safe_node_name(str(item.get("name", "")), str(rel), index))
		index += 1
		if node == null:
			continue
		var rot = item.get("rot", [0.0, 0.0, 1.0, 0.0])
		var pos = item.get("pos", [0.0, 0.0, 0.0])
		var scl = item.get("scale", [1.0, 1.0, 1.0])
		var ax := Vector3(float(rot[0]), float(rot[1]), float(rot[2]))
		var basis := Basis(ax.normalized(), deg_to_rad(float(rot[3]))) if ax.length() > 0.001 else Basis()
		basis = basis.scaled(Vector3(float(scl[0]), float(scl[1]), float(scl[2])))
		node.transform = Transform3D(basis, Vector3(float(pos[0]), float(pos[1]), float(pos[2])))
		node.set_meta("zone_glb", str(rel).get_file().get_basename())
		parent.add_child(node)
		node.owner = parent.owner

func _instance_editable(glb_path: String, node_name: String) -> Node3D:
	var scene_path := _editable_scene_path(glb_path)
	var ps := load(scene_path) as PackedScene
	if ps == null:
		push_warning("Missing editable wrapper " + scene_path)
		return null
	var inst := ps.instantiate() as Node3D
	if inst:
		inst.name = node_name
	return inst

func _add_fallback_floor(root: Node3D, collision_layer: int) -> void:
	var meshes := _mesh_instances(root)
	if meshes.is_empty():
		return
	var aabb: AABB
	var have := false
	for mi in meshes:
		var a: AABB = mi.global_transform * mi.get_aabb()
		if not have:
			aabb = a
			have = true
		else:
			aabb = aabb.merge(a)
	if not have or aabb.size.x < 4.0 or aabb.size.z < 4.0 or aabb.size.y < 3.0:
		return
	var body := StaticBody3D.new()
	body.name = "FallbackFloor"
	body.collision_layer = collision_layer
	body.collision_mask = WORLD_LAYER
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(maxf(aabb.size.x - 1.0, 1.0), 0.4, maxf(aabb.size.z - 1.0, 1.0))
	cs.shape = box
	body.add_child(cs)
	root.add_child(body)
	body.global_position = Vector3(aabb.position.x + aabb.size.x * 0.5, aabb.position.y + 0.2, aabb.position.z + aabb.size.z * 0.5)
	body.owner = root
	cs.owner = root

func _mesh_instances(node: Node) -> Array[MeshInstance3D]:
	var out: Array[MeshInstance3D] = []
	if node is MeshInstance3D:
		out.append(node)
	for child in node.get_children():
		out.append_array(_mesh_instances(child))
	return out

func _make_owned(node: Node, owner: Node) -> void:
	for child in node.get_children():
		child.owner = owner
		_make_owned(child, owner)

func _load_json(path: String) -> Dictionary:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return {}
	var data = JSON.parse_string(f.get_as_text())
	return data if data is Dictionary else {}

func _ensure_dir(path: String) -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(path))

func _editable_scene_path(glb_path: String) -> String:
	var rel := glb_path.trim_prefix(ASSET_ROOT + ZONE + "/").trim_suffix(".glb")
	return EDITABLE_DIR + rel.replace("/", "__") + ".tscn"

func _safe_scene_name(path: String) -> String:
	return path.get_file().get_basename().replace(".", "_").replace("-", "_")

func _safe_node_name(item_name: String, rel: String, index: int) -> String:
	var base_name := item_name.strip_edges()
	if base_name.is_empty():
		base_name = rel.get_file().get_basename()
	return "%s_%03d" % [base_name.replace(" ", "_"), index]

func _is_passthrough(rel: String) -> bool:
	for key in PASSTHROUGH_INTERIORS:
		if rel.findn(key) != -1:
			return true
	return false

func _static_should_collide(rel: String) -> bool:
	for prefix in COLLIDING_STATIC_PREFIXES:
		if rel.begins_with(prefix):
			return true
	return false
