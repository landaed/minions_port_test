class_name CharacterWindow
extends GameWindow
## In-game character sheet: name/class/level, resources, the nine core
## attributes, and combat-derived stats. When the character has unspent
## advancement points, a "+" button next to each attribute spends one to raise
## that attribute (sends the spend_stat_point gameplay command).

signal spend_stat(stat: String)

# (stat key on the wire, display name). MoM's nine core attributes.
const ATTRS := [
	["str", "Strength"], ["bdy", "Body"], ["agi", "Agility"],
	["dex", "Dexterity"], ["ref", "Reflexes"], ["mnd", "Mind"],
	["wis", "Wisdom"], ["mys", "Mysticism"], ["pre", "Presence"],
]

var _header: Label
var _resources: Label
var _points_label: Label
var _attr_rows: Dictionary = {}     # stat -> {value: Label, plus: Button}
var _derived: Label
var _last_info: Dictionary = {}

func _init():
	super._init("Character", Color(0.55, 0.8, 0.55))
	content.custom_minimum_size = Vector2(320, 0)

	_header = Label.new()
	_header.add_theme_font_size_override("font_size", 15)
	_header.add_theme_color_override("font_color", Color(0.95, 0.92, 0.75))
	content.add_child(_header)

	_resources = Label.new()
	_resources.add_theme_font_size_override("font_size", 12)
	_resources.add_theme_color_override("font_color", Color(0.8, 0.85, 0.95))
	content.add_child(_resources)

	var sep := HSeparator.new()
	content.add_child(sep)

	_points_label = Label.new()
	_points_label.add_theme_font_size_override("font_size", 13)
	_points_label.add_theme_color_override("font_color", Color(1.0, 0.85, 0.4))
	content.add_child(_points_label)

	# Attribute grid: name | value (base) | [+]
	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", 12)
	grid.add_theme_constant_override("v_separation", 7)
	content.add_child(grid)
	for entry in ATTRS:
		var key: String = entry[0]
		var name_label := Label.new()
		name_label.text = entry[1]
		name_label.add_theme_font_size_override("font_size", 14)
		name_label.custom_minimum_size = Vector2(110, 30)
		name_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		grid.add_child(name_label)
		var val_label := Label.new()
		val_label.add_theme_font_size_override("font_size", 14)
		val_label.add_theme_color_override("font_color", Color(0.92, 0.94, 0.98))
		val_label.custom_minimum_size = Vector2(96, 30)
		val_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		val_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		grid.add_child(val_label)
		var plus := Button.new()
		plus.text = "+"
		plus.focus_mode = Control.FOCUS_NONE
		plus.custom_minimum_size = Vector2(44, 30)
		plus.add_theme_font_size_override("font_size", 18)
		UIC.style_button(plus)
		plus.pressed.connect(func(): spend_stat.emit(key))
		grid.add_child(plus)
		_attr_rows[key] = {"value": val_label, "plus": plus}

	var sep2 := HSeparator.new()
	content.add_child(sep2)

	_derived = Label.new()
	_derived.add_theme_font_size_override("font_size", 12)
	_derived.add_theme_color_override("font_color", Color(0.8, 0.85, 0.95))
	content.add_child(_derived)

	var hint := Label.new()
	hint.text = "Gain advancement points by leveling up, then spend them here to raise your attributes."
	hint.add_theme_font_size_override("font_size", 10)
	hint.add_theme_color_override("font_color", Color(0.6, 0.64, 0.72))
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	content.add_child(hint)

func apply_info(info: Dictionary) -> void:
	if info.is_empty():
		return
	_last_info = info
	var name := str(info.get("name", "?"))
	var level := str(info.get("level", info.get("plevel", 1)))
	var klass := str(info.get("pclass", info.get("klass", "")))
	var race := str(info.get("race", ""))
	_header.text = "%s — Level %s %s %s" % [name, level, race, klass]

	var rapid: Dictionary = info.get("rapid_mob_info", {})
	if rapid is Dictionary and not rapid.is_empty():
		_resources.text = "HP %s/%s   MP %s/%s   SP %s/%s" % [
			str(int(rapid.get("health", 0))), str(int(rapid.get("maxhealth", 0))),
			str(int(rapid.get("mana", 0))), str(int(rapid.get("maxmana", 0))),
			str(int(rapid.get("stamina", 0))), str(int(rapid.get("maxstamina", 0)))]
	else:
		_resources.text = ""

	var points := int(info.get("advancement_points", 0))
	if points > 0:
		_points_label.text = "Advancement points to spend: %d" % points
	else:
		_points_label.text = "Advancement points: 0  (level up to earn more)"

	for entry in ATTRS:
		var key: String = entry[0]
		var row: Dictionary = _attr_rows[key]
		var cur := int(info.get(key, 0))
		var base := int(info.get(key + "_base", cur))
		# Show current; if buffs/items changed it from base, show base in parens.
		if cur != base and base > 0:
			row["value"].text = "%d  (%d)" % [cur, base]
		else:
			row["value"].text = str(cur)
		row["plus"].visible = points > 0
		row["plus"].disabled = points <= 0

	_derived.text = "Offense %d    Defense %d    Armor %d" % [
		int(info.get("offense", 0)), int(info.get("defense", 0)), int(info.get("armor", 0))]
