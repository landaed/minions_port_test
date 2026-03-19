extends Control

var socket := WebSocketPeer.new()
var connected := false

@onready var username_field := $VBoxContainer/UsernameField
@onready var password_field := $VBoxContainer/PasswordField
@onready var login_button := $VBoxContainer/LoginButton
@onready var register_button := $VBoxContainer/RegisterButton
@onready var email_field := $VBoxContainer/EmailField
@onready var status_label := $VBoxContainer/StatusLabel
@onready var world_list := $VBoxContainer/WorldList
@onready var join_button := $VBoxContainer/JoinWorldButton
@onready var world_password_field := $VBoxContainer/WorldPasswordField
@onready var fantasy_name_field := $VBoxContainer/FantasyNameField
@onready var create_world_account_button := $VBoxContainer/CreateWorldAccountButton
@onready var login_world_button := $VBoxContainer/LoginWorldButton
@onready var character_list := $VBoxContainer/CharacterList
@onready var character_name_field := $VBoxContainer/CharacterNameField
@onready var race_option := $VBoxContainer/RaceOption
@onready var class_option := $VBoxContainer/ClassOption
@onready var sex_option := $VBoxContainer/SexOption
@onready var create_character_button := $VBoxContainer/CreateCharacterButton
@onready var enter_world_button := $VBoxContainer/EnterWorldButton

var worlds: Array = []
var characters: Array = []
var selected_world: Dictionary = {}

func _ready():
	socket.connect_to_url("ws://localhost:9000")
	status_label.text = "Connecting to proxy..."
	_setup_options()
	_set_world_ui_visible(false)
	_set_character_ui_visible(false)

func _setup_options():
	for race in ["Human", "Half-Elf", "Elf", "Dwarf", "Orc"]:
		race_option.add_item(race)
	for klass in ["Warrior", "Cleric", "Paladin", "Wizard", "Doom Knight", "Ranger"]:
		class_option.add_item(klass)
	for sex in ["Male", "Female"]:
		sex_option.add_item(sex)
	race_option.select(0)
	class_option.select(0)
	sex_option.select(0)

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

func _set_world_ui_visible(visible: bool):
	world_password_field.visible = visible
	fantasy_name_field.visible = visible
	create_world_account_button.visible = visible
	login_world_button.visible = visible

func _set_character_ui_visible(visible: bool):
	character_list.visible = visible
	character_name_field.visible = visible
	race_option.visible = visible
	class_option.visible = visible
	sex_option.visible = visible
	create_character_button.visible = visible
	enter_world_button.visible = visible

func _selected_character_name() -> String:
	var selected_items = character_list.get_selected_items()
	if selected_items.is_empty():
		return ""
	var idx: int = selected_items[0]
	if idx < 0 or idx >= characters.size():
		return ""
	return str(characters[idx].get("name", ""))

func _on_login_button_pressed():
	var user = username_field.text.strip_edges()
	var pw = password_field.text.strip_edges()
	if user.is_empty() or pw.is_empty():
		status_label.text = "Enter username and password."
		return
	status_label.text = "Logging in..."
	_send({"type": "login", "username": user, "password": pw})

func _on_register_button_pressed():
	var user = username_field.text.strip_edges()
	var email = email_field.text.strip_edges()
	if user.is_empty() or email.is_empty():
		status_label.text = "Enter username and email to register."
		return
	status_label.text = "Registering..."
	_send({"type": "register", "username": user, "email": email})

func _on_join_world_button_pressed():
	var selected_items = world_list.get_selected_items()
	if selected_items.is_empty():
		status_label.text = "Select a world first."
		return
	var idx: int = selected_items[0]
	if idx >= worlds.size():
		return
	selected_world = worlds[idx]
	status_label.text = "Connecting to %s..." % selected_world.get("name", "")
	_send({
		"type": "select_world",
		"world_name": selected_world.get("name", ""),
		"ip": selected_world.get("ip", ""),
		"port": selected_world.get("port", 0),
	})

func _on_create_world_account_button_pressed():
	var fantasy_name = fantasy_name_field.text.strip_edges()
	status_label.text = "Creating world account..."
	_send({
		"type": "create_world_account",
		"fantasy_name": fantasy_name,
		"player_password": "",
	})

func _on_login_world_button_pressed():
	var world_pw = world_password_field.text.strip_edges()
	if world_pw.is_empty():
		status_label.text = "Enter the world password first."
		return
	status_label.text = "Logging into world..."
	_send({"type": "world_login", "world_password": world_pw, "role": "Player"})

func _on_create_character_button_pressed():
	var char_name = character_name_field.text.strip_edges()
	if char_name.is_empty():
		status_label.text = "Enter a character name first."
		return
	status_label.text = "Creating character..."
	_send({
		"type": "create_character",
		"name": char_name,
		"race": race_option.get_item_text(race_option.selected),
		"klass": class_option.get_item_text(class_option.selected),
		"sex": sex_option.get_item_text(sex_option.selected),
		"look": 0,
		"realm": 1,
	})

func _on_enter_world_button_pressed():
	var selected_name := _selected_character_name()
	if selected_name.is_empty():
		status_label.text = "Select a character first."
		return
	status_label.text = "Sending enter-world request for %s..." % selected_name
	_send({"type": "enter_world", "character_name": selected_name})

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
				_set_world_ui_visible(true)
				_set_character_ui_visible(false)
				if data.get("has_world_account", false):
					status_label.text = "World account found. Enter world password."
				else:
					status_label.text = "No world account yet. Create one, then log in."
			else:
				status_label.text = "World error: " + data.get("message", "")

		"world_account_result":
			if data.get("success", false):
				var world_pw: String = data.get("world_password", "")
				if not world_pw.is_empty():
					world_password_field.text = world_pw
				status_label.text = "World account created. Now log into the world."
			else:
				status_label.text = "World account failed: " + data.get("message", "")

		"player_login_result":
			if data.get("success", false):
				status_label.text = "World login ok. Loading characters..."
				_set_character_ui_visible(true)
			else:
				status_label.text = "World login failed: " + data.get("message", "")

		"character_list":
			characters = data.get("characters", [])
			_populate_character_list()

		"create_character_result":
			if data.get("success", false):
				status_label.text = "Character created: " + data.get("name", "")
				character_name_field.text = ""
			else:
				status_label.text = "Create character failed: " + data.get("message", "")

		"enter_world_result":
			if data.get("success", false):
				status_label.text = data.get("message", "Enter-world request sent.")
			else:
				status_label.text = "Enter world failed: " + data.get("message", "")

		"zone_transfer":
			status_label.text = "Zone handoff received. Next: bridge zone protocol / gameplay streaming."

		"world_time":
			# Useful as a signal that player login is fully alive.
			pass

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

func _populate_character_list():
	character_list.clear()
	if characters.is_empty():
		status_label.text = "No characters yet. Create one below."
		return

	for c in characters:
		var label := "%s - Lv %s %s %s (%s)" % [
			str(c.get("name", "?")),
			str(c.get("level", 1)),
			str(c.get("race", "Unknown")),
			str(c.get("klass", "Unknown")),
			str(c.get("status", "Unknown")),
		]
		character_list.add_item(label)

	character_list.select(0)
	status_label.text = "Character list loaded. Select one to enter the world, or create a new one."
