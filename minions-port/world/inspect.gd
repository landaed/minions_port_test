extends Node3D
## Dev-only zone inspection harness. Loads the real converted zone via
## zone_loader (terrain + building collision + props + environment) at native
## world coordinates, frames a camera on a chosen point, optionally drops the
## player avatar / NPC markers, and screenshots. Lets us review the gate,
## building collisions, NPC models and animations headlessly.
##
## All positions are given in SERVER (Torque) coords: "x,y,z" with z = height.
## Env vars:
##   ZONE   zone name (default trinst)
##   SHOT   output png (default /tmp/inspect.png)
##   FOCUS  server "x,y,z" to look at (default Trinst bind point)
##   DIST   camera distance from focus (default 16)
##   YAW    camera yaw degrees around focus (default 40)
##   PITCH  camera pitch degrees (default -12, negative looks down)
##   FOV    camera fov (default 70)
##   PLAYER "1" to drop the human avatar at FOCUS
##   MARKERS server points "x,y,z;x,y,z;..." to mark with bright spheres
##   FRAMES number of frames to render before the shot (default 30)

const ZoneLoaderScript := preload("res://world/zone_loader.gd")

func _env(k: String, d: String) -> String:
	var v := OS.get_environment(k)
	return v if v != "" else d

func _all_mesh(n: Node) -> Array:
	var r := []
	if n is MeshInstance3D:
		r.append(n)
	for c in n.get_children():
		r += _all_mesh(c)
	return r

func _server_to_godot(sx: float, sy: float, sz: float) -> Vector3:
	# server (x, y, z=height) -> godot (x, z, -y), matching the live client.
	return Vector3(sx, sz, -sy)

func _parse_server_vec(s: String, fallback: Vector3) -> Vector3:
	var parts := s.split(",")
	if parts.size() < 3:
		return fallback
	return _server_to_godot(float(parts[0]), float(parts[1]), float(parts[2]))

func _ready() -> void:
	var zone := _env("ZONE", "trinst")
	var shot := _env("SHOT", "/tmp/inspect.png")
	var focus := _parse_server_vec(_env("FOCUS", "257.095,133.949,152.194"), Vector3(257.095, 152.194, -133.949))
	var dist := float(_env("DIST", "16"))
	var yaw := deg_to_rad(float(_env("YAW", "40")))
	var pitch := deg_to_rad(float(_env("PITCH", "-12")))
	var fov := float(_env("FOV", "70"))
	var frames := int(_env("FRAMES", "30"))

	# Real zone with collision + the game's environment/lighting.
	var loader: Node3D = ZoneLoaderScript.new()
	add_child(loader)
	if not loader.build(zone, true):
		push_error("inspect: failed to build zone " + zone)
		get_tree().quit()
		return

	# Extra fill so detail is readable under software Vulkan (sky ambient is weak).
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-60, 200, 0)
	fill.light_energy = 0.8
	fill.light_color = Color(0.8, 0.85, 1.0)
	add_child(fill)
	var key := OmniLight3D.new()
	key.position = focus + Vector3(0, 10, 0)
	key.omni_range = 60.0
	key.light_energy = 2.0
	add_child(key)

	if _env("PLAYER", "") == "1":
		var avatar_scene = load("res://assets/characters/human.glb")
		if avatar_scene:
			var avatar = avatar_scene.instantiate()
			avatar.position = focus
			add_child(avatar)

	var markers := _env("MARKERS", "")
	if markers != "":
		for chunk in markers.split(";"):
			if chunk.strip_edges() == "":
				continue
			var p := _parse_server_vec(chunk, Vector3.ZERO)
			var m := MeshInstance3D.new()
			var sph := SphereMesh.new()
			sph.radius = 0.6
			sph.height = 1.2
			m.mesh = sph
			var mat := StandardMaterial3D.new()
			mat.albedo_color = Color(1, 0.2, 0.2)
			mat.emission_enabled = true
			mat.emission = Color(1, 0.2, 0.2)
			m.material_override = mat
			m.position = p
			add_child(m)

	# Orbit camera around the focus point.
	var cam := Camera3D.new()
	cam.fov = fov
	cam.far = 8000.0
	add_child(cam)
	var dir := Vector3(
		cos(pitch) * sin(yaw),
		sin(pitch),
		cos(pitch) * cos(yaw))
	cam.position = focus - dir * dist + Vector3(0, 0, 0)
	cam.look_at(focus, Vector3.UP)

	for _i in range(frames):
		await get_tree().process_frame

	if _env("DIAG", "") == "1":
		var space := get_viewport().world_3d.direct_space_state
		print("--- DIAG ground heights around focus (godot) ", focus, " ---")
		for off in [Vector3(0,0,0), Vector3(3,0,0), Vector3(-3,0,0), Vector3(0,0,3), Vector3(0,0,-3), Vector3(6,0,0), Vector3(-6,0,0)]:
			var p: Vector3 = focus + off
			var q := PhysicsRayQueryParameters3D.create(p + Vector3(0,60,0), p - Vector3(0,60,0))
			q.collision_mask = 1
			var hit := space.intersect_ray(q)
			if hit:
				print("  off=", off, " ground_y=", snappedf(hit.position.y, 0.01), " collider=", hit.collider.name)
			else:
				print("  off=", off, " NO HIT")
		# Report AABBs of the nearest interior meshes to the focus.
		var best := []
		for child in get_children():
			if child == cam:
				continue
			for mi in _all_mesh(child):
				var aabb: AABB = mi.get_aabb()
				var gpos: Vector3 = mi.global_position
				best.append([gpos.distance_to(focus), str(mi.name), gpos, aabb])
		best.sort_custom(func(a, b): return a[0] < b[0])
		print("--- nearest mesh AABBs to focus ---")
		for i in range(min(5, best.size())):
			var b = best[i]
			print("  d=", snappedf(b[0],0.1), " ", b[1], " gpos=", b[2], " world_top_y=", snappedf(b[2].y + b[3].position.y + b[3].size.y, 0.1), " base_y=", snappedf(b[2].y + b[3].position.y, 0.1))

	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	var err := img.save_png(shot)
	print("INSPECT zone=", zone, " focus=", focus, " cam=", cam.position, " err=", err, " -> ", shot)
	get_tree().quit()
