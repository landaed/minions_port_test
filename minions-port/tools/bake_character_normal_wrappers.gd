@tool
extends EditorScript
## Bake editor-repaired character scenes so gameplay can load fixed meshes
## without changing normals at runtime.
##
## Run from Godot with FileSystem ->
## res://tools/bake_character_normal_wrappers.gd -> Run.
## It creates/updates:
##   res://assets/characters/repaired/<character>.tscn

const CHARACTER_DIR := "res://assets/characters/"
const REPAIRED_DIR := "res://assets/characters/repaired/"
const MeshNormalRepairScript := preload("res://world/mesh_normal_repair.gd")


func _run() -> void:
	_bake_all_character_wrappers()
	get_editor_interface().get_resource_filesystem().scan()


func _bake_all_character_wrappers() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(REPAIRED_DIR))
	var dir := DirAccess.open(CHARACTER_DIR)
	if dir == null:
		push_error("Cannot open " + CHARACTER_DIR)
		return
	dir.list_dir_begin()
	var file_name := dir.get_next()
	while file_name != "":
		if not dir.current_is_dir() and file_name.get_extension().to_lower() == "glb":
			_bake_character_wrapper(CHARACTER_DIR + file_name)
		file_name = dir.get_next()
	dir.list_dir_end()


func _bake_character_wrapper(glb_path: String) -> void:
	var ps := load(glb_path) as PackedScene
	if ps == null:
		push_warning("Cannot load " + glb_path)
		return
	var root := Node3D.new()
	root.name = glb_path.get_file().get_basename()
	root.set_meta("source_glb", glb_path)
	var inst := ps.instantiate()
	inst.name = "Model"
	root.add_child(inst)
	inst.owner = root
	MeshNormalRepairScript.repair_node(inst)
	_make_owned(inst, root)
	var packed := PackedScene.new()
	var err := packed.pack(root)
	if err != OK:
		push_error("Could not pack repaired character " + glb_path + ": " + error_string(err))
		return
	var out_path := REPAIRED_DIR + glb_path.get_file().get_basename() + ".tscn"
	err = ResourceSaver.save(packed, out_path)
	if err != OK:
		push_error("Could not save " + out_path + ": " + error_string(err))


func _make_owned(node: Node, owner: Node) -> void:
	for child in node.get_children():
		child.owner = owner
		_make_owned(child, owner)
