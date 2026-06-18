extends Control

const GAMEPLAY_VIEW_SCENE := preload("res://gameplay_view.tscn")
const CharacterRigScript := preload("res://world/character_rig.gd")
const CHAR_ASSET_DIR := "res://assets/characters/"

var socket := WebSocketPeer.new()
var connected := false
var gameplay_view: Control = null
var world_time := {"hour": 0, "minute": 0}

# --- Menu visuals: a 3D character on a lit stage behind the login/creation form.
var _stage_viewport: SubViewport = null
var _stage_pivot: Node3D = null
var _stage_rig: Node3D = null
var _stage_model_key := ""
var _stage_spin := 0.0
var _form_panel: PanelContainer = null

# --- Character creation: appearance + starting stats ----------------------
var _build_option: OptionButton = null
var _stats_section: VBoxContainer = null
var _stat_points_label: Label = null
const STAT_KEYS := ["str", "bdy", "agi", "dex", "ref", "mnd", "wis", "mys"]
const STAT_NAMES := {
	"str": "Strength", "bdy": "Body", "agi": "Agility", "dex": "Dexterity",
	"ref": "Reflexes", "mnd": "Mind", "wis": "Wisdom", "mys": "Mysticism",
}
const STARTING_BONUS_POOL := 10
var _stat_bonus := {}            # stat -> points allocated
var _stat_value_labels := {}     # stat -> Label

@onready var login_panel := $VBoxContainer
@onready var title_label := $VBoxContainer/TitleLabel
@onready var hseparator := $VBoxContainer/HSeparator
@onready var server_field := $VBoxContainer/ServerField
@onready var connect_button := $VBoxContainer/ConnectButton
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

# --- Step-by-step login flow: only the controls for the current step show. ---
const PHASE_LOGIN := "login"
const PHASE_WORLD := "world"
const PHASE_WORLD_ACCOUNT := "world_account"
const PHASE_CHARACTER := "character"
var _current_phase := ""

func _phase_login_controls() -> Array:
	return [server_field, connect_button, username_field, password_field, email_field, login_button, register_button]

func _phase_world_controls() -> Array:
	return [world_list, join_button]

func _phase_world_account_controls() -> Array:
	return [fantasy_name_field, world_access_password_field, create_world_account_button, world_password_field, login_world_button]

func _phase_character_controls() -> Array:
	return [character_list, character_name_field, race_option, class_option, sex_option, _build_option, _stats_section, create_character_button, enter_world_button]

func _all_flow_controls() -> Array:
	return _phase_login_controls() + _phase_world_controls() + _phase_world_account_controls() + _phase_character_controls()

func _show_only(controls: Array):
	for c in _all_flow_controls():
		if c:
			c.visible = controls.has(c)
	if hseparator:
		hseparator.visible = false

func _set_phase(phase: String):
	_current_phase = phase
	match phase:
		PHASE_LOGIN:
			title_label.text = "Minions of Mirth\nStep 1 of 4 — Log In or Register"
			_show_only(_phase_login_controls())
		PHASE_WORLD:
			title_label.text = "Step 2 of 4 — Choose a World"
			_show_only(_phase_world_controls())
		PHASE_WORLD_ACCOUNT:
			title_label.text = "Step 3 of 4 — World Character Slot"
			_show_only(_phase_world_account_controls())
			# Access password only matters when the world is password-gated.
			world_access_password_field.visible = bool(selected_world.get("has_password", false))
		PHASE_CHARACTER:
			title_label.text = "Step 4 of 4 — Pick or Create a Character"
			_show_only(_phase_character_controls())

const SERVER_CFG_PATH := "user://mom_client.cfg"
# Use the IPv4 loopback, not "localhost": on Windows "localhost" often resolves
# to IPv6 ::1 first, but the proxy listens on IPv4 0.0.0.0, so a "localhost"
# client can stall. 127.0.0.1 forces IPv4.
const DEFAULT_SERVER := "127.0.0.1"
const DEFAULT_PROXY_PORT := 9000
var _current_server_url := ""

func _ready():
	_build_visuals()
	_setup_options()
	_build_creation_extras()
	_set_phase(PHASE_LOGIN)
	# Remember the last server you connected to (host or host:port). Leave the
	# field blank for localhost. To play with a friend, type the HOST's address
	# (their public IP / hostname, e.g. 203.0.113.7 or 203.0.113.7:9000).
	var saved := _load_server()
	server_field.text = saved
	_connect_to_server(saved)
	GameAudio.start_menu_music()

# --- Menu visuals ----------------------------------------------------------
func _build_visuals() -> void:
	# Dark backdrop behind everything.
	var bg := ColorRect.new()
	bg.color = Color(0.03, 0.04, 0.06)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(bg)
	move_child(bg, 0)

	# 3D stage: a lit, slowly rotating character in a SubViewport.
	var svc := SubViewportContainer.new()
	svc.set_anchors_preset(Control.PRESET_FULL_RECT)
	svc.stretch = true
	svc.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(svc)
	move_child(svc, 1)
	_stage_viewport = SubViewport.new()
	_stage_viewport.own_world_3d = true
	_stage_viewport.msaa_3d = Viewport.MSAA_4X
	svc.add_child(_stage_viewport)

	var we := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.05, 0.06, 0.10)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.30, 0.36, 0.50)
	env.ambient_light_energy = 0.7
	env.fog_enabled = true
	env.fog_light_color = Color(0.06, 0.07, 0.12)
	env.fog_density = 0.015
	we.environment = env
	_stage_viewport.add_child(we)

	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-32, 40, 0)
	key.light_energy = 1.6
	key.light_color = Color(1.0, 0.92, 0.78)
	_stage_viewport.add_child(key)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-8, -130, 0)
	fill.light_energy = 0.5
	fill.light_color = Color(0.55, 0.68, 1.0)
	_stage_viewport.add_child(fill)
	var rim := OmniLight3D.new()
	rim.position = Vector3(-1.5, 2.4, -2.2)
	rim.light_energy = 4.0
	rim.light_color = Color(0.75, 0.85, 1.0)
	rim.omni_range = 9.0
	_stage_viewport.add_child(rim)

	# Pedestal the character stands on.
	var ped := MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.top_radius = 1.5
	cyl.bottom_radius = 1.7
	cyl.height = 0.2
	ped.mesh = cyl
	ped.position = Vector3(0, -0.1, 0)
	var pmat := StandardMaterial3D.new()
	pmat.albedo_color = Color(0.09, 0.10, 0.14)
	pmat.metallic = 0.4
	pmat.roughness = 0.55
	ped.material_override = pmat
	_stage_viewport.add_child(ped)

	_stage_pivot = Node3D.new()
	_stage_viewport.add_child(_stage_pivot)

	var cam := Camera3D.new()
	cam.fov = 38.0
	cam.position = Vector3(0.0, 1.15, 4.3)
	_stage_viewport.add_child(cam)
	cam.look_at(Vector3(0.0, 1.0, 0.0), Vector3.UP)  # after entering the tree

	_update_preview_model("Human", "Male", "")
	_build_form_chrome()
	set_process(true)

func _build_form_chrome() -> void:
	# Big game-title banner across the top.
	var banner := Label.new()
	banner.text = "MINIONS OF MIRTH"
	banner.add_theme_font_size_override("font_size", 46)
	banner.add_theme_color_override("font_color", Color(0.95, 0.84, 0.52))
	banner.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.75))
	banner.add_theme_constant_override("shadow_offset_x", 2)
	banner.add_theme_constant_override("shadow_offset_y", 3)
	banner.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	banner.set_anchors_preset(Control.PRESET_TOP_WIDE)
	banner.offset_top = 28.0
	banner.offset_bottom = 96.0
	banner.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(banner)

	# Styled panel on the right; the character shows on the left.
	var panel := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.06, 0.07, 0.10, 0.90)
	sb.border_color = Color(0.5, 0.56, 0.72, 0.85)
	sb.set_border_width_all(1)
	sb.set_corner_radius_all(10)
	sb.content_margin_left = 20
	sb.content_margin_right = 20
	sb.content_margin_top = 16
	sb.content_margin_bottom = 16
	sb.shadow_color = Color(0, 0, 0, 0.55)
	sb.shadow_size = 16
	panel.add_theme_stylebox_override("panel", sb)
	panel.anchor_left = 1.0
	panel.anchor_right = 1.0
	panel.anchor_top = 0.5
	panel.anchor_bottom = 0.5
	panel.offset_left = -520.0
	panel.offset_right = -48.0
	panel.offset_top = -330.0
	panel.offset_bottom = 330.0
	panel.grow_vertical = Control.GROW_DIRECTION_BOTH
	panel.theme = _menu_theme()
	add_child(panel)
	_form_panel = panel

	# Move the existing form into the panel.
	remove_child(login_panel)
	panel.add_child(login_panel)
	login_panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	login_panel.offset_left = 0
	login_panel.offset_top = 0
	login_panel.offset_right = 0
	login_panel.offset_bottom = 0
	login_panel.add_theme_constant_override("separation", 9)

	title_label.add_theme_font_size_override("font_size", 21)
	title_label.add_theme_color_override("font_color", Color(0.86, 0.89, 0.97))
	status_label.add_theme_color_override("font_color", Color(0.68, 0.77, 0.9))

func _menu_theme() -> Theme:
	var th := Theme.new()
	var btn := StyleBoxFlat.new()
	btn.bg_color = Color(0.14, 0.17, 0.24)
	btn.border_color = Color(0.42, 0.56, 0.82)
	btn.set_border_width_all(1)
	btn.set_corner_radius_all(5)
	btn.content_margin_left = 10
	btn.content_margin_right = 10
	btn.content_margin_top = 8
	btn.content_margin_bottom = 8
	var btn_hover: StyleBoxFlat = btn.duplicate()
	btn_hover.bg_color = Color(0.21, 0.27, 0.38)
	btn_hover.border_color = Color(0.55, 0.7, 0.95)
	var btn_press: StyleBoxFlat = btn.duplicate()
	btn_press.bg_color = Color(0.11, 0.14, 0.2)
	for cls in ["Button", "OptionButton"]:
		th.set_stylebox("normal", cls, btn)
		th.set_stylebox("hover", cls, btn_hover)
		th.set_stylebox("pressed", cls, btn_press)
		th.set_stylebox("focus", cls, btn_hover)
		th.set_color("font_color", cls, Color(0.92, 0.94, 0.98))
		th.set_font_size("font_size", cls, 15)
	var le := StyleBoxFlat.new()
	le.bg_color = Color(0.10, 0.12, 0.16)
	le.border_color = Color(0.3, 0.35, 0.45)
	le.set_border_width_all(1)
	le.set_corner_radius_all(4)
	le.content_margin_left = 8
	le.content_margin_right = 8
	le.content_margin_top = 7
	le.content_margin_bottom = 7
	var le_focus: StyleBoxFlat = le.duplicate()
	le_focus.border_color = Color(0.5, 0.66, 0.92)
	th.set_stylebox("normal", "LineEdit", le)
	th.set_stylebox("focus", "LineEdit", le_focus)
	th.set_font_size("font_size", "LineEdit", 14)
	var list_bg := StyleBoxFlat.new()
	list_bg.bg_color = Color(0.08, 0.09, 0.13)
	list_bg.border_color = Color(0.3, 0.35, 0.45)
	list_bg.set_border_width_all(1)
	list_bg.set_corner_radius_all(4)
	th.set_stylebox("panel", "ItemList", list_bg)
	th.set_font_size("font_size", "ItemList", 14)
	return th

func _glb_for(race: String, sex: String, model: String) -> String:
	if model != "":
		var key := model.to_lower()
		if key.ends_with(".dts"):
			key = key.substr(0, key.length() - 4)
		key = key.replace("/", "_").replace("\\", "_")
		var mp := CHAR_ASSET_DIR + key + ".glb"
		if ResourceLoader.exists(mp):
			return mp
	var s := "female" if sex.to_lower().begins_with("f") else "male"
	var r := race.to_lower().replace(" ", "")
	if r != "":
		var rp := CHAR_ASSET_DIR + r + "_" + s + ".glb"
		if ResourceLoader.exists(rp):
			return rp
	var hp := CHAR_ASSET_DIR + "human_male.glb"
	return hp if ResourceLoader.exists(hp) else ""

func _update_preview_model(race: String, sex: String, model: String) -> void:
	if _stage_pivot == null:
		return
	var path := _glb_for(race, sex, model)
	if path == "" or path == _stage_model_key:
		return
	_stage_model_key = path
	if _stage_rig and is_instance_valid(_stage_rig):
		_stage_rig.queue_free()
	_stage_rig = CharacterRigScript.new()
	_stage_pivot.add_child(_stage_rig)
	_stage_rig.setup(path, 180.0)  # face the camera
	_apply_preview_build()

func _apply_preview_build() -> void:
	# Approximate the chosen body build by scaling the preview (the port ships one
	# mesh per race/sex, so Slender/Average/Burly nudge the silhouette).
	if _stage_rig == null or not is_instance_valid(_stage_rig):
		return
	var look: int = _build_option.selected if _build_option else 1
	var widths := [0.9, 1.0, 1.12]
	var wide: float = widths[clampi(look, 0, 2)]
	_stage_rig.scale = Vector3(wide, 1.0, wide)

func _build_creation_extras() -> void:
	# Body build (Slender/Average/Burly -> look 0/1/2).
	_build_option = OptionButton.new()
	for b in ["Slender build", "Average build", "Burly build"]:
		_build_option.add_item(b)
	_build_option.select(1)
	_build_option.item_selected.connect(func(_i): _apply_preview_build())
	login_panel.add_child(_build_option)
	login_panel.move_child(_build_option, sex_option.get_index() + 1)

	# Starting stat allocation.
	_stats_section = VBoxContainer.new()
	_stats_section.add_theme_constant_override("separation", 2)
	_stat_points_label = Label.new()
	_stat_points_label.add_theme_font_size_override("font_size", 12)
	_stat_points_label.add_theme_color_override("font_color", Color(1.0, 0.85, 0.4))
	_stats_section.add_child(_stat_points_label)
	var grid := GridContainer.new()
	grid.columns = 8
	grid.add_theme_constant_override("h_separation", 5)
	grid.add_theme_constant_override("v_separation", 3)
	_stats_section.add_child(grid)
	# Two attributes per row (name, -, value, +).
	for key in STAT_KEYS:
		_stat_bonus[key] = 0
		var name_l := Label.new()
		name_l.text = STAT_NAMES[key]
		name_l.add_theme_font_size_override("font_size", 11)
		name_l.custom_minimum_size = Vector2(72, 0)
		grid.add_child(name_l)
		var minus := Button.new()
		minus.text = "−"
		minus.custom_minimum_size = Vector2(26, 22)
		minus.focus_mode = Control.FOCUS_NONE
		minus.pressed.connect(_on_stat_minus.bind(key))
		grid.add_child(minus)
		var val_l := Label.new()
		val_l.text = "0"
		val_l.custom_minimum_size = Vector2(20, 0)
		val_l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		grid.add_child(val_l)
		_stat_value_labels[key] = val_l
		var plus := Button.new()
		plus.text = "+"
		plus.custom_minimum_size = Vector2(26, 22)
		plus.focus_mode = Control.FOCUS_NONE
		plus.pressed.connect(_on_stat_plus.bind(key))
		grid.add_child(plus)
	login_panel.add_child(_stats_section)
	login_panel.move_child(_stats_section, _build_option.get_index() + 1)
	_update_stat_points_label()

func _stat_points_spent() -> int:
	var t := 0
	for k in STAT_KEYS:
		t += int(_stat_bonus[k])
	return t

func _update_stat_points_label() -> void:
	if _stat_points_label:
		_stat_points_label.text = "Bonus starting points: %d / %d remaining" % [
			STARTING_BONUS_POOL - _stat_points_spent(), STARTING_BONUS_POOL]

func _on_stat_plus(key: String) -> void:
	if _stat_points_spent() >= STARTING_BONUS_POOL:
		return
	_stat_bonus[key] = int(_stat_bonus[key]) + 1
	_stat_value_labels[key].text = str(_stat_bonus[key])
	_update_stat_points_label()

func _on_stat_minus(key: String) -> void:
	if int(_stat_bonus[key]) <= 0:
		return
	_stat_bonus[key] = int(_stat_bonus[key]) - 1
	_stat_value_labels[key].text = str(_stat_bonus[key])
	_update_stat_points_label()

# Turn "host", "host:port", or "ws://host:port" into a WebSocket URL.
func _server_url(addr: String) -> String:
	addr = addr.strip_edges()
	if addr.is_empty():
		addr = DEFAULT_SERVER
	# Force IPv4 for localhost: on Windows "localhost" often resolves to IPv6
	# ::1 first, but the proxy listens on IPv4, so the client stalls for a while
	# before falling back. 127.0.0.1 connects immediately.
	if addr == "localhost":
		addr = "127.0.0.1"
	elif addr.begins_with("localhost:"):
		addr = "127.0.0.1" + addr.substr("localhost".length())
	if addr.begins_with("ws://") or addr.begins_with("wss://"):
		return addr
	if not (":" in addr):
		addr += ":" + str(DEFAULT_PROXY_PORT)
	return "ws://" + addr

func _connect_to_server(addr: String) -> void:
	var url := _server_url(addr)
	# Fresh peer so a re-connect to a new address starts clean.
	socket = WebSocketPeer.new()
	socket.inbound_buffer_size = 1048576  # entity snapshots can be large
	connected = false
	_current_server_url = url
	var err := socket.connect_to_url(url)
	if err != OK:
		status_label.text = "Could not start connection to %s (error %d)." % [url, err]
	else:
		status_label.text = "Connecting to %s ..." % url

func _on_connect_button_pressed():
	var addr: String = server_field.text.strip_edges()
	_save_server(addr)
	_connect_to_server(addr)

func _load_server() -> String:
	var cfg := ConfigFile.new()
	if cfg.load(SERVER_CFG_PATH) == OK:
		return str(cfg.get_value("connection", "server", DEFAULT_SERVER))
	return DEFAULT_SERVER

func _save_server(addr: String) -> void:
	var cfg := ConfigFile.new()
	cfg.load(SERVER_CFG_PATH)  # keep any other keys
	cfg.set_value("connection", "server", addr)
	cfg.save(SERVER_CFG_PATH)

func _setup_options():
	for race in ["Human", "Gnome", "Elf", "Halfling", "Dwarf", "Titan", "Drakken"]:
		race_option.add_item(race)
	for sex in ["Male", "Female"]:
		sex_option.add_item(sex)
	race_option.select(0)
	sex_option.select(0)
	sex_option.item_selected.connect(func(_i): _update_creation_preview())
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
	_update_creation_preview()

func _update_creation_preview() -> void:
	var race: String = race_option.get_item_text(race_option.selected)
	var sex: String = sex_option.get_item_text(sex_option.selected)
	_update_preview_model(race, sex, "")

func _process(delta):
	# Slowly turn the menu character.
	if _stage_pivot and is_instance_valid(_stage_pivot):
		_stage_spin += delta * 0.45
		_stage_pivot.rotation.y = _stage_spin

	socket.poll()

	var state := socket.get_ready_state()

	if state == WebSocketPeer.STATE_OPEN and not connected:
		connected = true
		status_label.text = "Connected to %s. Enter credentials." % _current_server_url

	if state == WebSocketPeer.STATE_CLOSED:
		if connected:
			connected = false
			status_label.text = "Disconnected from %s." % _current_server_url
		elif not _current_server_url.is_empty() and not status_label.text.begins_with("Could not reach"):
			# Never opened — connection refused/unreachable.
			status_label.text = "Could not reach %s. Check the address, that the host's servers are running, and that port 9000 is open." % _current_server_url

	if state == WebSocketPeer.STATE_OPEN:
		while socket.get_available_packet_count():
			var raw := socket.get_packet().get_string_from_utf8()
			var data = JSON.parse_string(raw)
			if data != null:
				handle_response(data)

func _send(msg: Dictionary):
	if socket.get_ready_state() == WebSocketPeer.STATE_OPEN:
		socket.send_text(JSON.stringify(msg))

# (visibility is now driven by _set_phase / _show_only above)

func _selected_character_name() -> String:
	var selected_items = character_list.get_selected_items()
	if selected_items.is_empty():
		return ""
	var idx: int = selected_items[0]
	if idx < 0 or idx >= characters.size():
		return ""
	return str(characters[idx].get("name", ""))

var _returning_to_chars := false  # suppress gameplay view while in char-select

func _ensure_gameplay_view() -> Control:
	if gameplay_view == null:
		gameplay_view = GAMEPLAY_VIEW_SCENE.instantiate()
		gameplay_view.visible = false
		if gameplay_view.has_signal("command_requested"):
			gameplay_view.command_requested.connect(_on_gameplay_view_command_requested)
		if gameplay_view.has_signal("menu_action_requested"):
			gameplay_view.menu_action_requested.connect(_on_menu_action)
		add_child(gameplay_view)
	return gameplay_view

func _on_menu_action(action: String) -> void:
	match action:
		"quit":
			get_tree().quit()
		"logout":
			# Drop the connection and return to a fresh login screen.
			if socket:
				socket.close()
			get_tree().reload_current_scene()
		"character_select":
			# Leave the world and return to the character list (re-entry attempts a
			# fresh enter_world). Free the in-world view so a clean one is built.
			_returning_to_chars = true
			_send({"type": "leave_world"})
			if gameplay_view:
				gameplay_view.queue_free()
				gameplay_view = null
			login_panel.visible = true
			_set_phase(PHASE_CHARACTER)
			_populate_character_list()
			GameAudio.start_menu_music()
			status_label.text = "Pick a character to enter, or Log Out."

func _on_gameplay_view_command_requested(command_type: String, payload: Dictionary = {}):
	if command_type == "cheat":
		_send({"type": "cheat", "action": payload.get("action", ""), "params": payload.get("params", {})})
		return
	var msg := {"type": "gameplay_command", "command": command_type}
	for key in payload.keys():
		msg[key] = payload[key]
	_send(msg)


func _show_gameplay_view(payload: Dictionary):
	var view := _ensure_gameplay_view()
	login_panel.visible = false
	view.visible = true
	if view.has_method("apply_world_state"):
		view.apply_world_state(payload, selected_world, world_time)
	GameAudio.start_world_music()

func _update_gameplay_clock():
	if gameplay_view and gameplay_view.visible and gameplay_view.has_method("set_world_time"):
		gameplay_view.set_world_time(world_time)

func _on_login_button_pressed():
	GameAudio.ui_accept()
	var user = username_field.text.strip_edges()
	var pw = password_field.text.strip_edges()
	if user.is_empty() or pw.is_empty():
		status_label.text = "Enter username and password."
		return
	status_label.text = "Logging in..."
	_send({"type": "login", "username": user, "password": pw})

func _on_register_button_pressed():
	GameAudio.ui_accept()
	var user = username_field.text.strip_edges()
	var email = email_field.text.strip_edges()
	var pw = password_field.text.strip_edges()
	if user.is_empty() or email.is_empty():
		status_label.text = "Enter username and email to register. Optionally type a password (4+ chars) to choose your own; leave it blank to have one assigned."
		return
	if pw.is_empty():
		status_label.text = "Registering... no password typed, so the server will assign one (it will be shown here)."
	else:
		status_label.text = "Registering with your chosen password..."
	# password is optional: if blank, the server assigns a random one.
	_send({"type": "register", "username": user, "email": email, "password": pw})

func _on_join_world_button_pressed():
	GameAudio.ui_accept()
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
	GameAudio.ui_accept()
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
	GameAudio.ui_accept()
	var world_pw = world_password_field.text.strip_edges()
	login_world_button.disabled = true
	if world_pw.is_empty():
		login_world_button.disabled = false
		status_label.text = "Enter the world password first. This is separate from the master account password."
		return
	status_label.text = "Logging into world..."
	_send({"type": "world_login", "world_password": world_pw, "role": "Player"})

func _on_create_character_button_pressed():
	GameAudio.ui_accept()
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
		"look": _build_option.selected if _build_option else 0,
		"bonus": _stat_bonus.duplicate(),
		"realm": 1,
	})

func _on_enter_world_button_pressed():
	GameAudio.ui_accept()
	enter_world_button.disabled = true
	var selected_name := _selected_character_name()
	if selected_name.is_empty():
		enter_world_button.disabled = false
		status_label.text = "Select a character first."
		return
	_returning_to_chars = false  # we're choosing to enter the world again
	status_label.text = "Sending enter-world request for %s..." % selected_name
	_send({"type": "enter_world", "character_name": selected_name})

func handle_response(data: Dictionary):
	var msg_type: String = data.get("type", "")
	# While returning to character select, ignore in-world stream messages so the
	# gameplay view doesn't pop back up before the player re-enters.
	if _returning_to_chars and msg_type in ["root_info", "gameplay_state", \
			"zone_transfer", "target_description", "entity_snapshot"]:
		return

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
					status_label.text = "Registered! Your master-account password is: " + pw + "  (login is pre-filled)"
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
				pass  # proxy auto-handles the world account; no manual step
				pass
				create_world_account_button.disabled = false
				login_world_button.disabled = false
				world_access_password_field.visible = bool(selected_world.get("has_password", false))
				if data.get("has_world_account", false):
					status_label.text = "Setting up your character slot..."
				else:
					if bool(selected_world.get("has_password", false)):
						status_label.text = "Setting up your character slot..."
					else:
						status_label.text = "Setting up your character slot..."
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
				_set_phase(PHASE_CHARACTER)
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

		"root_info":
			_show_gameplay_view(data)

		"gameplay_state":
			if gameplay_view and gameplay_view.visible and gameplay_view.has_method("update_state"):
				gameplay_view.update_state(data)
			else:
				_show_gameplay_view(data)

		"zone_transfer":
			_show_gameplay_view(data)
			if gameplay_view and gameplay_view.has_method("set_zone_transfer"):
				gameplay_view.set_zone_transfer(data)

		"target_description":
			_show_gameplay_view(data)
			if gameplay_view and gameplay_view.has_method("set_target_description"):
				gameplay_view.set_target_description(data.get("target", {}))

		"entity_snapshot":
			var view := _ensure_gameplay_view()
			if view.has_method("set_entities"):
				var entities_val = data.get("entities", [])
				if entities_val is Array:
					view.set_entities(entities_val)
			if view.has_method("apply_vfx_events"):
				var events_val = data.get("events", [])
				if events_val is Array and not events_val.is_empty():
					view.apply_vfx_events(events_val)

		"game_text":
			if gameplay_view and gameplay_view.has_method("append_game_text"):
				gameplay_view.append_game_text(str(data.get("text", "")))

		"text_messages":
			if gameplay_view and gameplay_view.has_method("append_text_messages"):
				gameplay_view.append_text_messages(data.get("messages", []))

		"world_time":
			world_time = {
				"hour": int(data.get("hour", 0)),
				"minute": int(data.get("minute", 0)),
			}
			_update_gameplay_clock()

		"set_selection":
			if gameplay_view and gameplay_view.has_method("on_server_selection"):
				gameplay_view.on_server_selection(
					int(data.get("tgt_sim_id", 0)),
					int(data.get("char_index", 0))
				)

		"mouse_select":
			if gameplay_view and gameplay_view.has_method("on_server_selection_by_mob"):
				gameplay_view.on_server_selection_by_mob(
					int(data.get("target_id", 0)),
					int(data.get("char_index", 0))
				)

		"gameplay_command_result":
			status_label.text = data.get("message", "Gameplay command sent.")
			if gameplay_view and gameplay_view.has_method("append_game_text"):
				gameplay_view.append_game_text(str(data.get("message", "")))

		"inventory", "cursor_item", "loot", "npc_window", "npc_dialog_start", \
		"npc_dialog", "npc_window_close", "vendor_stock", "journal_entry", "spellbook", \
		"cheat_result", "begin_casting", "play_sound", "alliance_info", "alliance_invite", \
		"player_death", "player_alive":
			if gameplay_view and gameplay_view.has_method("handle_ui_message"):
				gameplay_view.handle_ui_message(data)

		"error":
			create_world_account_button.disabled = false
			login_world_button.disabled = false
			create_character_button.disabled = false
			enter_world_button.disabled = false
			status_label.text = "Error: " + data.get("message", "")

func _populate_world_list():
	_set_phase(PHASE_WORLD)
	world_list.clear()

	if worlds.is_empty():
		status_label.text = "No worlds online."
		join_button.visible = false
		return

	for w in worlds:
		var world_name: String = w.get("name", "???")
		var players: int = w.get("num_players", 0)
		var max_p: int = w.get("max_players", 0)
		var label := "%s  (%d/%d players)" % [world_name, players, max_p]
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
