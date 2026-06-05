extends Node3D
## Generic asset inspector for the MoM->Godot pipeline.
## Loads a .glb/.gltf/.tscn (runtime, no import needed for glTF), frames it with a
## camera, adds a ground grid + a 1.8 m human-height reference, prints the asset's
## real-world AABB size (for scale checking), screenshots, then quits.
##
## Config via environment variables (set by tools/render.sh):
##   VIEW_PATH  asset to load ("" = empty stage)
##   OUT_PATH   screenshot path (default /tmp/view.png)
##   ORBIT_DEG  camera yaw around asset (default 35)

var _frames := 0
var _out_path := "/tmp/view.png"

func _ready() -> void:
	var view_path := _env("VIEW_PATH", "")
	_out_path = _env("OUT_PATH", "/tmp/view.png")
	var orbit := float(_env("ORBIT_DEG", "35"))

	_setup_environment()
	_add_ground_grid()
	_add_scale_reference()

	var aabb := AABB(Vector3.ZERO, Vector3.ZERO)
	if view_path != "":
		var loaded := _load_asset(view_path)
		if loaded != null:
			add_child(loaded)
			aabb = _node_aabb(loaded)
			print("ASSET_AABB pos=", aabb.position, " size=", aabb.size,
				" (W=%.2fm H=%.2fm D=%.2fm)" % [aabb.size.x, aabb.size.y, aabb.size.z])
		else:
			push_error("Failed to load: " + view_path)

	_place_camera(aabb, orbit)

func _process(_delta: float) -> void:
	_frames += 1
	if _frames == 10:
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		var err := img.save_png(_out_path)
		print("SCREENSHOT_SAVE_ERR=", err, " -> ", _out_path)
		print("RENDERER=", RenderingServer.get_video_adapter_name())
		get_tree().quit()

func _env(key: String, def: String) -> String:
	var v := OS.get_environment(key)
	return v if v != "" else def

func _setup_environment() -> void:
	var we := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	sky.sky_material = ProceduralSkyMaterial.new()
	e.sky = sky
	e.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	e.ambient_light_energy = 0.6
	we.environment = e
	add_child(we)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55, -45, 0)
	sun.shadow_enabled = true
	add_child(sun)

func _add_ground_grid() -> void:
	# Large ground plane with a world-space 1 m grid shader (crisp under software
	# rendering; thicker lines every 10 m).
	var plane := PlaneMesh.new()
	plane.size = Vector2(400, 400)
	var mi := MeshInstance3D.new()
	mi.mesh = plane
	var sh := Shader.new()
	sh.code = """
shader_type spatial;
render_mode unshaded, cull_disabled;
varying vec3 wpos;
void vertex() { wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz; }
void fragment() {
	vec2 g1 = abs(fract(wpos.xz) - 0.5);
	float l1 = step(min(g1.x, g1.y), 0.02);
	vec2 g10 = abs(fract(wpos.xz / 10.0) - 0.5);
	float l10 = step(min(g10.x, g10.y), 0.004);
	ALBEDO = mix(vec3(0.16, 0.18, 0.21), vec3(0.45, 0.48, 0.52), max(l1, l10));
}
"""
	var smat := ShaderMaterial.new()
	smat.shader = sh
	mi.material_override = smat
	mi.position = Vector3(0, -0.001, 0)
	add_child(mi)

func _add_scale_reference() -> void:
	# Translucent 1.8 m capsule at origin = human-height reference.
	var mi := MeshInstance3D.new()
	var cap := CapsuleMesh.new()
	cap.height = 1.8
	cap.radius = 0.3
	mi.mesh = cap
	mi.position = Vector3(1.3, 0.9, 0)  # beside the asset, not occluding it
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.2, 0.7, 1.0, 0.55)
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mi.material_override = mat
	add_child(mi)

func _load_asset(path: String) -> Node:
	var lower := path.to_lower()
	if lower.ends_with(".glb") or lower.ends_with(".gltf"):
		var doc := GLTFDocument.new()
		var state := GLTFState.new()
		var err := doc.append_from_file(path, state)
		if err != OK:
			push_error("GLTF load err " + str(err))
			return null
		return doc.generate_scene(state)
	elif lower.ends_with(".tscn") or lower.ends_with(".scn") or lower.ends_with(".res"):
		var res := ResourceLoader.load(path)
		if res is PackedScene:
			return (res as PackedScene).instantiate()
		return null
	return null

func _node_aabb(n: Node) -> AABB:
	var out := AABB()
	var first := true
	for c in _all_mesh_instances(n):
		var a: AABB = c.global_transform * c.get_aabb()
		if first:
			out = a
			first = false
		else:
			out = out.merge(a)
	return out

func _all_mesh_instances(n: Node) -> Array:
	var r := []
	if n is MeshInstance3D:
		r.append(n)
	for c in n.get_children():
		r += _all_mesh_instances(c)
	return r

func _place_camera(aabb: AABB, orbit_deg: float) -> void:
	var cam := Camera3D.new()
	add_child(cam)
	var center := aabb.position + aabb.size * 0.5
	var radius := maxf(aabb.size.length() * 0.5, 1.5)
	if aabb.size == Vector3.ZERO:
		center = Vector3(0, 1.0, 0)
		radius = 4.0
	var dist := radius * 1.7 + 1.5
	var yaw := deg_to_rad(orbit_deg)
	var off := Vector3(sin(yaw) * 0.85, 0.7, cos(yaw) * 0.85).normalized() * dist
	cam.position = center + off
	cam.look_at(center, Vector3.UP)
	cam.far = maxf(dist * 4.0, 4000.0)
