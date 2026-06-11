class_name CheatWindow
extends GameWindow
## Testing cheat panel (toggle with F8). Talks to the server's cheat API
## (mud/world/cheats.py via the proxy "cheat" message): grant XP, set level,
## give money, give any item, learn spells, raise skills, full heal.
## The world server only honors these when it runs with MOM_ENABLE_CHEATS=1.

signal cheat_requested(action: String, params: Dictionary)

var status_label: Label
var xp_amount: LineEdit
var level_spin: SpinBox
var money_amount: LineEdit
var skill_points: SpinBox
var item_search: LineEdit
var item_list: ItemList
var item_count: SpinBox
var spell_search: LineEdit
var spell_list: ItemList

func _init():
	super._init("Cheats (testing)", Color(0.9, 0.65, 0.25))
	content.custom_minimum_size = Vector2(440, 0)

	status_label = Label.new()
	status_label.text = "Server cheats: unknown (press ` to refresh)"
	status_label.add_theme_font_size_override("font_size", 11)
	status_label.add_theme_color_override("font_color", Color(0.95, 0.8, 0.45))
	status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	content.add_child(status_label)

	# --- Character: XP / level / heal / skills -------------------------
	content.add_child(_section_label("Character"))
	var xp_row := HBoxContainer.new()
	xp_row.add_theme_constant_override("separation", 6)
	content.add_child(xp_row)
	xp_amount = _line_edit("10000", 90)
	xp_row.add_child(_small_label("XP:"))
	xp_row.add_child(xp_amount)
	xp_row.add_child(_button("Give XP", func():
		cheat_requested.emit("give_xp", {"amount": int(xp_amount.text)})))
	xp_row.add_child(_small_label("  Level:"))
	level_spin = SpinBox.new()
	level_spin.min_value = 1
	level_spin.max_value = 100
	level_spin.value = 10
	level_spin.custom_minimum_size = Vector2(70, 0)
	xp_row.add_child(level_spin)
	xp_row.add_child(_button("Set Level", func():
		cheat_requested.emit("set_level", {"level": int(level_spin.value)})))

	var heal_row := HBoxContainer.new()
	heal_row.add_theme_constant_override("separation", 6)
	content.add_child(heal_row)
	heal_row.add_child(_button("Full Heal + Clear Cooldowns", func():
		cheat_requested.emit("full_heal", {})))
	heal_row.add_child(_small_label("  Skill points:"))
	skill_points = SpinBox.new()
	skill_points.min_value = 1
	skill_points.max_value = 100
	skill_points.value = 5
	skill_points.custom_minimum_size = Vector2(70, 0)
	heal_row.add_child(skill_points)
	heal_row.add_child(_button("Raise All Skills", func():
		cheat_requested.emit("raise_skills", {"points": int(skill_points.value)})))

	# --- Money ----------------------------------------------------------
	content.add_child(_section_label("Money"))
	var money_row := HBoxContainer.new()
	money_row.add_theme_constant_override("separation", 6)
	content.add_child(money_row)
	money_amount = _line_edit("1000", 90)
	money_row.add_child(_small_label("Platinum:"))
	money_row.add_child(money_amount)
	money_row.add_child(_button("Give Platinum", func():
		cheat_requested.emit("give_money", {"platinum": int(money_amount.text)})))

	# --- Items ------------------------------------------------------------
	content.add_child(_section_label("Give Item (search the whole item database)"))
	var item_row := HBoxContainer.new()
	item_row.add_theme_constant_override("separation", 6)
	content.add_child(item_row)
	item_search = _line_edit("", 200)
	item_search.placeholder_text = "e.g. longsword, plate, scroll of"
	item_search.text_submitted.connect(func(_t): _search_items())
	item_row.add_child(item_search)
	item_row.add_child(_button("Search", _search_items))
	item_row.add_child(_small_label(" x"))
	item_count = SpinBox.new()
	item_count.min_value = 1
	item_count.max_value = 20
	item_count.value = 1
	item_count.custom_minimum_size = Vector2(64, 0)
	item_row.add_child(item_count)
	item_row.add_child(_button("Give", _give_selected_item))
	item_list = ItemList.new()
	item_list.custom_minimum_size = Vector2(0, 110)
	item_list.add_theme_font_size_override("font_size", 11)
	item_list.item_activated.connect(func(_i): _give_selected_item())
	content.add_child(item_list)

	# --- Spells -----------------------------------------------------------
	content.add_child(_section_label("Learn Spell"))
	var spell_row := HBoxContainer.new()
	spell_row.add_theme_constant_override("separation", 6)
	content.add_child(spell_row)
	spell_search = _line_edit("", 200)
	spell_search.placeholder_text = "e.g. fireball, heal, gate"
	spell_search.text_submitted.connect(func(_t): _search_spells())
	spell_row.add_child(spell_search)
	spell_row.add_child(_button("Search", _search_spells))
	spell_row.add_child(_button("Learn", _learn_selected_spell))
	spell_row.add_child(_button("Learn All Class Spells", func():
		cheat_requested.emit("learn_class_spells", {})))
	spell_list = ItemList.new()
	spell_list.custom_minimum_size = Vector2(0, 110)
	spell_list.add_theme_font_size_override("font_size", 11)
	spell_list.item_activated.connect(func(_i): _learn_selected_spell())
	content.add_child(spell_list)

func _section_label(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", 12)
	l.add_theme_color_override("font_color", Color(0.75, 0.82, 0.95))
	return l

func _small_label(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", 11)
	return l

func _line_edit(text: String, width: int) -> LineEdit:
	var e := LineEdit.new()
	e.text = text
	e.custom_minimum_size = Vector2(width, 0)
	e.add_theme_font_size_override("font_size", 11)
	return e

func _button(text: String, on_press: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.focus_mode = Control.FOCUS_NONE
	UIC.style_button(b)
	b.pressed.connect(on_press)
	return b

func _search_items() -> void:
	cheat_requested.emit("list_items", {"filter": item_search.text.strip_edges(), "limit": 100})

func _search_spells() -> void:
	cheat_requested.emit("list_spells", {"filter": spell_search.text.strip_edges(), "limit": 100})

func _give_selected_item() -> void:
	var sel := item_list.get_selected_items()
	if sel.is_empty():
		status_label.text = "Select an item in the list first."
		return
	cheat_requested.emit("give_item", {
		"name": item_list.get_item_text(sel[0]),
		"count": int(item_count.value),
	})

func _learn_selected_spell() -> void:
	var sel := spell_list.get_selected_items()
	if sel.is_empty():
		status_label.text = "Select a spell in the list first."
		return
	cheat_requested.emit("learn_spell", {"name": spell_list.get_item_text(sel[0])})

func handle_result(data: Dictionary) -> void:
	var action := str(data.get("action", ""))
	status_label.text = str(data.get("message", ""))
	match action:
		"list_items":
			item_list.clear()
			for n in data.get("items", []):
				item_list.add_item(str(n))
		"list_spells":
			spell_list.clear()
			for n in data.get("spells", []):
				spell_list.add_item(str(n))
		"status":
			if bool(data.get("enabled", false)):
				status_label.text = "Server cheats are ENABLED."
