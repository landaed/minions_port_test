extends Control

signal command_requested(command_type: String, payload: Dictionary)

const MOVE_SPEED := 8.0
const INPUT_SYNC_INTERVAL := 0.05  # send movement inputs to server every 50ms
const LOOK_SENSITIVITY := 0.003
const JUMP_VELOCITY := 7.0
const GRAVITY := 20.0
const DEFAULT_ABILITY_NAMES := ["Attack", "Kick", "Block", "Taunt", "Shout", "Guard", "Heal", "Sprint"]
const ENTITY_INTERPOLATION_SPEED := 8.0
const ENTITY_MAX_DISPLAY_DISTANCE := 20.0
const ENTITY_CAPSULE_HALF_HEIGHT := 0.7
const ENTITY_SELECTION_DISTANCE := 150.0
const ZoneLoaderScript := preload("res://world/zone_loader.gd")
const DEFAULT_ZONE := "trinst"

var world_time := {"hour": 0, "minute": 0}
var current_payload: Dictionary = {}
var selected_world: Dictionary = {}
var velocity := Vector3.ZERO
var mouse_captured := false
var jump_requested := false
var interaction_message := ""
var placeholder_npcs: Array = []
var replicated_entities: Array = []
var replicated_entity_nodes: Dictionary = {}
var last_abilities_signature := ""
var server_target_description: Dictionary = {}
var combat_log: Array = []
var _highlighted_entity_key: String = ""
var _pending_target_sim_id: int = 0  # deferred highlight if entity not yet in snapshot
var _pending_target_mob_id: int = 0
var _has_spawned := false
var _input_sync_timer := 0.0
var _last_sent_input: Dictionary = {}
var _server_origin_offset := Vector3.ZERO  # fixed offset: maps server spawn to Godot origin
var _zone_loaded := false

@onready var npc_root: Node3D = $SubViewportContainer/SubViewport/WorldRoot/NpcRoot
@onready var sub_viewport: SubViewport = $SubViewportContainer/SubViewport
@onready var player_body: CharacterBody3D = $SubViewportContainer/SubViewport/WorldRoot/PlayerBody
@onready var camera_pitch: Node3D = $SubViewportContainer/SubViewport/WorldRoot/PlayerBody/CameraYaw/CameraPitch
@onready var camera: Camera3D = $SubViewportContainer/SubViewport/WorldRoot/PlayerBody/CameraYaw/CameraPitch/Camera3D

# --- HUD nodes (built in code by _build_hud) ---
var player_name_label: Label
var health_bar: ProgressBar
var mana_bar: ProgressBar
var stamina_bar: ProgressBar
var health_value_label: Label
var mana_value_label: Label
var stamina_value_label: Label
var combat_status_label: RichTextLabel
var target_frame: PanelContainer
var target_name_label: Label
var target_health_bar: ProgressBar
var target_health_value_label: Label
var ability_bar: HBoxContainer
var hint_label: Label
var combat_log_label: Label
var crosshair: Control
var debug_panel: PanelContainer
var debug_label: Label
# Legacy verbose labels are folded into the toggleable debug panel.
var info_label: Label
var summary_label: Label
var target_label: Label
var interaction_label: Label
var transfer_label: Label

# --- combat-state UI ---
var _crosshair_color := Color(1, 1, 1, 0.7)
var _looking_at_entity := false
var _looking_at_enemy := false
var _looked_entity_id := 0
var _debug_visible := false

func _ready():
	set_process_input(true)
	# Walk terrain at constant horizontal speed (don't lose ground to slopes) and
	# stay snapped to the surface, so client prediction tracks the server's flat
	# movement model instead of falling behind and rubber-banding on hills.
	player_body.floor_constant_speed = true
	player_body.floor_snap_length = 1.0
	player_body.floor_max_angle = deg_to_rad(60.0)
	_build_hud()
	_rebuild_ability_bar()
	_update_labels()

# ---------------------------------------------------------------------------
# HUD construction (a clean combat HUD built entirely in code)
# ---------------------------------------------------------------------------
func _panel_style(accent: Color) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.08, 0.10, 0.82)
	sb.border_color = accent
	sb.set_border_width_all(1)
	sb.border_width_left = 3
	sb.set_corner_radius_all(4)
	sb.content_margin_left = 10
	sb.content_margin_right = 10
	sb.content_margin_top = 6
	sb.content_margin_bottom = 6
	return sb

func _make_bar(color: Color) -> Array:
	# Returns [ProgressBar, value_label] — a colored bar with a centered "cur / max".
	var bar := ProgressBar.new()
	bar.show_percentage = false
	bar.custom_minimum_size = Vector2(190, 18)
	bar.max_value = 100.0
	bar.value = 100.0
	bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var bg := StyleBoxFlat.new()
	bg.bg_color = Color(0.03, 0.03, 0.04, 0.9)
	bg.set_corner_radius_all(3)
	var fill := StyleBoxFlat.new()
	fill.bg_color = color
	fill.set_corner_radius_all(3)
	bar.add_theme_stylebox_override("background", bg)
	bar.add_theme_stylebox_override("fill", fill)
	var value_label := Label.new()
	value_label.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	value_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	value_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	value_label.add_theme_font_size_override("font_size", 11)
	value_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	bar.add_child(value_label)
	return [bar, value_label]

func _make_resource_row(parent: VBoxContainer, tag: String, color: Color) -> Array:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var tag_label := Label.new()
	tag_label.text = tag
	tag_label.custom_minimum_size = Vector2(26, 0)
	tag_label.add_theme_color_override("font_color", color)
	tag_label.add_theme_font_size_override("font_size", 12)
	row.add_child(tag_label)
	var made := _make_bar(color)
	row.add_child(made[0])
	parent.add_child(row)
	return made

func _build_hud():
	# Player frame (top-left): name + HP/MP/SP bars + combat status.
	var player_frame := PanelContainer.new()
	player_frame.add_theme_stylebox_override("panel", _panel_style(Color(0.35, 0.65, 0.95)))
	player_frame.set_anchors_preset(Control.PRESET_TOP_LEFT)
	player_frame.offset_left = 16
	player_frame.offset_top = 16
	player_frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(player_frame)
	var pv := VBoxContainer.new()
	pv.add_theme_constant_override("separation", 3)
	player_frame.add_child(pv)
	player_name_label = Label.new()
	player_name_label.add_theme_font_size_override("font_size", 15)
	pv.add_child(player_name_label)
	var hp_made := _make_resource_row(pv, "HP", Color(0.85, 0.25, 0.28))
	health_bar = hp_made[0]; health_value_label = hp_made[1]
	var mp_made := _make_resource_row(pv, "MP", Color(0.30, 0.55, 0.95))
	mana_bar = mp_made[0]; mana_value_label = mp_made[1]
	var sp_made := _make_resource_row(pv, "SP", Color(0.95, 0.80, 0.25))
	stamina_bar = sp_made[0]; stamina_value_label = sp_made[1]
	combat_status_label = RichTextLabel.new()
	combat_status_label.bbcode_enabled = true
	combat_status_label.fit_content = true
	combat_status_label.scroll_active = false
	combat_status_label.custom_minimum_size = Vector2(230, 38)
	combat_status_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	pv.add_child(combat_status_label)

	# Target frame (top-center): only visible when a target is selected.
	target_frame = PanelContainer.new()
	target_frame.add_theme_stylebox_override("panel", _panel_style(Color(0.85, 0.35, 0.35)))
	target_frame.set_anchors_preset(Control.PRESET_CENTER_TOP)
	target_frame.grow_horizontal = Control.GROW_DIRECTION_BOTH
	target_frame.offset_top = 18
	target_frame.visible = false
	target_frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(target_frame)
	var tv := VBoxContainer.new()
	tv.add_theme_constant_override("separation", 3)
	target_frame.add_child(tv)
	target_name_label = Label.new()
	target_name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	target_name_label.add_theme_font_size_override("font_size", 14)
	tv.add_child(target_name_label)
	var t_made := _make_bar(Color(0.85, 0.30, 0.30))
	target_health_bar = t_made[0]; target_health_value_label = t_made[1]
	target_health_bar.custom_minimum_size = Vector2(230, 16)
	tv.add_child(target_health_bar)

	# Crosshair (screen center) — recolors when you look at an enemy.
	crosshair = Control.new()
	crosshair.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	crosshair.offset_left = -16
	crosshair.offset_top = -16
	crosshair.offset_right = 16
	crosshair.offset_bottom = 16
	crosshair.mouse_filter = Control.MOUSE_FILTER_IGNORE
	crosshair.draw.connect(_draw_crosshair)
	add_child(crosshair)

	# Ability bar + hint (bottom-center).
	var bottom := VBoxContainer.new()
	bottom.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	bottom.grow_horizontal = Control.GROW_DIRECTION_BOTH
	bottom.grow_vertical = Control.GROW_DIRECTION_BEGIN
	bottom.offset_bottom = -14
	bottom.alignment = BoxContainer.ALIGNMENT_CENTER
	bottom.add_theme_constant_override("separation", 4)
	bottom.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(bottom)
	hint_label = Label.new()
	hint_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	hint_label.add_theme_font_size_override("font_size", 11)
	hint_label.add_theme_color_override("font_color", Color(0.75, 0.78, 0.85))
	hint_label.text = "Tab/Click: target   •   Q: auto-attack   •   1-8: abilities   •   E: interact   •   F3: debug"
	bottom.add_child(hint_label)
	ability_bar = HBoxContainer.new()
	ability_bar.alignment = BoxContainer.ALIGNMENT_CENTER
	ability_bar.add_theme_constant_override("separation", 4)
	bottom.add_child(ability_bar)

	# Combat log (bottom-left).
	var log_panel := PanelContainer.new()
	log_panel.add_theme_stylebox_override("panel", _panel_style(Color(0.45, 0.5, 0.6)))
	log_panel.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	log_panel.grow_vertical = Control.GROW_DIRECTION_BEGIN
	log_panel.offset_left = 16
	log_panel.offset_bottom = -88  # sit above the ability bar instead of overlapping it
	log_panel.custom_minimum_size = Vector2(420, 0)
	log_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(log_panel)
	combat_log_label = Label.new()
	combat_log_label.add_theme_font_size_override("font_size", 12)
	combat_log_label.text = "Combat log:"
	log_panel.add_child(combat_log_label)

	# Debug panel (top-right, hidden by default, toggle with F3).
	debug_panel = PanelContainer.new()
	debug_panel.add_theme_stylebox_override("panel", _panel_style(Color(0.4, 0.45, 0.55)))
	debug_panel.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	debug_panel.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	debug_panel.offset_right = -16
	debug_panel.offset_top = 16
	debug_panel.custom_minimum_size = Vector2(520, 0)
	debug_panel.visible = false
	debug_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(debug_panel)
	var dv := VBoxContainer.new()
	debug_panel.add_child(dv)
	info_label = Label.new()
	info_label.add_theme_font_size_override("font_size", 11)
	dv.add_child(info_label)
	summary_label = Label.new()
	summary_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	summary_label.add_theme_font_size_override("font_size", 11)
	dv.add_child(summary_label)
	target_label = Label.new()
	target_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	target_label.add_theme_font_size_override("font_size", 11)
	dv.add_child(target_label)
	interaction_label = Label.new()
	interaction_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	interaction_label.add_theme_font_size_override("font_size", 11)
	dv.add_child(interaction_label)
	transfer_label = Label.new()
	transfer_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	transfer_label.add_theme_font_size_override("font_size", 11)
	dv.add_child(transfer_label)

func _draw_crosshair():
	var c := crosshair.size * 0.5
	var col := _crosshair_color
	var gap := 4.0
	var length := 10.0
	var w := 2.0
	crosshair.draw_line(c + Vector2(-length, 0), c + Vector2(-gap, 0), col, w)
	crosshair.draw_line(c + Vector2(gap, 0), c + Vector2(length, 0), col, w)
	crosshair.draw_line(c + Vector2(0, -length), c + Vector2(0, -gap), col, w)
	crosshair.draw_line(c + Vector2(0, gap), c + Vector2(0, length), col, w)
	crosshair.draw_circle(c, 1.5, col)

func _self_entity() -> Dictionary:
	for entity in replicated_entities:
		if entity is Dictionary and bool(entity.get("is_self", false)):
			return entity
	return {}

func _update_look_at():
	if camera == null or sub_viewport == null:
		return
	var looking := false
	var enemy := false
	var center := Vector2(sub_viewport.size) * 0.5
	var from := camera.project_ray_origin(center)
	var to := from + camera.project_ray_normal(center) * ENTITY_SELECTION_DISTANCE
	var query := PhysicsRayQueryParameters3D.create(from, to)
	query.collide_with_areas = false
	query.collide_with_bodies = true
	var result := player_body.get_world_3d().direct_space_state.intersect_ray(query)
	if not result.is_empty():
		var collider = result.get("collider")
		if collider != null and collider is Node3D and int(collider.get_meta("entity_id", 0)) > 0:
			looking = true
			var ent: Dictionary = collider.get_meta("entity", {})
			enemy = bool(ent.get("is_enemy", false))
			_looked_entity_id = int(collider.get_meta("entity_id", 0))
	_looking_at_entity = looking
	_looking_at_enemy = enemy
	var new_col: Color
	if enemy:
		new_col = Color(1.0, 0.3, 0.3, 1.0)
	elif looking:
		new_col = Color(1.0, 0.85, 0.35, 1.0)
	else:
		new_col = Color(1.0, 1.0, 1.0, 0.7)
	if new_col != _crosshair_color:
		_crosshair_color = new_col
		if crosshair:
			crosshair.queue_redraw()

func apply_world_state(payload: Dictionary, world: Dictionary, time_info: Dictionary):
	current_payload = payload.duplicate(true)
	selected_world = world.duplicate(true)
	world_time = time_info.duplicate(true)
	# Only reposition player on initial root_info, not on periodic updates.
	if not _has_spawned:
		# Don't compute offset from root_info — it may have stale/zero position.
		# Instead, offset will be computed from the first entity_snapshot with is_self.
		player_body.global_position = Vector3(0.0, 2.0, 0.0)
	camera.current = true
	visible = true
	_capture_mouse()
	_rebuild_ability_bar()
	_update_labels()

func update_state(payload: Dictionary):
	current_payload = payload.duplicate(true)
	_rebuild_ability_bar()
	_update_labels()

func set_world_time(time_info: Dictionary):
	world_time = time_info.duplicate(true)
	_update_labels()

func set_zone_transfer(payload: Dictionary):
	current_payload["zone_transfer"] = payload.duplicate(true)
	_update_labels()

func set_target_description(target: Dictionary):
	server_target_description = target.duplicate(true)
	_update_labels()

func set_entities(entities: Array):
	replicated_entities = entities.duplicate(true)
	_sync_entity_markers()
	_update_labels()

func on_server_selection(tgt_sim_id: int, _char_index: int):
	_pending_target_mob_id = 0
	if tgt_sim_id == 0:
		_pending_target_sim_id = 0
		server_target_description = {}
		_highlight_entity("")
		_update_labels()
		return
	_pending_target_sim_id = tgt_sim_id
	for entity in replicated_entities:
		if int(entity.get("sim_id", 0)) == tgt_sim_id:
			server_target_description = entity.duplicate(true)
			_highlight_entity(_entity_key(entity))
			_pending_target_sim_id = 0
			_update_labels()
			return
	server_target_description = {"name": "Target (sim %d)" % tgt_sim_id}
	_update_labels()

func on_server_selection_by_mob(target_id: int, _char_index: int):
	_pending_target_sim_id = 0
	if target_id == 0:
		_pending_target_mob_id = 0
		server_target_description = {}
		_highlight_entity("")
		_update_labels()
		return
	_pending_target_mob_id = target_id
	for entity in replicated_entities:
		if int(entity.get("id", 0)) == target_id:
			server_target_description = entity.duplicate(true)
			_highlight_entity(_entity_key(entity))
			_pending_target_mob_id = 0
			_update_labels()
			return
	# Don't overwrite if setSelection already provided a good description
	if not server_target_description.is_empty():
		return
	server_target_description = {"name": "Target (mob %d)" % target_id}
	_update_labels()

func _highlight_entity(key: String):
	# Remove highlight from previous target
	if not _highlighted_entity_key.is_empty() and replicated_entity_nodes.has(_highlighted_entity_key):
		var prev: StaticBody3D = replicated_entity_nodes[_highlighted_entity_key]
		if is_instance_valid(prev):
			var prev_entity: Dictionary = prev.get_meta("entity", {})
			var mesh: MeshInstance3D = prev.get_meta("mesh")
			if mesh:
				var mat := StandardMaterial3D.new()
				mat.albedo_color = _entity_color(prev_entity)
				mesh.material_override = mat
	_highlighted_entity_key = key
	# Apply highlight to new target
	if not key.is_empty() and replicated_entity_nodes.has(key):
		var body: StaticBody3D = replicated_entity_nodes[key]
		if is_instance_valid(body):
			var mesh: MeshInstance3D = body.get_meta("mesh")
			if mesh:
				var mat := StandardMaterial3D.new()
				mat.albedo_color = Color(1.0, 1.0, 0.2, 1.0)  # bright yellow highlight
				mat.emission_enabled = true
				mat.emission = Color(1.0, 1.0, 0.2, 1.0)
				mat.emission_energy_multiplier = 0.5
				mesh.material_override = mat

func append_game_text(message: String):
	_push_log(message)

func append_text_messages(messages: Array):
	for message in messages:
		_push_log(str(message))

func _push_log(message: String):
	var clean := message.strip_edges()
	if clean.is_empty():
		return
	combat_log.append(clean)
	if combat_log.size() > 8:
		combat_log = combat_log.slice(combat_log.size() - 8, combat_log.size())
	combat_log_label.text = "Combat / server log:\n" + "\n".join(combat_log)

func _capture_mouse():
	Input.set_mouse_mode(Input.MOUSE_MODE_CAPTURED)
	mouse_captured = true

func _release_mouse():
	Input.set_mouse_mode(Input.MOUSE_MODE_VISIBLE)
	mouse_captured = false

func _payload_position() -> Vector3:
	var pos: Variant = current_payload.get("position", [0.0, 0.0, 0.0])
	if pos is Array and pos.size() >= 3:
		return Vector3(float(pos[0]), float(pos[2]) + 1.0, float(-pos[1]))
	return Vector3(0.0, 1.0, 0.0)

func _player_char_info() -> Dictionary:
	var char_infos: Array = current_payload.get("char_infos", [])
	if char_infos.is_empty():
		return {}
	var first_entry = char_infos[0]
	if first_entry is Dictionary:
		return first_entry
	return {}

func _rapid_info() -> Dictionary:
	var info: Variant = _player_char_info().get("rapid_mob_info", {})
	if info is Dictionary:
		return info
	return {}

func _abilities() -> Array:
	var abilities: Variant = _player_char_info().get("abilities", [])
	if abilities is Array and not abilities.is_empty():
		return abilities.slice(0, min(abilities.size(), 8))
	var fallback: Array = []
	for ability_name in DEFAULT_ABILITY_NAMES:
		fallback.append({
			"name": ability_name,
			"rank": 1,
			"cooldown_active": false,
			"cooldown_seconds": 0,
			"source": "fallback",
		})
	return fallback

func _character_summary() -> String:
	var char_infos: Array = current_payload.get("char_infos", [])
	if char_infos.is_empty():
		return "No party data received"
	var bits: Array = []
	for entry in char_infos:
		if entry is Dictionary:
			bits.append("%s Lv%s %s" % [
				str(entry.get("name", "?")),
				str(entry.get("level", 1)),
				str(entry.get("pclass", entry.get("klass", "Unknown"))),
			])
	return ", ".join(bits)

func _set_bar(bar: ProgressBar, value: float, maximum: float, label: String, value_label: Label = null):
	bar.max_value = max(maximum, 1.0)
	bar.value = clamp(value, 0.0, bar.max_value)
	bar.tooltip_text = "%s %.0f / %.0f" % [label, bar.value, bar.max_value]
	if value_label:
		value_label.text = "%.0f / %.0f" % [bar.value, bar.max_value]

func _clear_npc_root():
	for child in npc_root.get_children():
		child.queue_free()
	replicated_entity_nodes.clear()

func _world_position_from_server(position_data) -> Vector3:
	if position_data is Array and position_data.size() >= 3:
		return Vector3(float(position_data[0]), float(position_data[2]), float(-position_data[1]))
	return Vector3.ZERO

func _server_to_godot(position_data) -> Vector3:
	"""Convert server position to Godot world position using fixed origin offset."""
	return _world_position_from_server(position_data) + _server_origin_offset

func _load_zone_art() -> void:
	# Load the real zone geometry into WorldRoot once we know the server spawn
	# offset, so terrain/buildings/props align with the server-driven player and
	# replicated entities. Replaces the greybox placeholder world.
	if _zone_loaded:
		return
	var world_root: Node3D = $SubViewportContainer/SubViewport/WorldRoot
	var zone := DEFAULT_ZONE
	var z = current_payload.get("zone", null)
	if z != null and str(z) != "":
		zone = str(z)
	var loader: Node3D = ZoneLoaderScript.new()
	loader.name = "ZoneArt"
	loader.position = _server_origin_offset
	world_root.add_child(loader)
	if not loader.build(zone, true):
		push_warning("Zone art unavailable for '%s'; keeping greybox world." % zone)
		loader.queue_free()
		return
	_zone_loaded = true
	for placeholder in ["FloorBody", "BoxA", "BoxB", "BoxC", "DirectionalLight3D"]:
		var n: Node = world_root.get_node_or_null(placeholder)
		if n != null:
			n.queue_free()
	print("[Godot] Loaded zone art '%s' at offset %s" % [zone, str(_server_origin_offset)])

func _ground_y(x: float, z: float, fallback: float) -> float:
	# Raycast down through the zone collision to find the ground at (x, z).
	# Falls back to the server-provided height if nothing is hit.
	var world := sub_viewport.find_world_3d()
	if world == null:
		return fallback
	var space := world.direct_space_state
	if space == null:
		return fallback
	var q := PhysicsRayQueryParameters3D.create(
		Vector3(x, fallback + 300.0, z), Vector3(x, fallback - 600.0, z))
	q.collide_with_areas = false
	var hit := space.intersect_ray(q)
	if hit and hit.has("position"):
		return float(hit.position.y)
	return fallback

func _godot_to_server_pos(godot_pos: Vector3) -> Array:
	"""Convert Godot position to server coordinates: server(x,y,z) = godot(x,-z,y)."""
	return [godot_pos.x, -godot_pos.z, godot_pos.y]

func _server_rotation_to_godot_y(rotation_data) -> float:
	"""Extract Y-axis rotation (yaw) from TGE axis-angle for Godot.
	TGE stores rotation as (axis_x, axis_y, axis_z, angle_radians).
	For yaw: axis is (0,0,+/-1) and angle is the rotation amount.
	Server Z-rotation = Godot Y-rotation (both are yaw)."""
	if not (rotation_data is Array) or rotation_data.size() < 4:
		return 0.0
	var axis_z: float = float(rotation_data[2])
	var angle_rad: float = float(rotation_data[3])
	# Reconstruct signed angle: axis_z sign indicates direction
	if absf(axis_z) < 0.001:
		return 0.0
	# Negate: server yaw is measured +X-from-+Y around Z-up; converting to
	# Godot's Y-up frame (where -Z is forward) flips the horizontal sense, so
	# a raw copy would mirror facing left<->right. Negating cancels the mirror.
	return -angle_rad * signf(axis_z)

func _spawn_placeholder_npcs():
	if npc_root.get_child_count() > 0:
		return
	var specs := [
		{"name": "Trainer Rowan", "position": Vector3(4, 0, -6), "color": Color(0.45, 0.82, 0.55, 1.0), "label": "visual placeholder trainer"},
		{"name": "Quartermaster Venn", "position": Vector3(-6, 0, -2), "color": Color(0.55, 0.62, 0.78, 1.0), "label": "visual placeholder vendor"},
		{"name": "Scout Ilya", "position": Vector3(9, 0, 5), "color": Color(0.78, 0.58, 0.32, 1.0), "label": "visual placeholder scout"},
	]
	for spec in specs:
		var body := StaticBody3D.new()
		body.name = spec["name"]
		body.position = spec["position"]

		var collider := CollisionShape3D.new()
		var shape := CapsuleShape3D.new()
		shape.radius = 0.55
		shape.height = 1.4
		collider.shape = shape
		body.add_child(collider)

		var mesh_instance := MeshInstance3D.new()
		var mesh := CapsuleMesh.new()
		mesh.radius = 0.55
		mesh.height = 1.4
		mesh_instance.mesh = mesh
		var mesh_material := StandardMaterial3D.new()
		mesh_material.albedo_color = spec["color"]
		mesh_instance.material_override = mesh_material
		body.add_child(mesh_instance)

		var label := Label3D.new()
		label.text = "%s (%s)" % [spec["name"], spec["label"]]
		label.position = Vector3(0, 1.6, 0)
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		body.add_child(label)

		npc_root.add_child(body)
		placeholder_npcs.append({
			"node": body,
			"mesh": mesh_instance,
			"label": label,
			"name": spec["name"],
		})

func _entity_key(entity: Dictionary) -> String:
	return str(entity.get("id", entity.get("sim_id", 0)))

func _entity_color(entity: Dictionary) -> Color:
	if bool(entity.get("attacking", false)):
		return Color(0.85, 0.35, 0.35, 1.0)
	if bool(entity.get("is_enemy", false)):
		return Color(0.78, 0.58, 0.32, 1.0)
	if bool(entity.get("is_player", false)):
		return Color(0.35, 0.65, 0.95, 1.0)
	return Color(0.55, 0.62, 0.78, 1.0)

func _entity_label_text(entity: Dictionary) -> String:
	var label_name := str(entity.get("public_name", entity.get("name", "Entity")))
	var health: float = float(entity.get("health", 0.0))
	var max_health: float = float(entity.get("max_health", 1.0))
	var health_pct := int(round((health / max(max_health, 1.0)) * 100.0))
	return "%s Lv%s %s [%d%%]" % [
		label_name,
		str(entity.get("level", "?")),
		str(entity.get("standing", entity.get("pclass", entity.get("race", "")))),
		health_pct,
	]

func _create_entity_marker(entity: Dictionary) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.name = str(entity.get("name", "Entity"))
	body.collision_layer = 1
	body.collision_mask = 1

	var collider := CollisionShape3D.new()
	var shape := CapsuleShape3D.new()
	shape.radius = 0.55
	shape.height = 1.4
	collider.shape = shape
	body.add_child(collider)

	var mesh_instance := MeshInstance3D.new()
	var mesh := CapsuleMesh.new()
	mesh.radius = 0.55
	mesh.height = 1.4
	mesh_instance.mesh = mesh
	body.add_child(mesh_instance)

	# Facing indicator (small cone pointing forward)
	var nose := MeshInstance3D.new()
	var cone := CylinderMesh.new()
	cone.top_radius = 0.0
	cone.bottom_radius = 0.2
	cone.height = 0.4
	nose.mesh = cone
	nose.position = Vector3(0, 0.6, -0.55)
	nose.rotation_degrees = Vector3(90, 0, 0)
	var nose_mat := StandardMaterial3D.new()
	nose_mat.albedo_color = Color(1.0, 1.0, 1.0, 0.9)
	nose.material_override = nose_mat
	body.add_child(nose)

	var label := Label3D.new()
	label.position = Vector3(0, 1.6, 0)
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	body.add_child(label)

	body.set_meta("mesh", mesh_instance)
	body.set_meta("nose", nose)
	body.set_meta("label", label)
	body.set_meta("entity_id", int(entity.get("id", 0)))
	_update_entity_marker(body, entity)
	npc_root.add_child(body)
	return body

func _update_entity_marker(body: StaticBody3D, entity: Dictionary):
	body.set_meta("entity", entity.duplicate(true))
	body.set_meta("entity_id", int(entity.get("id", 0)))
	var key := _entity_key(entity)
	var mesh_instance: MeshInstance3D = body.get_meta("mesh")
	# Preserve yellow highlight if this entity is the current target
	if key != _highlighted_entity_key:
		var mesh_material := StandardMaterial3D.new()
		mesh_material.albedo_color = _entity_color(entity)
		mesh_instance.material_override = mesh_material
	var label: Label3D = body.get_meta("label")
	label.text = _entity_label_text(entity)

func _sync_entity_markers():
	if replicated_entities.is_empty():
		return

	# Find self entity and reconcile player position with server
	for entity in replicated_entities:
		if entity is Dictionary and bool(entity.get("is_self", false)):
			var raw_pos = entity.get("position", [])
			# Compute spawn offset from first entity snapshot (more reliable than root_info)
			if not _has_spawned:
				_has_spawned = true
				var server_pos_raw := _world_position_from_server(raw_pos)
				_server_origin_offset = Vector3(0.0, 2.0, 0.0) - server_pos_raw
				player_body.global_position = Vector3(0.0, 2.0, 0.0)
				print("[Godot] SPAWN from entity snapshot: raw=%s  converted=%s  offset=%s" % [str(raw_pos), str(server_pos_raw), str(_server_origin_offset)])
				_load_zone_art()
				break
			var server_pos := _server_to_godot(raw_pos)
			if server_pos != Vector3.ZERO and _server_origin_offset != Vector3.ZERO:
				var current_pos := player_body.global_position
				var diff_xz := Vector2(server_pos.x - current_pos.x, server_pos.z - current_pos.z)
				var desync := diff_xz.length()
				if desync > 25.0:
					# Very large desync — snap to server position
					player_body.global_position.x = server_pos.x
					player_body.global_position.z = server_pos.z
				elif desync > 8.0:
					# Moderate desync — gently blend toward server (10% per sync tick)
					player_body.global_position.x = lerpf(current_pos.x, server_pos.x, 0.08)
					player_body.global_position.z = lerpf(current_pos.z, server_pos.z, 0.08)
				# else: within 8 units, TRUST client prediction. The server
				# snapshot always lags prediction by a few units (input latency +
				# snapshot interval), so a tight tolerance yanks the player back
				# every snapshot. That tight tolerance was the rubber-band.
			break

	var incoming_keys: Dictionary = {}
	var entity_list: Array = []
	for entity in replicated_entities:
		if not (entity is Dictionary):
			continue
		if bool(entity.get("is_self", false)):
			continue
		# Dead mobs disappear: skip them so their marker is freed below, and
		# drop them as the current target so the target frame/highlight clears.
		if bool(entity.get("dead", false)) or float(entity.get("health", 1.0)) <= 0.0:
			var dead_key := _entity_key(entity)
			if dead_key == _highlighted_entity_key:
				_highlight_entity("")
			if not server_target_description.is_empty() and _entity_key(server_target_description) == dead_key:
				server_target_description = {}
			continue
		entity_list.append(entity)

	for i in range(entity_list.size()):
		var entity_dict: Dictionary = entity_list[i]
		var key := _entity_key(entity_dict)
		incoming_keys[key] = true
		# Convert entity server position to absolute Godot world position, then drop
		# it onto the terrain/world collision so NPCs stand on the ground.
		var godot_pos := _server_to_godot(entity_dict.get("position", []))
		godot_pos.y = _ground_y(godot_pos.x, godot_pos.z, godot_pos.y) + ENTITY_CAPSULE_HALF_HEIGHT
		var is_new := false
		var body: StaticBody3D = replicated_entity_nodes.get(key)
		if body == null:
			is_new = true
			body = _create_entity_marker(entity_dict)
			replicated_entity_nodes[key] = body
		else:
			_update_entity_marker(body, entity_dict)
		# Set interpolation target; only snap position on first appearance
		body.set_meta("target_position", godot_pos)
		if is_new:
			body.position = godot_pos
		# Apply rotation from server (yaw only)
		var yaw := _server_rotation_to_godot_y(entity_dict.get("rotation", []))
		body.rotation.y = yaw

	for key in replicated_entity_nodes.keys():
		if incoming_keys.has(key):
			continue
		var old_body: Node = replicated_entity_nodes[key]
		if is_instance_valid(old_body):
			old_body.queue_free()
		replicated_entity_nodes.erase(key)

	# Resolve pending target highlight if entity just appeared in snapshot
	if _pending_target_sim_id != 0 or _pending_target_mob_id != 0:
		for entity_dict2 in entity_list:
			var matched := false
			if _pending_target_sim_id != 0 and int(entity_dict2.get("sim_id", 0)) == _pending_target_sim_id:
				matched = true
			elif _pending_target_mob_id != 0 and int(entity_dict2.get("id", 0)) == _pending_target_mob_id:
				matched = true
			if matched:
				server_target_description = entity_dict2.duplicate(true)
				_highlight_entity(_entity_key(entity_dict2))
				_pending_target_sim_id = 0
				_pending_target_mob_id = 0
				break

func _ability_signature() -> String:
	var names: Array = []
	for ability in _abilities():
		if ability is Dictionary:
			names.append("%s:%s:%s:%s" % [
				ability.get("name", ""),
				ability.get("rank", 0),
				ability.get("cooldown_active", false),
				ability.get("cooldown_seconds", 0),
			])
	return "|".join(names)

func _button_label(slot_index: int, ability: Dictionary) -> String:
	var name := str(ability.get("name", DEFAULT_ABILITY_NAMES[min(slot_index, DEFAULT_ABILITY_NAMES.size() - 1)]))
	var prefix := "%d: %s" % [slot_index + 1, name]
	var cooldown_seconds := int(ability.get("cooldown_seconds", 0))
	if bool(ability.get("cooldown_active", false)):
		prefix += " (%ds)" % max(cooldown_seconds, 1)
	return prefix

func _rebuild_ability_bar():
	if ability_bar == null:
		return
	var signature := _ability_signature()
	if signature == last_abilities_signature:
		return
	last_abilities_signature = signature
	for child in ability_bar.get_children():
		child.queue_free()
	var abilities := _abilities()
	for i in range(8):
		var button := Button.new()
		button.focus_mode = Control.FOCUS_NONE
		button.custom_minimum_size = Vector2(96, 44)
		button.clip_text = true
		var filled := i < abilities.size() and abilities[i] is Dictionary
		if filled:
			var ability: Dictionary = abilities[i]
			button.text = _button_label(i, ability)
			button.disabled = bool(ability.get("cooldown_active", false))
			button.tooltip_text = _ability_tooltip(ability)
		else:
			button.text = "%d" % [i + 1]
			button.disabled = true
		_style_ability_button(button, filled)
		button.pressed.connect(_on_ability_pressed.bind(i))
		ability_bar.add_child(button)

func _style_ability_button(button: Button, filled: bool):
	var normal := StyleBoxFlat.new()
	normal.bg_color = Color(0.13, 0.15, 0.19, 0.92) if filled else Color(0.08, 0.09, 0.11, 0.8)
	normal.border_color = Color(0.45, 0.62, 0.85) if filled else Color(0.22, 0.24, 0.28)
	normal.set_border_width_all(1)
	normal.set_corner_radius_all(4)
	var hover := normal.duplicate()
	hover.bg_color = Color(0.20, 0.24, 0.30, 0.95)
	button.add_theme_stylebox_override("normal", normal)
	button.add_theme_stylebox_override("hover", hover)
	button.add_theme_stylebox_override("pressed", hover)
	button.add_theme_stylebox_override("disabled", normal)
	button.add_theme_font_size_override("font_size", 12)
	button.add_theme_color_override("font_color", Color(0.92, 0.94, 0.98) if filled else Color(0.45, 0.48, 0.54))
	button.add_theme_color_override("font_disabled_color", Color(0.5, 0.54, 0.6) if filled else Color(0.35, 0.38, 0.43))

func _ability_tooltip(ability: Dictionary) -> String:
	var source := str(ability.get("source", "server"))
	var name := str(ability.get("name", "Ability"))
	var tooltip := "%s\nRank: %s\nSource: %s" % [name, str(ability.get("rank", 1)), source]
	if source == "server":
		tooltip += "\nUses the legacy server skill list from RootInfo."
	else:
		tooltip += "\nFallback only because no server skills were available."
	return tooltip

func _bridge_status_text() -> String:
	return "Bridge status: abilities, attack toggle, target cycling, interact, and click-to-target now go back to the legacy world server via PlayerAvatar.doCommand / targetEntity. Replicated entities are rendered from server snapshots and interpolated between updates for smoother motion."

func _update_labels():
	if health_bar == null:
		return  # HUD not built yet
	var char_info := _player_char_info()
	var rapid_info := _rapid_info()
	var world_name: String = str(selected_world.get("name", current_payload.get("world_name", "Unknown World")))
	var player_name: String = str(current_payload.get("player_name", "Unknown Player"))
	var guild_name: String = str(current_payload.get("guild_name", ""))
	var pos: Vector3 = player_body.global_position
	var time_text: String = "%02d:%02d" % [int(world_time.get("hour", 0)), int(world_time.get("minute", 0))]
	var autoattack: bool = bool(rapid_info.get("autoattack", false))

	# --- Player frame ---
	var char_name: String = str(char_info.get("name", player_name))
	var char_level: String = str(char_info.get("level", char_info.get("plevel", 1)))
	var char_class: String = str(char_info.get("pclass", "Unknown"))
	player_name_label.text = "%s   Lv%s %s" % [char_name, char_level, char_class]
	_set_bar(health_bar, float(rapid_info.get("health", 0.0)), float(rapid_info.get("maxhealth", 100.0)), "Health", health_value_label)
	_set_bar(mana_bar, float(rapid_info.get("mana", 0.0)), float(rapid_info.get("maxmana", 100.0)), "Mana", mana_value_label)
	_set_bar(stamina_bar, float(rapid_info.get("stamina", 0.0)), float(rapid_info.get("maxstamina", 100.0)), "Stamina", stamina_value_label)

	# --- Combat status (in-combat / auto-attack / looking-at) ---
	var self_ent := _self_entity()
	var has_target := not server_target_description.is_empty() or not str(rapid_info.get("tgt", "")).is_empty()
	var in_combat: bool = bool(self_ent.get("in_combat", false)) or bool(self_ent.get("attacking", false)) or (autoattack and has_target)
	var line1 := "[color=#ff5a5a]● IN COMBAT[/color]" if in_combat else "[color=#8a9099]○ Out of combat[/color]"
	var line2 := "[color=#5ad17a]● AUTO-ATTACK ON[/color]" if autoattack else "[color=#8a9099]○ Auto-attack OFF — press Q[/color]"
	var line3 := "\n[color=#ffcf5a]● Enemy in sight[/color]" if _looking_at_enemy else ""
	combat_status_label.text = line1 + "\n" + line2 + line3

	# --- Target frame ---
	if not server_target_description.is_empty():
		var t_name: String = str(server_target_description.get("public_name", server_target_description.get("name", "Unknown")))
		var t_level: String = str(server_target_description.get("plevel", server_target_description.get("level", "?")))
		var t_race: String = str(server_target_description.get("race", ""))
		var t_standing: String = str(server_target_description.get("standing", ""))
		var t_dead: bool = bool(server_target_description.get("dead", false))
		var t_health: float = float(server_target_description.get("health", -1.0))
		var t_max_health: float = float(server_target_description.get("max_health", server_target_description.get("maxhealth", 1.0)))
		var standing_txt := (" (%s)" % t_standing) if not t_standing.is_empty() else ""
		target_name_label.text = "%s   Lv%s %s%s%s" % [t_name, t_level, t_race, standing_txt, "  [DEAD]" if t_dead else ""]
		if t_health >= 0.0:
			_set_bar(target_health_bar, t_health, t_max_health, "Target", target_health_value_label)
			target_health_bar.visible = true
		else:
			target_health_bar.visible = false
		target_frame.visible = true
	else:
		var server_target_name: String = str(rapid_info.get("tgt", ""))
		if not server_target_name.is_empty():
			target_name_label.text = server_target_name
			var sth: float = float(rapid_info.get("tgthealth", -1.0))
			if sth >= 0.0:
				_set_bar(target_health_bar, sth * 100.0, 100.0, "Target", target_health_value_label)
				target_health_bar.visible = true
			else:
				target_health_bar.visible = false
			target_frame.visible = true
		else:
			target_frame.visible = false

	# --- Debug panel (toggle F3) ---
	if _debug_visible:
		var server_abilities: Variant = char_info.get("abilities", [])
		var ability_source_text: String = "server skills" if server_abilities is Array and not server_abilities.is_empty() else "fallback placeholders"
		var entity_count: int = max(replicated_entities.size() - 1, 0)
		info_label.text = "Greybox Test World\nWorld: %s   Time: %s   Player: %s" % [world_name, time_text, player_name]
		summary_label.text = "Guild: %s\nParty: %s\nAbility source: %s\nReplicated entities: %d\nPosition: (%.1f, %.1f, %.1f)   Grounded: %s   Paused: %s" % [
			guild_name if not guild_name.is_empty() else "<none>",
			_character_summary(),
			ability_source_text,
			entity_count,
			pos.x, pos.y, pos.z,
			"yes" if player_body.is_on_floor() else "no",
			"yes" if bool(current_payload.get("paused", false)) else "no",
		]
		target_label.text = "Looking at entity id: %d (enemy=%s)" % [_looked_entity_id if _looking_at_entity else 0, str(_looking_at_enemy)]
		interaction_label.text = interaction_message
		var transfer: Variant = current_payload.get("zone_transfer", {})
		if transfer is Dictionary and not transfer.is_empty():
			transfer_label.text = "Zone handoff: port %s, party %s" % [str(transfer.get("zone_port", "?")), str(transfer.get("party", []))]
		else:
			transfer_label.text = _bridge_status_text()

func _request_server_command(command_type: String, payload: Dictionary = {}):
	command_requested.emit(command_type, payload)

func _send_interact_command():
	interaction_message = "Sent INTERACT to the legacy world server."
	_request_server_command("interact")

func _cycle_target():
	interaction_message = "Sent CYCLETARGET to the legacy world server."
	_request_server_command("cycle_target")

func _toggle_autoattack():
	interaction_message = "Sent ATTACK toggle to the legacy world server."
	_request_server_command("attack_toggle")

func _activate_ability(slot_index: int):
	var abilities := _abilities()
	if slot_index < 0 or slot_index >= abilities.size():
		interaction_message = "That ability slot is empty."
		return
	var ability: Dictionary = abilities[slot_index]
	var ability_name := str(ability.get("name", "Ability"))
	if str(ability.get("source", "server")) != "server":
		interaction_message = "%s is only a fallback placeholder because no server skill data was available." % ability_name
		return
	interaction_message = "Sent SKILL %s to the legacy world server." % ability_name
	_request_server_command("use_ability", {"ability_name": ability_name})

func _target_entity_from_click(screen_position: Vector2) -> bool:
	if camera == null:
		return false
	var from := camera.project_ray_origin(screen_position)
	var to := from + camera.project_ray_normal(screen_position) * ENTITY_SELECTION_DISTANCE
	var query := PhysicsRayQueryParameters3D.create(from, to)
	query.collide_with_areas = false
	query.collide_with_bodies = true
	var result := player_body.get_world_3d().direct_space_state.intersect_ray(query)
	if result.is_empty():
		return false
	var collider = result.get("collider")
	if collider == null or not (collider is Node3D):
		return false
	var entity_id := int(collider.get_meta("entity_id", 0))
	if entity_id <= 0:
		return false
	var entity: Dictionary = collider.get_meta("entity", {})
	interaction_message = "Targeted %s on the legacy world server." % str(entity.get("public_name", entity.get("name", "entity")))
	_request_server_command("target_entity", {"entity_id": entity_id})
	return true

func _on_ability_pressed(slot_index: int):
	_activate_ability(slot_index)

func _input(event):
	if not visible:
		return
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		var selected := _target_entity_from_click(event.position)
		_capture_mouse()
		if selected:
			_update_labels()
	elif event.is_action_pressed("ui_cancel"):
		_release_mouse()
	elif event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_SPACE:
				jump_requested = true
			KEY_E:
				_send_interact_command()
			KEY_Q:
				_toggle_autoattack()
			KEY_TAB:
				_cycle_target()
			KEY_1, KEY_KP_1:
				_activate_ability(0)
			KEY_2, KEY_KP_2:
				_activate_ability(1)
			KEY_3, KEY_KP_3:
				_activate_ability(2)
			KEY_4, KEY_KP_4:
				_activate_ability(3)
			KEY_5, KEY_KP_5:
				_activate_ability(4)
			KEY_6, KEY_KP_6:
				_activate_ability(5)
			KEY_7, KEY_KP_7:
				_activate_ability(6)
			KEY_8, KEY_KP_8:
				_activate_ability(7)
			KEY_F3:
				_debug_visible = not _debug_visible
				if debug_panel:
					debug_panel.visible = _debug_visible
				_update_labels()
	elif event is InputEventMouseMotion and mouse_captured:
		player_body.rotate_y(-event.relative.x * LOOK_SENSITIVITY)
		camera_pitch.rotate_x(-event.relative.y * LOOK_SENSITIVITY)
		camera_pitch.rotation.x = clamp(camera_pitch.rotation.x, deg_to_rad(-70), deg_to_rad(70))

func _physics_process(delta):
	if not visible:
		return
	# Gather movement inputs
	var input_vec := Vector2.ZERO
	if Input.is_key_pressed(KEY_A):
		input_vec.x -= 1.0
	if Input.is_key_pressed(KEY_D):
		input_vec.x += 1.0
	if Input.is_key_pressed(KEY_W):
		input_vec.y += 1.0
	if Input.is_key_pressed(KEY_S):
		input_vec.y -= 1.0

	# Local prediction: move CharacterBody3D so movement feels responsive
	var basis: Basis = player_body.global_transform.basis
	var move_dir: Vector3 = (basis.x * input_vec.x) + (-basis.z * input_vec.y)
	if move_dir.length() > 1.0:
		move_dir = move_dir.normalized()
	velocity.x = move_dir.x * MOVE_SPEED
	velocity.z = move_dir.z * MOVE_SPEED
	if player_body.is_on_floor():
		if jump_requested:
			velocity.y = JUMP_VELOCITY
		else:
			velocity.y = 0.0
	else:
		velocity.y -= GRAVITY * delta
	jump_requested = false
	player_body.velocity = velocity
	player_body.move_and_slide()
	# Safety net: teleport back above the platform if player falls
	if player_body.global_position.y < -50.0:
		player_body.global_position = Vector3(player_body.global_position.x, 5.0, player_body.global_position.z)
		velocity = Vector3.ZERO

	# Send movement inputs to server periodically
	_input_sync_timer += delta
	if _input_sync_timer >= INPUT_SYNC_INTERVAL:
		_input_sync_timer = 0.0
		# Convert facing direction to server coords for the server movement sim
		var forward_dir := -basis.z  # Godot forward is -Z
		var server_forward := _godot_to_server_pos(forward_dir)
		var input_state := {
			"move_x": input_vec.x,
			"move_y": input_vec.y,
			"forward": server_forward,
			"jump": jump_requested,
		}
		if input_state != _last_sent_input:
			_last_sent_input = input_state.duplicate()
			_request_server_command("player_input", input_state)

	# Interpolate replicated entity positions toward server targets
	for body in replicated_entity_nodes.values():
		if body == null or not is_instance_valid(body):
			continue
		var target_position: Vector3 = body.get_meta("target_position", body.position)
		body.position = body.position.lerp(target_position, clamp(delta * ENTITY_INTERPOLATION_SPEED, 0.0, 1.0))

	_update_look_at()
	_update_labels()
