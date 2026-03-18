extends Control

var socket := WebSocketPeer.new()
var connected := false

# UI references - set in _ready()
@onready var username_field := $VBoxContainer/UsernameField
@onready var password_field := $VBoxContainer/PasswordField
@onready var login_button := $VBoxContainer/LoginButton
@onready var register_button := $VBoxContainer/RegisterButton
@onready var email_field := $VBoxContainer/EmailField
@onready var status_label := $VBoxContainer/StatusLabel
@onready var world_list := $VBoxContainer/WorldList
@onready var join_button := $VBoxContainer/JoinWorldButton

# Cached world data from server
var worlds: Array = []

func _ready():
	socket.connect_to_url("ws://localhost:9000")
	status_label.text = "Connecting to proxy..."
	join_button.visible = false
	world_list.visible = false

func _process(_delta):
	socket.poll()

	var state := socket.get_ready_state()

	if state == WebSocketPeer.STATE_OPEN and not connected:
		connected = true
		status_label.text = "Connected to proxy. Enter credentials."

	if state == WebSocketPeer.STATE_CLOSED and connected:
		connected = false
		status_label.text = "Disconnected from proxy."

	if state == WebSocketPeer.STATE_OPEN:
		while socket.get_available_packet_count():
			var raw := socket.get_packet().get_string_from_utf8()
			var data = JSON.parse_string(raw)
			if data != null:
				handle_response(data)

func _send(msg: Dictionary):
	if socket.get_ready_state() == WebSocketPeer.STATE_OPEN:
		socket.send_text(JSON.stringify(msg))

# --- Button handlers ---

func _on_login_button_pressed():
	var user := username_field.text.strip_edges()
	var pw := password_field.text.strip_edges()
	if user.is_empty() or pw.is_empty():
		status_label.text = "Enter username and password."
		return
	status_label.text = "Logging in..."
	_send({"type": "login", "username": user, "password": pw})

func _on_register_button_pressed():
	var user := username_field.text.strip_edges()
	var email := email_field.text.strip_edges()
	if user.is_empty() or email.is_empty():
		status_label.text = "Enter username and email to register."
		return
	status_label.text = "Registering..."
	_send({"type": "register", "username": user, "email": email})

func _on_join_world_button_pressed():
	var selected_items := world_list.get_selected_items()
	if selected_items.is_empty():
		status_label.text = "Select a world first."
		return
	var idx: int = selected_items[0]
	if idx >= worlds.size():
		return
	var w: Dictionary = worlds[idx]
	status_label.text = "Connecting to " + w.get("name", "") + "..."
	_send({
		"type": "select_world",
		"world_name": w.get("name", ""),
		"ip": w.get("ip", ""),
		"port": w.get("port", 0),
	})

# --- Response handling ---

func handle_response(data: Dictionary):
	var msg_type: String = data.get("type", "")

	match msg_type:
		"login_result":
			if data.get("success", false):
				status_label.text = "Logged in! Fetching worlds..."
				login_button.disabled = true
			else:
				status_label.text = "Login failed: " + data.get("message", "Unknown error")

		"register_result":
			if data.get("success", false):
				var pw: String = data.get("password", "")
				if pw.is_empty():
					status_label.text = "Registered! Check email for password."
				else:
					status_label.text = "Registered! Password: " + pw
					password_field.text = pw
			else:
				status_label.text = "Register failed: " + data.get("message", "")

		"world_list":
			worlds = data.get("worlds", [])
			_populate_world_list()

		"world_connected":
			if data.get("success", false):
				status_label.text = "Connected to world: " + data.get("world_name", "")
				# TODO: Next phase - character select screen
			else:
				status_label.text = "World error: " + data.get("message", "")

		"error":
			status_label.text = "Error: " + data.get("message", "")

func _populate_world_list():
	world_list.clear()
	world_list.visible = true
	join_button.visible = true

	if worlds.is_empty():
		status_label.text = "No worlds online."
		join_button.visible = false
		return

	for w in worlds:
		var name: String = w.get("name", "???")
		var players: int = w.get("num_players", 0)
		var max_p: int = w.get("max_players", 0)
		var label := "%s  (%d/%d players)" % [name, players, max_p]
		world_list.add_item(label)

	status_label.text = "Found %d world(s). Select one and click Join." % worlds.size()
