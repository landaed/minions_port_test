extends Node3D
## Assembles a converted MoM zone from a scene.json manifest (terrain + static
## placements + sun/sky), then screenshots it. Used to verify zone assembly and
## scale before committing assets into the real project.
##
## Env: SCENE (scene.json), OUT (png), CAM (aerial|ground|top)

var _frames := 0
var _out := "/tmp/trinst.png"
var _cache := {}

const TERRAIN_SHADER := """
shader_type spatial;
render_mode cull_disabled;
uniform sampler2D grass_tex : source_color, filter_linear, repeat_enable;
uniform sampler2D rock_tex : source_color, filter_linear, repeat_enable;
uniform sampler2D sand_tex : source_color, filter_linear, repeat_enable;
uniform float tex_scale = 0.12;
uniform float sand_height = 63.0;
uniform float sand_blend = 3.0;
varying vec3 wpos;
varying vec3 wnrm;
varying float oheight;
void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wnrm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
	oheight = VERTEX.y;  // object-space elevation; biome stays anchored if zone is re-origined
}
vec3 tri(sampler2D t, vec3 p, vec3 n) {
	vec3 bw = pow(abs(n), vec3(4.0));
	bw /= (bw.x + bw.y + bw.z);
	return texture(t, p.zy * tex_scale).rgb * bw.x
		 + texture(t, p.xz * tex_scale).rgb * bw.y
		 + texture(t, p.xy * tex_scale).rgb * bw.z;
}
void fragment() {
	vec3 n = normalize(wnrm);
	float slope = clamp(n.y, 0.0, 1.0);
	vec3 g = tri(grass_tex, wpos, n);
	vec3 r = tri(rock_tex, wpos, n);
	vec3 s = tri(sand_tex, wpos, n);
	float rockw = smoothstep(0.55, 0.32, slope);
	float sandw = smoothstep(sand_height + sand_blend, sand_height, oheight);
	vec3 col = mix(mix(g, s, sandw), r, rockw);
	ALBEDO = col;
	ROUGHNESS = 0.96;
}
"""

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
			_texture_terrain(terr, data.get("terrain_textures", {}))

	# statics + interiors (buildings); ONLY env can isolate either set
	var only := _env("ONLY", "all")
	var pts: Array[Vector3] = []
	if only != "interiors":
		_place_items(data.get("statics", []), pts)
	if only != "statics":
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
	if _frames == 18:
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

func _load_tex(path):
	if path == null or not FileAccess.file_exists(path):
		return null
	var img := Image.load_from_file(path)
	if img == null:
		return null
	return ImageTexture.create_from_image(img)

func _all_mesh_instances(n) -> Array:
	var r := []
	if n is MeshInstance3D:
		r.append(n)
	for c in n.get_children():
		r += _all_mesh_instances(c)
	return r

func _texture_terrain(node, texdict) -> void:
	var grass = _load_tex(texdict.get("grass", null))
	var rock = _load_tex(texdict.get("rock", null))
	var sand = _load_tex(texdict.get("sand", null))
	if grass == null:
		return
	var mat := ShaderMaterial.new()
	var sh := Shader.new()
	sh.code = TERRAIN_SHADER
	mat.shader = sh
	mat.set_shader_parameter("grass_tex", grass)
	mat.set_shader_parameter("rock_tex", rock if rock else grass)
	mat.set_shader_parameter("sand_tex", sand if sand else grass)
	for mi in _all_mesh_instances(node):
		mi.material_override = mat

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
	# physically-based sky + image-based ambient/reflections
	e.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	sky.sky_material = PhysicalSkyMaterial.new()
	e.sky = sky
	# explicit ambient (sky-sourced irradiance isn't reliable under software Vulkan,
	# which leaves shadowed slopes pitch black) — fill with a sky-blue ambient
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.55, 0.65, 0.82)
	e.ambient_light_energy = 0.45
	e.ambient_light_sky_contribution = 0.0  # use the color, not the (unprocessed) sky
	# modern filmic tonemapping
	e.tonemap_mode = Environment.TONE_MAPPER_ACES
	e.tonemap_white = 1.6
	# ground-truth ambient occlusion + screen-space indirect light
	e.ssao_enabled = true
	e.ssao_intensity = 1.0
	e.ssil_enabled = true
	# tasteful bloom on bright highlights
	e.glow_enabled = true
	e.glow_intensity = 0.5
	e.glow_bloom = 0.05
	e.glow_hdr_threshold = 1.1
	# subtle aerial-perspective depth fog
	e.fog_enabled = true
	e.fog_mode = Environment.FOG_MODE_DEPTH
	e.fog_depth_begin = 500.0
	e.fog_depth_end = 4000.0
	e.fog_light_color = Color(0.7, 0.78, 0.9)
	e.fog_sky_affect = 0.0
	e.fog_density = 1.0
	# gentle grade
	e.adjustment_enabled = true
	e.adjustment_contrast = 1.05
	e.adjustment_saturation = 1.05
	we.environment = e
	add_child(we)

	# sun (drives the physical sky disc too)
	var sun := DirectionalLight3D.new()
	var az := 40.0
	var s = data.get("sun", null)
	if s:
		az = float(s.get("azimuth", 40.0))
	# MoM's baked sun sits very low; lift it to a high, soft midday angle
	sun.rotation_degrees = Vector3(-46.0, az + 35.0, 0)
	sun.light_energy = 1.5
	sun.light_color = Color(1.0, 0.96, 0.88)
	sun.shadow_enabled = true
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	sun.directional_shadow_max_distance = 600.0
	sun.light_angular_distance = 1.0  # softens shadow edges
	add_child(sun)

func _place_camera(center: Vector3, spread: float, mode: String) -> void:
	var cam := Camera3D.new()
	add_child(cam)
	cam.far = 12000.0
	if mode == "ground":
		# lower, near-horizontal hero angle looking across the city to the hills
		var d := maxf(spread * 0.5, 160.0)
		cam.position = center + Vector3(d, d * 0.22, d)
		cam.look_at(center + Vector3(0.0, 12.0, 0.0), Vector3.UP)
	elif mode == "top":
		cam.position = center + Vector3(0.0, maxf(spread * 0.9, 150.0), 0.1)
		cam.look_at(center, Vector3.UP)
	else:  # aerial 3/4
		var dd := maxf(spread * 0.6, 120.0)
		cam.position = center + Vector3(dd * 0.55, dd * 0.6, dd * 0.55)
		cam.look_at(center, Vector3.UP)
