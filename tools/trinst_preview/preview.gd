extends Node3D
## Assembles a converted MoM zone from a scene.json manifest (terrain + static
## placements + sun/sky), then screenshots it. Used to verify zone assembly and
## scale before committing assets into the real project.
##
## Env: SCENE (scene.json), OUT (png), CAM (aerial|ground|top)

var _frames := 0
var _out := "/tmp/trinst.png"
var _cache := {}

func _ready() -> void:
	var scene_path := _env("SCENE", "/tmp/trinst_build/scene.json")
	_out = _env("OUT", "/tmp/trinst.png")
	var mode := _env("CAM", "aerial")

	var txt := ""
	var f := FileAccess.open(scene_path, FileAccess.READ)
	if f:
		txt = f.get_as_text()
	var data: Dictionary = JSON.parse_string(txt) if txt != "" else {}
	if data.is_empty():
		push_error("could not read scene.json at " + scene_path)
		_out_now()
		return

	_setup_env(data)

	# terrain
	if data.has("terrain_glb"):
		var terr = _load_glb(data["terrain_glb"])
		if terr:
			var tp = data["terrain"]["pos"]
			terr.position = Vector3(tp[0], tp[1], tp[2])
			add_child(terr)

	# statics + interiors (buildings)
	var pts: Array[Vector3] = []
	_place_items(data.get("statics", []), pts)
	_place_items(data.get("interiors", []), pts)

	# robust framing: centroid + 80th-percentile radius (ignore outliers)
	var center := Vector3.ZERO
	for p in pts:
		center += p
	if pts.size() > 0:
		center /= pts.size()
	var dists := []
	for p in pts:
		dists.append(p.distance_to(center))
	dists.sort()
	var spread := 200.0
	if dists.size() > 0:
		spread = float(dists[int(dists.size() * 0.8)]) * 2.0 + 40.0
	print("PLACED_STATICS=", pts.size())
	print("CITY_CENTER=", center, " SPREAD=", spread)
	_place_camera(center, spread, mode)

func _process(_d: float) -> void:
	_frames += 1
	if _frames == 12:
		_out_now()

func _out_now() -> void:
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	print("SCREENSHOT_SAVE_ERR=", img.save_png(_out), " -> ", _out)
	get_tree().quit()

func _env(k: String, d: String) -> String:
	var v := OS.get_environment(k)
	return v if v != "" else d

func _place_items(items, pts: Array[Vector3]) -> void:
	for s in items:
		if s.get("glb", null) == null:
			continue
		var proto = _load_glb(s["glb"])
		if proto == null:
			continue
		var inst = proto.duplicate()
		var rot = s["rot"]; var pos = s["pos"]; var scl = s["scale"]
		var ax := Vector3(rot[0], rot[1], rot[2])
		var b := Basis(ax.normalized(), deg_to_rad(rot[3])) if ax.length() > 0.001 else Basis()
		b = b.scaled(Vector3(scl[0], scl[1], scl[2]))
		inst.transform = Transform3D(b, Vector3(pos[0], pos[1], pos[2]))
		add_child(inst)
		pts.append(Vector3(pos[0], pos[1], pos[2]))

func _load_glb(path):
	if path in _cache:
		return _cache[path]
	if path == null or not FileAccess.file_exists(path):
		_cache[path] = null
		return null
	var doc := GLTFDocument.new()
	var st := GLTFState.new()
	if doc.append_from_file(path, st) != OK:
		_cache[path] = null
		return null
	var n := doc.generate_scene(st)
	_cache[path] = n
	return n

func _setup_env(data: Dictionary) -> void:
	var we := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	sky.sky_material = ProceduralSkyMaterial.new()
	e.sky = sky
	e.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	e.ambient_light_energy = 0.55
	var skyinfo = data.get("sky", null)
	if skyinfo and float(skyinfo.get("fogDistance", 0)) > 0:
		e.fog_enabled = true
		e.fog_density = 0.0004
		var fc = skyinfo.get("fogColor", null)
		if fc and fc.size() >= 3:
			e.fog_light_color = Color(fc[0], fc[1], fc[2])
	we.environment = e
	add_child(we)

	var sun := DirectionalLight3D.new()
	var elev := 35.0
	var az := 20.0
	var s = data.get("sun", null)
	if s:
		elev = float(s.get("elevation", 35.0))
		az = float(s.get("azimuth", 20.0))
	sun.rotation_degrees = Vector3(-max(elev, 12.0), az, 0)
	sun.shadow_enabled = true
	sun.light_energy = 1.1
	add_child(sun)

func _place_camera(center: Vector3, spread: float, mode: String) -> void:
	var cam := Camera3D.new()
	add_child(cam)
	cam.far = 12000.0
	if mode == "ground":
		cam.position = center + Vector3(0.0, 2.0, 0.0)
		cam.look_at(center + Vector3(spread * 0.1, 1.0, spread * 0.05), Vector3.UP)
	elif mode == "top":
		cam.position = center + Vector3(0.0, maxf(spread * 0.9, 150.0), 0.1)
		cam.look_at(center, Vector3.UP)
	else:  # aerial 3/4
		var dd := maxf(spread * 0.6, 120.0)
		cam.position = center + Vector3(dd * 0.55, dd * 0.6, dd * 0.55)
		cam.look_at(center, Vector3.UP)
