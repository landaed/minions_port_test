extends Node3D
## Assembles the walkable Trinst zone from assets/trinst/scene.json:
## terrain (textured + collision), buildings (collision), props, a modern
## real-time environment, and positions the Player. No baked lightmaps.

const BASE := "res://assets/trinst/"

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
void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wnrm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
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
	g = mix(g, vec3(0.26, 0.40, 0.14), 0.25);
	vec3 r = tri(rock_tex, wpos, n);
	vec3 s = tri(sand_tex, wpos, n);
	float rockw = smoothstep(0.55, 0.32, slope);
	float sandw = smoothstep(sand_height + sand_blend, sand_height, wpos.y);
	ALBEDO = mix(mix(g, s, sandw), r, rockw);
	ROUGHNESS = 0.96;
}
"""

@onready var player: CharacterBody3D = $Player


func _ready() -> void:
	var data := _load_json(BASE + "scene.json")
	if data.is_empty():
		push_error("Trinst: missing " + BASE + "scene.json")
		return
	_setup_environment(data)
	var world := Node3D.new()
	world.name = "World"
	add_child(world)
	_build_terrain(world, data)
	_place_items(world, data.get("statics", []), false)
	_place_items(world, data.get("interiors", []), true)
	_spawn_player(data)
	_maybe_headless()


func _load_json(path: String) -> Dictionary:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return {}
	var d = JSON.parse_string(f.get_as_text())
	return d if d is Dictionary else {}


func _build_terrain(world: Node3D, data: Dictionary) -> void:
	if not data.has("terrain_glb"):
		return
	var ps := load(BASE + str(data["terrain_glb"])) as PackedScene
	if ps == null:
		return
	var terr := ps.instantiate()
	var tp = data["terrain"]["pos"]
	terr.position = Vector3(tp[0], tp[1], tp[2])
	world.add_child(terr)
	_texture_terrain(terr, data.get("terrain_textures", {}))
	for mi in _mesh_instances(terr):
		mi.create_trimesh_collision()


func _place_items(world: Node3D, items, collide: bool) -> void:
	for s in items:
		var rel = s.get("glb", null)
		if rel == null:
			continue
		var ps := load(BASE + str(rel)) as PackedScene
		if ps == null:
			continue
		var inst := ps.instantiate()
		var rot = s["rot"]; var pos = s["pos"]; var scl = s["scale"]
		var ax := Vector3(rot[0], rot[1], rot[2])
		var b := Basis(ax.normalized(), deg_to_rad(rot[3])) if ax.length() > 0.001 else Basis()
		b = b.scaled(Vector3(scl[0], scl[1], scl[2]))
		inst.transform = Transform3D(b, Vector3(pos[0], pos[1], pos[2]))
		world.add_child(inst)
		if collide:
			for mi in _mesh_instances(inst):
				mi.create_trimesh_collision()


func _texture_terrain(node: Node, texdict) -> void:
	var grass = _load_tex(texdict.get("grass", null))
	if grass == null:
		return
	var rock = _load_tex(texdict.get("rock", null))
	var sand = _load_tex(texdict.get("sand", null))
	var mat := ShaderMaterial.new()
	var sh := Shader.new()
	sh.code = TERRAIN_SHADER
	mat.shader = sh
	mat.set_shader_parameter("grass_tex", grass)
	mat.set_shader_parameter("rock_tex", rock if rock else grass)
	mat.set_shader_parameter("sand_tex", sand if sand else grass)
	for mi in _mesh_instances(node):
		mi.material_override = mat


func _load_tex(rel):
	if rel == null:
		return null
	return load(BASE + str(rel))


func _mesh_instances(n: Node) -> Array:
	var r := []
	if n is MeshInstance3D:
		r.append(n)
	for c in n.get_children():
		r += _mesh_instances(c)
	return r


func _spawn_player(data: Dictionary) -> void:
	if player == null:
		return
	var sp = data.get("spawn", null)
	if sp != null and sp.size() == 3:
		player.global_position = Vector3(sp[0], sp[1], sp[2])


func _setup_environment(data: Dictionary) -> void:
	var we := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	sky.sky_material = PhysicalSkyMaterial.new()
	e.sky = sky
	# sky-sourced ambient renders black under software Vulkan; fill with color
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.55, 0.65, 0.82)
	e.ambient_light_energy = 0.45
	e.ambient_light_sky_contribution = 0.0
	e.tonemap_mode = Environment.TONE_MAPPER_ACES
	e.tonemap_white = 1.6
	e.ssao_enabled = true
	e.ssao_intensity = 1.0
	e.ssil_enabled = true
	e.glow_enabled = true
	e.glow_intensity = 0.5
	e.glow_bloom = 0.05
	e.glow_hdr_threshold = 1.1
	e.fog_enabled = true
	e.fog_mode = Environment.FOG_MODE_DEPTH
	e.fog_depth_begin = 500.0
	e.fog_depth_end = 4000.0
	e.fog_light_color = Color(0.7, 0.78, 0.9)
	e.fog_sky_affect = 0.0
	e.adjustment_enabled = true
	e.adjustment_contrast = 1.05
	e.adjustment_saturation = 1.05
	we.environment = e
	add_child(we)

	var sun := DirectionalLight3D.new()
	var az := 40.0
	var s = data.get("sun", null)
	if s:
		az = float(s.get("azimuth", 40.0))
	sun.rotation_degrees = Vector3(-46.0, az + 35.0, 0)
	sun.light_energy = 1.5
	sun.light_color = Color(1.0, 0.96, 0.88)
	sun.shadow_enabled = true
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	sun.directional_shadow_max_distance = 600.0
	sun.light_angular_distance = 1.0
	add_child(sun)


## Headless walk test: SHOT=<png> renders from the player camera after the
## player settles (and optionally DEMO_WALK auto-walks first), then quits.
func _maybe_headless() -> void:
	var shot := OS.get_environment("SHOT")
	if shot == "":
		return
	for i in range(70):
		await get_tree().physics_frame
	if OS.get_environment("DEMO_WALK") != "":
		player.auto_forward = true
		for i in range(70):
			await get_tree().physics_frame
		player.auto_forward = false
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	img.save_png(shot)
	print("WALK_SHOT pos=", player.global_position, " on_floor=", player.is_on_floor(),
		" -> ", shot)
	get_tree().quit()
