extends Node
## Headless check: drives gameplay_view with a faked server enter-world + entity
## snapshots (no live server) to confirm the Trinst zone loads, the player lands
## on terrain, and replicated NPCs render with the correct animated models. The
## test skeleton walks toward the player so its walk animation triggers, then we
## screenshot the gameplay SubViewport from a third-person camera. Dev-only.

var gv
const BIND := [257.095, 133.949, 152.194]  # server coords (z = height)

func _env(k: String, d: String) -> String:
	var v := OS.get_environment(k)
	return v if v != "" else d

func _env_vec(k: String, d: Vector3) -> Vector3:
	var s := OS.get_environment(k)
	if s == "":
		return d
	var p := s.split(",")
	if p.size() < 3:
		return d
	return Vector3(float(p[0]), float(p[1]), float(p[2]))

func _snapshot(t: float) -> void:
	# Put the NPCs on open ground ~14u out (the bind point itself is ringed by the
	# bindpoint monument's boulders). The skeleton walks across that clear area.
	var walk: float = minf(t * 2.5, 12.0)
	gv.set_entities([
		{"is_self": true, "position": BIND, "health": 1.0, "max_health": 1.0,
			"name": "You", "public_name": "Tester", "sim_id": 1, "id": 1,
			"race": "Human", "sex": "Male", "level": 1, "pclass": "Warrior"},
		{"is_self": false, "position": [BIND[0] + 16.0 - walk, BIND[1] + 14.0, BIND[2]],
			"health": 1.0, "max_health": 1.0, "name": "Skeleton", "public_name": "Skeleton",
			"sim_id": 2, "id": 2, "level": 3, "race": "Undead", "sex": "Male",
			"model": "undead/skeleton", "is_enemy": true, "standing": "Hostile",
			"attacking": walk >= 12.0},  # swing once it arrives
		{"is_self": false, "position": [BIND[0] + 10.0, BIND[1] + 17.0, BIND[2]],
			"health": 1.0, "max_health": 1.0, "name": "Townsperson", "public_name": "Townsperson",
			"sim_id": 3, "id": 3, "level": 5, "race": "Human", "sex": "Female",
			"standing": "Neutral", "pclass": "Cleric"},
	])

func _ready() -> void:
	gv = load("res://gameplay_view.tscn").instantiate()
	add_child(gv)
	await get_tree().process_frame
	gv.apply_world_state({"world_name": "Trinst", "player_name": "Tester"},
		{"name": "Trinst"}, {"hour": 12, "minute": 0})
	_snapshot(0.0)
	for i in range(420):
		await get_tree().physics_frame
		if i % 6 == 0:
			_snapshot(i / 60.0)

	# Third-person camera framing the animated NPCs on the open ground.
	var wr = gv.get_node("SubViewportContainer/SubViewport/WorldRoot")
	var icam := Camera3D.new()
	wr.add_child(icam)
	var pp: Vector3 = gv.player_body.global_position
	# Aim at the skeleton's marker if present, else the player.
	var focus := pp
	if _env("FOCUS", "skeleton") == "player":
		focus = pp
	else:
		var sk = gv.replicated_entity_nodes.get("2")
		if sk != null and is_instance_valid(sk):
			focus = sk.global_position
	var off := _env_vec("CAM_OFF", Vector3(4.0, 2.2, 4.5))
	var at := _env_vec("CAM_AT", Vector3(0.0, 0.9, 0.0))
	icam.global_position = focus + off
	icam.look_at(focus + at, Vector3.UP)
	icam.current = true
	icam.fov = float(_env("FOV", "55"))
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var out := OS.get_environment("SHOT")
	if out == "":
		out = "/tmp/gv.png"
	gv.sub_viewport.get_texture().get_image().save_png(out)
	print("VERIFY player=", gv.player_body.global_position,
		" on_floor=", gv.player_body.is_on_floor(),
		" zone_loaded=", gv._zone_loaded,
		" player_model=", gv._player_model_key, " -> ", out)
	get_tree().quit()
