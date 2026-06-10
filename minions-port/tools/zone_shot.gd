extends SceneTree
## Renders the authored trinst zone (no servers needed) from a configurable
## camera and saves a screenshot. Used to eyeball zone art / material changes.
##
##   xvfb-run godot --path minions-port --script res://tools/zone_shot.gd
## Env:
##   SHOT      output png (default /tmp/zone_shot.png)
##   CAM_POS   "x,y,z" camera position in zone-local (godot) coords
##   CAM_LOOK  "x,y,z" look-at point
##   SUN_DEG   sun elevation degrees (default 50)

var frames := 0
var cam: Camera3D

func _initialize() -> void:
	var zone: PackedScene = load("res://world/zones/trinst.tscn")
	var node: Node3D = zone.instantiate()
	root.add_child(node)
	if node.has_method("prepare_authored_scene"):
		node.prepare_authored_scene("trinst", true)
	cam = Camera3D.new()
	cam.far = 1200.0
	root.add_child(cam)
	cam.look_at_from_position(_vec_env("CAM_POS", Vector3(10.0, 140.0, 290.0)), _vec_env("CAM_LOOK", Vector3(41.0, 132.0, 254.0)))
	cam.current = true
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-float(OS.get_environment("SUN_DEG").to_float() if OS.get_environment("SUN_DEG") != "" else 50.0), -35.0, 0.0)
	sun.light_energy = 1.2
	sun.shadow_enabled = true
	root.add_child(sun)

func _vec_env(name: String, fallback: Vector3) -> Vector3:
	var s := OS.get_environment(name)
	if s.is_empty():
		return fallback
	var parts := s.split(",")
	if parts.size() < 3:
		return fallback
	return Vector3(parts[0].to_float(), parts[1].to_float(), parts[2].to_float())

func _process(_delta: float) -> bool:
	frames += 1
	if frames == 30:
		var path := OS.get_environment("SHOT")
		if path.is_empty():
			path = "/tmp/zone_shot.png"
		var img := root.get_viewport().get_texture().get_image()
		img.save_png(path)
		print("[zone_shot] saved ", path, " size=", img.get_size())
		quit()
	return false
