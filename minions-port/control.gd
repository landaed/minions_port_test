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
@onready var world_access_password_field := $VBoxContainer/WorldAccessPasswordField
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
	for race in ["Human", "Gnome", "Elf", "Halfling", "Dwarf", "Titan", "Drakken"]:
		race_option.add_item(race)
	for sex in ["Male", "Female"]:
		sex_option.add_item(sex)
	race_option.select(0)
	sex_option.select(0)
	_refresh_class_options()

func _refresh_class_options():
	var race: String = race_option.get_item_text(race_option.selected)
	var race_classes := {
		"Human": ["Paladin", "Cleric", "Necromancer", "Tempest", "Wizard", "Shaman", "Monk", "Barbarian", "Warrior", "Assassin", "Revealer", "Druid", "Ranger", "Bard", "Thief", "Doom Knight"],
		"Gnome": ["Necromancer", "Wizard", "Assassin", "Revealer", "Thief", "Monk", "Tempest", "Cleric"],
		"Halfling": ["Paladin", "Cleric", "Shaman", "Warrior", "Druid", "Ranger", "Bard", "Thief", "Monk", "Tempest", "Wizard"],
		"Elf": ["Paladin", "Cleric", "Tempest", "Wizard", "Shaman", "Monk", "Warrior", "Druid", "Ranger", "Bard", "Revealer"],
		"Dwarf": ["Paladin", "Cleric", "Barbarian", "Warrior", "Shaman", "Tempest", "Revealer"],
		"Titan": ["Paladin", "Cleric", "Tempest", "Wizard", "Monk", "Warrior", "Ranger"],
		"Drakken": ["Cleric", "Necromancer", "Tempest", "Wizard", "Shaman", "Barbarian", "Warrior", "Assassin", "Revealer", "Thief", "Doom Knight", "Monk", "Ranger"],
	}
	var light_classes := ["Shaman", "Warrior", "Paladin", "Cleric", "Tempest", "Wizard", "Monk", "Barbarian", "Thief", "Druid", "Bard", "Ranger", "Revealer"]
	class_option.clear()
	for klass in race_classes.get(race, []):
		if klass in light_classes:
			class_option.add_item(klass)
	if class_option.item_count > 0:
		class_option.select(0)

func _on_race_option_item_selected(_index):
	_refresh_class_options()

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
	world_access_password_field.visible = visible and bool(selected_world.get("has_password", false))
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
		status_label.text = "Enter username and email to register. Registration ignores the login password box and the server assigns one."
		return
	status_label.text = "Registering... the server will assign your master-account password."
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
		"has_password": selected_world.get("has_password", false),
	})

func _on_create_world_account_button_pressed():
	var fantasy_name = fantasy_name_field.text.strip_edges()
	var access_pw = world_access_password_field.text.strip_edges()
	if bool(selected_world.get("has_password", false)) and access_pw.is_empty():
		status_label.text = "This world requires its shared access password before a world account can be created. For your setup that should likely be the world server PLAYERPASSWORD (for example, mmo)."
		return
	create_world_account_button.disabled = true
	status_label.text = "Creating world account... this creates a world-specific password, separate from master login."
	_send({
		"type": "create_world_account",
		"fantasy_name": fantasy_name,
		"player_password": access_pw,
	})

func _on_login_world_button_pressed():
	var world_pw = world_password_field.text.strip_edges()
	login_world_button.disabled = true
	if world_pw.is_empty():
		login_world_button.disabled = false
		status_label.text = "Enter the world password first. This is separate from the master account password."
		return
	status_label.text = "Logging into world..."
	_send({"type": "world_login", "world_password": world_pw, "role": "Player"})

func _on_create_character_button_pressed():
	create_character_button.disabled = true
	var char_name = character_name_field.text.strip_edges()
	if char_name.is_empty():
		create_character_button.disabled = false
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
	enter_world_button.disabled = true
	var selected_name := _selected_character_name()
	if selected_name.is_empty():
		enter_world_button.disabled = false
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
					status_label.text = "Registered! Check email for the master-account password."
				else:
					status_label.text = "Registered! Master-account password assigned by server: " + pw
					password_field.text = pw
			else:
				status_label.text = "Register failed: " + data.get("message", "")

		"world_list":
			worlds = data.get("worlds", [])
			_populate_world_list()

		"world_connected":
			if data.get("success", false):
				if data.get("requires_world_access_password", false):
					selected_world["has_password"] = true
				_set_world_ui_visible(true)
				_set_character_ui_visible(false)
				create_world_account_button.disabled = false
				login_world_button.disabled = false
				world_access_password_field.visible = bool(selected_world.get("has_password", false))
				if data.get("has_world_account", false):
					status_label.text = "World account found. Trying to recover its saved world password from master..."
				else:
					if bool(selected_world.get("has_password", false)):
						status_label.text = "No world account yet. First enter the world access password (for this setup likely mmo), then create the world account."
					else:
						status_label.text = "No world account yet. Create one; it will get its own password separate from master login."
			else:
				status_label.text = "World error: " + data.get("message", "")


		"world_access_password_result":
			if data.get("success", false):
				var access_pw: String = data.get("world_access_password", "")
				if not access_pw.is_empty():
					world_access_password_field.text = access_pw
				if not data.get("has_world_account", false):
					status_label.text = "Recovered local world access password from serverconfig. You can now create the world account."
			else:
				status_label.text = "Could not recover local world access password automatically: " + data.get("message", "")

		"world_password_result":
			login_world_button.disabled = false
			if data.get("success", false):
				var recovered_pw: String = data.get("world_password", "")
				if not recovered_pw.is_empty():
					world_password_field.text = recovered_pw
				status_label.text = "Recovered world password from master. You can now log into the world."
			else:
				status_label.text = "Could not recover world password automatically: " + data.get("message", "")

		"world_account_result":
			create_world_account_button.disabled = false
			if data.get("success", false):
				var world_pw: String = data.get("world_password", "")
				if not world_pw.is_empty():
					world_password_field.text = world_pw
				status_label.text = "World account created. Use the auto-filled world-account password to log in; it is separate from both the master password and any shared world access password."
			else:
				status_label.text = "World account failed: " + data.get("message", "")

		"player_login_result":
			login_world_button.disabled = false
			if data.get("success", false):
				status_label.text = "World login ok. Loading characters..."
				_set_character_ui_visible(true)
			else:
				status_label.text = "World login failed: " + data.get("message", "")

		"character_list":
			characters = data.get("characters", [])
			_populate_character_list()

		"create_character_result":
			create_character_button.disabled = false
			if data.get("success", false):
				status_label.text = "Character created: " + data.get("name", "")
				character_name_field.text = ""
			else:
				status_label.text = "Create character failed: " + data.get("message", "")

		"enter_world_result":
			enter_world_button.disabled = false
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
			create_world_account_button.disabled = false
			login_world_button.disabled = false
			create_character_button.disabled = false
			enter_world_button.disabled = false
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
