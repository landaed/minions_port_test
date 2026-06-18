class_name SlotButton
extends Button
## Square item/spell/action slot used by the inventory, loot window, spellbook
## and hotbar. Shows the original game's icon art (or a short text fallback),
## a stack-count badge, and supports Godot drag & drop between windows.

signal slot_clicked(alt: bool, ctrl: bool)
signal slot_right_clicked

var payload: Dictionary = {}      # whatever the owner wants to remember per slot
var drag_kind := ""               # "" = not draggable; e.g. "spell"/"skill"/"action"
var accept_kinds: Array = []      # drag kinds this slot accepts ([] = none)
var drop_handler: Callable        # func(data: Dictionary) -> void
var count_label: Label
var corner_label: Label
var _rich_tip := ""               # custom hover tooltip text (replaces flaky built-in)

func _init(size_px: int = 44):
	custom_minimum_size = Vector2(size_px, size_px)
	focus_mode = Control.FOCUS_NONE
	clip_text = true
	expand_icon = true
	add_theme_font_size_override("font_size", 10)
	UIC.style_button(self, false)
	count_label = Label.new()
	count_label.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	count_label.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	count_label.grow_vertical = Control.GROW_DIRECTION_BEGIN
	count_label.offset_right = -3
	count_label.offset_bottom = -1
	count_label.add_theme_font_size_override("font_size", 11)
	count_label.add_theme_color_override("font_color", Color(1, 1, 0.7))
	count_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(count_label)
	corner_label = Label.new()
	corner_label.set_anchors_preset(Control.PRESET_TOP_LEFT)
	corner_label.offset_left = 3
	corner_label.add_theme_font_size_override("font_size", 9)
	corner_label.add_theme_color_override("font_color", Color(0.7, 0.74, 0.8))
	corner_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(corner_label)
	# Self-managed hover tooltip (the built-in one vanishes on the slightest
	# jitter / when the spellbook rebuilds). Stays up until the mouse leaves.
	mouse_entered.connect(_on_tip_enter)
	mouse_exited.connect(UIC.hide_tip)
	tree_exiting.connect(func(): UIC.hide_tip_if_owner(self))

func set_rich_tip(text: String) -> void:
	_rich_tip = text
	# Suppress Godot's built-in tooltip so the two don't fight.
	tooltip_text = ""

func _on_tip_enter() -> void:
	var text := _rich_tip if not _rich_tip.is_empty() else tooltip_text
	UIC.show_tip(self, text)

func set_slot(display_icon: Texture2D, fallback_text: String, count: int = 0, corner: String = "") -> void:
	icon = display_icon
	text = "" if display_icon != null else fallback_text
	count_label.text = str(count) if count > 1 else ""
	corner_label.text = corner
	UIC.style_button(self, display_icon != null or not fallback_text.is_empty())

func clear_slot(corner: String = "") -> void:
	icon = null
	text = ""
	tooltip_text = ""
	payload = {}
	count_label.text = ""
	corner_label.text = corner
	UIC.style_button(self, false)

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_LEFT:
			slot_clicked.emit(event.shift_pressed, event.ctrl_pressed)
		elif event.button_index == MOUSE_BUTTON_RIGHT:
			slot_right_clicked.emit()

func _get_drag_data(_at: Vector2) -> Variant:
	if drag_kind.is_empty() or payload.is_empty():
		return null
	var data := payload.duplicate(true)
	data["kind"] = drag_kind
	var preview := Button.new()
	preview.text = str(payload.get("name", "?"))
	if icon != null:
		preview.icon = icon
		preview.expand_icon = true
		preview.custom_minimum_size = Vector2(40, 40)
	UIC.style_button(preview)
	set_drag_preview(preview)
	return data

func _can_drop_data(_at: Vector2, data: Variant) -> bool:
	return data is Dictionary and accept_kinds.has(str(data.get("kind", "")))

func _drop_data(_at: Vector2, data: Variant) -> void:
	if drop_handler.is_valid():
		drop_handler.call(data)
