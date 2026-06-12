extends SceneTree
## Dev harness: render a character with mounted equipment (helmet on Mount3,
## weapon on Mount0) head-on and in profile, to verify mount orientation.
## Run: xvfb-run godot --path minions-port --script res://tools/mount_check.gd
## Env: MODEL (default characters/human_male.glb), HELM (head/helmet.dts),
##      WEAPON (weapons/sword01.dts), SHOT (default /tmp/mount_check)

const CharacterRigScript := preload("res://world/character_rig.gd")

var rig: Node3D
var cam: Camera3D
var frame := 0
var shot_base := "/tmp/mount_check"

func _env(k: String, d: String) -> String:
	var v := OS.get_environment(k)
	return v if v != "" else d

func _initialize() -> void:
	shot_base = _env("SHOT", "/tmp/mount_check")
	var world := Node3D.new()
	root.add_child(world)

	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color(0.18, 0.2, 0.24)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(1, 1, 1)
	e.ambient_light_energy = 1.0
	env.environment = e
	world.add_child(env)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-40, 30, 0)
	world.add_child(sun)

	rig = CharacterRigScript.new()
	world.add_child(rig)
	var model := "res://assets/" + _env("MODEL", "characters/human_male.glb")
	if not rig.setup(model, 0.0):
		print("[MOUNTCHECK] FAILED to load ", model)
		quit(1)
		return
	rig.apply_mounts({
		"0": {"model": _env("WEAPON", "weapons/sword01.dts"), "material": ""},
		"3": {"model": _env("HELM", "head/helmet.dts"), "material": ""},
	})

	cam = Camera3D.new()
	cam.position = Vector3(0, 1.2, 3.2)
	cam.look_at_from_position(cam.position, Vector3(0, 1.0, 0))
	world.add_child(cam)
	cam.current = true

func _process(_delta: float) -> bool:
	frame += 1
	if frame == 25:
		_shot("front")
	elif frame == 30:
		cam.position = Vector3(3.2, 1.2, 0)
		cam.look_at_from_position(cam.position, Vector3(0, 1.0, 0))
	elif frame == 55:
		_shot("side")
	elif frame == 60:
		cam.position = Vector3(0, 1.6, 1.2)
		cam.look_at_from_position(cam.position, Vector3(0, 1.55, 0))
	elif frame == 85:
		_shot("head_back")
	elif frame == 90:
		cam.position = Vector3(0, 1.6, -1.2)
		cam.look_at_from_position(cam.position, Vector3(0, 1.55, 0))
	elif frame == 115:
		_shot("face_front")
		quit(0)
	return false

func _shot(tag: String) -> void:
	var img := root.get_viewport().get_texture().get_image()
	img.save_png("%s_%s.png" % [shot_base, tag])
	print("[MOUNTCHECK] shot -> %s_%s.png" % [shot_base, tag])
