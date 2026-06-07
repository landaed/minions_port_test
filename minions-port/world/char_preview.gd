extends Node3D
## Dev harness: load a (possibly /tmp) .glb at runtime via GLTFDocument, play an
## animation, seek to a time, and screenshot. Verifies skinned + animated DTS/DSQ
## conversions without needing project import.
## Env: GLB (path), ANIM (animation name), TIME (seconds, default 0.3),
##      SHOT (png), DIST (camera distance), YAW, FOV, GRID(1)

const MeshNormalRepairScript := preload("res://world/mesh_normal_repair.gd")

func _env(k: String, d: String) -> String:
	var v := OS.get_environment(k)
	return v if v != "" else d

func _ready() -> void:
	var glb := _env("GLB", "/tmp/human_anim.glb")
	var anim := _env("ANIM", "walk")
	var t := float(_env("TIME", "0.3"))
	var shot := _env("SHOT", "/tmp/char.png")
	var dist := float(_env("DIST", "3.2"))
	var yaw := deg_to_rad(float(_env("YAW", "25")))

	# Environment + lights
	var we := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color(0.20, 0.23, 0.28)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.7, 0.75, 0.85)
	e.ambient_light_energy = 0.7
	we.environment = e
	add_child(we)
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-35, 35, 0)
	key.light_energy = 1.6
	add_child(key)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-20, -140, 0)
	fill.light_energy = 0.6
	add_child(fill)

	if _env("GRID", "") == "1":
		var g := MeshInstance3D.new()
		var pm := PlaneMesh.new()
		pm.size = Vector2(10, 10)
		g.mesh = pm
		var m := StandardMaterial3D.new()
		m.albedo_color = Color(0.3, 0.32, 0.36)
		g.material_override = m
		add_child(g)

	# Runtime glb load
	var doc := GLTFDocument.new()
	var st := GLTFState.new()
	var err := doc.append_from_file(glb, st)
	if err != OK:
		push_error("char_preview: failed to load " + glb)
		get_tree().quit()
		return
	var model := doc.generate_scene(st)
	add_child(model)
	MeshNormalRepairScript.repair_node(model, true)

	# AABB to frame the model
	var aabb := _scene_aabb(model)
	var center := aabb.position + aabb.size * 0.5
	var height := maxf(aabb.size.y, 1.0)
	print("CHAR_AABB size=", aabb.size, " center=", center)

	# Find AnimationPlayer + list anims
	var ap := _find_anim_player(model)
	var played := "<none>"
	if ap:
		var names := ap.get_animation_list()
		print("ANIMS=", names)
		var target := anim
		if not ap.has_animation(target) and names.size() > 0:
			target = names[0]
		if ap.has_animation(target):
			var a := ap.get_animation(target)
			a.loop_mode = Animation.LOOP_LINEAR
			ap.play(target)
			ap.seek(clampf(t, 0.0, a.length), true)
			ap.advance(0.0)
			played = "%s @%.2f/%.2f" % [target, t, a.length]
	print("PLAYED=", played)

	# Camera
	var cam := Camera3D.new()
	cam.fov = float(_env("FOV", "45"))
	add_child(cam)
	var dir := Vector3(sin(yaw), 0.25, cos(yaw)).normalized()
	cam.position = center + dir * (dist + height)
	cam.look_at(center, Vector3.UP)

	for _i in range(8):
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	print("SHOT_ERR=", img.save_png(shot), " -> ", shot)
	get_tree().quit()

func _find_anim_player(n: Node) -> AnimationPlayer:
	if n is AnimationPlayer:
		return n
	for c in n.get_children():
		var r := _find_anim_player(c)
		if r:
			return r
	return null

func _scene_aabb(n: Node) -> AABB:
	var out := AABB()
	var have := false
	for mi in _all_mesh(n):
		var a: AABB = mi.global_transform * mi.get_aabb()
		if not have:
			out = a
			have = true
		else:
			out = out.merge(a)
	if not have:
		return AABB(Vector3(-0.5, 0, -0.5), Vector3(1, 1.8, 1))
	return out

func _all_mesh(n: Node) -> Array:
	var r := []
	if n is MeshInstance3D:
		r.append(n)
	for c in n.get_children():
		r += _all_mesh(c)
	return r
