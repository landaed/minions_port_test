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
# The window is re-polled every couple of seconds while open (to refresh
# cooldowns). Rebuilding every row each poll destroyed whatever the mouse was
# hovering, so spell tooltips "disappeared really fast". We now only rebuild
# when the spell/ability *set* actually changes; an unchanged poll is a no-op,
# so the hovered row (and its tooltip) survives.
var _spells_signature := ""
var _skills_signature := ""

func _spells_sig(spells: Array) -> String:
	var parts: Array = []
	for s in spells:
		if s is Dictionary:
			parts.append("%s|%d|%d|%d" % [
				str(s.get("name", "")), int(s.get("slot", 0)),
				int(s.get("power_level", 1)), 1 if bool(s.get("castable", true)) else 0])
	return "\n".join(parts)

func _skills_sig(abilities: Array) -> String:
	var parts: Array = []
	for a in abilities:
		if a is Dictionary:
			parts.append("%s|%s" % [str(a.get("name", "")), str(a.get("rank", 1))])
	return "\n".join(parts)

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
	# Skip the destructive rebuild when the spell set is unchanged (keeps a
	# hovered tooltip alive across the periodic refresh).
	var sig := _spells_sig(_spells)
	if sig == _spells_signature and spells_box.get_child_count() > 0:
		return
	_spells_signature = sig
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
	var sig := _skills_sig(abilities)
	if sig == _skills_signature and skills_box.get_child_count() > 0:
		return
	_skills_signature = sig
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
	var tip := _spell_tooltip(spell)
	slot.set_rich_tip(tip)
	row.add_child(slot)
	var info := Label.new()
	info.text = "%s  (Lv %d)\nMana %d  •  Cast %.1fs  •  Recast %.1fs" % [
		str(spell.get("name", "?")), int(spell.get("power_level", 1)),
		int(spell.get("mana", 0)), float(spell.get("cast_time", 0)),
		float(spell.get("recast_time", 0))]
	info.add_theme_font_size_override("font_size", 11)
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_wire_tip(info, tip)
	row.add_child(info)
	var cast := Button.new()
	cast.text = "Cast"
	cast.focus_mode = Control.FOCUS_NONE
	UIC.style_button(cast)
	var recast_left := int(spell.get("recast_left", 0))
	if recast_left > 0:
		cast.disabled = true
		cast.text = "Cast (%ds)" % recast_left
	if not bool(spell.get("castable", true)):
		# Scribed ahead of its class-level requirement: visible in the book
		# but greyed until the character qualifies.
		cast.disabled = true
		cast.text = "Too low"
		row.modulate = Color(1, 1, 1, 0.45)
		var low_tip := tip + "\nYou cannot cast this yet (class level too low)."
		slot.set_rich_tip(low_tip)
		_wire_tip(info, low_tip)
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
	var atip := "%s\nRank %s" % [str(ability.get("name", "?")), str(ability.get("rank", 1))]
	slot.set_rich_tip(atip)
	row.add_child(slot)
	var info := Label.new()
	info.text = "%s   (Rank %s)" % [str(ability.get("name", "?")), str(ability.get("rank", 1))]
	info.add_theme_font_size_override("font_size", 11)
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_wire_tip(info, atip)
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

func _wire_tip(c: Control, text: String) -> void:
	# Make a non-SlotButton control (e.g. the info Label) drive the same custom
	# hover tooltip, so hovering anywhere on the row shows the details.
	c.mouse_filter = Control.MOUSE_FILTER_STOP
	c.mouse_entered.connect(func(): UIC.show_tip(c, text))
	c.mouse_exited.connect(UIC.hide_tip)
	c.tree_exiting.connect(func(): UIC.hide_tip_if_owner(c))

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
