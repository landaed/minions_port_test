extends SceneTree
## Bake spawn markers (exported by tools/godot_spawns.py) into a zone scene as
## editable MoMSpawnPoint nodes under a "Spawns" Node3D. One-time import: after
## this, the zone .tscn is the source of truth for marker placement (the server
## reads it directly), and you adjust spawns by moving the nodes in the editor.
##
##   ../tools/godot_spawns.py --zone trinst            # writes the JSON
##   godot --headless --script res://tools/import_spawn_points.gd
##
## Env:
##   MOM_SPAWN_JSON   input json (default /tmp/mom_spawn_import.json)
## Re-running REPLACES the whole Spawns node with the legacy mission layout.

const SPAWN_SCRIPT := "res://world/spawn_point.gd"

func _initialize() -> void:
	var json_path := OS.get_environment("MOM_SPAWN_JSON")
	if json_path.is_empty():
		json_path = "/tmp/mom_spawn_import.json"
	var f := FileAccess.open(json_path, FileAccess.READ)
	if f == null:
		push_error("[import_spawns] cannot open " + json_path)
		quit(1)
		return
	var data: Variant = JSON.parse_string(f.get_as_text())
	if not (data is Dictionary) or not data.has("points"):
		push_error("[import_spawns] bad json in " + json_path)
		quit(1)
		return
	var zone := str(data.get("zone", "trinst"))
	var scene_path := "res://world/zones/%s.tscn" % zone
	var packed: PackedScene = load(scene_path)
	if packed == null:
		push_error("[import_spawns] cannot load " + scene_path)
		quit(1)
		return
	var root_node: Node = packed.instantiate(PackedScene.GEN_EDIT_STATE_MAIN)
	var spawns: Node3D = root_node.get_node_or_null("Spawns")
	if spawns != null:
		root_node.remove_child(spawns)
		spawns.free()
	spawns = Node3D.new()
	spawns.name = "Spawns"
	root_node.add_child(spawns)
	spawns.owner = root_node

	var spawn_script: Script = load(SPAWN_SCRIPT)
	var used_names := {}
	var count := 0
	for p in data["points"]:
		if not (p is Dictionary):
			continue
		var group := str(p.get("group", ""))
		var base_name := "SP_" + group.replace(" ", "_")
		var nm := base_name
		var i := 1
		while used_names.has(nm):
			i += 1
			nm = "%s_%d" % [base_name, i]
		used_names[nm] = true
		var node := Node3D.new()
		node.name = nm
		node.set_script(spawn_script)
		spawns.add_child(node)
		node.owner = root_node
		var gp: Array = p.get("godot_position", [0, 0, 0])
		node.position = Vector3(float(gp[0]), float(gp[1]), float(gp[2]))
		node.rotation = Vector3(0.0, float(p.get("godot_yaw", 0.0)), 0.0)
		node.set("spawn_group", group)
		node.set("wander_group", int(p.get("wander_group", -1)))
		var preview: Dictionary = p.get("preview", {})
		node.set("preview_name", str(preview.get("name", "")))
		node.set("preview_model", str(preview.get("model", "")))
		node.set("preview_info", str(preview.get("info", "")))
		node.set("preview_scale", float(preview.get("scale", 1.0)))
		count += 1

	var repacked := PackedScene.new()
	if repacked.pack(root_node) != OK:
		push_error("[import_spawns] failed to pack " + scene_path)
		quit(1)
		return
	repacked.take_over_path(scene_path)
	if ResourceSaver.save(repacked, scene_path) != OK:
		push_error("[import_spawns] failed to save " + scene_path)
		quit(1)
		return
	print("[import_spawns] baked %d spawn points into %s" % [count, scene_path])
	quit(0)
