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
const CAMERA_NEAR_HEIGHT := 0.45     # shoulder-level camera height at closest zoom
const CAMERA_FP_OFFSET := Vector3(0.0, -0.45, 0.0)  # eye position (relative to the 1.4-high yaw pivot)
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
const GAMEPAD_LOOK_SENSITIVITY := 2.8    # right-stick yaw, radians/sec at full tilt
const GAMEPAD_PITCH_SENSITIVITY := 2.0   # right-stick pitch, radians/sec at full tilt
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
const ENTITY_FLYING_LIFT := 1.4  # how far Flying/Levitate raises a model off the ground
const ENTITY_FLOOR_PROBE_UP := 4.0
const ENTITY_FLOOR_PROBE_DOWN := 8.0
const ENTITY_MAX_DISPLAY_DISTANCE := 20.0
const ENTITY_CAPSULE_HALF_HEIGHT := 0.7
const ENTITY_SELECTION_DISTANCE := 150.0
const TAB_TARGET_MAX_DISTANCE := 60.0
const TAB_TARGET_CONE_DEG := 70.0  # half-angle of the Tab-targeting frontal cone
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
var _entity_cache: Dictionary = {}  # id -> merged full entity (proxy sends deltas)
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
var _first_person := false
var _camera_base_rotation_x := 0.0
var _pos_history: Array = []        # recent [{t, pos}] samples for latency-aware reconcile
var _last_server_pos := Vector3.ZERO  # previous snapshot's server position
var _has_last_server_pos := false     # whether _last_server_pos is valid yet
var _reconcile_error := Vector3.ZERO  # smoothed-out correction toward the server position
var _camera_base_local_offset := Vector3.ZERO
var _camera_attributes: CameraAttributesPractical = null
var _dof_focus_distance := DOF_DEFAULT_FOCUS
var _dead_entity_remove_at: Dictionary = {}
var _tab_cycle_ids: Array = []
var _tab_cycle_pos := -1

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
var target_prompt_label: Label  # contextual "Press E/G..." hint under the target frame
var hint_label: Label
var combat_log_label: Label
var _buff_bar: HBoxContainer            # player's active buffs/debuffs (top-left)
var _target_buff_bar: HBoxContainer     # current target's debuffs (under target frame)
var _effect_row_sigs: Dictionary = {}   # container -> last rendered signature
var chat_input: LineEdit          # slash-command / chat box (toggle with Enter)
var _sky3d: Node = null           # Sky3D in the loaded zone, driven by server world_time
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
var _cast_bar: ProgressBar
var _cast_started := 0.0
var _cast_duration := 0.0
var _self_prev_health := -1.0
var _self_pain_cooldown := 0.0
var _pet_bar: PanelContainer
var _pet_label: Label
# Party / alliance UI
var _party_panel: PanelContainer
var _party_box: VBoxContainer
var _party_title: Label
var _party_members: Array = []          # [{public_name, name, health_ratio, mob_id}]
var _party_hp_bars: Array = []          # [{bar:ProgressBar, mob_id:int, fallback:float}]
var _party_invite_panel: PanelContainer
var _party_invite_label: Label
var _party_invite_from := ""
var _interaction_active := false
# Death overlay (shown while the player's character is dead; respawns at bind).
var _is_dead := false
var _death_overlay: Control = null
var _death_respawn_button: Button = null
var _ui_char_name := ""          # journal/hotbar persistence key
var _ui_char_id := 0             # server character DB id for inventory/spell calls
var _last_inventory: Dictionary = {}
var _last_spellbook: Dictionary = {}
var _ui_poll_timer := 0.0

func _ready():
	set_process_input(true)
	_setup_input_actions()
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
	_camera_base_rotation_x = camera.rotation.x
	_camera_zoom = _camera_base_local_offset.z
	_apply_camera_zoom()
	_setup_dynamic_dof()
	_build_hud()
	_build_game_windows()
	_build_death_overlay()
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
	# Active buffs/debuffs row (under the resource bars).
	_buff_bar = HBoxContainer.new()
	_buff_bar.add_theme_constant_override("separation", 4)
	_buff_bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	pv.add_child(_buff_bar)

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
	# Contextual interaction prompt (what E / G / Q do for this target type).
	target_prompt_label = Label.new()
	target_prompt_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	target_prompt_label.add_theme_font_size_override("font_size", 11)
	target_prompt_label.add_theme_color_override("font_color", Color(0.80, 0.92, 0.80))
	target_prompt_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	tv.add_child(target_prompt_label)
	# Target's active debuffs/buffs row.
	_target_buff_bar = HBoxContainer.new()
	_target_buff_bar.alignment = BoxContainer.ALIGNMENT_CENTER
	_target_buff_bar.add_theme_constant_override("separation", 4)
	_target_buff_bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	tv.add_child(_target_buff_bar)

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
	hint_label.text = "Move WASD/L-stick • Look mouse/R-stick • Tab/B target • Q/RB attack • E/X talk-loot • 1-0/D-pad abilities • R/Y swap bar • Shift/LB hold = bar 2 • Space/A jump • I inventory • P spells • J journal • Enter chat • ` cheats"
	bottom.add_child(hint_label)
	hotbar = HotbarScript.new()
	hotbar.action_triggered.connect(_on_hotbar_action)
	bottom.add_child(hotbar)

	# Pet command bar (left edge; shown only while a pet is up).
	_pet_bar = PanelContainer.new()
	_pet_bar.add_theme_stylebox_override("panel", _panel_style(Color(0.5, 0.75, 0.5)))
	_pet_bar.set_anchors_preset(Control.PRESET_CENTER_LEFT)
	_pet_bar.offset_left = 16
	_pet_bar.visible = false
	add_child(_pet_bar)
	var pet_box := VBoxContainer.new()
	pet_box.add_theme_constant_override("separation", 4)
	_pet_bar.add_child(pet_box)
	_pet_label = Label.new()
	_pet_label.text = "Pet"
	_pet_label.add_theme_font_size_override("font_size", 12)
	_pet_label.add_theme_color_override("font_color", Color(0.7, 0.95, 0.7))
	pet_box.add_child(_pet_label)
	for pet_cmd in [["Attack my target", "pet_attack"], ["Follow me", "pet_follow"],
			["Stay", "pet_stay"], ["Back off", "pet_back_off"], ["Dismiss", "pet_dismiss"]]:
		var pb := Button.new()
		pb.text = pet_cmd[0]
		pb.focus_mode = Control.FOCUS_NONE
		UICommonScript.style_button(pb)
		var cmd: String = pet_cmd[1]
		pb.pressed.connect(func(): _request_server_command(cmd))
		pet_box.add_child(pb)

	# Party / alliance panel (top-left, below the player frame; shown only while
	# grouped). Members + live health, with a Leave button.
	_party_panel = PanelContainer.new()
	_party_panel.add_theme_stylebox_override("panel", _panel_style(Color(0.55, 0.8, 0.55)))
	_party_panel.set_anchors_preset(Control.PRESET_TOP_LEFT)
	_party_panel.offset_left = 16
	_party_panel.offset_top = 150
	_party_panel.visible = false
	_party_panel.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(_party_panel)
	_party_box = VBoxContainer.new()
	_party_box.add_theme_constant_override("separation", 3)
	_party_panel.add_child(_party_box)
	_party_title = Label.new()
	_party_title.text = "Party"
	_party_title.add_theme_font_size_override("font_size", 12)
	_party_title.add_theme_color_override("font_color", Color(0.75, 0.97, 0.75))
	_party_box.add_child(_party_title)

	# Incoming party-invite prompt (center-top, below the target frame).
	_party_invite_panel = PanelContainer.new()
	_party_invite_panel.add_theme_stylebox_override("panel", _panel_style(Color(0.95, 0.85, 0.4)))
	_party_invite_panel.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_party_invite_panel.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_party_invite_panel.offset_top = 70
	_party_invite_panel.visible = false
	add_child(_party_invite_panel)
	var inv_box := VBoxContainer.new()
	inv_box.add_theme_constant_override("separation", 4)
	_party_invite_panel.add_child(inv_box)
	_party_invite_label = Label.new()
	_party_invite_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_party_invite_label.add_theme_font_size_override("font_size", 13)
	inv_box.add_child(_party_invite_label)
	var inv_btns := HBoxContainer.new()
	inv_btns.alignment = BoxContainer.ALIGNMENT_CENTER
	inv_btns.add_theme_constant_override("separation", 8)
	inv_box.add_child(inv_btns)
	var accept_btn := Button.new()
	accept_btn.text = "Accept (Y)"
	accept_btn.focus_mode = Control.FOCUS_NONE
	UICommonScript.style_button(accept_btn)
	accept_btn.pressed.connect(_accept_party_invite)
	inv_btns.add_child(accept_btn)
	var decline_btn := Button.new()
	decline_btn.text = "Decline (N)"
	decline_btn.focus_mode = Control.FOCUS_NONE
	UICommonScript.style_button(decline_btn)
	decline_btn.pressed.connect(_decline_party_invite)
	inv_btns.add_child(decline_btn)

	# Cast bar (bottom-center, above the hotbar; shown while casting).
	_cast_bar = ProgressBar.new()
	_cast_bar.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	_cast_bar.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_cast_bar.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_cast_bar.offset_bottom = -96
	_cast_bar.custom_minimum_size = Vector2(260, 16)
	_cast_bar.min_value = 0.0
	_cast_bar.max_value = 1.0
	_cast_bar.show_percentage = false
	_cast_bar.visible = false
	_cast_bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var cast_fill := StyleBoxFlat.new()
	cast_fill.bg_color = Color(0.55, 0.65, 1.0)
	cast_fill.set_corner_radius_all(3)
	_cast_bar.add_theme_stylebox_override("fill", cast_fill)
	add_child(_cast_bar)

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

	# Chat / slash-command box (hidden until you press Enter). Sits at the very
	# bottom-left under the combat log.
	chat_input = LineEdit.new()
	chat_input.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	chat_input.offset_left = 16
	chat_input.offset_bottom = -16
	chat_input.offset_top = -42
	chat_input.custom_minimum_size = Vector2(420, 26)
	chat_input.placeholder_text = "/time set day   (Enter to send, Esc to cancel)"
	chat_input.visible = false
	chat_input.text_submitted.connect(_on_chat_submitted)
	chat_input.gui_input.connect(_on_chat_gui_input)
	add_child(chat_input)

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

# ---------------------------------------------------------------------------
# Death overlay: shown while the player's character is dead. Releasing the
# spirit (button / Enter / controller A) calls the server "respawn" command,
# which revives the character at its bind point. Before this existed a dead
# player was stuck at 1 HP with no entity stream until they relogged.
# ---------------------------------------------------------------------------
func _build_death_overlay() -> void:
	_death_overlay = ColorRect.new()
	_death_overlay.color = Color(0.05, 0.0, 0.0, 0.6)
	_death_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_death_overlay.mouse_filter = Control.MOUSE_FILTER_STOP
	_death_overlay.visible = false
	_death_overlay.z_index = 150
	add_child(_death_overlay)
	var box := VBoxContainer.new()
	box.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	box.grow_horizontal = Control.GROW_DIRECTION_BOTH
	box.grow_vertical = Control.GROW_DIRECTION_BOTH
	box.alignment = BoxContainer.ALIGNMENT_CENTER
	box.add_theme_constant_override("separation", 18)
	_death_overlay.add_child(box)
	var title := Label.new()
	title.text = "You have died"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 44)
	title.add_theme_color_override("font_color", Color(0.92, 0.22, 0.22))
	box.add_child(title)
	var sub := Label.new()
	sub.text = "Release your spirit to respawn at your bind point."
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sub.add_theme_font_size_override("font_size", 16)
	sub.add_theme_color_override("font_color", Color(0.85, 0.85, 0.9))
	box.add_child(sub)
	_death_respawn_button = Button.new()
	_death_respawn_button.text = "Release / Respawn   (Enter)"
	_death_respawn_button.focus_mode = Control.FOCUS_NONE
	UICommonScript.style_button(_death_respawn_button)
	_death_respawn_button.custom_minimum_size = Vector2(260, 46)
	_death_respawn_button.pressed.connect(_do_respawn)
	box.add_child(_death_respawn_button)

func _show_death_overlay(on: bool) -> void:
	_is_dead = on
	if _death_overlay:
		_death_overlay.visible = on
	if on:
		# Can't act, loot or shop while dead; drop into UI/mouse mode.
		_close_all_windows()
		_release_mouse()
		if _death_respawn_button:
			_death_respawn_button.text = "Release / Respawn   (Enter)"
			_death_respawn_button.disabled = false
	else:
		_capture_mouse()

func _do_respawn() -> void:
	if _death_respawn_button:
		_death_respawn_button.text = "Respawning..."
		_death_respawn_button.disabled = true
	_request_server_command("respawn")
	_push_log("Releasing spirit — respawning at your bind point.")

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
				# load_for cleared the slots; force the next rebuild to refill
				# them even if the ability/spell signature hasn't changed.
				last_abilities_signature = ""
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
		"begin_casting":
			# Wind-up: looping spellprepare on the avatar + a cast bar; the
			# release (spellcast anim, ring, particles) arrives as zone events.
			var cast_time := float(data.get("cast_time", 0.0))
			if _player_rig and is_instance_valid(_player_rig):
				_player_rig.play_overlay("spellprepare", maxf(cast_time, 0.4))
			_begin_cast_bar(cast_time)
		"play_sound":
			VFX.sound_ui(self, str(data.get("sound", "")))
		"player_death":
			_show_death_overlay(true)
		"player_alive":
			_show_death_overlay(false)
		"alliance_info":
			var members_val = data.get("members", [])
			_party_members = members_val if members_val is Array else []
			_refresh_party_panel()
			# Once you're grouped there is no outstanding invite to answer.
			if _party_members.size() >= 2 and _party_invite_panel:
				_party_invite_panel.visible = false
				_party_invite_from = ""
		"alliance_invite":
			if bool(data.get("pending", false)):
				_party_invite_from = str(data.get("from", ""))
				_party_invite_label.text = "Party invite from %s — Accept (Y) / Decline (N)" % (
					_party_invite_from if not _party_invite_from.is_empty() else "another player")
				_party_invite_panel.visible = true
			else:
				_party_invite_from = ""
				_party_invite_panel.visible = false

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

# ---------------------------------------------------------------------------
# Party / alliance
# ---------------------------------------------------------------------------
func _refresh_party_panel() -> void:
	if _party_panel == null:
		return
	for child in _party_box.get_children():
		if child != _party_title:
			child.queue_free()
	_party_hp_bars.clear()
	var grouped := _party_members.size() > 1
	_party_panel.visible = grouped
	if not grouped:
		return
	_party_title.text = "Party (%d/6)" % _party_members.size()
	for m in _party_members:
		if not (m is Dictionary):
			continue
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 6)
		_party_box.add_child(row)
		var name_lbl := Label.new()
		name_lbl.text = str(m.get("name", "?"))
		name_lbl.add_theme_font_size_override("font_size", 12)
		name_lbl.custom_minimum_size = Vector2(120, 0)
		row.add_child(name_lbl)
		var hp := ProgressBar.new()
		hp.custom_minimum_size = Vector2(96, 12)
		hp.min_value = 0.0
		hp.max_value = 1.0
		hp.show_percentage = false
		var fill := StyleBoxFlat.new()
		fill.bg_color = Color(0.3, 0.85, 0.35)
		fill.set_corner_radius_all(2)
		hp.add_theme_stylebox_override("fill", fill)
		hp.value = clampf(float(m.get("health_ratio", 1.0)), 0.0, 1.0)
		row.add_child(hp)
		_party_hp_bars.append({"bar": hp, "mob_id": int(m.get("mob_id", -1)),
			"fallback": float(m.get("health_ratio", 1.0))})
	var leave := Button.new()
	leave.text = "Leave party"
	leave.focus_mode = Control.FOCUS_NONE
	UICommonScript.style_button(leave)
	leave.pressed.connect(func(): _request_server_command("leave_alliance"))
	_party_box.add_child(leave)

func _update_party_health() -> void:
	# Pull live member health from the entity snapshots each frame (matched by
	# mob id); members in another zone keep their last alliance-info value.
	if _party_hp_bars.is_empty():
		return
	for entry in _party_hp_bars:
		var mob_id: int = int(entry.get("mob_id", -1))
		var ratio: float = float(entry.get("fallback", 1.0))
		if mob_id > 0:
			for e in replicated_entities:
				if e is Dictionary and int(e.get("id", 0)) == mob_id:
					ratio = float(e.get("health_ratio", e.get("health", 1.0)))
					break
		var bar: ProgressBar = entry.get("bar")
		if is_instance_valid(bar):
			bar.value = clampf(ratio, 0.0, 1.0)

# ---------------------------------------------------------------------------
# Buff / debuff bars (player's own effects + the current target's). Fed by the
# per-entity "effects" list the server streams (timed spell processes).
# ---------------------------------------------------------------------------
func _fmt_secs(s: int) -> String:
	return ("%dm" % int(s / 60.0)) if s >= 60 else ("%ds" % maxi(s, 0))

func _make_effect_chip(e: Dictionary) -> Control:
	var harmful := bool(e.get("harmful", false))
	var accent := Color(0.9, 0.4, 0.4) if harmful else Color(0.4, 0.82, 0.5)
	var panel := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.06, 0.07, 0.09, 0.9)
	sb.border_color = accent
	sb.set_border_width_all(2)
	sb.set_corner_radius_all(3)
	sb.content_margin_left = 3; sb.content_margin_right = 3
	sb.content_margin_top = 2; sb.content_margin_bottom = 2
	panel.add_theme_stylebox_override("panel", sb)
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.tooltip_text = "%s (%s)" % [str(e.get("name", "")), "debuff" if harmful else "buff"]
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 0)
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(box)
	var icon := UICommonScript.spell_icon(str(e.get("icon", "")))
	if icon != null:
		var ti := TextureRect.new()
		ti.texture = icon
		ti.custom_minimum_size = Vector2(26, 26)
		ti.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		ti.mouse_filter = Control.MOUSE_FILTER_IGNORE
		box.add_child(ti)
	else:
		var nm := Label.new()
		nm.text = str(e.get("name", "?")).left(6)
		nm.add_theme_font_size_override("font_size", 10)
		nm.mouse_filter = Control.MOUSE_FILTER_IGNORE
		box.add_child(nm)
	var timer := Label.new()
	timer.text = _fmt_secs(int(e.get("remaining", 0)))
	timer.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	timer.add_theme_font_size_override("font_size", 9)
	timer.add_theme_color_override("font_color", accent)
	timer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_child(timer)
	return panel

func _render_effect_row(container: HBoxContainer, effects: Array) -> void:
	if container == null:
		return
	# Rebuild only when the effect set / remaining-seconds actually change.
	var sig := ""
	for e in effects:
		if e is Dictionary:
			sig += "%s:%s:%s|" % [str(e.get("name", "")), e.get("remaining", 0), e.get("harmful", false)]
	if _effect_row_sigs.get(container) == sig:
		return
	_effect_row_sigs[container] = sig
	for c in container.get_children():
		c.queue_free()
	for e in effects:
		if e is Dictionary:
			container.add_child(_make_effect_chip(e))

func _update_buff_bar() -> void:
	var eff = _self_entity().get("effects", [])
	_render_effect_row(_buff_bar, eff if eff is Array else [])

func _invite_target() -> void:
	var t := _live_target_entity()
	if t.is_empty() or not bool(t.get("is_player", false)):
		_push_log("Target a player first, then press G to invite them to your party.")
		return
	_request_server_command("invite")
	_push_log("Invited %s to your party." % str(t.get("name", "player")))

func _accept_party_invite() -> void:
	_request_server_command("accept_alliance")
	_party_invite_panel.visible = false
	_party_invite_from = ""

func _decline_party_invite() -> void:
	_request_server_command("decline_alliance")
	_party_invite_panel.visible = false
	_party_invite_from = ""

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
	_apply_player_visibility()
	_update_camera_collision()


func _desired_camera_local_offset() -> Vector3:
	var desired := _camera_base_local_offset
	if desired == Vector3.ZERO and camera != null:
		desired = camera.position
	# Blend from the high "over the shoulder from above" framing at far zoom
	# down to shoulder level up close, so zooming in keeps the character in
	# frame instead of staring down at the top of their head.
	var t := clampf((_camera_zoom - CAMERA_ZOOM_MIN) / (CAMERA_ZOOM_MAX - CAMERA_ZOOM_MIN), 0.0, 1.0)
	desired.y = lerpf(CAMERA_NEAR_HEIGHT, desired.y, t)
	desired.z = _camera_zoom
	return desired


func _set_first_person(on: bool) -> void:
	if _first_person == on:
		return
	_first_person = on
	if not on:
		_camera_zoom = CAMERA_ZOOM_MIN
	_apply_camera_zoom()


func _apply_player_visibility() -> void:
	# In first person the player's own model (and the capsule fallback) must
	# not block the view.
	if _player_rig and is_instance_valid(_player_rig):
		_player_rig.visible = not _first_person
	var capsule_mesh := player_body.get_node_or_null("PlayerMesh") if player_body else null
	if capsule_mesh:
		capsule_mesh.visible = (not _first_person) and _player_model_key == ""


func _update_camera_collision() -> void:
	if camera == null or camera_pitch == null or player_body == null:
		return
	if _first_person:
		camera.position = CAMERA_FP_OFFSET
		camera.rotation.x = 0.0
		return
	# Level the camera's fixed downward tilt out as the player zooms in.
	var t := clampf((_camera_zoom - CAMERA_ZOOM_MIN) / (CAMERA_ZOOM_MAX - CAMERA_ZOOM_MIN), 0.0, 1.0)
	camera.rotation.x = lerpf(0.0, _camera_base_rotation_x, t)
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
	# Zooming in past the closest third-person distance enters first person;
	# the first zoom-out step leaves it again.
	if direction < 0.0:
		if _first_person:
			return
		if _camera_zoom <= CAMERA_ZOOM_MIN + 0.01:
			_set_first_person(true)
			return
	elif _first_person:
		_set_first_person(false)
		return
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
	_apply_world_time_to_sky()
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
	_apply_world_time_to_sky()
	_update_labels()

# --- Server-authoritative time of day -> Sky3D ----------------------------------
func _find_sky() -> Node:
	if _sky3d != null and is_instance_valid(_sky3d):
		return _sky3d
	# The zone scene (e.g. trinst.tscn) carries a Sky3D under the world subviewport.
	var found := find_children("*", "Sky3D", true, false)
	if not found.is_empty():
		_sky3d = found[0]
		# Match the server clock (theworld.py: 1 game day = 1 real hour) so the sky
		# advances smoothly between the server's syncTime snaps instead of drifting.
		if "minutes_per_day" in _sky3d:
			_sky3d.minutes_per_day = 60.0
	return _sky3d

func _apply_world_time_to_sky() -> void:
	var sky := _find_sky()
	if sky == null:
		return
	var h := float(int(world_time.get("hour", 12)))
	var m := float(int(world_time.get("minute", 0)))
	if "current_time" in sky:
		sky.current_time = h + m / 60.0

# --- Chat / slash commands ------------------------------------------------------
func _open_chat() -> void:
	if chat_input == null:
		return
	_release_mouse()
	chat_input.text = ""
	chat_input.visible = true
	chat_input.grab_focus()

func _close_chat() -> void:
	if chat_input == null:
		return
	chat_input.release_focus()
	chat_input.visible = false
	_capture_mouse()

func _on_chat_gui_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		_close_chat()
		accept_event()

func _on_chat_submitted(text: String) -> void:
	_close_chat()
	text = text.strip_edges()
	if text.is_empty():
		return
	if text.begins_with("/"):
		_run_slash_command(text.substr(1))
	else:
		# Plain text: no chat channel wired yet, so just echo locally.
		_push_log("%s: %s" % [str(current_payload.get("player_name", "You")), text])

func _run_slash_command(cmd: String) -> void:
	var parts := cmd.split(" ", false)
	if parts.is_empty():
		return
	var name := String(parts[0]).to_lower()
	var args: Array = parts.slice(1)
	match name:
		"time":
			_cmd_time(args)
		"help", "commands", "?":
			_push_log("[cmd] /time set <day|night|dawn|dusk|noon|midnight|HH[:MM]>   •   /time (show)   •   /help")
		_:
			_push_log("[cmd] Unknown command: /%s   (try /help)" % name)

func _cmd_time(args: Array) -> void:
	if args.is_empty() or String(args[0]).to_lower() == "show":
		_push_log("[time] World time is %02d:%02d" % [int(world_time.get("hour", 0)), int(world_time.get("minute", 0))])
		return
	# Accept "/time set day" and the shorthand "/time day".
	var word := String(args[0]).to_lower()
	if word == "set":
		word = String(args[1]).to_lower() if args.size() > 1 else ""
	var hm := _parse_timeword(word)
	if hm.is_empty():
		_push_log("[time] Usage: /time set <day|night|dawn|dusk|noon|midnight|HH[:MM]>")
		return
	# Server is authoritative: it sets world.time and syncTimes every client, so
	# the change is shared by everyone (routed through the existing cheat channel).
	_request_server_command("cheat", {"action": "set_time", "params": hm})
	_push_log("[time] Requested %02d:%02d" % [int(hm.get("hour", 12)), int(hm.get("minute", 0))])

func _parse_timeword(w: String) -> Dictionary:
	w = w.strip_edges().to_lower()
	match w:
		"day", "noon", "midday": return {"hour": 12, "minute": 0}
		"midnight": return {"hour": 0, "minute": 0}
		"night": return {"hour": 22, "minute": 0}
		"dawn", "sunrise", "morning": return {"hour": 6, "minute": 0}
		"dusk", "sunset", "evening": return {"hour": 18, "minute": 0}
	if w.contains(":"):
		var p := w.split(":")
		if p.size() == 2 and String(p[0]).is_valid_int() and String(p[1]).is_valid_int():
			return {"hour": clampi(int(p[0]), 0, 23), "minute": clampi(int(p[1]), 0, 59)}
	elif w.is_valid_int():
		return {"hour": clampi(int(w), 0, 23), "minute": 0}
	return {}

func set_zone_transfer(payload: Dictionary):
	current_payload["zone_transfer"] = payload.duplicate(true)
	_update_labels()

func set_target_description(target: Dictionary):
	server_target_description = target.duplicate(true)
	_update_labels()

func apply_vfx_events(events: Array):
	# Zone visual events captured server-side (see stubsim._capture_vfx_call):
	# skill/spell animations, particles, explosions, casting rings, 3D sounds.
	if events.is_empty():
		return
	for ev in events:
		if not (ev is Dictionary):
			continue
		var etype := str(ev.get("event", ""))
		var sim_id := int(ev.get("sim_id", 0))
		if etype == "sound3d":
			var raw = ev.get("position", [])
			if raw is Array and raw.size() >= 3 and _server_origin_offset != Vector3.ZERO:
				var world_root := npc_root.get_parent()
				VFX.sound3d(world_root, _server_to_godot(raw), str(ev.get("sound", "")), bool(ev.get("big", false)))
			continue
		var node := _node_for_sim_id(sim_id)
		if node == null:
			continue
		var rig = _rig_for_node(node)
		match etype:
			"anim":
				if rig:
					rig.play_overlay(str(ev.get("anim", "")))
			"particles":
				var emitter_name := str(ev.get("emitter", ""))
				var p := VFX.emitter(node, Vector3(0, 1.1, 0), emitter_name,
					str(ev.get("texture", "")), float(ev.get("duration", 1.5)))
				# Tag cast wind-up emitters so the casting-end event (fired on
				# every completion/interrupt path) can stop them early.
				if emitter_name.to_lower().contains("casting"):
					VFX.tag_emitter(p, "casting")
			"particle_nodes":
				for pn in ev.get("nodes", []):
					if pn is Dictionary:
						VFX.emitter(node, Vector3(0, 1.1, 0), str(pn.get("particle", "")),
							str(pn.get("texture", "")), float(pn.get("duration", 2.0)))
			"explosion":
				VFX.explosion(node, Vector3(0, 1.0, 0), str(ev.get("name", "")))
			"spell_effect":
				# SimpleZodiacN etc — the casting circle under the character.
				VFX.tag_emitter(VFX.casting_ring(node, 12.0), "casting")
			"casting":
				if not bool(ev.get("on", true)):
					VFX.stop_emitters(node, "casting")
					if rig:
						rig.clear_overlay()
					if node == player_body and _cast_bar:
						_cast_bar.visible = false
				elif rig and node != player_body:
					# NPC cast wind-up (the local player gets begin_casting).
					rig.play_overlay("spellprepare", 10.0)
			"item_particle":
				if rig:
					# server slots: 11 primary -> mount 0, 12 secondary -> mount 1
					var slot := int(ev.get("slot", 11))
					var mkey := "0" if slot == 11 else "1"
					rig.set_mount_particle(mkey, str(ev.get("particle", "")), str(ev.get("texture", "")))

func _node_for_sim_id(sim_id: int) -> Node3D:
	if sim_id <= 0:
		return null
	var self_ent := _self_entity()
	if int(self_ent.get("sim_id", -1)) == sim_id:
		return player_body
	for body in replicated_entity_nodes.values():
		if body is StaticBody3D and is_instance_valid(body):
			var ent = body.get_meta("entity", {})
			if ent is Dictionary and int(ent.get("sim_id", -1)) == sim_id:
				return body
	return null

func _rig_for_node(node: Node3D):
	if node == player_body:
		return _player_rig
	if node and node.has_meta("rig"):
		var rig = node.get_meta("rig")
		if rig and is_instance_valid(rig):
			return rig
	return null

func set_entities(entities: Array):
	# The proxy delta-compresses snapshots: after an entity's static identity /
	# model / appearance / equipment has been sent once, later snapshots carry
	# only its dynamic fields (position, rotation, health, combat flags). Merge
	# each partial onto its cached full copy so the rest of the view always sees
	# complete entities. Entities absent from a snapshot are dropped from the
	# cache, so they get a fresh full block if they come back into range.
	var merged: Array = []
	var present: Dictionary = {}
	for e in entities:
		if not (e is Dictionary):
			continue
		var key = e.get("id", e.get("sim_id", 0))
		present[key] = true
		var full: Dictionary
		if _entity_cache.has(key):
			full = _entity_cache[key]
			for k in e.keys():
				full[k] = e[k]
		else:
			full = (e as Dictionary).duplicate(true)
			_entity_cache[key] = full
		merged.append(full)
	for key in _entity_cache.keys():
		if not present.has(key):
			_entity_cache.erase(key)
	replicated_entities = merged
	_sync_entity_markers()
	_update_pet_bar()
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
	GameAudio.attach_zone_ambience(zone_node, zone)
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
	# How far the SERVER position moved since the last snapshot. A real teleport
	# (zone link, respawn, GM warp) is a single large jump; gradual divergence
	# (e.g. holding into a wall — the headless server has no collision, so its
	# copy of us keeps sliding forward) is many small steps.
	var server_jump := 0.0
	if _has_last_server_pos:
		server_jump = Vector2(server_pos.x - _last_server_pos.x, server_pos.z - _last_server_pos.z).length()
	_last_server_pos = server_pos
	_has_last_server_pos = true

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
	# Hard-snap ONLY on a genuine server teleport (sudden jump). A large drift that
	# built up gradually is corrected smoothly via move_and_slide below, so the
	# player slides along geometry and is never teleported THROUGH a wall.
	if server_jump >= SERVER_RECONCILE_SNAP_THRESHOLD:
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

func _single_tex_for(entity: Dictionary) -> String:
	# Whole-body monster texture (spawn.textureSingle) streamed by the server,
	# e.g. "single/elemental_fire". Empty for players and embedded-texture mobs.
	return str(entity.get("tex_single", ""))

func _mounts_for(entity: Dictionary) -> Dictionary:
	# Worn equipment models from the server: {"0": {model, material}, ...}
	# (mount0 primary hand / 1 off hand / 2 shield / 3 head).
	var mounts = entity.get("mounts", {})
	return mounts if mounts is Dictionary else {}

func _ensure_player_model(entity: Dictionary) -> void:
	# Build/replace the avatar once we know the player's race/sex/model, then
	# keep its armor textures + mounted equipment in sync with the server
	# (the rig dedupes by signature, so per-snapshot calls are cheap).
	var path := _glb_for_entity(entity)
	if path == "":
		return
	if path != _player_model_key:
		if _player_rig and is_instance_valid(_player_rig):
			_player_rig.queue_free()
		_player_rig = CharacterRigScript.new()
		_player_rig.position = Vector3(0.0, -0.9, 0.0)
		player_body.add_child(_player_rig)
		if not _player_rig.setup(path, 0.0):
			return
		_player_model_key = path
		var capsule_mesh := player_body.get_node_or_null("PlayerMesh")
		if capsule_mesh:
			capsule_mesh.visible = false
		_apply_player_visibility()
	if _player_rig and is_instance_valid(_player_rig):
		_player_rig.apply_appearance(_appearance_for(entity))
		_player_rig.apply_single_texture(_single_tex_for(entity))
		_player_rig.apply_mounts(_mounts_for(entity))
		# Show our own buff state on the avatar: Enlarge/Shrink (scale),
		# Invisibility (fade), Flying/Levitate (lift). Scale the visual rig only —
		# the collision capsule stays normal so movement is unaffected.
		var s := float(entity.get("scale", 1.0))
		if s > 0.0:
			_player_rig.scale = Vector3(s, s, s)
		_player_rig.set_fade(float(entity.get("visibility", 1.0)))
		_player_rig.position.y = -0.9 + (ENTITY_FLYING_LIFT if float(entity.get("flying", 0.0)) > 0.0 else 0.0)

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
		rig.apply_single_texture(_single_tex_for(entity))
		rig.apply_mounts(_mounts_for(entity))
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
	# Hit reaction: flinch when health drops (the original client did this
	# locally on damage too). Rate-limited so sustained melee doesn't stunlock
	# the animation; skipped while dead or mid-swing.
	var prev: Dictionary = body.get_meta("entity", {})
	var prev_hp := float(prev.get("health", -1.0))
	var new_hp := float(entity.get("health", -1.0))
	if prev_hp > 0.0 and new_hp >= 0.0 and new_hp < prev_hp - 0.5 and not bool(entity.get("dead", false)):
		var now := Time.get_ticks_msec() / 1000.0
		if now >= float(body.get_meta("pain_cooldown", 0.0)) and not bool(entity.get("attacking", false)):
			body.set_meta("pain_cooldown", now + 1.6)
			var pain_rig = body.get_meta("rig", null)
			if pain_rig and is_instance_valid(pain_rig):
				pain_rig.play_overlay("pain1" if randi() % 2 == 0 else "pain2")
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
	# Keep armor textures + mounted equipment in sync (rig dedupes by signature).
	var rig = body.get_meta("rig", null)
	if rig and is_instance_valid(rig):
		rig.apply_appearance(_appearance_for(entity))
		rig.apply_single_texture(_single_tex_for(entity))
		rig.apply_mounts(_mounts_for(entity))
		# Invisibility (visibility < 1) fades the model; Flying/Levitate lifts it.
		rig.set_fade(float(entity.get("visibility", 1.0)))
		rig.position.y = ENTITY_FLYING_LIFT if float(entity.get("flying", 0.0)) > 0.0 else 0.0

func _sync_entity_markers():
	if replicated_entities.is_empty():
		return

	# Find self entity and reconcile player position with server
	for entity in replicated_entities:
		if entity is Dictionary and bool(entity.get("is_self", false)):
			var raw_pos = entity.get("position", [])
			# Pick the avatar model from the player's own race/sex/model.
			_ensure_player_model(entity)
			# Flinch when our own health drops (same as NPC hit reactions).
			var hp := float(entity.get("health", -1.0))
			var now_s := Time.get_ticks_msec() / 1000.0
			if _self_prev_health > 0.0 and hp >= 0.0 and hp < _self_prev_health - 0.5 \
					and now_s >= _self_pain_cooldown and _player_rig and is_instance_valid(_player_rig):
				_self_pain_cooldown = now_s + 1.6
				_player_rig.play_overlay("pain1" if randi() % 2 == 0 else "pain2")
			if hp >= 0.0:
				_self_prev_health = hp
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
		# A corpse must not move. The first frame an entity is dead we snap it to the
		# death spot (ground-snapped) and mark it frozen; after that we ignore the
		# server's position/rotation entirely, so rubber-banding or a mob that died
		# mid-stride can't make the body slide or spin. Alive entities interpolate
		# toward the latest server position as usual.
		var entity_is_dead := bool(entity_dict.get("dead", false)) or float(entity_dict.get("health", 1.0)) <= 0.0
		if entity_is_dead:
			if not bool(body.get_meta("dead_frozen", false)):
				body.position = godot_pos
				body.set_meta("target_position", godot_pos)
				body.set_meta("dead_frozen", true)
		else:
			body.set_meta("dead_frozen", false)
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

func _update_pet_bar() -> void:
	if _pet_bar == null:
		return
	var pet: Dictionary = {}
	for entity in replicated_entities:
		if entity is Dictionary and bool(entity.get("is_my_pet", false)) and not bool(entity.get("dead", false)):
			pet = entity
			break
	if pet.is_empty():
		_pet_bar.visible = false
		return
	_pet_label.text = "%s  %d%%" % [str(pet.get("name", "Pet")),
		int(round(float(pet.get("health_ratio", 1.0)) * 100.0))]
	_pet_bar.visible = true

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
	hotbar.prune_unknown(abilities, _last_spellbook.has("spells"), spells)
	hotbar.default_fill_from_skills(abilities, spells)
	hotbar.update_cooldowns(abilities, spells)
	if spellbook_window:
		spellbook_window.apply_skills(abilities)

func _live_target_entity() -> Dictionary:
	# Current snapshot data for the targeted entity (matched by sim id, then by
	# name), so target UI reflects live health rather than acquire-time values.
	var want_id := int(server_target_description.get("id", server_target_description.get("sim_id", 0)))
	var want_name := str(server_target_description.get("name", ""))
	var by_name: Dictionary = {}
	for entity in replicated_entities:
		if not (entity is Dictionary) or entity.get("is_self"):
			continue
		if want_id != 0 and int(entity.get("id", 0)) == want_id:
			return entity
		if not want_name.is_empty() and str(entity.get("name", "")) == want_name and by_name.is_empty():
			by_name = entity
	return by_name


func _target_action_prompt() -> Dictionary:
	# Contextual hint shown under the target frame, keyed off the current target's
	# type. Prefer the live replicated entity (authoritative is_player/is_enemy/
	# dead flags), falling back to the acquire-time description.
	var live := _live_target_entity()
	var src: Dictionary = live if not live.is_empty() else server_target_description
	var is_dead := bool(src.get("dead", false)) or float(src.get("health", 1.0)) <= 0.0
	if is_dead:
		return {"text": "Press E to loot", "color": Color(0.95, 0.85, 0.45)}
	if bool(src.get("is_player", false)):
		return {"text": "Press G to invite to party", "color": Color(0.55, 0.80, 0.98)}
	if bool(src.get("is_enemy", false)):
		return {"text": "Press Q to attack", "color": Color(0.96, 0.55, 0.45)}
	# Neutral NPC (vendor / trainer / quest giver).
	return {"text": "Press E to talk", "color": Color(0.72, 0.92, 0.74)}

func _bridge_status_text() -> String:
	return "Bridge status: abilities, attack toggle, target cycling, interact, and click-to-target now go back to the legacy world server via PlayerAvatar.doCommand / targetEntity. Replicated entities are rendered from server snapshots and interpolated between updates for smoother motion."

func _update_labels():
	if health_bar == null:
		return  # HUD not built yet
	_update_party_health()
	_update_buff_bar()
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
		# The description is a one-shot copy from when the target was acquired;
		# track the live replicated entity so the bar follows actual damage.
		var live := _live_target_entity()
		if not live.is_empty():
			t_health = float(live.get("health", t_health))
			t_max_health = float(live.get("max_health", t_max_health))
			t_dead = bool(live.get("dead", t_dead)) or t_health <= 0.0
		var standing_txt := (" (%s)" % t_standing) if not t_standing.is_empty() else ""
		target_name_label.text = "%s   Lv%s %s%s%s" % [t_name, t_level, t_race, standing_txt, "  [DEAD]" if t_dead else ""]
		if t_health >= 0.0:
			_set_bar(target_health_bar, t_health, t_max_health, "Target", target_health_value_label)
			target_health_bar.visible = true
		else:
			target_health_bar.visible = false
		var prompt := _target_action_prompt()
		target_prompt_label.text = str(prompt.get("text", ""))
		target_prompt_label.add_theme_color_override("font_color", prompt.get("color", Color(0.80, 0.92, 0.80)))
		target_prompt_label.visible = true
		var t_eff = (live.get("effects", []) if not live.is_empty() else server_target_description.get("effects", []))
		_render_effect_row(_target_buff_bar, t_eff if t_eff is Array else [])
		target_frame.visible = true
	else:
		_render_effect_row(_target_buff_bar, [])
		var server_target_name: String = str(rapid_info.get("tgt", ""))
		if not server_target_name.is_empty():
			target_name_label.text = server_target_name
			var sth: float = float(rapid_info.get("tgthealth", -1.0))
			if sth >= 0.0:
				_set_bar(target_health_bar, sth * 100.0, 100.0, "Target", target_health_value_label)
				target_health_bar.visible = true
			else:
				target_health_bar.visible = false
			# No type info on this lightweight path; show a generic interact hint.
			target_prompt_label.text = "Press E to interact"
			target_prompt_label.add_theme_color_override("font_color", Color(0.80, 0.92, 0.80))
			target_prompt_label.visible = true
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
	# Tab targets what you're roughly looking at: rank the live entities inside
	# a frontal cone by how close they are to the crosshair, and cycle through
	# that ranking on repeated presses. The legacy CYCLETARGET command ignored
	# facing entirely (it walked the server's mob list by distance).
	var cands := _tab_target_candidates()
	if cands.is_empty():
		interaction_message = "No target in front of you."
		return
	var ids: Array = []
	for c in cands:
		ids.append(int(c["id"]))
	if ids != _tab_cycle_ids:
		_tab_cycle_ids = ids
		_tab_cycle_pos = 0
	else:
		_tab_cycle_pos = (_tab_cycle_pos + 1) % ids.size()
	var chosen: Dictionary = cands[_tab_cycle_pos]
	interaction_message = "Targeted %s." % str(chosen.get("name", "entity"))
	_request_server_command("target_entity", {"entity_id": int(chosen["id"])})

func _tab_target_candidates() -> Array:
	# Alive entities inside the frontal cone, ordered by angular distance from
	# the crosshair (with a mild bias toward nearer mobs at similar angles).
	var out: Array = []
	if camera == null:
		return out
	var cam_pos := camera.global_position
	var fwd := -camera.global_transform.basis.z
	for entity in replicated_entities:
		if not (entity is Dictionary) or entity.get("is_self"):
			continue
		if bool(entity.get("dead", false)) or float(entity.get("health", 1.0)) <= 0.0:
			continue
		var id := int(entity.get("id", 0))
		if id <= 0:
			continue
		var pos: Vector3
		var body: Variant = replicated_entity_nodes.get(_entity_key(entity))
		if body is Node3D and is_instance_valid(body):
			pos = (body as Node3D).global_position
		else:
			pos = _world_position_from_server(entity.get("position", [0.0, 0.0, 0.0]))
		var rel := pos - cam_pos
		var dist := rel.length()
		if dist < 0.01 or dist > TAB_TARGET_MAX_DISTANCE:
			continue
		var ang := rad_to_deg(fwd.angle_to(rel / dist))
		if ang > TAB_TARGET_CONE_DEG:
			continue
		out.append({
			"id": id,
			"name": entity.get("public_name", entity.get("name", "entity")),
			"score": ang + dist * 0.5,
		})
	out.sort_custom(func(a, b): return float(a["score"]) < float(b["score"]))
	return out

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

func _begin_cast_bar(cast_time: float) -> void:
	if _cast_bar == null or cast_time <= 0.05:
		return
	_cast_started = Time.get_ticks_msec() / 1000.0
	_cast_duration = cast_time
	_cast_bar.value = 0.0
	_cast_bar.visible = true

func _update_cast_bar() -> void:
	if _cast_bar == null or not _cast_bar.visible:
		return
	var now := Time.get_ticks_msec() / 1000.0
	var t := (now - _cast_started) / maxf(_cast_duration, 0.01)
	if t >= 1.0:
		_cast_bar.visible = false
	else:
		_cast_bar.value = t

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

# ---------------------------------------------------------------------------
# Input map: gameplay actions bound to BOTH keyboard/mouse and a gamepad, so the
# game plays like an action MMO on a controller (left stick move, right stick
# camera, face/shoulder buttons + d-pad for actions and the two hotbars).
# Defined in code (idempotent) so the bindings live with the gameplay logic and
# can't drift from the handlers that use them.
# ---------------------------------------------------------------------------
func _setup_input_actions() -> void:
	# axis pairs: left stick = move, right stick = look. value is the sign of the
	# half-axis this action listens to.
	var defs := {
		"mom_move_left":   [{"key": KEY_A}, {"axis": JOY_AXIS_LEFT_X, "v": -1.0}],
		"mom_move_right":  [{"key": KEY_D}, {"axis": JOY_AXIS_LEFT_X, "v": 1.0}],
		"mom_move_forward":[{"key": KEY_W}, {"axis": JOY_AXIS_LEFT_Y, "v": -1.0}],
		"mom_move_back":   [{"key": KEY_S}, {"axis": JOY_AXIS_LEFT_Y, "v": 1.0}],
		"mom_look_left":   [{"key": KEY_LEFT}, {"axis": JOY_AXIS_RIGHT_X, "v": -1.0}],
		"mom_look_right":  [{"key": KEY_RIGHT}, {"axis": JOY_AXIS_RIGHT_X, "v": 1.0}],
		"mom_look_up":     [{"key": KEY_UP}, {"axis": JOY_AXIS_RIGHT_Y, "v": -1.0}],
		"mom_look_down":   [{"key": KEY_DOWN}, {"axis": JOY_AXIS_RIGHT_Y, "v": 1.0}],
		"mom_jump":        [{"key": KEY_SPACE}, {"button": JOY_BUTTON_A}],
		"mom_interact":    [{"key": KEY_E}, {"button": JOY_BUTTON_X}],
		"mom_attack":      [{"key": KEY_Q}, {"button": JOY_BUTTON_RIGHT_SHOULDER}],
		"mom_target":      [{"key": KEY_TAB}, {"button": JOY_BUTTON_B}],
		"mom_hotbar_page": [{"key": KEY_R}, {"button": JOY_BUTTON_Y}],
		"mom_hotbar_secondary": [{"key": KEY_SHIFT}, {"button": JOY_BUTTON_LEFT_SHOULDER}],
		"mom_inventory":   [{"key": KEY_I}, {"button": JOY_BUTTON_BACK}],
		# Hotbar slots 1-4 reachable on the d-pad; 5-0 stay keyboard (or reached on
		# the pad via page-cycle / secondary-hold).
		"mom_hotbar_1": [{"key": KEY_1}, {"key": KEY_KP_1}, {"button": JOY_BUTTON_DPAD_UP}],
		"mom_hotbar_2": [{"key": KEY_2}, {"key": KEY_KP_2}, {"button": JOY_BUTTON_DPAD_RIGHT}],
		"mom_hotbar_3": [{"key": KEY_3}, {"key": KEY_KP_3}, {"button": JOY_BUTTON_DPAD_DOWN}],
		"mom_hotbar_4": [{"key": KEY_4}, {"key": KEY_KP_4}, {"button": JOY_BUTTON_DPAD_LEFT}],
		"mom_hotbar_5": [{"key": KEY_5}, {"key": KEY_KP_5}],
		"mom_hotbar_6": [{"key": KEY_6}, {"key": KEY_KP_6}],
		"mom_hotbar_7": [{"key": KEY_7}, {"key": KEY_KP_7}],
		"mom_hotbar_8": [{"key": KEY_8}, {"key": KEY_KP_8}],
		"mom_hotbar_9": [{"key": KEY_9}, {"key": KEY_KP_9}],
		"mom_hotbar_10": [{"key": KEY_0}, {"key": KEY_KP_0}],
	}
	for action in defs:
		if not InputMap.has_action(action):
			InputMap.add_action(action, 0.2)  # deadzone for stick-driven actions
		else:
			InputMap.action_erase_events(action)
		for ev_def in defs[action]:
			var ev: InputEvent
			if ev_def.has("key"):
				var k := InputEventKey.new()
				k.keycode = ev_def["key"]
				k.physical_keycode = ev_def["key"]
				ev = k
			elif ev_def.has("button"):
				var b := InputEventJoypadButton.new()
				b.button_index = ev_def["button"]
				ev = b
			else:
				var m := InputEventJoypadMotion.new()
				m.axis = ev_def["axis"]
				m.axis_value = ev_def["v"]
				ev = m
			InputMap.action_add_event(action, ev)

# Discrete gameplay actions (work from key OR gamepad). Returns true if handled.
func _handle_action_event(event: InputEvent) -> bool:
	if event.is_action_pressed("mom_jump"):
		jump_requested = true
		return true
	if event.is_action_pressed("mom_interact"):
		_send_interact_command()
		return true
	if event.is_action_pressed("mom_attack"):
		_toggle_autoattack()
		return true
	if event.is_action_pressed("mom_target"):
		_cycle_target()
		return true
	if event.is_action_pressed("mom_hotbar_page"):
		if hotbar:
			hotbar.cycle_page()
		return true
	if event.is_action_pressed("mom_inventory"):
		_toggle_inventory()
		return true
	for i in range(10):
		if event.is_action_pressed("mom_hotbar_%d" % (i + 1)):
			if hotbar:
				hotbar.activate(i)
			return true
	return false

func _input(event):
	if not visible:
		return
	if _is_dead:
		# While dead the only interaction is releasing the spirit. Enter/Space
		# respawn; the overlay button still receives mouse clicks (we don't
		# accept_event for those), and movement keys are ignored in _physics_process.
		if event is InputEventKey and event.pressed and not event.echo \
				and event.keycode in [KEY_ENTER, KEY_KP_ENTER, KEY_SPACE]:
			_do_respawn()
			accept_event()
		return
	# Discrete gameplay actions (jump / interact / attack / target / abilities /
	# hotbar page / inventory) from key OR gamepad. Skipped while a text field is
	# focused so typing doesn't fire abilities.
	if not _typing_in_ui() and _handle_action_event(event):
		accept_event()
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
			KEY_ENTER, KEY_KP_ENTER:
				_open_chat()
				accept_event()
			KEY_QUOTELEFT, KEY_F8:
				# ` (backquote) is the primary cheat hotkey. F8 also works in a
				# standalone build, but when the game runs embedded in the Godot
				# editor F8 is the editor's own Stop shortcut and kills the run.
				_toggle_cheats()
			KEY_U:
				_unstuck()
			KEY_G:
				_invite_target()
			KEY_Y:
				if _party_invite_panel and _party_invite_panel.visible:
					_accept_party_invite()
			KEY_N:
				if _party_invite_panel and _party_invite_panel.visible:
					_decline_party_invite()
			KEY_J:
				_toggle_journal()
			KEY_P, KEY_B:
				_toggle_spellbook()
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
	# Gather movement inputs (not while typing into a window text field, and not
	# while dead — a corpse shouldn't run around). WASD and the left stick both
	# feed the mom_move_* actions, so this is one analog read for both.
	var input_vec := Vector2.ZERO
	if not _typing_in_ui() and not _is_dead:
		input_vec = Input.get_vector("mom_move_left", "mom_move_right", "mom_move_back", "mom_move_forward")
		# Right-stick (or arrow keys) camera look — the action-MMO feel. Mouse look
		# stays in _input; this runs every frame for smooth analog turning.
		var look := Input.get_vector("mom_look_left", "mom_look_right", "mom_look_up", "mom_look_down")
		if look.length_squared() > 0.0004:
			player_body.rotate_y(-look.x * GAMEPAD_LOOK_SENSITIVITY * delta)
			camera_pitch.rotate_x(-look.y * GAMEPAD_PITCH_SENSITIVITY * delta)
			camera_pitch.rotation.x = clamp(camera_pitch.rotation.x, deg_to_rad(-70), deg_to_rad(70))
			_update_camera_collision()
		# Hold the secondary-bar modifier (Shift / left bumper) to reveal + use bar 2.
		if hotbar:
			hotbar.set_secondary_peek(Input.is_action_pressed("mom_hotbar_secondary"))
	elif hotbar:
		hotbar.set_secondary_peek(false)

	# Local prediction: move CharacterBody3D so movement feels responsive
	var basis: Basis = player_body.global_transform.basis
	var move_dir: Vector3 = (basis.x * input_vec.x) + (-basis.z * input_vec.y)
	if move_dir.length() > 1.0:
		move_dir = move_dir.normalized()
	velocity.x = move_dir.x * MOVE_SPEED
	velocity.z = move_dir.z * MOVE_SPEED
	# Flying / Levitate / Slow Fall: when the buff is active, descend gently
	# (and jump floatier) instead of normal gravity, so the effect is felt.
	var flying := float(_self_entity().get("flying", 0.0)) > 0.0
	if player_body.is_on_floor():
		if jump_requested:
			velocity.y = JUMP_VELOCITY
		else:
			velocity.y = 0.0
	else:
		velocity.y -= (GRAVITY * 0.18 if flying else GRAVITY) * delta
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
		# Frozen corpse: never interpolate it (so it can't slide); just hold the
		# death pose. Everything below only applies to living entities.
		if bool(body.get_meta("dead_frozen", false)):
			var dead_rig = body.get_meta("rig", null)
			if dead_rig != null and is_instance_valid(dead_rig):
				dead_rig.drive(0.0, false, true)
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

	_update_cast_bar()

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
