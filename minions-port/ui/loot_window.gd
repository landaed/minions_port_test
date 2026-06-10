class_name LootWindow
extends GameWindow
## Corpse/lootable-object window. The server pushes the loot table (re-fetched
## after every take because slot indices shift); clicking an item quick-loots it
## into the bags, Take All loops over what's left.

signal loot_slot_clicked(slot: int)
signal take_all_requested
signal looting_ended

var _slots: Array[SlotButton] = []
var _status: Label
var current_items: Dictionary = {}  # "0".."15" -> item dict

func _init():
	super._init("Loot", Color(0.7, 0.5, 0.2))
	var grid := GridContainer.new()
	grid.columns = 4
	grid.add_theme_constant_override("h_separation", 4)
	grid.add_theme_constant_override("v_separation", 4)
	content.add_child(grid)
	for i in range(16):
		var b := SlotButton.new(44)
		b.clear_slot()
		b.slot_clicked.connect(func(_alt, _ctrl): loot_slot_clicked.emit(i))
		grid.add_child(b)
		_slots.append(b)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	content.add_child(row)
	var take_all := Button.new()
	take_all.text = "Take All"
	take_all.focus_mode = Control.FOCUS_NONE
	UIC.style_button(take_all)
	take_all.pressed.connect(func(): take_all_requested.emit())
	row.add_child(take_all)
	_status = Label.new()
	_status.add_theme_font_size_override("font_size", 11)
	row.add_child(_status)
	closed.connect(func(): looting_ended.emit())

func apply_loot(items: Dictionary) -> void:
	current_items = items
	if items.is_empty():
		# Empty table = corpse fully looted / crumbled; close silently.
		if visible:
			visible = false  # not close_window(): endLooting already happened server-side
		return
	open_window()
	for i in range(16):
		var item = items.get(str(i))
		var b := _slots[i]
		if item is Dictionary and not item.is_empty():
			var tex := UIC.item_icon(str(item.get("bitmap", "")))
			b.set_slot(tex, str(item.get("name", "?")).left(9), int(item.get("stack_count", 1)))
			b.tooltip_text = UIC.item_tooltip(item)
			b.payload = item
		else:
			b.clear_slot()
	_status.text = "%d item(s)" % items.size()
