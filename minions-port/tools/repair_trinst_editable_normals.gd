@tool
extends EditorScript
## Repair converted Trinst editable wrapper normals in the editor, then save the
## repaired .tscn files. Runtime zone loading does not change mesh normals.
##
## Run from Godot with FileSystem ->
## res://tools/repair_trinst_editable_normals.gd -> Run.
## Terrain is skipped so its editor-selected mesh/material/shader stays untouched.

const EDITABLE_DIR := "res://assets/trinst/editable/"
const MeshNormalRepairScript := preload("res://world/mesh_normal_repair.gd")


func _run() -> void:
	_repair_editable_wrappers()
	get_editor_interface().get_resource_filesystem().scan()


func _repair_editable_wrappers() -> void:
	var dir := DirAccess.open(EDITABLE_DIR)
	if dir == null:
		push_error("Cannot open " + EDITABLE_DIR)
		return
	dir.list_dir_begin()
	var file_name := dir.get_next()
	while file_name != "":
		if _should_repair_file(dir, file_name):
			_repair_wrapper(EDITABLE_DIR + file_name)
		file_name = dir.get_next()
	dir.list_dir_end()


func _should_repair_file(dir: DirAccess, file_name: String) -> bool:
	if dir.current_is_dir():
		return false
	if file_name.get_extension().to_lower() != "tscn":
		return false
	return file_name != "terrain.tscn"


func _repair_wrapper(scene_path: String) -> void:
	var ps := load(scene_path) as PackedScene
	if ps == null:
		push_warning("Cannot load " + scene_path)
		return
	var root := ps.instantiate()
	MeshNormalRepairScript.repair_node(root)
	_make_owned(root, root)
	var packed := PackedScene.new()
	var err := packed.pack(root)
	if err != OK:
		push_error("Could not pack " + scene_path + ": " + error_string(err))
		return
	err = ResourceSaver.save(packed, scene_path)
	if err != OK:
		push_error("Could not save " + scene_path + ": " + error_string(err))


func _make_owned(node: Node, owner: Node) -> void:
	for child in node.get_children():
		child.owner = owner
		_make_owned(child, owner)
