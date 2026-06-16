extends SceneTree
## Minimal: load the login screen and screenshot it (shows the Server field).
func _initialize() -> void:
	var dir := OS.get_environment("MOM_SHOT_DIR")
	if dir.is_empty():
		dir = "/tmp"
	DirAccess.make_dir_recursive_absolute(dir)
	var scene: PackedScene = load("res://control.tscn")
	var control: Control = scene.instantiate()
	root.add_child(control)
	var shot := ShotNode.new()
	shot.dir = dir
	root.add_child(shot)

class ShotNode:
	extends Node
	var dir: String
	var t := 0.0
	var done := false
	func _process(delta: float) -> void:
		t += delta
		if t > 2.5 and not done:
			done = true
			await RenderingServer.frame_post_draw
			var img := get_viewport().get_texture().get_image()
			img.save_png(dir + "/login_screen.png")
			print("[LOGIN_SHOT] saved ", dir, "/login_screen.png")
			get_tree().quit()
