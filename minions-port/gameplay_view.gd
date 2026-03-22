extends Control

signal command_requested(command_type: String, payload: Dictionary)

const MOVE_SPEED := 8.0
const LOOK_SENSITIVITY := 0.003
const JUMP_VELOCITY := 7.0
const GRAVITY := 20.0
const DEFAULT_ABILITY_NAMES := ["Attack", "Kick", "Block", "Taunt", "Shout", "Guard", "Heal", "Sprint"]

var world_time := {"hour": 0, "minute": 0}
var current_payload: Dictionary = {}
var selected_world: Dictionary = {}
var velocity := Vector3.ZERO
var mouse_captured := false
var jump_requested := false
var interaction_message := ""
var placeholder_npcs: Array = []
var replicated_entities: Array = []
var last_abilities_signature := ""
var server_target_description: Dictionary = {}
var combat_log: Array = []

@onready var npc_root: Node3D = $SubViewportContainer/SubViewport/WorldRoot/NpcRoot
@onready var info_label: Label = $HUDMargin/HUDVBox/InfoLabel
@onready var summary_label: Label = $HUDMargin/HUDVBox/SummaryLabel
@onready var target_label: Label = $HUDMargin/HUDVBox/TargetLabel
@onready var health_bar: ProgressBar = $HUDMargin/HUDVBox/HealthBar
@onready var mana_bar: ProgressBar = $HUDMargin/HUDVBox/ManaBar
@onready var stamina_bar: ProgressBar = $HUDMargin/HUDVBox/StaminaBar
@onready var ability_bar: HBoxContainer = $HUDMargin/HUDVBox/AbilityBar
@onready var interaction_label: Label = $HUDMargin/HUDVBox/InteractionLabel
@onready var transfer_label: Label = $HUDMargin/HUDVBox/TransferLabel
@onready var combat_log_label: Label = $HUDMargin/HUDVBox/CombatLogLabel
@onready var player_body: CharacterBody3D = $SubViewportContainer/SubViewport/WorldRoot/PlayerBody
@onready var camera_pitch: Node3D = $SubViewportContainer/SubViewport/WorldRoot/PlayerBody/CameraYaw/CameraPitch
@onready var camera: Camera3D = $SubViewportContainer/SubViewport/WorldRoot/PlayerBody/CameraYaw/CameraPitch/Camera3D

func _ready():
	set_process_input(true)
	_spawn_placeholder_npcs()
	_rebuild_ability_bar()
	_update_labels()

func apply_world_state(payload: Dictionary, world: Dictionary, time_info: Dictionary):
	current_payload = payload.duplicate(true)
	selected_world = world.duplicate(true)
	world_time = time_info.duplicate(true)
	var spawn_position: Vector3 = _payload_position()
	player_body.global_position = Vector3(spawn_position.x, max(spawn_position.y, 2.0), spawn_position.z)
	camera.current = true
	visible = true
	_capture_mouse()
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
	_rebuild_entity_markers()
	_update_labels()

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
	var pos = current_payload.get("position", [0.0, 0.0, 0.0])
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
	var info = _player_char_info().get("rapid_mob_info", {})
	if info is Dictionary:
		return info
	return {}

func _abilities() -> Array:
	var abilities = _player_char_info().get("abilities", [])
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

func _set_bar(bar: ProgressBar, value: float, maximum: float, label: String):
	bar.max_value = max(maximum, 1.0)
	bar.value = clamp(value, 0.0, bar.max_value)
	bar.show_percentage = true
	bar.tooltip_text = "%s %.0f / %.0f" % [label, bar.value, bar.max_value]

func _clear_npc_root():
	for child in npc_root.get_children():
		child.queue_free()

func _world_position_from_server(position_data) -> Vector3:
	if position_data is Array and position_data.size() >= 3:
		return Vector3(float(position_data[0]), float(position_data[2]), float(-position_data[1]))
	return Vector3.ZERO

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


func _rebuild_entity_markers():
	_clear_npc_root()
	if replicated_entities.is_empty():
		_spawn_placeholder_npcs()
		return
	for entity in replicated_entities:
		if not (entity is Dictionary):
			continue
		if bool(entity.get("is_self", false)):
			continue
		var body := StaticBody3D.new()
		body.name = str(entity.get("name", "Entity"))
		body.position = _world_position_from_server(entity.get("position", []))

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
		if bool(entity.get("attacking", false)):
			mesh_material.albedo_color = Color(0.85, 0.35, 0.35, 1.0)
		elif bool(entity.get("is_enemy", false)):
			mesh_material.albedo_color = Color(0.78, 0.58, 0.32, 1.0)
		elif bool(entity.get("is_player", false)):
			mesh_material.albedo_color = Color(0.35, 0.65, 0.95, 1.0)
		else:
			mesh_material.albedo_color = Color(0.55, 0.62, 0.78, 1.0)
		mesh_instance.material_override = mesh_material
		body.add_child(mesh_instance)

		var label := Label3D.new()
		var label_name := str(entity.get("public_name", entity.get("name", "Entity")))
		label.text = "%s Lv%s %s" % [label_name, str(entity.get("level", "?")), str(entity.get("pclass", entity.get("race", "")))]
		label.position = Vector3(0, 1.6, 0)
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		body.add_child(label)

		npc_root.add_child(body)
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
		button.custom_minimum_size = Vector2(120, 48)
		if i < abilities.size() and abilities[i] is Dictionary:
			var ability: Dictionary = abilities[i]
			button.text = _button_label(i, ability)
			button.disabled = bool(ability.get("cooldown_active", false))
			button.tooltip_text = _ability_tooltip(ability)
		else:
			button.text = "%d: -" % [i + 1]
			button.disabled = true
		button.pressed.connect(_on_ability_pressed.bind(i))
		ability_bar.add_child(button)

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
	return "Bridge status: abilities, attack toggle, target cycling, and interact now go back to the legacy world server via PlayerAvatar.doCommand. NPC aggro/position/rotation/combat are server-authoritative in MoM, but this Godot bridge still lacks full zone/sim replication for rendering those entities live."

func _update_labels():
	var char_info := _player_char_info()
	var rapid_info := _rapid_info()
	var world_name := str(selected_world.get("name", current_payload.get("world_name", "Unknown World")))
	var player_name := str(current_payload.get("player_name", "Unknown Player"))
	var guild_name := str(current_payload.get("guild_name", ""))
	var pos: Vector3 = player_body.global_position
	var time_text := "%02d:%02d" % [int(world_time.get("hour", 0)), int(world_time.get("minute", 0))]
	var paused_text := "yes" if bool(current_payload.get("paused", false)) else "no"
	var grounded_text := "yes" if player_body.is_on_floor() else "no"
	var autoattack_text := "on" if bool(rapid_info.get("autoattack", false)) else "off"
	var server_abilities = _player_char_info().get("abilities", [])
	var ability_source_text := "server skills" if server_abilities is Array and not server_abilities.is_empty() else "fallback placeholders"
	var entity_count := max(replicated_entities.size() - 1, 0)
	info_label.text = "Greybox Test World\nWorld: %s\nPlayer: %s\nTime: %s" % [world_name, player_name, time_text]
	summary_label.text = "Guild: %s\nParty: %s\nClass: %s\nAbility source: %s\nAuto-attack: %s\nReplicated entities: %d\nSpawn position: (%.1f, %.1f, %.1f)\nPaused: %s\nGrounded: %s\nWASD move, Space jumps, Tab cycles server targets, Q toggles server auto-attack, 1-8 uses server abilities, E interacts, left click captures mouse, Esc releases cursor." % [
		guild_name if not guild_name.is_empty() else "<none>",
		_character_summary(),
		str(char_info.get("pclass", "Unknown")),
		ability_source_text,
		autoattack_text,
		entity_count,
		pos.x,
		pos.y,
		pos.z,
		paused_text,
		grounded_text,
	]
	_set_bar(health_bar, float(rapid_info.get("health", 0.0)), float(rapid_info.get("maxhealth", 100.0)), "Health")
	_set_bar(mana_bar, float(rapid_info.get("mana", 0.0)), float(rapid_info.get("maxmana", 100.0)), "Mana")
	_set_bar(stamina_bar, float(rapid_info.get("stamina", 0.0)), float(rapid_info.get("maxstamina", 100.0)), "Stamina")
	var server_target_name := str(rapid_info.get("tgt", ""))
	var server_target_health: float = float(rapid_info.get("tgthealth", -1.0))
	if not server_target_description.is_empty():
		target_label.text = "Server target: %s Lv%s %s | %s" % [
			str(server_target_description.get("name", "Unknown")),
			str(server_target_description.get("plevel", "?")),
			str(server_target_description.get("race", "Unknown")),
			str(server_target_description.get("standing", "")),
		]
	elif not server_target_name.is_empty():
		target_label.text = "Server target: %s (%.0f%% health)" % [server_target_name, server_target_health * 100.0]
	else:
		target_label.text = "No current server target"
	interaction_label.text = "Replicated entities are rendered from the MoM server snapshot when available; otherwise greybox placeholders are shown.\n%s" % interaction_message
	var transfer = current_payload.get("zone_transfer", {})
	if transfer is Dictionary and not transfer.is_empty():
		transfer_label.text = "Zone handoff prepared: zone port %s, party %s\n%s" % [
			str(transfer.get("zone_port", "?")),
			str(transfer.get("party", [])),
			_bridge_status_text(),
		]
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

func _on_ability_pressed(slot_index: int):
	_activate_ability(slot_index)

func _input(event):
	if not visible:
		return
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		_capture_mouse()
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
	elif event is InputEventMouseMotion and mouse_captured:
		player_body.rotate_y(-event.relative.x * LOOK_SENSITIVITY)
		camera_pitch.rotate_x(-event.relative.y * LOOK_SENSITIVITY)
		camera_pitch.rotation.x = clamp(camera_pitch.rotation.x, deg_to_rad(-70), deg_to_rad(70))

func _physics_process(delta):
	if not visible:
		return
	var input_vec := Vector2.ZERO
	if Input.is_key_pressed(KEY_A):
		input_vec.x -= 1.0
	if Input.is_key_pressed(KEY_D):
		input_vec.x += 1.0
	if Input.is_key_pressed(KEY_W):
		input_vec.y += 1.0
	if Input.is_key_pressed(KEY_S):
		input_vec.y -= 1.0
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
	_update_labels()
