class_name CharacterRig
extends Node3D
## Wraps an animated character .glb: loads the model, finds its AnimationPlayer
## and skinned mesh, and drives a small idle/walk/run/attack/death state machine.
## Used for both the player avatar and replicated NPCs so every visible character
## shares the same animation behaviour. If the model fails to load, the caller can
## fall back to a capsule so a character is never invisible. Character GLBs from
## the Torque/DTS pipeline arrive with lighting normals reversed in Godot, so the
## rig fixes those vertex normals after instancing without changing animation or
## triangle winding.

const RUN_SPEED := 5.0   # server move speeds: NPC ~5 u/s, player ~8 u/s
const WALK_MIN := 0.35   # below this we consider the character standing still
const TEX_DIR := "res://assets/character_textures/"
const EDITOR_REPAIRED_CHARACTER_DIR := "res://assets/characters/repaired/"
const MeshNormalRepairScript := preload("res://world/mesh_normal_repair.gd")

var anim_player: AnimationPlayer
var skinned_meshes: Array[MeshInstance3D] = []
var _anims: Dictionary = {}
var _state := ""
var _attack_until := 0.0
var loaded := false

func setup(glb_path: String, face_offset_deg: float = 0.0) -> bool:
	if glb_path == "" or not ResourceLoader.exists(glb_path):
		return false
	var scene_path := _editor_repaired_scene_path(glb_path)
	var scene = load(scene_path)
	if scene == null:
		return false
	var inst = scene.instantiate()
	if face_offset_deg != 0.0:
		inst.rotation_degrees.y += face_offset_deg
	MeshNormalRepairScript.invert_node_normals(inst)
	add_child(inst)
	anim_player = _find_anim_player(inst)
	skinned_meshes = _find_meshes(inst)
	if anim_player:
		for a in anim_player.get_animation_list():
			_anims[a] = true
			var anim := anim_player.get_animation(a)
			if anim and (a == "idle" or a == "walk" or a == "run"):
				anim.loop_mode = Animation.LOOP_LINEAR
	loaded = true
	if OS.get_environment("RIG_DEBUG") == "1":
		print("[RIG] setup ", glb_path.get_file(), " anim_player=", anim_player != null,
			" anims=", _anims.keys(), " meshes=", skinned_meshes.size())
	# Start in idle so a freshly spawned character isn't frozen in bind pose.
	_play("idle")
	return true

func _editor_repaired_scene_path(glb_path: String) -> String:
	if glb_path.begins_with("res://assets/characters/"):
		var repaired_path := (
			EDITOR_REPAIRED_CHARACTER_DIR + glb_path.get_file().get_basename() + ".tscn"
		)
		if ResourceLoader.exists(repaired_path):
			return repaired_path
	return glb_path


func _play(name: String, blend: float = 0.15) -> void:
	if anim_player == null or not _anims.has(name):
		return
	if _state == name:
		return
	_state = name
	anim_player.play(name, blend)

# speed: horizontal speed in units/sec; attacking/dead: server flags.
func drive(speed: float, attacking: bool, dead: bool) -> void:
	if anim_player == null:
		return
	var now := Time.get_ticks_msec() / 1000.0
	if dead:
		_play("death", 0.2)
		return
	# A fresh attack flag triggers the swing; hold it briefly so a single melee
	# swing reads clearly even if the server flag flickers.
	if attacking and _anims.has("attack"):
		_attack_until = now + 0.5
	if now < _attack_until and _anims.has("attack"):
		if _state != "attack":
			_state = "attack"
			anim_player.play("attack", 0.1)
		elif not anim_player.is_playing():
			anim_player.play("attack", 0.05)  # repeat while still attacking
		return
	if speed >= RUN_SPEED * 0.85 and _anims.has("run"):
		_play("run")
	elif speed > WALK_MIN and _anims.has("walk"):
		_play("walk")
	else:
		_play("idle")

func apply_appearance(parts: Dictionary) -> void:
	# parts maps a body part -> texture index, e.g. {"head":5,"body":12,...}.
	# Overrides the model's base.<part> materials with the chosen numbered skin/
	# armor texture. No-op for monster models whose surfaces aren't named base.<part>
	# (they keep their own embedded textures), so it's safe to call on anything.
	if parts == null or parts.is_empty():
		return
	for mi in skinned_meshes:
		if not is_instance_valid(mi) or mi.mesh == null:
			continue
		var m: Mesh = mi.mesh
		for si in range(m.get_surface_count()):
			var base_mat := m.surface_get_material(si)
			if base_mat == null:
				continue
			var nm := str(base_mat.resource_name).to_lower()
			var dot := nm.rfind(".")
			var part := nm.substr(dot + 1) if dot >= 0 else nm
			if not parts.has(part):
				continue
			var idx := int(parts[part])
			var tex_path := "%s%s/%s%d.jpg" % [TEX_DIR, part, part, idx]
			if not ResourceLoader.exists(tex_path):
				continue
			var nmat: Material
			if base_mat is StandardMaterial3D:
				nmat = base_mat.duplicate()
				nmat.albedo_texture = load(tex_path)
			else:
				var sm := StandardMaterial3D.new()
				sm.albedo_texture = load(tex_path)
				nmat = sm
			mi.set_surface_override_material(si, nmat)

func set_highlight(on: bool) -> void:
	for mi in skinned_meshes:
		if not is_instance_valid(mi):
			continue
		if on:
			var m := StandardMaterial3D.new()
			m.albedo_color = Color(1, 1, 0.25)
			m.emission_enabled = true
			m.emission = Color(1, 1, 0.2)
			m.emission_energy_multiplier = 0.45
			mi.material_override = m
		else:
			mi.material_override = null

func _find_anim_player(n: Node) -> AnimationPlayer:
	if n is AnimationPlayer:
		return n
	for c in n.get_children():
		var r := _find_anim_player(c)
		if r:
			return r
	return null

func _find_meshes(n: Node) -> Array[MeshInstance3D]:
	var out: Array[MeshInstance3D] = []
	if n is MeshInstance3D:
		out.append(n)
	for c in n.get_children():
		out += _find_meshes(c)
	return out
