@tool
extends Node3D
## Canonical runtime support for a converted MoM zone. It can either build the
## legacy JSON description into children, or finalize an authored .tscn version
## of that same zone by applying terrain material, collision, and lighting.
##
## Used by the live game (gameplay_view loads this into WorldRoot at the server
## origin offset), the generated Trinst .tscn scene, and the offline art preview.
## No player/camera of its own.

const ASSET_ROOT := "res://assets/"

const TERRAIN_SHADER_PATH := "res://world/zone_terrain.gdshader"

@export var authored_zone_name := ""
@export var authored_with_environment := true

var zone_name := ""
var base := ""


func _ready() -> void:
	# Tool-mode preview: make the authored terrain look in the editor like it does
	# in game, without generating collision bodies or adding runtime lighting.
	if not Engine.is_editor_hint() or authored_zone_name == "":
		return
	zone_name = authored_zone_name
	base = ASSET_ROOT + zone_name + "/"
	_apply_authored_terrain_material(self)


func _apply_authored_terrain_material(node: Node) -> void:
	for child in node.get_children():
		if child is Node3D:
			var n := child as Node3D
			if str(n.get_meta("zone_role", "")) == "terrain":
				_texture_terrain(n, _terrain_texture_defaults())
		_apply_authored_terrain_material(child)


func _terrain_texture_defaults() -> Dictionary:
	return {
		"grass": "textures/grass01.jpg",
		"rock": "textures/rock009.jpg",
		"sand": "textures/sand006.jpg",
	}

# Interiors that should be walk-through (no collision): decorative monuments /
# spawn markers the player stands at or passes through. The bindpoint monument
# (a tall obelisk ringed by boulders) is exactly where a new character spawns, so
# colliding geometry there traps the player — in the original you pass through it.
const PASSTHROUGH_INTERIORS := ["architecture_bindpoint"]

func _is_passthrough(rel: String) -> bool:
	for key in PASSTHROUGH_INTERIORS:
		if rel.findn(key) != -1:
			return true
	return false


## Build the zone from the legacy JSON description. Kept as a fallback and for
## tooling/preview scenes; the live Trinst path now loads res://world/zones/trinst.tscn.
## `with_environment` lets the live game opt out if it manages lighting itself.
## Returns true on success.
func build(zone: String, with_environment: bool = true) -> bool:
	zone_name = zone
	base = ASSET_ROOT + zone + "/"
	var data := _load_json(base + "scene.json")
	if data.is_empty():
		push_error("zone_loader: missing or empty " + base + "scene.json")
		return false
	if with_environment:
		_setup_environment(data)
	_build_terrain(data)
	_place_items(data.get("statics", []), false)
	_place_items(data.get("interiors", []), true)
	return true


## Finalize a pre-authored Godot scene for runtime use. This intentionally does
## not instantiate scene objects from JSON; it only applies runtime-only state
## (collision, terrain shader, and optional environment) to nodes that already
## exist in the .tscn and can be moved/edited in the Godot editor.
func prepare_authored_scene(zone: String = "", with_environment: bool = true) -> bool:
	zone_name = zone if zone != "" else authored_zone_name
	if zone_name == "":
		push_error("zone_loader: authored scene has no zone_name")
		return false
	base = ASSET_ROOT + zone_name + "/"
	if with_environment and authored_with_environment:
		_setup_environment({})
	_finalize_authored_children()
	return true


func _finalize_authored_children() -> void:
	_finalize_authored_node(self)


func _finalize_authored_node(node: Node) -> void:
	for child in node.get_children():
		if child is WorldEnvironment or child is DirectionalLight3D:
			continue
		if child is Node3D:
			var n := child as Node3D
			var rel := str(n.get_meta("zone_glb", ""))
			var role := str(n.get_meta("zone_role", ""))
			for mi in _mesh_instances(n):
				mi.lod_bias = 64.0
			if role == "terrain":
				_texture_terrain(n, _terrain_texture_defaults())
				_ensure_mesh_collision(n, true)
			elif bool(n.get_meta("zone_collide", false)) and not _is_passthrough(rel):
				_ensure_mesh_collision(n, false)
				_add_fallback_floor(n)
		_finalize_authored_node(child)


func _ensure_mesh_collision(node: Node3D, terrain_only_mask: bool) -> void:
	for mi in _mesh_instances(node):
		var has_body := false
		for c in mi.get_children():
			if c is StaticBody3D:
				has_body = true
				if terrain_only_mask:
					c.collision_layer = c.collision_layer | 4
		if not has_body:
			mi.create_trimesh_collision()
			if terrain_only_mask:
				for c in mi.get_children():
					if c is StaticBody3D:
						c.collision_layer = c.collision_layer | 4


func spawn_point(zone: String = "") -> Variant:
	var z := zone if zone != "" else zone_name
	var data := _load_json(ASSET_ROOT + z + "/scene.json")
	var sp = data.get("spawn", null)
	if sp != null and sp.size() == 3:
		return Vector3(sp[0], sp[1], sp[2])
	return null


func _load_json(path: String) -> Dictionary:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return {}
	var d = JSON.parse_string(f.get_as_text())
	return d if d is Dictionary else {}


func _build_terrain(data: Dictionary) -> void:
	if not data.has("terrain_glb"):
		return
	var ps := load(base + str(data["terrain_glb"])) as PackedScene
	if ps == null:
		return
	var terr := ps.instantiate()
	var tp = data["terrain"]["pos"]
	terr.position = Vector3(tp[0], tp[1], tp[2])
	add_child(terr)
	_texture_terrain(terr, data.get("terrain_textures", {}))
	for mi in _mesh_instances(terr):
		mi.lod_bias = 64.0
		mi.create_trimesh_collision()
		# Tag the terrain collider with bit 3 (value 4) in addition to bit 1, so the
		# client's NPC ground-snap ray can hit terrain only (climb hills, ignore
		# building roofs) while the player still collides via bit 1.
		for c in mi.get_children():
			if c is StaticBody3D:
				c.collision_layer = c.collision_layer | 4


func _place_items(items, collide: bool) -> void:
	for s in items:
		var rel = s.get("glb", null)
		if rel == null:
			continue
		var ps := load(base + str(rel)) as PackedScene
		if ps == null:
			continue
		var inst := ps.instantiate()
		var rot = s["rot"]; var pos = s["pos"]; var scl = s["scale"]
		var ax := Vector3(rot[0], rot[1], rot[2])
		var b := Basis(ax.normalized(), deg_to_rad(rot[3])) if ax.length() > 0.001 else Basis()
		b = b.scaled(Vector3(scl[0], scl[1], scl[2]))
		inst.transform = Transform3D(b, Vector3(pos[0], pos[1], pos[2]))
		# Tag with the source glb name so the client can report which building the
		# player is looking at (debug panel) — handy for pinning down the gate.
		inst.set_meta("zone_glb", str(rel).get_file().get_basename())
		add_child(inst)
		var do_collide := collide and not _is_passthrough(str(rel))
		for mi in _mesh_instances(inst):
			# Auto-generated mesh LODs decimate alpha-card foliage (leaves vanish
			# at distance); keep full detail.
			mi.lod_bias = 64.0
			if do_collide:
				mi.create_trimesh_collision()
		if do_collide:
			_add_fallback_floor(inst)


func _add_fallback_floor(inst: Node3D) -> void:
	# Some converted interiors are missing floor collision (the player/NPCs fall
	# through and get stuck under the building). Add a thin collision slab at the
	# building's base, covering its footprint, as a safety net. Only real buildings
	# get one (small props are skipped).
	var meshes := _mesh_instances(inst)
	if meshes.is_empty():
		return
	var aabb: AABB
	var have := false
	for mi in meshes:
		var a: AABB = mi.global_transform * mi.get_aabb()
		if not have:
			aabb = a
			have = true
		else:
			aabb = aabb.merge(a)
	if not have or aabb.size.x < 4.0 or aabb.size.z < 4.0 or aabb.size.y < 3.0:
		return
	var body := StaticBody3D.new()
	body.collision_layer = 1
	body.set_meta("zone_glb", inst.get_meta("zone_glb", "building") + " (floor)")
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(maxf(aabb.size.x - 1.0, 1.0), 0.4, maxf(aabb.size.z - 1.0, 1.0))
	cs.shape = box
	body.add_child(cs)
	add_child(body)
	body.global_position = Vector3(aabb.position.x + aabb.size.x * 0.5,
		aabb.position.y + 0.2, aabb.position.z + aabb.size.z * 0.5)


func _texture_terrain(node: Node, texdict) -> void:
	var grass = _load_tex(texdict.get("grass", null))
	if grass == null:
		return
	var rock = _load_tex(texdict.get("rock", null))
	var sand = _load_tex(texdict.get("sand", null))
	var mat := ShaderMaterial.new()
	mat.shader = load(TERRAIN_SHADER_PATH) as Shader
	if mat.shader == null:
		push_warning("zone_loader: terrain shader missing at " + TERRAIN_SHADER_PATH)
		return
	mat.set_shader_parameter("grass_tex", grass)
	mat.set_shader_parameter("rock_tex", rock if rock else grass)
	mat.set_shader_parameter("sand_tex", sand if sand else grass)
	for mi in _mesh_instances(node):
		mi.material_override = mat


func _load_tex(rel):
	if rel == null:
		return null
	return load(base + str(rel))


func _mesh_instances(n: Node) -> Array:
	var r := []
	if n is MeshInstance3D:
		r.append(n)
	for c in n.get_children():
		r += _mesh_instances(c)
	return r


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
