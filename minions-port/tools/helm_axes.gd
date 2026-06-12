extends SceneTree
## Dev harness: render an equipment GLB alone with axis markers to learn its
## intrinsic orientation. Red box = +X, blue box = +Z, green box = +Y.
## Run: xvfb-run godot --path minions-port --script res://tools/helm_axes.gd

var cam: Camera3D
var frame := 0
var shots := [
	["from_plusZ", Vector3(0, 0.25, 1.6)],
	["from_minusZ", Vector3(0, 0.25, -1.6)],
	["from_plusX", Vector3(1.6, 0.25, 0)],
	["from_above", Vector3(0.01, 1.8, 0.01)],
]
var shot_idx := 0

func _marker(world: Node3D, pos: Vector3, color: Color) -> void:
	var mi := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = Vector3(0.08, 0.08, 0.08)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	box.material = mat
	mi.mesh = box
	mi.position = pos
	world.add_child(mi)

func _initialize() -> void:
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

	var glb := OS.get_environment("GLB")
	if glb.is_empty():
		glb = "res://assets/equipment/head_helmet.glb"
	var scene = load(glb)
	var inst: Node3D = scene.instantiate()
	world.add_child(inst)

	_marker(world, Vector3(0.5, 0, 0), Color.RED)      # +X
	_marker(world, Vector3(0, 0, 0.5), Color.BLUE)     # +Z
	_marker(world, Vector3(0, 0.5, 0), Color.GREEN)    # +Y

	cam = Camera3D.new()
	world.add_child(cam)
	cam.current = true

func _process(_delta: float) -> bool:
	frame += 1
	# Reposition on one frame, screenshot 20 frames later (no awaits: SceneTree
	# _process must synchronously return bool).
	if frame % 25 == 5:
		if shot_idx >= shots.size():
			quit(0)
			return true
		cam.look_at_from_position(shots[shot_idx][1], Vector3(0, 0.1, 0))
	elif frame % 25 == 0 and shot_idx < shots.size():
		var tag: String = shots[shot_idx][0]
		var img := root.get_viewport().get_texture().get_image()
		img.save_png("/tmp/helm_%s.png" % tag)
		print("[HELMAXES] shot -> /tmp/helm_%s.png" % tag)
		shot_idx += 1
	return false
