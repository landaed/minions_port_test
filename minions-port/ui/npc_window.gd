class_name NpcWindow
extends GameWindow
## NPC interaction window: legacy dialog tree (text + numbered choices, which is
## also how class trainers teach skills) plus the vendor pane when the NPC
## sells. Selling uses the player's bag items list (fed from inventory
## snapshots).

signal choice_selected(index: int)
signal buy_requested(vendor_index: int)
signal sell_requested(slot: int)
signal interaction_ended

var dialog_text: RichTextLabel
var choices_box: VBoxContainer
var vendor_box: VBoxContainer
var stock_list: ItemList
var sell_list: ItemList
var _stock: Array = []
var _sellables: Array = []
var npc_name := ""

func _init():
	super._init("NPC", Color(0.4, 0.7, 0.5))
	custom_minimum_size = Vector2(420, 200)

	dialog_text = RichTextLabel.new()
	dialog_text.bbcode_enabled = false
	dialog_text.fit_content = false
	dialog_text.scroll_following = true
	dialog_text.custom_minimum_size = Vector2(400, 150)
	dialog_text.add_theme_font_size_override("normal_font_size", 13)
	content.add_child(dialog_text)

	choices_box = VBoxContainer.new()
	choices_box.add_theme_constant_override("separation", 3)
	content.add_child(choices_box)

	vendor_box = VBoxContainer.new()
	vendor_box.add_theme_constant_override("separation", 4)
	vendor_box.visible = false
	content.add_child(vendor_box)
	var shop_row := HBoxContainer.new()
	shop_row.add_theme_constant_override("separation", 10)
	vendor_box.add_child(shop_row)

	var buy_col := VBoxContainer.new()
	shop_row.add_child(buy_col)
	var wares_label := Label.new()
	wares_label.text = "Wares (click to buy)"
	wares_label.add_theme_font_size_override("font_size", 12)
	buy_col.add_child(wares_label)
	stock_list = ItemList.new()
	stock_list.custom_minimum_size = Vector2(230, 170)
	stock_list.add_theme_font_size_override("font_size", 11)
	buy_col.add_child(stock_list)
	var buy_btn := Button.new()
	buy_btn.text = "Buy selected"
	buy_btn.focus_mode = Control.FOCUS_NONE
	UIC.style_button(buy_btn)
	buy_btn.pressed.connect(_on_buy)
	buy_col.add_child(buy_btn)

	var sell_col := VBoxContainer.new()
	shop_row.add_child(sell_col)
	var sell_label := Label.new()
	sell_label.text = "Your items (click to sell)"
	sell_label.add_theme_font_size_override("font_size", 12)
	sell_col.add_child(sell_label)
	sell_list = ItemList.new()
	sell_list.custom_minimum_size = Vector2(230, 170)
	sell_list.add_theme_font_size_override("font_size", 11)
	sell_col.add_child(sell_list)
	var sell_btn := Button.new()
	sell_btn.text = "Sell selected"
	sell_btn.focus_mode = Control.FOCUS_NONE
	UIC.style_button(sell_btn)
	sell_btn.pressed.connect(_on_sell)
	sell_col.add_child(sell_btn)

	closed.connect(func(): interaction_ended.emit())

static func clean_text(raw: String) -> String:
	# Legacy dialog text carries Torque markup: literal \n escapes, \cN color
	# codes and <a:...>link</a> wiki anchors. Strip to plain text.
	var s := raw.replace("\\n", "\n").replace("\\t", "  ")
	var re := RegEx.new()
	re.compile("<a:[^>]*>")
	s = re.sub(s, "", true)
	s = s.replace("</a>", "")
	re.compile("\\\\c[0-9o]")
	s = re.sub(s, "", true)
	return s.strip_edges()

func begin(npc: String) -> void:
	npc_name = npc
	title_label.text = npc if not npc.is_empty() else "NPC"
	dialog_text.text = ""
	_set_choices([])
	vendor_box.visible = false
	stock_list.clear()
	open_window()

func add_line(text: String, choices: Array) -> void:
	var clean := clean_text(text)
	if not clean.is_empty():
		if not dialog_text.text.is_empty():
			dialog_text.text += "\n\n"
		dialog_text.text += clean
	_set_choices(choices)
	open_window()

func _set_choices(choices: Array) -> void:
	for c in choices_box.get_children():
		c.queue_free()
	for i in range(choices.size()):
		var b := Button.new()
		b.text = "%d. %s" % [i + 1, clean_text(str(choices[i]))]
		b.focus_mode = Control.FOCUS_NONE
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		UIC.style_button(b)
		b.pressed.connect(_on_choice.bind(i))
		choices_box.add_child(b)

func _on_choice(index: int) -> void:
	# Disable until the server answers with the next line (prevents double-fires).
	for c in choices_box.get_children():
		if c is Button:
			c.disabled = true
	choice_selected.emit(index)

func set_stock(items: Array, markup: float) -> void:
	_stock = items
	vendor_box.visible = not items.is_empty()
	stock_list.clear()
	for item in items:
		if not (item is Dictionary):
			continue
		var price := int(round(float(item.get("worth_tin", 0)) * markup))
		var idx := stock_list.add_item("%s  —  %s" % [str(item.get("name", "?")), UIC.money_text(price)],
			UIC.item_icon(str(item.get("bitmap", ""))))
		stock_list.set_item_tooltip(idx, UIC.item_tooltip(item))
	if visible:
		open_window()

func set_sellables(items: Array) -> void:
	# Carry-slot items with a sale value, from the latest inventory snapshot.
	_sellables = []
	sell_list.clear()
	for item in items:
		if not (item is Dictionary):
			continue
		var slot := int(item.get("slot", -1))
		if slot < UIC.CARRY_BEGIN or slot >= UIC.CARRY_BEGIN + UIC.CARRY_COUNT:
			continue
		if int(item.get("worth_tin", 0)) <= 0:
			continue
		_sellables.append(item)
		var idx := sell_list.add_item("%s  —  %s" % [str(item.get("name", "?")),
			UIC.money_text(int(item.get("worth_tin", 0)) / 2)],
			UIC.item_icon(str(item.get("bitmap", ""))))
		sell_list.set_item_tooltip(idx, UIC.item_tooltip(item))

func _on_buy() -> void:
	var sel := stock_list.get_selected_items()
	if sel.is_empty() or sel[0] >= _stock.size():
		return
	buy_requested.emit(int(_stock[sel[0]].get("vendor_index", sel[0])))

func _on_sell() -> void:
	var sel := sell_list.get_selected_items()
	if sel.is_empty() or sel[0] >= _sellables.size():
		return
	sell_requested.emit(int(_sellables[sel[0]].get("slot", -1)))
