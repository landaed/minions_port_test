extends Control

const MOVE_SPEED := 8.0
const LOOK_SENSITIVITY := 0.003
const JUMP_VELOCITY := 7.0
const GRAVITY := 20.0
const NPC_INTERACT_RANGE := 5.0
const DEFAULT_ABILITY_NAMES := ["Attack", "Kick", "Block", "Taunt", "Shout", "Guard", "Heal", "Sprint"]

var world_time := {"hour": 0, "minute": 0}
var current_payload: Dictionary = {}
var selected_world: Dictionary = {}
var velocity := Vector3.ZERO
var mouse_captured := false
var jump_requested := false
var interaction_message := ""
var placeholder_npcs: Array = []
var nearest_npc_index := -1
var current_target_index := -1
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
	var position: Vector3 = _payload_position()
	player_body.global_position = Vector3(position.x, max(position.y, 2.0), position.z)
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
	if combat_log.size() > 6:
		combat_log = combat_log.slice(combat_log.size() - 6, combat_log.size())
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
		return abilities
	var fallback: Array = []
	for i in range(DEFAULT_ABILITY_NAMES.size()):
		fallback.append({
			"name": DEFAULT_ABILITY_NAMES[i],
			"rank": 1,
			"cooldown_active": false,
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

func _spawn_placeholder_npcs():
	if npc_root.get_child_count() > 0:
		return
	var specs := [
		{"name": "Trainer Rowan", "position": Vector3(4, 0, -6), "dialogue": "Placeholder trainer: movement and camera work; next we wire in real NPC replication."},
		{"name": "Quartermaster Venn", "position": Vector3(-6, 0, -2), "dialogue": "Placeholder vendor: next step is server-backed inventory and interaction windows."},
		{"name": "Scout Ilya", "position": Vector3(9, 0, 5), "dialogue": "Placeholder scout: once zone data exists, this should become a real replicated spawn."},
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
		mesh.mid_height = 1.4
		mesh_instance.mesh = mesh
		var material := StandardMaterial3D.new()
		material.albedo_color = Color(0.55, 0.62, 0.78, 1.0)
		mesh_instance.material_override = material
		body.add_child(mesh_instance)

		var label := Label3D.new()
		label.text = spec["name"]
		label.position = Vector3(0, 1.6, 0)
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		body.add_child(label)

		npc_root.add_child(body)
		placeholder_npcs.append({
			"node": body,
			"mesh": mesh_instance,
			"label": label,
			"dialogue": spec["dialogue"],
			"name": spec["name"],
			"health": 100.0,
			"max_health": 100.0,
		})

func _ability_signature() -> String:
	var names: Array = []
	for ability in _abilities():
		if ability is Dictionary:
			names.append("%s:%s:%s" % [ability.get("name", ""), ability.get("rank", 0), ability.get("cooldown_active", false)])
	return "|".join(names)

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
			button.text = "%d: %s" % [i + 1, str(ability.get("name", DEFAULT_ABILITY_NAMES[i]))]
			button.disabled = bool(ability.get("cooldown_active", false))
		else:
			button.text = "%d: -" % [i + 1]
			button.disabled = true
		button.pressed.connect(_on_ability_pressed.bind(i))
		ability_bar.add_child(button)

func _nearest_npc_text() -> String:
	if nearest_npc_index == -1:
		return "No placeholder NPC nearby"
	var npc: Dictionary = placeholder_npcs[nearest_npc_index]
	return "Press E to hail %s" % npc.get("name", "NPC")

func _targeted_npc() -> Dictionary:
	if current_target_index < 0 or current_target_index >= placeholder_npcs.size():
		return {}
	return placeholder_npcs[current_target_index]

func _update_target_visuals():
	for i in range(placeholder_npcs.size()):
		var npc: Dictionary = placeholder_npcs[i]
		var mesh_instance: MeshInstance3D = npc.get("mesh")
		var label: Label3D = npc.get("label")
		if mesh_instance == null or label == null:
			continue
		var material: StandardMaterial3D = mesh_instance.material_override
		if material == null:
			material = StandardMaterial3D.new()
		var health_pct: float = float(npc.get("health", 0.0)) / max(float(npc.get("max_health", 1.0)), 1.0)
		if health_pct <= 0.0:
			material.albedo_color = Color(0.25, 0.25, 0.25, 1.0)
			label.text = "%s (defeated)" % npc.get("name", "NPC")
		elif i == current_target_index:
			material.albedo_color = Color(1.0, 0.75, 0.35, 1.0)
			label.text = "[%s] %d%%" % [npc.get("name", "NPC"), int(health_pct * 100.0)]
		else:
			material.albedo_color = Color(0.55, 0.62, 0.78, 1.0)
			label.text = "%s %d%%" % [npc.get("name", "NPC"), int(health_pct * 100.0)]
		mesh_instance.material_override = material

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
	info_label.text = "Greybox Test World\nWorld: %s\nPlayer: %s\nTime: %s" % [world_name, player_name, time_text]
	summary_label.text = "Guild: %s\nParty: %s\nClass: %s\nSpawn position: (%.1f, %.1f, %.1f)\nPaused: %s\nGrounded: %s\nWASD move, Space jumps, Tab cycles targets, 1-8 uses abilities, E interacts, left click captures mouse, Esc releases cursor." % [
		guild_name if not guild_name.is_empty() else "<none>",
		_character_summary(),
		str(char_info.get("pclass", "Unknown")),
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
	var local_target := _targeted_npc()
	if not local_target.is_empty():
		target_label.text = "Local target: %s (%.0f / %.0f HP)" % [
			str(local_target.get("name", "NPC")),
			float(local_target.get("health", 0.0)),
			float(local_target.get("max_health", 100.0)),
		]
	elif not server_target_description.is_empty():
		target_label.text = "Server target: %s Lv%s %s | %s" % [
			str(server_target_description.get("name", "Unknown")),
			str(server_target_description.get("plevel", "?")),
			str(server_target_description.get("race", "Unknown")),
			str(server_target_description.get("standing", "")),
		]
	elif not server_target_name.is_empty():
		target_label.text = "Server target: %s (%.0f%% health)" % [server_target_name, server_target_health * 100.0]
	else:
		target_label.text = "No current target"
	interaction_label.text = "%s\n%s" % [_nearest_npc_text(), interaction_message]
	var transfer = current_payload.get("zone_transfer", {})
	if transfer is Dictionary and not transfer.is_empty():
		transfer_label.text = "Zone handoff prepared: zone port %s, party %s" % [
			str(transfer.get("zone_port", "?")),
			str(transfer.get("party", [])),
		]
	else:
		transfer_label.text = "Gameplay bridge status: root_info/gameplay_state synced from the legacy server. Placeholder NPC combat remains local until real zone entity replication is implemented."
	_update_target_visuals()

func _update_nearest_npc():
	nearest_npc_index = -1
	var nearest_distance: float = INF
	for i in range(placeholder_npcs.size()):
		var npc: Dictionary = placeholder_npcs[i]
		if float(npc.get("health", 0.0)) <= 0.0:
			continue
		var node: StaticBody3D = npc.get("node")
		if node == null:
			continue
		var distance: float = player_body.global_position.distance_to(node.global_position)
		if distance < NPC_INTERACT_RANGE and distance < nearest_distance:
			nearest_distance = distance
			nearest_npc_index = i

func _cycle_target():
	var alive_indices: Array = []
	for i in range(placeholder_npcs.size()):
		if float(placeholder_npcs[i].get("health", 0.0)) > 0.0:
			alive_indices.append(i)
	if alive_indices.is_empty():
		current_target_index = -1
		interaction_message = "No living placeholder targets remain."
		return
	var next_slot := 0
	if current_target_index != -1:
		var current_pos: int = alive_indices.find(current_target_index)
		if current_pos != -1:
			next_slot = (current_pos + 1) % alive_indices.size()
	current_target_index = alive_indices[next_slot]
	var target := _targeted_npc()
	interaction_message = "Targeted %s." % target.get("name", "NPC")

func _interact_with_npc():
	if nearest_npc_index == -1:
		interaction_message = "No placeholder NPC close enough to interact with."
		return
	var npc: Dictionary = placeholder_npcs[nearest_npc_index]
	interaction_message = "%s says: %s" % [npc.get("name", "NPC"), npc.get("dialogue", "...")]

func _activate_ability(slot_index: int):
	var abilities := _abilities()
	if slot_index < 0 or slot_index >= abilities.size():
		interaction_message = "That ability slot is empty."
		return
	var ability: Dictionary = abilities[slot_index]
	var target := _targeted_npc()
	if target.is_empty():
		interaction_message = "%s fizzles because nothing is targeted." % ability.get("name", "Ability")
		return
	var target_health: float = float(target.get("health", 0.0))
	if target_health <= 0.0:
		interaction_message = "%s is already defeated." % target.get("name", "NPC")
		return
	var damage: float = 8.0 + float(slot_index * 3)
	var new_health: float = max(0.0, target_health - damage)
	placeholder_npcs[current_target_index]["health"] = new_health
	interaction_message = "Used %s on %s for %.0f damage." % [ability.get("name", "Ability"), target.get("name", "NPC"), damage]
	if new_health <= 0.0:
		interaction_message += " Target defeated."

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
				_interact_with_npc()
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
	_update_nearest_npc()
	_update_labels()
