extends SceneTree
## Headless check of the zoom -> first-person camera logic in gameplay_view.

func _initialize() -> void:
	var ps: PackedScene = load("res://gameplay_view.tscn")
	var view: Control = ps.instantiate()
	root.add_child(view)
	await process_frame
	await process_frame
	var cam: Camera3D = view.camera
	print("[CAMCHECK] start zoom=%.1f cam=%s rot_x=%.2f" % [view._camera_zoom, cam.position, cam.rotation.x])
	# zoom all the way in
	for i in range(20):
		view._adjust_camera_zoom(-1.0)
	await process_frame
	print("[CAMCHECK] zoomed-in: fp=%s cam=%s rig_visible=%s" % [view._first_person, cam.position,
		view._player_rig.visible if view._player_rig else "?"])
	assert(view._first_person, "should be first person at max zoom-in")
	assert(not view._player_rig.visible, "rig must be hidden in first person")
	# one step back out
	view._adjust_camera_zoom(1.0)
	await process_frame
	print("[CAMCHECK] zoomed-out-one: fp=%s zoom=%.1f cam=%s rig_visible=%s" % [view._first_person,
		view._camera_zoom, cam.position, view._player_rig.visible])
	assert(not view._first_person, "one wheel-down should leave first person")
	assert(view._player_rig.visible, "rig visible again in third person")
	# near third-person framing should be shoulder-ish height, not 3.0
	assert(cam.position.y < 1.0, "near zoom camera should drop toward shoulder height")
	for i in range(20):
		view._adjust_camera_zoom(1.0)
	await process_frame
	print("[CAMCHECK] zoomed-out-max: zoom=%.1f cam=%s rot_x=%.2f" % [view._camera_zoom, cam.position, cam.rotation.x])
	assert(absf(view._camera_zoom - 14.0) < 0.01, "max zoom clamp")
	print("[CAMCHECK] ALL OK")
	quit(0)
