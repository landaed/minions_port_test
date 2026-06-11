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
const EQUIP_DIR := "res://assets/equipment/"
const EDITOR_REPAIRED_CHARACTER_DIR := "res://assets/characters/repaired/"
const MeshNormalRepairScript := preload("res://world/mesh_normal_repair.gd")

var anim_player: AnimationPlayer
var skinned_meshes: Array[MeshInstance3D] = []
var _anims: Dictionary = {}
var _state := ""
var _attack_until := 0.0
var _overlay_until := 0.0
var _skeleton: Skeleton3D = null
var _mount_attachments: Dictionary = {}  # mount key ("0".."3") -> BoneAttachment3D
var _mounts_signature := ""
var _appearance_signature := ""
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
	_skeleton = _find_skeleton(inst)
	if anim_player:
		for a in anim_player.get_animation_list():
			_anims[a] = true
			var anim := anim_player.get_animation(a)
			if anim and (a == "idle" or a == "walk" or a == "run" or a == "spellprepare"):
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


## Server playAnimation names -> candidate clips in priority order. The GLBs
## carry the original DSQ clips where the skeleton had them (kick1, spellcast,
## pain1, ...); older/creature rigs fall back to the closest generic swing.
const ANIM_FALLBACKS := {
	"_attack": ["attack", "attack2"],
	"kick1": ["kick1", "attack2", "attack"],
	"kick2": ["kick2", "kick1", "attack2", "attack"],
	"spellcast": ["spellcast", "spellcast2", "attack2", "attack"],
	"spellcast2": ["spellcast2", "spellcast", "attack2", "attack"],
	"spellprepare": ["spellprepare", "spellcast", "idle"],
	"pain1": ["pain1", "pain2"],
	"pain2": ["pain2", "pain1"],
	"bowattack": ["bowattack", "attack"],
	"shieldblock": ["shieldblock", "attack2"],
	"2hslash": ["2hslash", "attack"],
	"2hthrust": ["2hthrust", "2hslash", "attack"],
	"1hthrust": ["1hthrust", "attack"],
}

func _play(name: String, blend: float = 0.15) -> void:
	if anim_player == null or not _anims.has(name):
		return
	if _state == name:
		return
	_state = name
	anim_player.play(name, blend)

func resolve_anim(name: String) -> String:
	var lname := name.to_lower()
	if _anims.has(lname):
		return lname
	for cand in ANIM_FALLBACKS.get(lname, []):
		if _anims.has(cand):
			return cand
	return ""

func play_overlay(name: String, loop_for: float = 0.0) -> float:
	# One-shot action animation from a server playAnimation event (kick, cast,
	# pain, emote...). Suppresses the locomotion state machine until done.
	# loop_for > 0 holds a looping clip (e.g. spellprepare) that long instead.
	if anim_player == null:
		return 0.0
	var clip := resolve_anim(name)
	if clip.is_empty():
		return 0.0
	var anim := anim_player.get_animation(clip)
	var dur := loop_for if loop_for > 0.0 else (anim.length if anim else 0.8)
	var now := Time.get_ticks_msec() / 1000.0
	_state = "overlay:" + clip
	_overlay_until = now + dur
	anim_player.play(clip, 0.1)
	return dur

func clear_overlay() -> void:
	_overlay_until = 0.0

# speed: horizontal speed in units/sec; attacking/dead: server flags.
func drive(speed: float, attacking: bool, dead: bool) -> void:
	if anim_player == null:
		return
	var now := Time.get_ticks_msec() / 1000.0
	if dead:
		_overlay_until = 0.0
		_play("death", 0.2)
		return
	# An action overlay (kick/cast/pain/emote event) owns the rig until it ends,
	# but real movement cancels it so characters never moonwalk.
	if now < _overlay_until:
		if speed > WALK_MIN:
			_overlay_until = 0.0
		else:
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
	# Deduped by signature: called per entity snapshot, re-applies only when the
	# server-streamed appearance actually changes (e.g. armor equipped).
	if parts == null or parts.is_empty():
		return
	var signature := JSON.stringify(parts)
	if signature == _appearance_signature:
		return
	_appearance_signature = signature
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

func apply_mounts(mounts: Dictionary) -> void:
	# mounts: {"0": {"model": "weapons/sword01.dts", "material": ""}, ...} from
	# the server entity snapshot. Mount0 = primary hand, 1 = off hand,
	# 2 = shield, 3 = head — matching the Mount0..Mount3 bones the DTS->GLB
	# pipeline preserved in every character skeleton. Equipment GLBs live at
	# assets/equipment/<path-with-underscores>.glb (see tools/build_equipment.py).
	if _skeleton == null:
		return
	var signature := JSON.stringify(mounts)
	if signature == _mounts_signature:
		return
	_mounts_signature = signature
	for key in ["0", "1", "2", "3"]:
		var existing: BoneAttachment3D = _mount_attachments.get(key)
		var want = mounts.get(key)
		if not (want is Dictionary) or str(want.get("model", "")).is_empty():
			if existing != null:
				existing.queue_free()
				_mount_attachments.erase(key)
			continue
		var glb_path := _equipment_glb_path(str(want.get("model", "")))
		var material := str(want.get("material", ""))
		if existing != null:
			if existing.get_meta("glb", "") == glb_path and existing.get_meta("mat", "") == material:
				continue
			existing.queue_free()
			_mount_attachments.erase(key)
		if glb_path.is_empty() or not ResourceLoader.exists(glb_path):
			continue
		var bone_idx := _skeleton.find_bone("Mount" + key)
		if bone_idx < 0:
			continue
		var scene = load(glb_path)
		if scene == null:
			continue
		var attach := BoneAttachment3D.new()
		attach.bone_name = "Mount" + key
		_skeleton.add_child(attach)
		var inst: Node3D = scene.instantiate()
		MeshNormalRepairScript.invert_node_normals(inst)
		if not material.is_empty():
			_apply_equipment_material(inst, material)
		attach.add_child(inst)
		attach.set_meta("glb", glb_path)
		attach.set_meta("mat", material)
		_mount_attachments[key] = attach

static func _equipment_glb_path(model: String) -> String:
	# "weapons/sword01.dts" -> res://assets/equipment/weapons_sword01.glb
	var p := model.to_lower().replace("\\", "/")
	if p.ends_with(".dts"):
		p = p.substr(0, p.length() - 4)
	p = p.replace("/", "_")
	return EQUIP_DIR + p + ".glb" if not p.is_empty() else ""

func _apply_equipment_material(inst: Node, material: String) -> void:
	# material is a texture override like "weapons/sword_03_dra" or
	# "head/helmet_brass"; the art was copied to assets/equipment/textures/.
	var tex_path := EQUIP_DIR + "textures/" + material.to_lower() + ".jpg"
	if not ResourceLoader.exists(tex_path):
		return
	var tex: Texture2D = load(tex_path)
	if tex == null:
		return
	for mi in _find_meshes(inst):
		if mi.mesh == null:
			continue
		for si in range(mi.mesh.get_surface_count()):
			var base_mat := mi.mesh.surface_get_material(si)
			var nmat: StandardMaterial3D
			if base_mat is StandardMaterial3D:
				nmat = base_mat.duplicate()
			else:
				nmat = StandardMaterial3D.new()
			nmat.albedo_texture = tex
			mi.set_surface_override_material(si, nmat)

func set_mount_particle(key: String, particle: String, texture: String) -> void:
	# Persistent equipped-weapon effect (e.g. a flaming blade): a long-lived
	# emitter pinned to the mount attachment. Replaces any previous one.
	var attach: BoneAttachment3D = _mount_attachments.get(key)
	if attach == null:
		return
	for c in attach.get_children():
		if c is CPUParticles3D:
			c.queue_free()
	VFX.emitter(attach, Vector3.ZERO, particle, texture, 3600.0)

func _find_skeleton(n: Node) -> Skeleton3D:
	if n is Skeleton3D:
		return n
	for c in n.get_children():
		var r := _find_skeleton(c)
		if r:
			return r
	return null

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
