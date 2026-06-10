class_name InventoryWindow
extends GameWindow
## Equipment (paper-doll slots) + 60-slot bag grid + money, driven by the
## server's plain-data inventory snapshots. Item moves use the legacy cursor
## model: click picks the item up onto the server cursor, click again places/
## swaps/equips. Shift-click quick-(un)equips, right-click uses the item.

signal inv_slot_clicked(slot: int, alt: bool, ctrl: bool)
signal destroy_cursor_requested

var money_label: Label
var hint_label: Label
var destroy_button: Button
var _worn_slots: Dictionary = {}   # slot index -> SlotButton
var _bag_slots: Dictionary = {}    # slot index -> SlotButton
var char_id := 0
var cursor_item: Dictionary = {}
var snapshot: Dictionary = {}

func _init():
	super._init("Inventory", Color(0.75, 0.6, 0.3))

	var columns := HBoxContainer.new()
	columns.add_theme_constant_override("separation", 12)
	content.add_child(columns)

	# Paper-doll: two columns of named equipment slots.
	var worn_grid := GridContainer.new()
	worn_grid.columns = 2
	worn_grid.add_theme_constant_override("h_separation", 4)
	worn_grid.add_theme_constant_override("v_separation", 4)
	columns.add_child(worn_grid)
	for slot in range(UIC.WORN_BEGIN, UIC.WORN_END):
		var b := SlotButton.new(40)
		b.clear_slot(UIC.SLOT_NAMES.get(slot, str(slot)))
		b.slot_clicked.connect(_on_slot.bind(slot))
		b.slot_right_clicked.connect(_on_slot_use.bind(slot))
		worn_grid.add_child(b)
		_worn_slots[slot] = b

	# Bags: 10 x 6 grid of carry slots.
	var right := VBoxContainer.new()
	right.add_theme_constant_override("separation", 6)
	columns.add_child(right)
	var bag_grid := GridContainer.new()
	bag_grid.columns = 10
	bag_grid.add_theme_constant_override("h_separation", 4)
	bag_grid.add_theme_constant_override("v_separation", 4)
	right.add_child(bag_grid)
	for i in range(UIC.CARRY_COUNT):
		var slot := UIC.CARRY_BEGIN + i
		var b := SlotButton.new(40)
		b.clear_slot()
		b.slot_clicked.connect(_on_slot.bind(slot))
		b.slot_right_clicked.connect(_on_slot_use.bind(slot))
		bag_grid.add_child(b)
		_bag_slots[slot] = b

	var bottom := HBoxContainer.new()
	bottom.add_theme_constant_override("separation", 10)
	right.add_child(bottom)
	money_label = Label.new()
	money_label.add_theme_font_size_override("font_size", 13)
	money_label.add_theme_color_override("font_color", Color(0.95, 0.85, 0.45))
	bottom.add_child(money_label)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bottom.add_child(spacer)
	destroy_button = Button.new()
	destroy_button.text = "Destroy cursor item"
	destroy_button.visible = false
	destroy_button.focus_mode = Control.FOCUS_NONE
	UIC.style_button(destroy_button)
	destroy_button.pressed.connect(func(): destroy_cursor_requested.emit())
	bottom.add_child(destroy_button)

	hint_label = Label.new()
	hint_label.text = "Click: pick up / place / equip   •   Shift-click: quick equip/unequip   •   Right-click: use"
	hint_label.add_theme_font_size_override("font_size", 10)
	hint_label.add_theme_color_override("font_color", Color(0.65, 0.68, 0.75))
	right.add_child(hint_label)

func _on_slot(alt: bool, ctrl: bool, slot: int) -> void:
	inv_slot_clicked.emit(slot, alt, ctrl)

func _on_slot_use(slot: int) -> void:
	inv_slot_clicked.emit(slot, false, true)  # right-click = use

func apply_snapshot(inv: Dictionary) -> void:
	snapshot = inv
	char_id = int(inv.get("char_id", char_id))
	var by_slot: Dictionary = {}
	for item in inv.get("items", []):
		if item is Dictionary:
			by_slot[int(item.get("slot", -1))] = item
	for slot in _worn_slots.keys():
		_fill(_worn_slots[slot], by_slot.get(slot), UIC.SLOT_NAMES.get(slot, ""))
	for slot in _bag_slots.keys():
		_fill(_bag_slots[slot], by_slot.get(slot), "")
	money_label.text = "Money: %s" % UIC.money_text(int(inv.get("tin", 0)))
	var cur = inv.get("cursor")
	set_cursor_item(cur if cur is Dictionary else {})

func set_cursor_item(item: Dictionary) -> void:
	cursor_item = item if item != null else {}
	destroy_button.visible = not cursor_item.is_empty()

func _fill(button: SlotButton, item, corner: String) -> void:
	if item == null or not (item is Dictionary) or item.is_empty():
		button.clear_slot(corner)
		return
	var tex := UIC.item_icon(str(item.get("bitmap", "")))
	button.set_slot(tex, str(item.get("name", "?")).left(10), int(item.get("stack_count", 1)), corner)
	button.payload = item
	button.tooltip_text = UIC.item_tooltip(item)
	button.add_theme_color_override("font_color", UIC.quality_color(int(item.get("quality", 1))))
