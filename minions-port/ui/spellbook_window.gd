class_name SpellbookWindow
extends GameWindow
## Known spells (the legacy spellbook slots) and active class skills, both
## draggable onto the hotbar. Casting a spell goes through the legacy
## onSpellSlot path; skills go through the SKILL command.

signal cast_spell(book_slot: int)
signal use_skill(skill_name: String)

var spells_box: VBoxContainer
var skills_box: VBoxContainer
var char_id := 0
var _spells: Array = []
var _skills: Array = []

func _init():
	super._init("Spellbook & Abilities", Color(0.35, 0.55, 0.9))
	var tabs := TabContainer.new()
	tabs.custom_minimum_size = Vector2(430, 300)
	tabs.add_theme_font_size_override("font_size", 12)
	content.add_child(tabs)

	var spells_scroll := ScrollContainer.new()
	spells_scroll.name = "Spells"
	tabs.add_child(spells_scroll)
	spells_box = VBoxContainer.new()
	spells_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	spells_box.add_theme_constant_override("separation", 3)
	spells_scroll.add_child(spells_box)

	var skills_scroll := ScrollContainer.new()
	skills_scroll.name = "Abilities"
	tabs.add_child(skills_scroll)
	skills_box = VBoxContainer.new()
	skills_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	skills_box.add_theme_constant_override("separation", 3)
	skills_scroll.add_child(skills_box)

	var hint := Label.new()
	hint.text = "Drag a spell or ability onto the hotbar to bind it.  Trainers in town teach new ones."
	hint.add_theme_font_size_override("font_size", 10)
	hint.add_theme_color_override("font_color", Color(0.65, 0.68, 0.75))
	content.add_child(hint)

func apply_spellbook(data: Dictionary) -> void:
	char_id = int(data.get("char_id", char_id))
	_spells = data.get("spells", [])
	for c in spells_box.get_children():
		c.queue_free()
	if _spells.is_empty():
		var empty := Label.new()
		empty.text = "No spells known yet.\nLearn spells from scrolls (right-click them in your bags)\nor train with your class trainer."
		empty.add_theme_font_size_override("font_size", 12)
		spells_box.add_child(empty)
		return
	for spell in _spells:
		if spell is Dictionary:
			spells_box.add_child(_spell_row(spell))

func apply_skills(abilities: Array) -> void:
	_skills = abilities
	for c in skills_box.get_children():
		c.queue_free()
	if _skills.is_empty():
		var empty := Label.new()
		empty.text = "No active abilities known yet."
		empty.add_theme_font_size_override("font_size", 12)
		skills_box.add_child(empty)
		return
	for ability in _skills:
		if ability is Dictionary:
			skills_box.add_child(_skill_row(ability))

func _spell_row(spell: Dictionary) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var slot := SlotButton.new(36)
	var icon := UIC.spell_icon(str(spell.get("icon", "")))
	slot.set_slot(icon, str(spell.get("name", "?")).left(8))
	slot.payload = {
		"name": str(spell.get("name", "?")),
		"action": "spell",
		"book_slot": int(spell.get("slot", 0)),
		"icon": str(spell.get("icon", "")),
	}
	slot.drag_kind = "action"
	slot.tooltip_text = _spell_tooltip(spell)
	row.add_child(slot)
	var info := Label.new()
	info.text = "%s  (Lv %d)\nMana %d  •  Cast %.1fs  •  Recast %.1fs" % [
		str(spell.get("name", "?")), int(spell.get("power_level", 1)),
		int(spell.get("mana", 0)), float(spell.get("cast_time", 0)),
		float(spell.get("recast_time", 0))]
	info.add_theme_font_size_override("font_size", 11)
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.tooltip_text = slot.tooltip_text
	row.add_child(info)
	var cast := Button.new()
	cast.text = "Cast"
	cast.focus_mode = Control.FOCUS_NONE
	UIC.style_button(cast)
	var recast_left := int(spell.get("recast_left", 0))
	if recast_left > 0:
		cast.disabled = true
		cast.text = "Cast (%ds)" % recast_left
	cast.pressed.connect(func(): cast_spell.emit(int(spell.get("slot", 0))))
	row.add_child(cast)
	return row

func _skill_row(ability: Dictionary) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var slot := SlotButton.new(36)
	var icon := UIC.spell_icon(str(ability.get("icon", "")))
	slot.set_slot(icon, str(ability.get("name", "?")).left(8))
	slot.payload = {
		"name": str(ability.get("name", "?")),
		"action": "skill",
		"icon": str(ability.get("icon", "")),
	}
	slot.drag_kind = "action"
	slot.tooltip_text = "%s\nRank %s" % [str(ability.get("name", "?")), str(ability.get("rank", 1))]
	row.add_child(slot)
	var info := Label.new()
	info.text = "%s   (Rank %s)" % [str(ability.get("name", "?")), str(ability.get("rank", 1))]
	info.add_theme_font_size_override("font_size", 11)
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(info)
	var use := Button.new()
	use.text = "Use"
	use.focus_mode = Control.FOCUS_NONE
	UIC.style_button(use)
	if bool(ability.get("cooldown_active", false)):
		use.disabled = true
		use.text = "Use (%ds)" % int(ability.get("cooldown_seconds", 0))
	use.pressed.connect(func(): use_skill.emit(str(ability.get("name", "?"))))
	row.add_child(use)
	return row

func _spell_tooltip(spell: Dictionary) -> String:
	var lines: Array = [
		"%s (Lv %d)" % [str(spell.get("name", "?")), int(spell.get("power_level", 1))],
		"Mana: %d" % int(spell.get("mana", 0)),
		"Cast: %.1fs   Recast: %.1fs" % [float(spell.get("cast_time", 0)), float(spell.get("recast_time", 0))],
		"Range: %.0f" % float(spell.get("cast_range", 0)),
	]
	var skill := str(spell.get("skill", ""))
	if not skill.is_empty():
		lines.append("Skill: %s" % skill)
	var desc := str(spell.get("desc", ""))
	if not desc.is_empty():
		lines.append(NpcWindow.clean_text(desc))
	return "\n".join(lines)
