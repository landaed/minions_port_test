extends Node
## Headless check: drives gameplay_view with a faked server enter-world + self
## entity snapshot (no live server) to confirm the Trinst zone loads into
## WorldRoot and the server-driven player lands on the terrain. Screenshots the
## gameplay SubViewport. Dev-only harness.

func _ready() -> void:
	var gv = load("res://gameplay_view.tscn").instantiate()
	add_child(gv)
	await get_tree().process_frame
	gv.apply_world_state({"world_name": "Trinst", "player_name": "Tester"},
		{"name": "Trinst"}, {"hour": 12, "minute": 0})
	# Self at the Trinst bind point (rpgBindPoint in city.mis, outside the gates).
	# Server coords are Torque (x, y, z=height).
	gv.set_entities([
		{"is_self": true, "position": [257.095, 133.949, 152.194],
			"health": 1.0, "name": "You", "sim_id": 1, "char_index": 0, "mob_id": 0},
		{"is_self": false, "position": [272.0, 140.0, 150.0],
			"health": 1.0, "name": "Gate Guard", "sim_id": 2, "char_index": 0,
			"mob_id": 42, "level": 10},
	])
	for i in range(300):
		await get_tree().physics_frame
	# external camera framing the player so the avatar is clearly visible
	var wr = gv.get_node("SubViewportContainer/SubViewport/WorldRoot")
	var icam := Camera3D.new()
	wr.add_child(icam)
	var pp: Vector3 = gv.player_body.global_position
	icam.global_position = pp + Vector3(2.2, 1.0, 3.0)
	icam.look_at(pp + Vector3(0.0, 0.8, 0.0), Vector3.UP)
	icam.current = true
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var out := OS.get_environment("SHOT")
	if out == "":
		out = "/tmp/gv.png"
	gv.sub_viewport.get_texture().get_image().save_png(out)
	print("VERIFY player=", gv.player_body.global_position,
		" on_floor=", gv.player_body.is_on_floor(),
		" zone_loaded=", gv._zone_loaded, " -> ", out)
	get_tree().quit()
