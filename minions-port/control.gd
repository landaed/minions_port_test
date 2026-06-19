extends Control

const GAMEPLAY_VIEW_SCENE := preload("res://gameplay_view.tscn")
const CharacterRigScript := preload("res://world/character_rig.gd")
const CHAR_ASSET_DIR := "res://assets/characters/"

var socket := WebSocketPeer.new()
var connected := false
var gameplay_view: Control = null
var world_time := {"hour": 0, "minute": 0}

# --- Menu visuals: lit 3D stages (pedestals) the camera pans between. ---
var _stage_viewport: SubViewport = null
var _form_panel: PanelContainer = null
var _cam: Camera3D = null
var _cam_pos := Vector3(0, 1.3, 4.6)        # current smoothed camera position
var _cam_look := Vector3(0, 1.05, 0)        # current smoothed look target
var _cam_target_pos := Vector3(0, 1.3, 4.6) # where the camera is gliding to
var _cam_target_look := Vector3(0, 1.05, 0)
# Three pedestals: login (idling mobs), select (your characters), create (preview).
const PED_LOGIN := Vector3(0, 0, 0)
const PED_SELECT := Vector3(10, 0, 0)
const PED_CREATE := Vector3(20, 0, 0)
var _login_pivot: Node3D = null
var _select_pivot: Node3D = null
var _create_pivot: Node3D = null
var _create_rig: Node3D = null
var _create_model_key := ""
var _select_rigs: Array = []                # account-character rigs on the select pedestal
var _selected_char_index := 0

# Default per-part skin texture indices by race+sex (mirrors the server's
# mud/world/appearance.py _MTEX/_FTEX) so preview models show the right race
# instead of the shared elf-male base skin baked into every GLB.
const RACE_LOOKS_MALE := {
	"Human": {"head":1,"arms":0,"legs":0,"body":0,"feet":0,"hands":0},
	"Elf": {"head":3,"arms":2,"legs":2,"body":2,"feet":2,"hands":2},
	"Titan": {"head":38,"arms":70,"legs":70,"body":72,"feet":0,"hands":70},
	"Gnome": {"head":29,"arms":32,"legs":33,"body":34,"feet":33,"hands":33},
	"Dwarf": {"head":6,"arms":5,"legs":5,"body":6,"feet":5,"hands":5},
	"Halfling": {"head":8,"arms":7,"legs":7,"body":8,"feet":7,"hands":7},
	"Drakken": {"head":10,"arms":10,"legs":10,"body":12,"feet":10,"hands":11},
	"Orc": {"head":42,"arms":79,"legs":80,"body":81,"feet":77,"hands":79},
	"Troll": {"head":31,"arms":52,"legs":53,"body":54,"feet":53,"hands":53},
}
const RACE_LOOKS_FEMALE := {
	"Human": {"head":5,"arms":4,"legs":4,"body":5,"feet":4,"hands":4},
	"Elf": {"head":4,"arms":3,"legs":3,"body":4,"feet":3,"hands":3},
	"Titan": {"head":39,"arms":71,"legs":72,"body":73,"feet":0,"hands":71},
	"Gnome": {"head":33,"arms":54,"legs":55,"body":56,"feet":55,"hands":55},
	"Dwarf": {"head":7,"arms":6,"legs":6,"body":7,"feet":6,"hands":6},
	"Halfling": {"head":9,"arms":9,"legs":8,"body":10,"feet":8,"hands":9},
	"Drakken": {"head":12,"arms":16,"legs":17,"body":18,"feet":17,"hands":17},
	"Orc": {"head":43,"arms":80,"legs":81,"body":82,"feet":78,"hands":80},
	"Troll": {"head":36,"arms":67,"legs":67,"body":69,"feet":67,"hands":67},
}
# Monster models to idle on the login pedestal (DTS paths -> <key>.glb).
const LOGIN_MOB_MODELS := [
	"undead/skeleton", "goblin_male", "orc_male", "troll_male", "imp/imp",
	"gargoyle/gargoyle", "insects/spider",
]

func _appearance_for(race: String, sex: String) -> Dictionary:
	var tbl := RACE_LOOKS_FEMALE if str(sex).to_lower().begins_with("f") else RACE_LOOKS_MALE
	return tbl.get(race, {})

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
const PHASE_CHARACTER := "character"   # pick from your characters (camera on the roster)
const PHASE_CREATE := "create"         # design a new character (camera on the forge)
var _current_phase := ""
var _make_new_button: Button = null
var _back_button: Button = null

func _phase_login_controls() -> Array:
	return [server_field, connect_button, username_field, password_field, email_field, login_button, register_button]

func _phase_world_controls() -> Array:
	return [world_list, join_button]

func _phase_world_account_controls() -> Array:
	return [fantasy_name_field, world_access_password_field, create_world_account_button, world_password_field, login_world_button]

func _phase_character_controls() -> Array:
	return [character_list, enter_world_button, _make_new_button]

func _phase_create_controls() -> Array:
	return [character_name_field, race_option, class_option, sex_option, _build_option, _stats_section, create_character_button, _back_button]

func _all_flow_controls() -> Array:
	return _phase_login_controls() + _phase_world_controls() + _phase_world_account_controls() + _phase_character_controls() + _phase_create_controls()

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
			title_label.text = "Log In or Register"
			_show_only(_phase_login_controls())
			_focus_pedestal(PED_LOGIN, 6.4, 1.8)
		PHASE_WORLD:
			title_label.text = "Choose a World"
			_show_only(_phase_world_controls())
			_focus_pedestal(PED_LOGIN, 6.4, 1.8)
		PHASE_WORLD_ACCOUNT:
			title_label.text = "World Character Slot"
			_show_only(_phase_world_account_controls())
			# Access password only matters when the world is password-gated.
			world_access_password_field.visible = bool(selected_world.get("has_password", false))
			_focus_pedestal(PED_LOGIN, 6.4, 1.8)
		PHASE_CHARACTER:
			title_label.text = "Choose Your Hero"
			_show_only(_phase_character_controls())
			_focus_select_character(_selected_char_index)
		PHASE_CREATE:
			title_label.text = "Create a Character"
			_show_only(_phase_create_controls())
			_focus_pedestal(PED_CREATE, 4.4, 1.4)
			_update_creation_preview()

func _focus_pedestal(pos: Vector3, dist: float = 5.0, height: float = 1.5) -> void:
	_cam_target_pos = pos + Vector3(0.5, height, dist)
	_cam_target_look = pos + Vector3(0.0, 1.0, 0.0)

func _focus_select_character(index: int) -> void:
	var n := _select_rigs.size()
	if n == 0:
		_focus_pedestal(PED_SELECT, 5.8, 1.7)
		return
	index = clampi(index, 0, n - 1)
	_selected_char_index = index
	var rig = _select_rigs[index]
	var cx: float = rig.position.x if (rig and is_instance_valid(rig)) else 0.0
	var world := PED_SELECT + Vector3(cx, 0, 0)
	_cam_target_pos = world + Vector3(0.0, 1.25, 3.6)
	_cam_target_look = world + Vector3(0.0, 1.0, 0.0)
	# Dim the others, spotlight the selected.
	for i in range(n):
		var r = _select_rigs[i]
		if r and is_instance_valid(r) and r.has_method("set_fade"):
			r.set_fade(1.0 if i == index else 0.55)

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

	# 3D stage in a SubViewport with three pedestals the camera pans between.
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
	env.ambient_light_color = Color(0.34, 0.40, 0.55)
	env.ambient_light_energy = 0.85
	env.fog_enabled = true
	env.fog_light_color = Color(0.06, 0.07, 0.12)
	env.fog_density = 0.012
	we.environment = env
	_stage_viewport.add_child(we)

	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-32, 40, 0)
	key.light_energy = 1.7
	key.light_color = Color(1.0, 0.92, 0.78)
	_stage_viewport.add_child(key)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-8, -130, 0)
	fill.light_energy = 0.55
	fill.light_color = Color(0.55, 0.68, 1.0)
	_stage_viewport.add_child(fill)

	_login_pivot = _make_pedestal(PED_LOGIN, 2.4)
	_select_pivot = _make_pedestal(PED_SELECT, 3.4)
	_create_pivot = _make_pedestal(PED_CREATE, 1.7)

	_cam = Camera3D.new()
	_cam.fov = 42.0
	_cam.position = _cam_pos
	_stage_viewport.add_child(_cam)
	_cam.look_at(_cam_look, Vector3.UP)

	_spawn_login_mobs()
	_update_preview_model("Human", "Male", "")
	_build_form_chrome()
	set_process(true)

func _make_pedestal(pos: Vector3, radius: float) -> Node3D:
	# A dark stone disc with a soft spotlight; returns a pivot Node3D at its top.
	var ped := MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.top_radius = radius
	cyl.bottom_radius = radius + 0.2
	cyl.height = 0.2
	ped.mesh = cyl
	ped.position = pos + Vector3(0, -0.1, 0)
	var pmat := StandardMaterial3D.new()
	pmat.albedo_color = Color(0.09, 0.10, 0.14)
	pmat.metallic = 0.4
	pmat.roughness = 0.55
	ped.material_override = pmat
	_stage_viewport.add_child(ped)
	var spot := OmniLight3D.new()
	spot.position = pos + Vector3(-1.4, 2.6, 2.0)
	spot.light_energy = 3.0
	spot.light_color = Color(0.8, 0.88, 1.0)
	spot.omni_range = radius + 8.0
	_stage_viewport.add_child(spot)
	var pivot := Node3D.new()
	pivot.position = pos
	_stage_viewport.add_child(pivot)
	return pivot

# Build a character/monster rig, dressed in the correct race+sex skin.
func _make_rig(race: String, sex: String, model: String) -> Node3D:
	var path := _glb_for(race, sex, model)
	if path == "":
		return null
	var rig = CharacterRigScript.new()
	if not rig.setup(path, 180.0):  # face the camera (+Z)
		rig.queue_free()
		return null
	if model == "":  # playable race -> apply its default skin
		var look := _appearance_for(race, sex)
		if not look.is_empty():
			rig.apply_appearance(look)
	return rig

func _spawn_login_mobs() -> void:
	# A few monsters idling on the first pedestal before you log in.
	if _login_pivot == null:
		return
	for c in _login_pivot.get_children():
		c.queue_free()
	var pool := LOGIN_MOB_MODELS.duplicate()
	pool.shuffle()
	var n: int = min(3, pool.size())
	var spacing := 1.6
	for i in range(n):
		var rig := _make_rig("", "", pool[i])
		if rig == null:
			continue
		rig.position = Vector3((i - (n - 1) / 2.0) * spacing, 0, 0)
		rig.rotation.y = deg_to_rad(randf_range(-25, 25))
		_login_pivot.add_child(rig)

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
	# The creation-pedestal preview, dressed in the chosen race+sex skin.
	if _create_pivot == null:
		return
	var path := _glb_for(race, sex, model)
	if path == "":
		return
	if path != _create_model_key:
		_create_model_key = path
		if _create_rig and is_instance_valid(_create_rig):
			_create_rig.queue_free()
		_create_rig = _make_rig(race, sex, model)
		if _create_rig:
			_create_pivot.add_child(_create_rig)
	_apply_preview_build()

func _apply_preview_build() -> void:
	# Approximate the chosen body build by scaling the preview (the port ships one
	# mesh per race/sex, so Slender/Average/Burly nudge the silhouette).
	if _create_rig == null or not is_instance_valid(_create_rig):
		return
	var look: int = _build_option.selected if _build_option else 1
	var widths := [0.9, 1.0, 1.12]
	var wide: float = widths[clampi(look, 0, 2)]
	_create_rig.scale = Vector3(wide, 1.0, wide)

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

	# "Make New Character" lives on the roster screen, under Enter World.
	_make_new_button = Button.new()
	_make_new_button.text = "+ Make New Character"
	_make_new_button.pressed.connect(func():
		GameAudio.ui_accept()
		_set_phase(PHASE_CREATE))
	login_panel.add_child(_make_new_button)
	login_panel.move_child(_make_new_button, enter_world_button.get_index() + 1)

	# "Back" returns from the creation screen to the roster.
	_back_button = Button.new()
	_back_button.text = "← Back to Characters"
	_back_button.pressed.connect(func():
		GameAudio.ui_cancel()
		_set_phase(PHASE_CHARACTER))
	login_panel.add_child(_back_button)
	login_panel.move_child(_back_button, create_character_button.get_index() + 1)

	# Selecting a character on the roster zooms the camera onto it.
	character_list.item_selected.connect(func(idx): _focus_select_character(int(idx)))

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
	# Smoothly glide the camera toward the active pedestal / highlighted character.
	if _cam and is_instance_valid(_cam):
		var t := clampf(delta * 3.0, 0.0, 1.0)
		_cam_pos = _cam_pos.lerp(_cam_target_pos, t)
		_cam_look = _cam_look.lerp(_cam_target_look, t)
		_cam.position = _cam_pos
		_cam.look_at(_cam_look, Vector3.UP)

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
				# Reset the bonus allocation and return to the roster (which the
				# server refreshes via a fresh character_list).
				for k in STAT_KEYS:
					_stat_bonus[k] = 0
					if _stat_value_labels.has(k):
						_stat_value_labels[k].text = "0"
				_update_stat_points_label()
				_set_phase(PHASE_CHARACTER)
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
					# Activity-driven replication: "full" snapshots are authoritative
					# (erase absent); deltas carry an explicit "removed" id list and
					# leave idle entities cached. Legacy servers omit both -> full=true.
					var removed_val = data.get("removed", [])
					var full_val: bool = bool(data.get("full", true))
					view.set_entities(entities_val, removed_val if removed_val is Array else [], full_val)
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
	_rebuild_roster_pedestal()
	if characters.is_empty():
		status_label.text = "No characters yet — press Make New Character."
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
	_focus_select_character(0)
	status_label.text = "Select a hero to enter the world, or make a new one."

func _rebuild_roster_pedestal() -> void:
	# Stand each of your characters on the roster pedestal, in their race+sex skin.
	if _select_pivot == null:
		return
	for r in _select_rigs:
		if r and is_instance_valid(r):
			r.queue_free()
	_select_rigs.clear()
	var n := characters.size()
	if n == 0:
		return
	var spacing := 2.4
	for i in range(n):
		var c = characters[i]
		var rig := _make_rig(str(c.get("race", "Human")), str(c.get("sex", "Male")), "")
		if rig == null:
			_select_rigs.append(null)
			continue
		rig.position = Vector3((i - (n - 1) / 2.0) * spacing, 0, 0)
		_select_pivot.add_child(rig)
		_select_rigs.append(rig)
