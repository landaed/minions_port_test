@tool
class_name MoMSpawnPoint
extends Node3D
## Editor-authorable NPC/monster spawn marker.
##
## Place these under the zone scene's "Spawns" node (world/zones/trinst.tscn) to
## control WHERE a spawn point sits and which way the mob faces — move/rotate the
## node like any other. The world server reads these markers straight out of the
## zone .tscn at zone start (mud/world/godotspawns.py), so editor placement is the
## single source of truth while the server keeps full authority over everything
## else: which mob actually spawns (the DB spawn group), respawn timers, loot,
## levels and AI never leave the server.
##
## The editor preview (mob model, name label, wander ring) is cosmetic, built only
## inside the editor, and never saved into the scene or loaded in game.
##
## Fields:
##   spawn_group   DB SpawnGroup name (e.g. "BATS", "FRIZZLE_FRY"). Must exist in
##                 the world DB for this zone or the server ignores the marker.
##   wander_group  -1 = stationary (vendors/guards); >= 0 = the mob strolls around
##                 the marker (matches the legacy WanderGroup semantics).
##   enabled       Untick to keep the marker but stop the server using it.
##   preview_*     Cosmetic hints for the editor preview only (filled by the
##                 importer from the DB; safe to leave empty on new markers).

const CHAR_ASSET_DIR := "res://assets/characters/"
const WANDER_RADIUS := 10.0  # matches stubsim._WANDER_RADIUS

@export var spawn_group: String = "":
	set(v):
		spawn_group = v
		_refresh_preview()
@export_range(-1, 64) var wander_group: int = -1:
	set(v):
		wander_group = v
		_refresh_preview()
@export var enabled: bool = true:
	set(v):
		enabled = v
		_refresh_preview()

@export_group("Editor Preview (cosmetic)")
## Mob name(s) this group can spawn, e.g. "Vicious Bat" — shown on the label.
@export var preview_name: String = "":
	set(v):
		preview_name = v
		_refresh_preview()
## Server model path of the representative mob (e.g. "animal/bat.dts");
## used to show the real model in the editor when the converted glb exists.
@export var preview_model: String = "":
	set(v):
		preview_model = v
		_refresh_preview()
## Extra info baked by the importer (respawn time, rare spawns, ...).
@export var preview_info: String = ""
@export var preview_scale: float = 1.0:
	set(v):
		preview_scale = v
		_refresh_preview()

var _preview: Node3D = null

func _ready() -> void:
	if _preview_allowed():
		_refresh_preview()

func _preview_allowed() -> bool:
	# Editor only. MOM_FORCE_SPAWN_PREVIEW=1 additionally enables previews in
	# headless capture tools (tools/zone_shot.gd) so spawn layouts can be
	# screenshotted without opening the editor; it is never set in the game.
	return Engine.is_editor_hint() or OS.get_environment("MOM_FORCE_SPAWN_PREVIEW") == "1"

func _glb_path() -> String:
	if preview_model.is_empty():
		return ""
	var key := preview_model.to_lower()
	if key.ends_with(".dts"):
		key = key.substr(0, key.length() - 4)
	key = key.replace("/", "_").replace("\\", "_")
	var p := CHAR_ASSET_DIR + key + ".glb"
	return p if ResourceLoader.exists(p) else ""

func _refresh_preview() -> void:
	if not _preview_allowed() or not is_inside_tree():
		return
	if _preview != null and is_instance_valid(_preview):
		_preview.queue_free()
	_preview = Node3D.new()
	# No owner is ever assigned, so none of this is saved into the scene file.
	add_child(_preview, false, Node.INTERNAL_MODE_BACK)

	var tint := Color(0.35, 0.9, 0.45) if wander_group < 0 else Color(0.95, 0.55, 0.25)
	if not enabled:
		tint = Color(0.45, 0.45, 0.5)

	# Model preview (falls back to a capsule silhouette).
	var model_path := _glb_path()
	var have_model := false
	if not model_path.is_empty():
		var ps: PackedScene = load(model_path)
		if ps != null:
			var inst := ps.instantiate()
			if inst is Node3D:
				inst.scale = Vector3.ONE * preview_scale
				if not enabled:
					_dim_meshes(inst)
				_preview.add_child(inst)
				have_model = true
	if not have_model:
		var mi := MeshInstance3D.new()
		var capsule := CapsuleMesh.new()
		capsule.radius = 0.4
		capsule.height = 1.7
		mi.mesh = capsule
		mi.position = Vector3(0, 0.85, 0)
		var m := StandardMaterial3D.new()
		m.albedo_color = Color(tint, 0.55)
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		mi.material_override = m
		_preview.add_child(mi)

	# Ground marker: disc + facing arrow in the group colour.
	var ring := MeshInstance3D.new()
	var torus := TorusMesh.new()
	torus.inner_radius = 0.55
	torus.outer_radius = 0.7
	ring.mesh = torus
	ring.position = Vector3(0, 0.05, 0)
	var ring_mat := StandardMaterial3D.new()
	ring_mat.albedo_color = tint
	ring_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	ring.material_override = ring_mat
	_preview.add_child(ring)
	var arrow := MeshInstance3D.new()
	var prism := PrismMesh.new()
	prism.size = Vector3(0.4, 0.5, 0.12)
	arrow.mesh = prism
	arrow.rotation_degrees = Vector3(-90, 0, 0)
	arrow.position = Vector3(0, 0.05, -0.95)  # -Z = facing direction
	arrow.material_override = ring_mat
	_preview.add_child(arrow)

	# Wander ring: where a roaming mob may stroll (server-side wander radius).
	if wander_group >= 0 and enabled:
		var wring := MeshInstance3D.new()
		var wtorus := TorusMesh.new()
		wtorus.inner_radius = WANDER_RADIUS - 0.08
		wtorus.outer_radius = WANDER_RADIUS
		wring.mesh = wtorus
		wring.position = Vector3(0, 0.05, 0)
		var wmat := StandardMaterial3D.new()
		wmat.albedo_color = Color(tint, 0.5)
		wmat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		wmat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		wring.material_override = wmat
		_preview.add_child(wring)

	# Floating label with the spawn facts.
	var label := Label3D.new()
	var lines: Array[String] = []
	lines.append(spawn_group if not spawn_group.is_empty() else "<no group>")
	if not preview_name.is_empty():
		lines.append(preview_name)
	if not preview_info.is_empty():
		lines.append(preview_info)
	if wander_group >= 0:
		lines.append("wander %d (r=%.0f)" % [wander_group, WANDER_RADIUS])
	if not enabled:
		lines.append("[DISABLED]")
	label.text = "\n".join(lines)
	label.position = Vector3(0, 2.3 * maxf(preview_scale, 0.6), 0)
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.fixed_size = true
	label.pixel_size = 0.0035
	label.modulate = tint
	label.outline_size = 6
	_preview.add_child(label)

func _dim_meshes(node: Node) -> void:
	if node is MeshInstance3D:
		node.transparency = 0.7
	for c in node.get_children():
		_dim_meshes(c)
