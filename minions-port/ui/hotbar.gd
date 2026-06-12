class_name Hotbar
extends HBoxContainer
## 10-slot action bar. Slots accept drag & drop from the spellbook/abilities
## window ("action" payloads: skill name or spellbook slot), trigger on click or
## the 1-0 keys, and persist per character. If the player never customized the
## bar, it auto-fills with the character's active skills (legacy default).

signal action_triggered(payload: Dictionary)

const SLOT_COUNT := 10

var _slots: Array[SlotButton] = []
var _assignments: Array = []   # of Dictionary or null
var _char_name := ""
var _user_modified := false

func _init():
	add_theme_constant_override("separation", 4)
	alignment = BoxContainer.ALIGNMENT_CENTER
	_assignments.resize(SLOT_COUNT)
	for i in range(SLOT_COUNT):
		var b := SlotButton.new(46)
		b.accept_kinds = ["action"]
		b.drop_handler = _make_drop_handler(i)
		b.drag_kind = "action"  # allow dragging between hotbar slots
		b.slot_clicked.connect(func(_alt, _ctrl): activate(i))
		b.slot_right_clicked.connect(func(): clear_assignment(i))
		b.clear_slot(_key_label(i))
		add_child(b)
		_slots.append(b)

func _key_label(i: int) -> String:
	return str((i + 1) % 10)

func _make_drop_handler(i: int) -> Callable:
	return func(data: Dictionary):
		assign(i, data, true)

func _save_path() -> String:
	return "user://hotbar_%s.json" % _char_name.to_lower()

func load_for(char_name: String) -> void:
	_char_name = char_name
	_user_modified = false
	_assignments = []
	_assignments.resize(SLOT_COUNT)
	if FileAccess.file_exists(_save_path()):
		var f := FileAccess.open(_save_path(), FileAccess.READ)
		if f:
			var data = JSON.parse_string(f.get_as_text())
			if data is Array:
				for i in range(mini(SLOT_COUNT, data.size())):
					if data[i] is Dictionary and not (data[i] as Dictionary).is_empty():
						_assignments[i] = data[i]
				_user_modified = true
	_refresh_all()

func _persist() -> void:
	if _char_name.is_empty():
		return
	var out: Array = []
	for a in _assignments:
		out.append(a if a is Dictionary else {})
	var f := FileAccess.open(_save_path(), FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(out))

func assign(i: int, payload: Dictionary, by_user: bool = false) -> void:
	if i < 0 or i >= SLOT_COUNT:
		return
	var clean := {
		"name": str(payload.get("name", "?")),
		"action": str(payload.get("action", "skill")),
		"book_slot": int(payload.get("book_slot", -1)),
		"icon": str(payload.get("icon", "")),
	}
	_assignments[i] = clean
	if by_user:
		_user_modified = true
		_persist()
	_refresh_slot(i)

func clear_assignment(i: int) -> void:
	if i < 0 or i >= SLOT_COUNT:
		return
	_assignments[i] = null
	_user_modified = true
	_persist()
	_refresh_slot(i)

func default_fill_from_skills(abilities: Array, spells: Array = []) -> void:
	# Only when the player hasn't customized: mirror active skills into slots,
	# then memorized spells (in spellbook order) into the remaining ones — so a
	# fresh caster spawns with its class spells ready on the bar.
	if _user_modified:
		return
	var fills: Array = []
	for ab in abilities:
		if ab is Dictionary:
			fills.append({
				"name": str(ab.get("name", "?")),
				"action": "skill",
				"book_slot": -1,
				"icon": str(ab.get("icon", "")),
			})
	for sp in spells:
		if sp is Dictionary:
			# Scribed-but-not-yet-castable spells (class level too low) stay in
			# the book until they qualify; don't put dead buttons on the bar.
			if not bool(sp.get("castable", true)):
				continue
			fills.append({
				"name": str(sp.get("name", "?")),
				"action": "spell",
				"book_slot": int(sp.get("slot", 0)),
				"icon": str(sp.get("icon", "")),
			})
	for i in range(SLOT_COUNT):
		_assignments[i] = fills[i] if i < fills.size() else null
	_refresh_all()

func prune_unknown(abilities: Array, spells_ready: bool, spells: Array) -> void:
	# Saved bars are keyed by character name only, so a same-named character
	# (e.g. recreated after a database reset) inherits the previous layout.
	# Drop any entry the server says this character doesn't actually have.
	# Skills are only validated once the (possibly empty-at-connect) ability
	# list has content; spells once a spellbook message has arrived.
	var known_skills := {}
	for ab in abilities:
		if ab is Dictionary:
			known_skills[str(ab.get("name", ""))] = true
	var known_spells := {}
	for sp in spells:
		if sp is Dictionary:
			known_spells[str(sp.get("name", ""))] = true
	var changed := false
	for i in range(SLOT_COUNT):
		var a = _assignments[i]
		if not (a is Dictionary) or a.is_empty():
			continue
		var nm := str(a.get("name", ""))
		var stale := false
		if str(a.get("action", "skill")) == "skill":
			stale = not abilities.is_empty() and not known_skills.has(nm)
		else:
			stale = spells_ready and not known_spells.has(nm)
		if stale:
			_assignments[i] = null
			_refresh_slot(i)
			changed = true
	if changed:
		var any_left := false
		for a in _assignments:
			if a is Dictionary and not a.is_empty():
				any_left = true
				break
		if not any_left:
			# Everything was stale (different character entirely): forget the
			# saved layout so the default fill can rebuild a sensible bar.
			_user_modified = false
		_persist()

func activate(i: int) -> void:
	if i < 0 or i >= SLOT_COUNT:
		return
	var a = _assignments[i]
	if a is Dictionary and not a.is_empty():
		action_triggered.emit(a)

func update_cooldowns(abilities: Array, spells: Array) -> void:
	var skill_cd: Dictionary = {}
	for ab in abilities:
		if ab is Dictionary and bool(ab.get("cooldown_active", false)):
			skill_cd[str(ab.get("name", ""))] = int(ab.get("cooldown_seconds", 0))
	var spell_cd: Dictionary = {}
	for sp in spells:
		if sp is Dictionary and int(sp.get("recast_left", 0)) > 0:
			spell_cd[int(sp.get("slot", -1))] = int(sp.get("recast_left", 0))
	for i in range(SLOT_COUNT):
		var a = _assignments[i]
		var b := _slots[i]
		if not (a is Dictionary) or a.is_empty():
			continue
		var cd := 0
		if str(a.get("action", "")) == "skill":
			cd = int(skill_cd.get(str(a.get("name", "")), 0))
		else:
			cd = int(spell_cd.get(int(a.get("book_slot", -1)), 0))
		b.disabled = cd > 0
		b.count_label.text = ("%ds" % cd) if cd > 0 else ""

func _refresh_all() -> void:
	for i in range(SLOT_COUNT):
		_refresh_slot(i)

func _refresh_slot(i: int) -> void:
	var b := _slots[i]
	var a = _assignments[i]
	if not (a is Dictionary) or a.is_empty():
		b.clear_slot(_key_label(i))
		b.payload = {}
		return
	var icon := UIC.spell_icon(str(a.get("icon", "")))
	b.set_slot(icon, str(a.get("name", "?")).left(8), 0, _key_label(i))
	b.payload = a.duplicate(true)
	b.payload["action"] = a.get("action", "skill")
	b.tooltip_text = "%s\nLeft-click or key %s to use • right-click to clear • drag to move" % [
		str(a.get("name", "?")), _key_label(i)]
