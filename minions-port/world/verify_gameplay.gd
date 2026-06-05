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
	# Self entity in server coords near the Trinst city centre, spawned high so it
	# falls onto whatever terrain/roof is there (server z = height).
	gv.set_entities([{
		"is_self": true, "position": [77.0, 69.0, 150.0],
		"health": 1.0, "name": "Tester", "sim_id": 1, "char_index": 0, "mob_id": 0,
	}])
	for i in range(300):
		await get_tree().physics_frame
	await RenderingServer.frame_post_draw
	var out := OS.get_environment("SHOT")
	if out == "":
		out = "/tmp/gv.png"
	gv.sub_viewport.get_texture().get_image().save_png(out)
	print("VERIFY player=", gv.player_body.global_position,
		" on_floor=", gv.player_body.is_on_floor(),
		" zone_loaded=", gv._zone_loaded, " -> ", out)
	get_tree().quit()
