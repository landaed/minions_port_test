extends Control

const MOVE_SPEED := 8.0
const LOOK_SENSITIVITY := 0.003

var world_time := {"hour": 0, "minute": 0}
var current_payload: Dictionary = {}
var selected_world: Dictionary = {}
var velocity := Vector3.ZERO
var mouse_captured := false

@onready var info_label := $MarginContainer/VBoxContainer/InfoLabel
@onready var detail_label := $MarginContainer/VBoxContainer/DetailLabel
@onready var transfer_label := $MarginContainer/VBoxContainer/TransferLabel
@onready var player_body := $SubViewportContainer/SubViewport/WorldRoot/PlayerBody
@onready var camera_pivot := $SubViewportContainer/SubViewport/WorldRoot/PlayerBody/CameraPivot
@onready var camera := $SubViewportContainer/SubViewport/WorldRoot/PlayerBody/CameraPivot/Camera3D

func _ready():
	set_process_unhandled_input(true)
	_update_labels()

func apply_world_state(payload: Dictionary, world: Dictionary, time_info: Dictionary):
	current_payload = payload.duplicate(true)
	selected_world = world.duplicate(true)
	world_time = time_info.duplicate(true)
	var position = _payload_position()
	player_body.global_position = position
	camera.current = true
	visible = true
	_update_labels()

func set_world_time(time_info: Dictionary):
	world_time = time_info.duplicate(true)
	_update_labels()

func set_zone_transfer(payload: Dictionary):
	current_payload["zone_transfer"] = payload.duplicate(true)
	_update_labels()

func _payload_position() -> Vector3:
	var pos = current_payload.get("position", [0.0, 0.0, 0.0])
	if pos is Array and pos.size() >= 3:
		return Vector3(float(pos[0]), float(pos[2]) + 1.0, float(-pos[1]))
	return Vector3(0.0, 1.0, 0.0)

func _character_summary() -> String:
	var char_infos: Array = current_payload.get("char_infos", [])
	if char_infos.is_empty():
		return "No party data received"
	var bits: Array = []
	for entry in char_infos:
		bits.append("%s Lv%s %s" % [
			str(entry.get("name", "?")),
			str(entry.get("level", 1)),
			str(entry.get("pclass", entry.get("klass", "Unknown"))),
		])
	return ", ".join(bits)

func _update_labels():
	var world_name := str(selected_world.get("name", current_payload.get("world_name", "Unknown World")))
	var player_name := str(current_payload.get("player_name", "Unknown Player"))
	var guild_name := str(current_payload.get("guild_name", ""))
	var pos := player_body.global_position
	var time_text := "%02d:%02d" % [int(world_time.get("hour", 0)), int(world_time.get("minute", 0))]
	info_label.text = "Greybox Test World\nWorld: %s\nPlayer: %s\nTime: %s" % [world_name, player_name, time_text]
	var paused_text := "yes" if bool(current_payload.get("paused", false)) else "no"
	detail_label.text = "Guild: %s\nParty: %s\nSpawn position: (%.1f, %.1f, %.1f)\nPaused: %s\nWASD move, mouse look, Esc release cursor." % [
		guild_name if not guild_name.is_empty() else "<none>",
		_character_summary(),
		pos.x,
		pos.y,
		pos.z,
		paused_text,
	]
	var transfer = current_payload.get("zone_transfer", {})
	if transfer.is_empty():
		transfer_label.text = "Gameplay bridge status: root_info received. Using local greybox scene until the real zone stream is implemented."
	else:
		transfer_label.text = "Zone handoff prepared: zone port %s, party %s" % [
			str(transfer.get("zone_port", "?")),
			str(transfer.get("party", [])),
		]

func _unhandled_input(event):
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		Input.set_mouse_mode(Input.MOUSE_MODE_CAPTURED)
		mouse_captured = true
	elif event.is_action_pressed("ui_cancel"):
		Input.set_mouse_mode(Input.MOUSE_MODE_VISIBLE)
		mouse_captured = false
	elif event is InputEventMouseMotion and mouse_captured:
		player_body.rotate_y(-event.relative.x * LOOK_SENSITIVITY)
		camera_pivot.rotate_x(-event.relative.y * LOOK_SENSITIVITY)
		camera_pivot.rotation.x = clamp(camera_pivot.rotation.x, deg_to_rad(-70), deg_to_rad(70))

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
	var basis := player_body.global_transform.basis
	var move_dir := (basis.x * input_vec.x) + (-basis.z * input_vec.y)
	if move_dir.length() > 1.0:
		move_dir = move_dir.normalized()
	velocity.x = move_dir.x * MOVE_SPEED
	velocity.z = move_dir.z * MOVE_SPEED
	if not player_body.is_on_floor():
		velocity.y -= 20.0 * delta
	else:
		velocity.y = 0.0
	player_body.velocity = velocity
	player_body.move_and_slide()
	_update_labels()
