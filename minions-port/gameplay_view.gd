extends Control

signal command_requested(command_type: String, payload: Dictionary)

const MOVE_SPEED := 8.0
# --- server reconciliation (see _update_reconcile_error) ---
# Entity snapshots describe where the server thought the player was one poll
# interval + transit ago, so while moving the raw client-vs-server difference is
# mostly latency, not drift. Desync is therefore measured against the client's
# recent trajectory (position history), which lets the dead zone be ~6x smaller
# than the old 2u (originally 8u) threshold without rubber-banding.
const SERVER_RECONCILE_SNAP_THRESHOLD := 12.0  # true teleports: jump immediately
const RECONCILE_DEAD_ZONE := 0.35       # ignore drift below this (jitter floor)
const RECONCILE_HISTORY_WINDOW := 0.8   # seconds of client positions to match against
const RECONCILE_RATE := 8.0             # fraction of the error consumed per second
const RECONCILE_MAX_SPEED := 10.0       # cap correction speed (units/sec)
const CAMERA_ZOOM_MIN := 2.5
const CAMERA_ZOOM_MAX := 14.0
const CAMERA_ZOOM_STEP := 1.0
const CAMERA_COLLISION_MASK := 1  # world geometry only; ignore entity markers on layer 2
const CAMERA_COLLISION_PADDING := 0.35
const CAMERA_COLLISION_MIN_DISTANCE := 1.2
const DOF_ENABLED := true
const DOF_FOCUS_MIN := 4.0
const DOF_FOCUS_MAX := 120.0
const DOF_DEFAULT_FOCUS := 36.0
const DOF_FOCUS_SMOOTH_SPEED := 5.0
const DOF_FOCUS_RAY_LENGTH := 160.0
const DOF_NEAR_MARGIN := 999.0  # near blur disabled; keep player/weapon readable
const DOF_FAR_MARGIN := 28.0
const DOF_NEAR_TRANSITION := 12.0
const DOF_FAR_TRANSITION := 34.0
const DOF_BLUR_AMOUNT := 0.025
const INPUT_SYNC_INTERVAL := 0.05  # send movement inputs to server every 50ms
const LOOK_SENSITIVITY := 0.003
const JUMP_VELOCITY := 7.0
const GRAVITY := 20.0
const PLAYER_FOOT_OFFSET := 0.9
# Torque's player datablock allowed ~1.0+ step heights and several MoM stair
# meshes (and the 1.5x-scaled guard towers) have risers above 0.75, so the old
# limit left the player bumping into stairs. 1.1 climbs every authored staircase
# without letting the player walk up walls.
const PLAYER_STEP_UP_HEIGHT := 1.1
const PLAYER_STEP_FORWARD_SCALE := 0.9
const ENTITY_INTERPOLATION_SPEED := 14.0
const ENTITY_SNAP_DISTANCE := 8.0
const ENTITY_DEATH_DESPAWN_DELAY := 2.75
const ENTITY_FLOOR_PROBE_UP := 4.0
const ENTITY_FLOOR_PROBE_DOWN := 8.0
const ENTITY_MAX_DISPLAY_DISTANCE := 20.0
const ENTITY_CAPSULE_HALF_HEIGHT := 0.7
const ENTITY_SELECTION_DISTANCE := 150.0
const TERRAIN_MASK := 4  # collision bit 3: terrain only (set by zone_loader), for ground-snap rays
const ZoneLoaderScript := preload("res://world/zone_loader.gd")
const ZONE_SCENE_ROOT := "res://world/zones/"
const CharacterRigScript := preload("res://world/character_rig.gd")
const DEFAULT_ZONE := "trinst"
const CHAR_ASSET_DIR := "res://assets/characters/"
const UICommonScript := preload("res://ui/ui_common.gd")
const GameWindowScript := preload("res://ui/game_window.gd")
const SlotButtonScript := preload("res://ui/slot_button.gd")
const InventoryWindowScript := preload("res://ui/inventory_window.gd")
const LootWindowScript := preload("res://ui/loot_window.gd")
const NpcWindowScript := preload("res://ui/npc_window.gd")
const JournalWindowScript := preload("res://ui/journal_window.gd")
const SpellbookWindowScript := preload("res://ui/spellbook_window.gd")
const CheatWindowScript := preload("res://ui/cheat_window.gd")
const HotbarScript := preload("res://ui/hotbar.gd")

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
var _player_rig: Node3D = null  # animated player avatar (CharacterRig)
var _player_model_key := ""     # which glb the avatar currently uses
var _player_attack_until := 0.0 # local attack-animation trigger (seconds)
var _camera_zoom := 7.0
var _pos_history: Array = []        # recent [{t, pos}] samples for latency-aware reconcile
var _reconcile_error := Vector3.ZERO  # smoothed-out correction toward the server position
var _camera_base_local_offset := Vector3.ZERO
var _camera_attributes: CameraAttributesPractical = null
var _dof_focus_distance := DOF_DEFAULT_FOCUS
var _dead_entity_remove_at: Dictionary = {}

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
var _looking_at_dead := false
var _looked_entity_id := 0
var _looking_at_world := ""  # name of the building/world geometry under the crosshair (debug)
var _debug_visible := false

# --- game windows (inventory / loot / NPC dialog / journal / spellbook) ---
var inventory_window: InventoryWindow
var loot_window: LootWindow
var npc_window: NpcWindow
var journal_window: JournalWindow
var spellbook_window: SpellbookWindow
var cheat_window: CheatWindow
var hotbar: Hotbar
var cursor_item_ghost: Button   # follows the mouse while an item is on the cursor
var _interaction_active := false
var _ui_char_name := ""          # journal/hotbar persistence key
var _ui_char_id := 0             # server character DB id for inventory/spell calls
var _last_inventory: Dictionary = {}
var _last_spellbook: Dictionary = {}
var _ui_poll_timer := 0.0

func _ready():
	set_process_input(true)
	# Walk terrain at constant horizontal speed (don't lose ground to slopes) and
	# stay snapped to the surface, so client prediction tracks the server's flat
	# movement model instead of falling behind and rubber-banding on hills.
	player_body.floor_constant_speed = true
	player_body.floor_snap_length = 1.35
	player_body.floor_max_angle = deg_to_rad(68.0)
	# Animated player avatar. The real race/sex isn't known until the first self
	# snapshot, so build the rig node now and load the model in _ensure_player_model
	# once we know it. The capsule stays visible until the model loads, so the
	# player is never invisible.
	_player_rig = CharacterRigScript.new()
	_player_rig.position = Vector3(0.0, -0.9, 0.0)  # feet at the capsule bottom
	player_body.add_child(_player_rig)
	_camera_base_local_offset = camera.position
	_camera_zoom = _camera_base_local_offset.z
	_apply_camera_zoom()
	_setup_dynamic_dof()
	_build_hud()
	_build_game_windows()
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
	hint_label.text = "Tab: target  •  Q: auto-attack  •  E: talk/loot  •  1-0: hotbar  •  I: inventory  •  P: spells  •  J: journal  •  U: unstuck  •  F3: debug"
	bottom.add_child(hint_label)
	hotbar = HotbarScript.new()
	hotbar.action_triggered.connect(_on_hotbar_action)
	bottom.add_child(hotbar)

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

# ---------------------------------------------------------------------------
# Game windows: inventory / loot / NPC dialog+vendor / journal / spellbook
# ---------------------------------------------------------------------------
func _build_game_windows():
	inventory_window = InventoryWindowScript.new()
	inventory_window.position = Vector2(620, 90)
	inventory_window.inv_slot_clicked.connect(_on_inventory_slot_clicked)
	inventory_window.destroy_cursor_requested.connect(_on_destroy_cursor)
	add_child(inventory_window)

	loot_window = LootWindowScript.new()
	loot_window.position = Vector2(360, 200)
	loot_window.loot_slot_clicked.connect(_on_loot_slot_clicked)
	loot_window.take_all_requested.connect(_on_take_all_loot)
	loot_window.looting_ended.connect(func(): _request_server_command("end_looting"))
	add_child(loot_window)

	npc_window = NpcWindowScript.new()
	npc_window.position = Vector2(280, 110)
	npc_window.choice_selected.connect(_on_dialog_choice)
	npc_window.buy_requested.connect(func(index): _request_server_command("buy_item", {"index": index}))
	npc_window.sell_requested.connect(func(slot): _request_server_command("sell_item", {"slot": slot}))
	npc_window.interaction_ended.connect(_on_interaction_window_closed)
	add_child(npc_window)

	journal_window = JournalWindowScript.new()
	journal_window.position = Vector2(120, 120)
	add_child(journal_window)

	spellbook_window = SpellbookWindowScript.new()
	spellbook_window.position = Vector2(460, 120)
	spellbook_window.cast_spell.connect(func(book_slot): _request_server_command("spell_slot", {"char_id": _ui_char_id, "slot": book_slot}))
	spellbook_window.use_skill.connect(func(skill_name): _request_server_command("use_ability", {"ability_name": skill_name}))
	add_child(spellbook_window)

	cheat_window = CheatWindowScript.new()
	cheat_window.position = Vector2(540, 60)
	cheat_window.cheat_requested.connect(func(action, params):
		_request_server_command("cheat", {"action": action, "params": params}))
	add_child(cheat_window)

	for w in [inventory_window, loot_window, npc_window, journal_window, spellbook_window, cheat_window]:
		w.visibility_changed.connect(_on_window_visibility_changed)

	# Item-on-cursor ghost that follows the mouse while rearranging inventory.
	cursor_item_ghost = Button.new()
	cursor_item_ghost.visible = false
	cursor_item_ghost.disabled = true
	cursor_item_ghost.custom_minimum_size = Vector2(40, 40)
	cursor_item_ghost.expand_icon = true
	cursor_item_ghost.mouse_filter = Control.MOUSE_FILTER_IGNORE
	cursor_item_ghost.z_index = 200
	UICommonScript.style_button(cursor_item_ghost)
	add_child(cursor_item_ghost)

func _on_window_visibility_changed():
	# Free the mouse while any window is up; back to mouselook when all close.
	if not visible:
		return
	if _ui_open():
		_release_mouse()
	else:
		_capture_mouse()

func _toggle_inventory():
	if inventory_window.visible:
		inventory_window.close_window()
	else:
		_request_server_command("get_inventory")
		inventory_window.open_window()

func _toggle_journal():
	journal_window.toggle_window()

func _toggle_spellbook():
	if spellbook_window.visible:
		spellbook_window.close_window()
	else:
		_request_server_command("get_spellbook")
		spellbook_window.apply_skills(_abilities())
		spellbook_window.open_window()

func _toggle_cheats():
	if cheat_window.visible:
		cheat_window.close_window()
	else:
		_request_server_command("cheat", {"action": "status", "params": {}})
		cheat_window.open_window()

func _on_inventory_slot_clicked(slot: int, alt: bool, ctrl: bool):
	if ctrl:
		_request_server_command("inv_use", {"char_id": _ui_char_id, "slot": slot})
	elif alt:
		_request_server_command("inv_click_alt", {"char_id": _ui_char_id, "slot": slot})
	else:
		_request_server_command("inv_click", {"char_id": _ui_char_id, "slot": slot})

func _on_destroy_cursor():
	_request_server_command("destroy_cursor")
	_push_log("Destroyed the item on the cursor.")

func _on_loot_slot_clicked(slot: int):
	_request_server_command("loot_item", {"slot": slot, "alt": true})

func _on_take_all_loot():
	# Loot slot 0 repeatedly: the server compacts the table after each take and
	# pushes a refresh, so taking the head of the list drains everything.
	_request_server_command("loot_item", {"slot": 0, "alt": true})

func _on_dialog_choice(index: int):
	_request_server_command("dialog_choice", {"index": index})

func _on_interaction_window_closed():
	if _interaction_active:
		_interaction_active = false
		_request_server_command("end_interaction")

func _ensure_interaction(npc: String):
	if not _interaction_active:
		_interaction_active = true
		npc_window.begin(npc)
	elif not npc.is_empty():
		npc_window.title_label.text = npc

func handle_ui_message(data: Dictionary):
	match str(data.get("type", "")):
		"inventory":
			_last_inventory = data
			_ui_char_id = int(data.get("char_id", _ui_char_id))
			var cname := str(data.get("char_name", ""))
			if not cname.is_empty() and cname != _ui_char_name:
				_ui_char_name = cname
				journal_window.load_for(cname)
				hotbar.load_for(cname)
				_rebuild_ability_bar()
			inventory_window.apply_snapshot(data)
			npc_window.set_sellables(data.get("items", []))
			_update_cursor_ghost(data.get("cursor"))
		"cursor_item":
			var item = data.get("item")
			inventory_window.set_cursor_item(item if item is Dictionary else {})
			_update_cursor_ghost(item)
		"loot":
			var items = data.get("items", {})
			loot_window.apply_loot(items if items is Dictionary else {})
		"npc_window":
			_ensure_interaction(str(data.get("name", "")))
		"npc_dialog_start":
			_ensure_interaction(str(data.get("npc", "")))
			if bool(data.get("has_dialog", false)):
				npc_window.add_line(str(data.get("text", "")), data.get("choices", []))
			_maybe_add_journal(data.get("journal"))
		"npc_dialog":
			_ensure_interaction("")
			npc_window.add_line(str(data.get("text", "")), data.get("choices", []))
			_maybe_add_journal(data.get("journal"))
		"npc_window_close":
			_interaction_active = false
			if npc_window.visible:
				npc_window.visible = false
				_on_window_visibility_changed()
		"vendor_stock":
			if bool(data.get("is_vendor", false)):
				_ensure_interaction("")
				npc_window.set_stock(data.get("items", []), float(data.get("markup", 1.0)))
				npc_window.set_sellables(_last_inventory.get("items", []))
				_request_server_command("get_inventory")
		"journal_entry":
			_maybe_add_journal(data)
		"spellbook":
			_last_spellbook = data
			_ui_char_id = int(data.get("char_id", _ui_char_id))
			spellbook_window.apply_spellbook(data)
			_rebuild_ability_bar()
			hotbar.update_cooldowns(_abilities(), data.get("spells", []))
		"cheat_result":
			cheat_window.handle_result(data)
			var cheat_msg := str(data.get("message", ""))
			if not cheat_msg.is_empty() and str(data.get("action", "")) not in ["list_items", "list_spells", "status"]:
				_push_log("[Cheat] " + cheat_msg)

func _maybe_add_journal(journal) -> void:
	if not (journal is Dictionary) or journal.is_empty():
		return
	var topic := str(journal.get("topic", ""))
	var entry := str(journal.get("entry", ""))
	var text := str(journal.get("text", ""))
	if topic.is_empty() and entry.is_empty():
		return
	if journal_window.add_entry(topic, entry, text):
		_push_log("Journal updated: %s — %s  (press J)" % [topic, entry])

func _update_cursor_ghost(item) -> void:
	if item is Dictionary and not item.is_empty():
		cursor_item_ghost.icon = UICommonScript.item_icon(str(item.get("bitmap", "")))
		cursor_item_ghost.text = "" if cursor_item_ghost.icon != null else str(item.get("name", "?")).left(8)
		cursor_item_ghost.visible = true
	else:
		cursor_item_ghost.visible = false

func _apply_camera_zoom() -> void:
	if camera == null:
		return
	_camera_zoom = clampf(_camera_zoom, CAMERA_ZOOM_MIN, CAMERA_ZOOM_MAX)
	_update_camera_collision()


func _desired_camera_local_offset() -> Vector3:
	var desired := _camera_base_local_offset
	if desired == Vector3.ZERO and camera != null:
		desired = camera.position
	desired.z = _camera_zoom
	return desired


func _update_camera_collision() -> void:
	if camera == null or camera_pitch == null or player_body == null:
		return
	var desired_local := _desired_camera_local_offset()
	var desired_len := desired_local.length()
	if desired_len <= 0.001:
		camera.position = desired_local
		return
	var pivot := camera_pitch.global_position
	var desired_global := camera_pitch.to_global(desired_local)
	var world := player_body.get_world_3d()
	if world == null:
		camera.position = desired_local
		return
	var query := PhysicsRayQueryParameters3D.create(pivot, desired_global)
	query.collide_with_areas = false
	query.collide_with_bodies = true
	query.collision_mask = CAMERA_COLLISION_MASK
	query.exclude = [player_body]
	var hit := world.direct_space_state.intersect_ray(query)
	if hit and hit.has("position"):
		var clipped_len := clampf(
			pivot.distance_to(hit.position) - CAMERA_COLLISION_PADDING,
			CAMERA_COLLISION_MIN_DISTANCE,
			desired_len
		)
		camera.position = desired_local.normalized() * clipped_len
	else:
		camera.position = desired_local


func _adjust_camera_zoom(direction: float) -> void:
	_camera_zoom = clampf(_camera_zoom + direction * CAMERA_ZOOM_STEP, CAMERA_ZOOM_MIN, CAMERA_ZOOM_MAX)
	_apply_camera_zoom()


func _setup_dynamic_dof() -> void:
	if camera == null or not DOF_ENABLED:
		return
	_camera_attributes = CameraAttributesPractical.new()
	_camera_attributes.dof_blur_near_enabled = false
	_camera_attributes.dof_blur_far_enabled = true
	_camera_attributes.dof_blur_amount = DOF_BLUR_AMOUNT
	_camera_attributes.dof_blur_near_transition = DOF_NEAR_TRANSITION
	_camera_attributes.dof_blur_far_transition = DOF_FAR_TRANSITION
	camera.attributes = _camera_attributes
	_apply_dof_focus(DOF_DEFAULT_FOCUS)


func _update_dynamic_dof(delta: float) -> void:
	if _camera_attributes == null or camera == null or sub_viewport == null:
		return
	var target_focus: float = DOF_DEFAULT_FOCUS
	var center: Vector2 = Vector2(sub_viewport.size) * 0.5
	var from: Vector3 = camera.project_ray_origin(center)
	var to: Vector3 = from + camera.project_ray_normal(center) * DOF_FOCUS_RAY_LENGTH
	var query: PhysicsRayQueryParameters3D = PhysicsRayQueryParameters3D.create(from, to)
	query.collide_with_areas = false
	query.collide_with_bodies = true
	query.exclude = [player_body]
	var hit: Dictionary = player_body.get_world_3d().direct_space_state.intersect_ray(query)
	if hit and hit.has("position"):
		target_focus = from.distance_to(hit.position)
	target_focus = clampf(target_focus, DOF_FOCUS_MIN, DOF_FOCUS_MAX)
	var blend: float = clampf(delta * DOF_FOCUS_SMOOTH_SPEED, 0.0, 1.0)
	_dof_focus_distance = lerpf(_dof_focus_distance, target_focus, blend)
	_apply_dof_focus(_dof_focus_distance)


func _apply_dof_focus(focus_distance: float) -> void:
	if _camera_attributes == null:
		return
	_camera_attributes.dof_blur_near_distance = maxf(DOF_FOCUS_MIN, focus_distance - DOF_NEAR_MARGIN)
	_camera_attributes.dof_blur_far_distance = minf(DOF_FOCUS_MAX, focus_distance + DOF_FAR_MARGIN)


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

func _find_zone_glb_name(node: Node) -> String:
	# Walk up to the interior/building node tagged with its source glb name.
	var n: Node = node
	while n != null:
		if n.has_meta("zone_glb"):
			return str(n.get_meta("zone_glb"))
		n = n.get_parent()
	return ""

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
	_looking_at_world = ""
	var dead := false
	if not result.is_empty():
		var collider = result.get("collider")
		if collider != null and collider is Node3D and int(collider.get_meta("entity_id", 0)) > 0:
			looking = true
			var ent: Dictionary = collider.get_meta("entity", {})
			enemy = bool(ent.get("is_enemy", false))
			dead = bool(ent.get("dead", false)) or float(ent.get("health", 1.0)) <= 0.0
			_looked_entity_id = int(collider.get_meta("entity_id", 0))
		elif collider != null and collider is Node:
			# World geometry — report which building, to help identify e.g. the gate.
			_looking_at_world = _find_zone_glb_name(collider)
	_looking_at_entity = looking
	_looking_at_enemy = enemy
	_looking_at_dead = dead
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
	_apply_camera_zoom()
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

func _set_marker_highlight(body: StaticBody3D, on: bool):
	var rig = body.get_meta("rig", null)
	if rig != null and is_instance_valid(rig):
		rig.set_highlight(on)
		return
	var mesh: MeshInstance3D = body.get_meta("mesh", null)
	if mesh == null:
		return
	if on:
		var mat := StandardMaterial3D.new()
		mat.albedo_color = Color(1.0, 1.0, 0.2, 1.0)  # bright yellow highlight
		mat.emission_enabled = true
		mat.emission = Color(1.0, 1.0, 0.2, 1.0)
		mat.emission_energy_multiplier = 0.5
		mesh.material_override = mat
	else:
		var prev_entity: Dictionary = body.get_meta("entity", {})
		var restore := StandardMaterial3D.new()
		restore.albedo_color = _entity_color(prev_entity)
		mesh.material_override = restore

func _highlight_entity(key: String):
	if not _highlighted_entity_key.is_empty() and replicated_entity_nodes.has(_highlighted_entity_key):
		var prev: StaticBody3D = replicated_entity_nodes[_highlighted_entity_key]
		if is_instance_valid(prev):
			_set_marker_highlight(prev, false)
	_highlighted_entity_key = key
	if not key.is_empty() and replicated_entity_nodes.has(key):
		var body: StaticBody3D = replicated_entity_nodes[key]
		if is_instance_valid(body):
			_set_marker_highlight(body, true)

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

func _unstuck():
	# "/unstuck": lift the player out of geometry and re-seat them on the nearest
	# ground surface directly below. Fixes getting buried in terrain/buildings.
	# Player height is client-side (the server holds player z constant), so this is
	# safe to do locally and the server won't fight it.
	var space := player_body.get_world_3d().direct_space_state
	var origin := player_body.global_position
	# Cast from a few units above (to escape if shallowly buried) straight down.
	var q := PhysicsRayQueryParameters3D.create(
		origin + Vector3(0, 3.0, 0), origin - Vector3(0, 400.0, 0))
	q.collide_with_areas = false
	q.collision_mask = 1
	q.exclude = [player_body]
	var hit := space.intersect_ray(q)
	if hit and hit.has("position"):
		player_body.global_position.y = float(hit.position.y) + 1.0
		_push_log("Unstuck: re-seated on the ground.")
	else:
		# No ground below — pop straight up so gravity can settle onto something.
		player_body.global_position.y += 6.0
		_push_log("Unstuck: lifted (no ground found below).")
	velocity = Vector3.ZERO

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
	# Real active skills streamed from the server. May legitimately be empty
	# (a fresh caster has no active skills, just spells) — no fake fallback.
	var abilities: Variant = _player_char_info().get("abilities", [])
	if abilities is Array:
		return abilities.slice(0, min(abilities.size(), 8))
	return []

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
	# replicated entities. Prefer an editable authored .tscn (Trinst) and fall back
	# to the legacy JSON builder for zones that have not been converted yet.
	if _zone_loaded:
		return
	var world_root: Node3D = $SubViewportContainer/SubViewport/WorldRoot
	var zone := DEFAULT_ZONE
	var z = current_payload.get("zone", null)
	if z != null and str(z) != "":
		zone = str(z)
	var zone_node: Node3D = null
	var authored_scene_path := ZONE_SCENE_ROOT + zone + ".tscn"
	if ResourceLoader.exists(authored_scene_path):
		var ps := load(authored_scene_path) as PackedScene
		if ps != null:
			zone_node = ps.instantiate() as Node3D
			if zone_node != null:
				zone_node.name = "ZoneArt"
				zone_node.position = _server_origin_offset
				world_root.add_child(zone_node)
				if zone_node.has_method("prepare_authored_scene") and not zone_node.prepare_authored_scene(zone, true):
					zone_node.queue_free()
					zone_node = null
	if zone_node == null:
		var loader: Node3D = ZoneLoaderScript.new()
		loader.name = "ZoneArt"
		loader.position = _server_origin_offset
		world_root.add_child(loader)
		if not loader.build(zone, true):
			push_warning("Zone art unavailable for '%s'; keeping greybox world." % zone)
			loader.queue_free()
			return
		zone_node = loader
	_zone_loaded = true
	for placeholder in ["FloorBody", "BoxA", "BoxB", "BoxC", "DirectionalLight3D"]:
		var n: Node = world_root.get_node_or_null(placeholder)
		if n != null:
			n.queue_free()
	print("[Godot] Loaded zone art '%s' from %s at offset %s" % [zone, authored_scene_path if ResourceLoader.exists(authored_scene_path) else "scene.json", str(_server_origin_offset)])

func _ground_y(x: float, z: float, fallback: float) -> float:
	# Seat an entity on collision near the server's intended height first. This is
	# important for multi-floor interiors such as prefabs_tower1: the server Z says
	# which floor the mob belongs on, while a terrain-only snap drops it outside/on
	# the ground. If no nearby floor exists, fall back to terrain snapping.
	var world: World3D = sub_viewport.find_world_3d()
	if world == null:
		return fallback
	var space: PhysicsDirectSpaceState3D = world.direct_space_state
	if space == null:
		return fallback

	# Prefer any solid floor close to the authoritative server height.
	var near_from := Vector3(x, fallback + ENTITY_FLOOR_PROBE_UP, z)
	var near_to := Vector3(x, fallback - ENTITY_FLOOR_PROBE_DOWN, z)
	var near_q := PhysicsRayQueryParameters3D.create(near_from, near_to)
	near_q.collide_with_areas = false
	near_q.collision_mask = 1
	var near_hit: Dictionary = space.intersect_ray(near_q)
	if near_hit and near_hit.has("position"):
		return float(near_hit.position.y)

	var from := Vector3(x, fallback + 60.0, z)
	var to := Vector3(x, fallback - 60.0, z)
	# Terrain-only hit: the true ground at any height, so NPCs follow hills.
	var qt := PhysicsRayQueryParameters3D.create(from, to)
	qt.collide_with_areas = false
	qt.collision_mask = TERRAIN_MASK
	var ht: Dictionary = space.intersect_ray(qt)
	var ter_y := float(ht.position.y) if (ht and ht.has("position")) else fallback
	# The server height is authoritative for which *floor* an entity is on. If it
	# says the entity sits well above the terrain (tower/upper-storey spawns) but
	# no walkable surface was found near that height, keep the server height —
	# dropping to the terrain teleports interior mobs to the ground floor and
	# makes them visibly "fall" through the building.
	var elevated := (fallback - ter_y) > 3.0
	# First solid from above (terrain or building floor; entities are on layer 2).
	var qa := PhysicsRayQueryParameters3D.create(from, to)
	qa.collide_with_areas = false
	qa.collision_mask = 1
	var ha: Dictionary = space.intersect_ray(qa)
	if ha and ha.has("position"):
		var any_y := float(ha.position.y)
		# A high hit far from the server's expected height is probably a roof/canopy.
		if ht and (any_y - ter_y) > 5.0:
			return fallback if elevated else ter_y
		return any_y
	return fallback if elevated else ter_y

func _godot_direction_to_server(godot_dir: Vector3) -> Array:
	"""Convert a Godot direction vector to server coordinates (no origin offset)."""
	return [godot_dir.x, -godot_dir.z, godot_dir.y]

func _godot_world_to_server(godot_pos: Vector3) -> Array:
	"""Convert an absolute Godot world position back to server coordinates.

	The zone art, player, and replicated entities are shifted by
	_server_origin_offset after spawn. Inverting that offset is required when
	replicating player Z; otherwise Trinst's ~147u source height becomes ~2u on
	the server and nearby NPCs fail the server-side visibility range check.
	"""
	var server_space_pos := godot_pos - _server_origin_offset
	return [server_space_pos.x, -server_space_pos.z, server_space_pos.y]

func _record_position_history() -> void:
	var now := Time.get_ticks_msec() / 1000.0
	_pos_history.append({"t": now, "pos": player_body.global_position})
	while not _pos_history.is_empty() and now - float(_pos_history[0]["t"]) > RECONCILE_HISTORY_WINDOW:
		_pos_history.pop_front()

func _update_reconcile_error(server_pos: Vector3) -> void:
	# Measure true drift: the server position should lie somewhere on the client's
	# recent path (it is the same input stream integrated slightly later). The
	# residual against the closest history sample is real client/server divergence;
	# the raw difference against the current position would also include snapshot
	# latency and punish the player for simply moving.
	var current := player_body.global_position
	var best := Vector2(server_pos.x - current.x, server_pos.z - current.z)
	for sample in _pos_history:
		var p: Vector3 = sample["pos"]
		var d := Vector2(server_pos.x - p.x, server_pos.z - p.z)
		if d.length_squared() < best.length_squared():
			best = d
	var drift := best.length()
	if drift <= RECONCILE_DEAD_ZONE:
		_reconcile_error = Vector3.ZERO
		return
	if drift >= SERVER_RECONCILE_SNAP_THRESHOLD:
		# A real teleport (server moved the player), not drift: jump straight there.
		player_body.global_position.x = server_pos.x
		player_body.global_position.z = server_pos.z
		_pos_history.clear()
		_reconcile_error = Vector3.ZERO
		velocity.x = 0.0
		velocity.z = 0.0
		return
	_reconcile_error = Vector3(best.x, 0.0, best.y)

func _consume_correction(delta: float) -> Vector3:
	# Hand a slice of the reconcile error to this frame's move_and_slide (bounded
	# speed) instead of teleporting on snapshot arrival, so corrections read as a
	# gentle glide rather than 3-10 Hz stutter. Riding along with move_and_slide
	# (not a separate move_and_collide) matters: a raw collide stops dead on the
	# first slope/wall contact, which silently disabled corrections on uneven
	# terrain, while sliding follows the ground like ordinary movement — and still
	# can't be dragged through walls.
	if _reconcile_error == Vector3.ZERO:
		return Vector3.ZERO
	var step: Vector3 = _reconcile_error * clampf(delta * RECONCILE_RATE, 0.0, 1.0)
	var max_step := RECONCILE_MAX_SPEED * delta
	if step.length() > max_step:
		step = step.normalized() * max_step
	_reconcile_error -= step
	if _reconcile_error.length() < 0.01:
		_reconcile_error = Vector3.ZERO
	return step

func _try_step_up(horizontal_motion: Vector3, was_on_floor: bool, pre_move_pos: Vector3) -> void:
	# CharacterBody3D has slope snapping but no built-in stair stepping. Whenever a
	# grounded move was meaningfully blocked horizontally (stair riser, raised
	# doorstep, ledge built into a larger mesh), retry it from a lifted position
	# and settle onto the first floor below. The classic up-forward-down sweep.
	if not was_on_floor or horizontal_motion.length_squared() < 0.000001:
		return
	# Trigger on lost horizontal progress, not just on near-vertical contact
	# normals: trimesh stair edges often report tilted normals that the old
	# riser-only check missed, which is why many staircases were unclimbable.
	var actual := player_body.global_position - pre_move_pos
	var actual_h := Vector2(actual.x, actual.z)
	var wanted_h := Vector2(horizontal_motion.x, horizontal_motion.z)
	if actual_h.length() >= wanted_h.length() * 0.55:
		return

	var original_pos := player_body.global_position
	# Find the real headroom (may be under a low stairwell ceiling): lift as far
	# as possible up to the step height instead of giving up on any contact.
	var lift := PLAYER_STEP_UP_HEIGHT
	var up_hit := player_body.move_and_collide(Vector3.UP * lift, true)
	if up_hit != null:
		lift = maxf(up_hit.get_travel().y - 0.02, 0.0)
		if lift < 0.15:
			return  # not enough clearance to step
	var lifted_pos := original_pos + Vector3.UP * lift
	player_body.global_position = lifted_pos
	var step_motion := horizontal_motion * PLAYER_STEP_FORWARD_SCALE
	var fwd_hit := player_body.move_and_collide(step_motion, true)
	if fwd_hit != null:
		# Take whatever forward travel is free; if there is almost none the
		# obstacle is a real wall, so bail out.
		step_motion = fwd_hit.get_travel()
		if Vector2(step_motion.x, step_motion.z).length() < 0.02:
			player_body.global_position = original_pos
			return

	var candidate_pos := lifted_pos + step_motion
	var world := player_body.get_world_3d()
	if world == null:
		player_body.global_position = original_pos
		return
	var q := PhysicsRayQueryParameters3D.create(
		candidate_pos, candidate_pos - Vector3.UP * (lift + player_body.floor_snap_length + 0.25))
	q.collide_with_areas = false
	q.collision_mask = 1
	q.exclude = [player_body]
	var floor_hit := world.direct_space_state.intersect_ray(q)
	if not (floor_hit and floor_hit.has("position")):
		player_body.global_position = original_pos
		return
	var floor_y := float(floor_hit.position.y) + PLAYER_FOOT_OFFSET
	if floor_y < original_pos.y - 0.05 or floor_y > original_pos.y + PLAYER_STEP_UP_HEIGHT + 0.05:
		player_body.global_position = original_pos
		return
	player_body.global_position = Vector3(candidate_pos.x, floor_y, candidate_pos.z)
	velocity.y = 0.0

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

func _glb_for(race: String, sex: String, model: String) -> String:
	# Map an entity (or the player) to a converted character glb. Monster models
	# are keyed by their server model path (undead/skeleton -> undead_skeleton.glb);
	# playable races by <race>_<sex>.glb. Falls back to a human of the right sex so
	# a character is never modelless.
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
	var hp := CHAR_ASSET_DIR + "human_" + s + ".glb"
	return hp if ResourceLoader.exists(hp) else ""

func _glb_for_entity(entity: Dictionary) -> String:
	return _glb_for(str(entity.get("race", "")), str(entity.get("sex", "")), str(entity.get("model", "")))

func _appearance_for(entity: Dictionary) -> Dictionary:
	# The server streams per-part texture indices in entity["tex"]:
	# {"head":N,"body":N,"arms":N,"legs":N,"feet":N,"hands":N}. Empty -> the model
	# keeps its baked default textures.
	var tex = entity.get("tex", {})
	return tex if tex is Dictionary else {}

func _ensure_player_model(entity: Dictionary) -> void:
	# Build/replace the avatar once we know the player's race/sex/model.
	var path := _glb_for_entity(entity)
	if path == "" or path == _player_model_key:
		return
	if _player_rig and is_instance_valid(_player_rig):
		_player_rig.queue_free()
	_player_rig = CharacterRigScript.new()
	_player_rig.position = Vector3(0.0, -0.9, 0.0)
	player_body.add_child(_player_rig)
	if _player_rig.setup(path, 0.0):
		_player_model_key = path
		_player_rig.apply_appearance(_appearance_for(entity))
		var capsule_mesh := player_body.get_node_or_null("PlayerMesh")
		if capsule_mesh:
			capsule_mesh.visible = false

func _create_entity_marker(entity: Dictionary) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.name = str(entity.get("name", "Entity"))
	# Entities live on layer 2: ground-snap rays (mask 1) ignore them so NPCs never
	# stand on each other's heads, and the player walks through NPCs instead of
	# getting stuck on them. Click/look targeting uses an all-layers ray, so it
	# still hits these markers and reads their entity_id meta. The body origin is at
	# the feet (ground), so the model and collider start at y=0.
	body.collision_layer = 2
	body.collision_mask = 1

	# Invisible collision capsule (feet..head) for click/look targeting.
	var collider := CollisionShape3D.new()
	var shape := CapsuleShape3D.new()
	shape.radius = 0.5
	shape.height = 1.6
	collider.shape = shape
	collider.position = Vector3(0, 0.9, 0)
	body.add_child(collider)

	# Animated model; fall back to a coloured capsule if it can't load so the
	# entity is never invisible.
	var rig: Node3D = CharacterRigScript.new()
	var fallback_mesh: MeshInstance3D = null
	if rig.setup(_glb_for_entity(entity), 0.0):
		body.add_child(rig)
		body.set_meta("rig", rig)
		rig.apply_appearance(_appearance_for(entity))
	else:
		fallback_mesh = MeshInstance3D.new()
		var mesh := CapsuleMesh.new()
		mesh.radius = 0.5
		mesh.height = 1.6
		fallback_mesh.mesh = mesh
		fallback_mesh.position = Vector3(0, 0.9, 0)
		body.add_child(fallback_mesh)

	var label := Label3D.new()
	label.position = Vector3(0, 2.05, 0)
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.fixed_size = false
	body.add_child(label)

	body.set_meta("mesh", fallback_mesh)
	body.set_meta("label", label)
	body.set_meta("entity_id", int(entity.get("id", 0)))
	_update_entity_marker(body, entity)
	npc_root.add_child(body)
	return body

func _update_entity_marker(body: StaticBody3D, entity: Dictionary):
	body.set_meta("entity", entity.duplicate(true))
	body.set_meta("entity_id", int(entity.get("id", 0)))
	var key := _entity_key(entity)
	# Colour the fallback capsule when there's no model (highlight preserved).
	var fb: MeshInstance3D = body.get_meta("mesh", null)
	if fb and key != _highlighted_entity_key:
		var mesh_material := StandardMaterial3D.new()
		mesh_material.albedo_color = _entity_color(entity)
		fb.material_override = mesh_material
	# Apply the server's per-spawn scale multiplier (anchored at the feet).
	var scl := float(entity.get("scale", 1.0))
	if scl > 0.0:
		body.scale = Vector3(scl, scl, scl)
	var label: Label3D = body.get_meta("label")
	label.text = _entity_label_text(entity)

func _sync_entity_markers():
	if replicated_entities.is_empty():
		return

	# Find self entity and reconcile player position with server
	for entity in replicated_entities:
		if entity is Dictionary and bool(entity.get("is_self", false)):
			var raw_pos = entity.get("position", [])
			# Pick the avatar model from the player's own race/sex/model.
			_ensure_player_model(entity)
			# Compute spawn offset from first entity snapshot (more reliable than root_info)
			if not _has_spawned:
				_has_spawned = true
				var server_pos_raw := _world_position_from_server(raw_pos)
				_server_origin_offset = Vector3(0.0, 2.0, 0.0) - server_pos_raw
				player_body.global_position = Vector3(0.0, 2.0, 0.0)
				print("[Godot] SPAWN from entity snapshot: raw=%s  converted=%s  offset=%s" % [str(raw_pos), str(server_pos_raw), str(_server_origin_offset)])
				_load_zone_art()
				# Prime the UI data (inventory for char/journal identity, spellbook).
				_request_server_command("get_inventory")
				_request_server_command("get_spellbook")
				break
			var server_pos := _server_to_godot(raw_pos)
			if server_pos != Vector3.ZERO and _server_origin_offset != Vector3.ZERO:
				_update_reconcile_error(server_pos)
			break

	var incoming_keys: Dictionary = {}
	var entity_list: Array = []
	var now_seconds: float = Time.get_ticks_msec() / 1000.0
	for entity in replicated_entities:
		if not (entity is Dictionary):
			continue
		if bool(entity.get("is_self", false)):
			continue
		var entity_key := _entity_key(entity)
		var entity_dead := bool(entity.get("dead", false)) or float(entity.get("health", 1.0)) <= 0.0
		if entity_dead:
			# Corpses stay visible (and clickable for looting) for as long as the
			# server streams them — the server removes them once fully looted or
			# on the corpse timer. Clear any combat highlight, keep the body.
			if entity_key == _highlighted_entity_key:
				_highlight_entity("")
			var dead_entity: Dictionary = entity.duplicate(true)
			dead_entity["dead"] = true
			dead_entity["health"] = 0.0
			entity_list.append(dead_entity)
		else:
			_dead_entity_remove_at.erase(entity_key)
			entity_list.append(entity)

	for i in range(entity_list.size()):
		var entity_dict: Dictionary = entity_list[i]
		var key := _entity_key(entity_dict)
		incoming_keys[key] = true
		# Convert entity server position to absolute Godot world position, then drop
		# it onto the terrain/world collision so NPCs stand on the ground.
		var godot_pos := _server_to_godot(entity_dict.get("position", []))
		# Body origin is at the feet, so seat it right on the ground.
		godot_pos.y = _ground_y(godot_pos.x, godot_pos.z, godot_pos.y) + 0.05
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
			var old_entity: Dictionary = old_body.get_meta("entity", {})
			var old_dead := bool(old_entity.get("dead", false)) or float(old_entity.get("health", 1.0)) <= 0.0
			if old_dead:
				if not _dead_entity_remove_at.has(key):
					_dead_entity_remove_at[key] = now_seconds + ENTITY_DEATH_DESPAWN_DELAY
				if now_seconds < float(_dead_entity_remove_at.get(key, now_seconds)):
					continue
			old_body.queue_free()
		_dead_entity_remove_at.erase(key)
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
	for spell in _last_spellbook.get("spells", []):
		if spell is Dictionary:
			names.append("sp:%s:%s:%s" % [
				spell.get("name", ""),
				spell.get("slot", -1),
				spell.get("recast_left", 0),
			])
	return "|".join(names)

func _rebuild_ability_bar():
	# Feed the hotbar + spellbook "Abilities" tab from the server skill list
	# and the memorized spellbook spells.
	if hotbar == null:
		return
	var signature := _ability_signature()
	if signature == last_abilities_signature:
		return
	last_abilities_signature = signature
	var abilities := _abilities()
	var spells: Array = _last_spellbook.get("spells", [])
	hotbar.default_fill_from_skills(abilities, spells)
	hotbar.update_cooldowns(abilities, spells)
	if spellbook_window:
		spellbook_window.apply_skills(abilities)

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
		target_label.text = "Looking at entity id: %d (enemy=%s)   building: %s" % [_looked_entity_id if _looking_at_entity else 0, str(_looking_at_enemy), _looking_at_world if _looking_at_world != "" else "<none>"]
		interaction_label.text = interaction_message
		var transfer: Variant = current_payload.get("zone_transfer", {})
		if transfer is Dictionary and not transfer.is_empty():
			transfer_label.text = "Zone handoff: port %s, party %s" % [str(transfer.get("zone_port", "?")), str(transfer.get("party", []))]
		else:
			transfer_label.text = _bridge_status_text()

func _request_server_command(command_type: String, payload: Dictionary = {}):
	command_requested.emit(command_type, payload)

func _send_interact_command():
	# E does the contextual thing: loot the dead entity in front of you (or the
	# dead target), otherwise INTERACT (dialog/vendor/trainer) with the target.
	if _looking_at_entity and _looking_at_dead and _looked_entity_id > 0:
		interaction_message = "Looting corpse %d." % _looked_entity_id
		_request_server_command("select_entity", {"entity_id": _looked_entity_id, "double_click": true})
		return
	var tgt_dead := bool(server_target_description.get("dead", false))
	var tgt_id := int(server_target_description.get("id", 0))
	if tgt_dead and tgt_id > 0:
		interaction_message = "Looting corpse %d." % tgt_id
		_request_server_command("select_entity", {"entity_id": tgt_id, "double_click": true})
		return
	interaction_message = "Sent INTERACT to the legacy world server."
	_request_server_command("interact")

func _cycle_target():
	interaction_message = "Sent CYCLETARGET to the legacy world server."
	_request_server_command("cycle_target")

func _toggle_autoattack():
	interaction_message = "Sent ATTACK toggle to the legacy world server."
	_request_server_command("attack_toggle")

func _on_hotbar_action(payload: Dictionary):
	var action := str(payload.get("action", "skill"))
	var ability_name := str(payload.get("name", ""))
	if action == "spell":
		interaction_message = "Casting %s." % ability_name
		_request_server_command("spell_slot", {
			"char_id": _ui_char_id,
			"slot": int(payload.get("book_slot", 0)),
		})
		return
	interaction_message = "Sent SKILL %s to the legacy world server." % ability_name
	# Play the attack swing locally for immediate feedback (server confirms via the
	# self entity's `attacking` flag for sustained combat).
	_player_attack_until = Time.get_ticks_msec() / 1000.0 + 0.6
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
	if bool(entity.get("dead", false)) or float(entity.get("health", 1.0)) <= 0.0:
		interaction_message = "Looting %s." % str(entity.get("name", "corpse"))
		_request_server_command("select_entity", {"entity_id": entity_id, "double_click": true})
		return true
	interaction_message = "Targeted %s on the legacy world server." % str(entity.get("public_name", entity.get("name", "entity")))
	_request_server_command("target_entity", {"entity_id": entity_id})
	return true

func _typing_in_ui() -> bool:
	var focus := get_viewport().gui_get_focus_owner()
	return focus is LineEdit or focus is TextEdit

func _ui_open() -> bool:
	for w in [inventory_window, loot_window, npc_window, journal_window, spellbook_window]:
		if w != null and w.visible:
			return true
	return false

func _close_all_windows():
	for w in [inventory_window, loot_window, npc_window, journal_window, spellbook_window]:
		if w != null and w.visible:
			w.close_window()

func _input(event):
	if not visible:
		return
	var ui_open := _ui_open()
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_UP:
		if ui_open:
			return
		_adjust_camera_zoom(-1.0)
		_capture_mouse()
	elif event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
		if ui_open:
			return
		_adjust_camera_zoom(1.0)
		_capture_mouse()
	elif event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		if ui_open:
			return  # windows take the mouse; world clicks resume when they close
		var selected := _target_entity_from_click(event.position)
		_capture_mouse()
		if selected:
			_update_labels()
	elif event.is_action_pressed("ui_cancel"):
		if ui_open:
			_close_all_windows()
			_capture_mouse()
		else:
			_release_mouse()
	elif event is InputEventKey and event.pressed and not event.echo:
		if _typing_in_ui():
			return  # a window text field owns the keyboard
		match event.keycode:
			KEY_F8:
				_toggle_cheats()
			KEY_SPACE:
				jump_requested = true
			KEY_E:
				_send_interact_command()
			KEY_U:
				_unstuck()
			KEY_Q:
				_toggle_autoattack()
			KEY_TAB:
				_cycle_target()
			KEY_I:
				_toggle_inventory()
			KEY_J:
				_toggle_journal()
			KEY_P, KEY_B:
				_toggle_spellbook()
			KEY_1, KEY_KP_1:
				hotbar.activate(0)
			KEY_2, KEY_KP_2:
				hotbar.activate(1)
			KEY_3, KEY_KP_3:
				hotbar.activate(2)
			KEY_4, KEY_KP_4:
				hotbar.activate(3)
			KEY_5, KEY_KP_5:
				hotbar.activate(4)
			KEY_6, KEY_KP_6:
				hotbar.activate(5)
			KEY_7, KEY_KP_7:
				hotbar.activate(6)
			KEY_8, KEY_KP_8:
				hotbar.activate(7)
			KEY_9, KEY_KP_9:
				hotbar.activate(8)
			KEY_0, KEY_KP_0:
				hotbar.activate(9)
			KEY_F3:
				_debug_visible = not _debug_visible
				if debug_panel:
					debug_panel.visible = _debug_visible
				_update_labels()
	elif event is InputEventMouseMotion and mouse_captured:
		player_body.rotate_y(-event.relative.x * LOOK_SENSITIVITY)
		camera_pitch.rotate_x(-event.relative.y * LOOK_SENSITIVITY)
		camera_pitch.rotation.x = clamp(camera_pitch.rotation.x, deg_to_rad(-70), deg_to_rad(70))
		_update_camera_collision()

func _physics_process(delta: float) -> void:
	if not visible:
		return
	# Gather movement inputs (not while typing into a window text field)
	var input_vec := Vector2.ZERO
	if not _typing_in_ui():
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
	var horizontal_motion: Vector3 = Vector3(velocity.x, 0.0, velocity.z) * delta
	var was_on_floor := player_body.is_on_floor()
	var pre_move_pos := player_body.global_position
	var correction := _consume_correction(delta)
	player_body.velocity = velocity + correction / delta
	player_body.move_and_slide()
	_try_step_up(horizontal_motion, was_on_floor, pre_move_pos)
	_record_position_history()
	# Safety net: teleport back above the platform if player falls
	if player_body.global_position.y < -50.0:
		player_body.global_position = Vector3(player_body.global_position.x, 5.0, player_body.global_position.z)
		velocity = Vector3.ZERO

	_update_camera_collision()

	# Send movement inputs to server periodically
	_input_sync_timer += delta
	if _input_sync_timer >= INPUT_SYNC_INTERVAL:
		_input_sync_timer = 0.0
		# Convert facing direction to server coords for the server movement sim
		var forward_dir := -basis.z  # Godot forward is -Z
		var server_forward := _godot_direction_to_server(forward_dir)
		var input_state := {
			"move_x": input_vec.x,
			"move_y": input_vec.y,
			"forward": server_forward,
			"jump": jump_requested,
			# Replicate the client-resolved floor height back to the headless server.
			# The server stores positions as (x, y, z), where z is vertical.
			"position_z": _godot_world_to_server(player_body.global_position)[2],
		}
		if input_state != _last_sent_input:
			_last_sent_input = input_state.duplicate()
			_request_server_command("player_input", input_state)

	# Drive the player avatar animation from predicted horizontal speed + combat.
	if _player_rig and _player_rig.has_method("drive"):
		var pspeed := Vector2(velocity.x, velocity.z).length()
		var now := Time.get_ticks_msec() / 1000.0
		var attacking := bool(_self_entity().get("attacking", false)) or now < _player_attack_until
		_player_rig.drive(pspeed, attacking, false)

	# Interpolate replicated entity positions toward server targets, and drive each
	# NPC's animation from how fast its marker is actually moving.
	var entity_space: PhysicsDirectSpaceState3D = null
	var entity_world := sub_viewport.find_world_3d() if sub_viewport else null
	if entity_world != null:
		entity_space = entity_world.direct_space_state
	for body in replicated_entity_nodes.values():
		if body == null or not is_instance_valid(body):
			continue
		var target_position: Vector3 = body.get_meta("target_position", body.position)
		var prev_xz := Vector2(body.position.x, body.position.z)
		if body.position.distance_to(target_position) > ENTITY_SNAP_DISTANCE:
			body.position = target_position
			body.set_meta("stuck_time", 0.0)
		else:
			var desired: Vector3 = body.position.lerp(target_position, clamp(delta * ENTITY_INTERPOLATION_SPEED, 0.0, 1.0))
			# The headless server has no world collision, so a chasing/returning
			# mob's straight-line path can cross walls. Clamp each interpolation
			# step against world geometry at knee height; if the marker stays
			# blocked while the server target keeps moving away, snap to the
			# server position so the mob can't be left behind forever.
			var step_vec: Vector3 = desired - body.position
			var step_h := Vector3(step_vec.x, 0.0, step_vec.z)
			if entity_space != null and step_h.length() > 0.002:
				var ray_from: Vector3 = body.position + Vector3(0, 0.55, 0)
				var rq := PhysicsRayQueryParameters3D.create(ray_from, ray_from + step_h)
				rq.collide_with_areas = false
				rq.collision_mask = 1
				var rh: Dictionary = entity_space.intersect_ray(rq)
				if rh and rh.has("position"):
					var free := maxf(ray_from.distance_to(rh.position) - 0.25, 0.0)
					var dir := step_h.normalized()
					desired.x = body.position.x + dir.x * free
					desired.z = body.position.z + dir.z * free
			body.position = desired
			var lag := Vector2(body.position.x - target_position.x, body.position.z - target_position.z).length()
			if lag > 1.5:
				var stuck := float(body.get_meta("stuck_time", 0.0)) + delta
				if stuck >= 2.0:
					body.position = target_position
					stuck = 0.0
				body.set_meta("stuck_time", stuck)
			else:
				body.set_meta("stuck_time", 0.0)
		var moved := Vector2(body.position.x, body.position.z).distance_to(prev_xz)
		var inst_speed := moved / maxf(delta, 0.001)
		var smoothed := lerpf(float(body.get_meta("speed", 0.0)), inst_speed, 0.25)
		body.set_meta("speed", smoothed)
		var rig = body.get_meta("rig", null)
		if rig != null and is_instance_valid(rig):
			var ent: Dictionary = body.get_meta("entity", {})
			rig.drive(smoothed, bool(ent.get("attacking", false)), bool(ent.get("dead", false)))

	# Cursor-item ghost follows the mouse while a window is open.
	if cursor_item_ghost and cursor_item_ghost.visible:
		cursor_item_ghost.position = get_local_mouse_position() + Vector2(14, 10)

	# Periodically refresh open windows so cooldowns/charges stay current.
	_ui_poll_timer += delta
	if _ui_poll_timer >= 2.0:
		_ui_poll_timer = 0.0
		if inventory_window and inventory_window.visible:
			_request_server_command("get_inventory")
		if spellbook_window and spellbook_window.visible:
			_request_server_command("get_spellbook")

	_update_dynamic_dof(delta)
	_update_look_at()
	_update_labels()
