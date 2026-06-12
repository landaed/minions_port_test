class_name GameWindow
extends PanelContainer
## Draggable in-game window with a title bar and close button. Subclasses (or
## callers) fill `content`. Windows live above the 3D viewport inside the
## gameplay UI; the gameplay view frees the mouse while any window is open.

signal closed

var title_label: Label
var content: VBoxContainer
var _dragging := false
var _drag_offset := Vector2.ZERO

func _init(title: String = "Window", accent: Color = Color(0.45, 0.5, 0.6)):
	add_theme_stylebox_override("panel", UIC.panel_style(accent))
	custom_minimum_size = Vector2(280, 120)
	visible = false
	mouse_filter = Control.MOUSE_FILTER_STOP

	var root := VBoxContainer.new()
	root.add_theme_constant_override("separation", 6)
	add_child(root)

	var bar := HBoxContainer.new()
	bar.mouse_filter = Control.MOUSE_FILTER_STOP
	root.add_child(bar)
	title_label = Label.new()
	title_label.text = title
	title_label.add_theme_font_size_override("font_size", 14)
	title_label.add_theme_color_override("font_color", Color(0.95, 0.9, 0.75))
	title_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	bar.add_child(title_label)
	var close := Button.new()
	close.text = "✕"
	close.focus_mode = Control.FOCUS_NONE
	close.custom_minimum_size = Vector2(24, 24)
	UIC.style_button(close)
	close.pressed.connect(close_window)
	bar.add_child(close)
	bar.gui_input.connect(_on_bar_input)

	content = VBoxContainer.new()
	content.add_theme_constant_override("separation", 6)
	root.add_child(content)

func close_window() -> void:
	if not visible:
		return
	visible = false
	GameAudio.ui_cancel()
	closed.emit()

func open_window() -> void:
	visible = true
	GameAudio.ui_accept()
	move_to_front()

func toggle_window() -> void:
	if visible:
		close_window()
	else:
		open_window()

func _on_bar_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		_dragging = event.pressed
		_drag_offset = get_global_mouse_position() - global_position
		move_to_front()
	elif event is InputEventMouseMotion and _dragging:
		global_position = get_global_mouse_position() - _drag_offset

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed:
		move_to_front()
