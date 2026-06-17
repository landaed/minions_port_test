class_name Hotbar
extends VBoxContainer
## Two-page action bar (10 slots each, 20 abilities total). Slots accept drag &
## drop from the spellbook/abilities window ("action" payloads: skill name or
## spellbook slot), trigger on click or the 1-0 keys / controller buttons, and
## persist per character. If the player never customized a bar it auto-fills with
## the character's active skills + spells (legacy default).
##
## Paging:
##   - cycle_page() swaps which page is "active" (a button on keyboard/controller).
##   - set_secondary_peek(true) reveals the *other* page as a second row and
##     routes activations there while held (hold a controller bumper / Shift).
## Only two pages are ever shown, matching the request to "limit to 2 hotbars".

signal action_triggered(payload: Dictionary)

const SLOT_COUNT := 10
const PAGE_COUNT := 2

var _rows: Array = []                  # [Array[SlotButton], Array[SlotButton]]
var _assignments_pages: Array = []     # [Array(of Dictionary/null), ...] per page
var _row_boxes: Array = []             # HBoxContainer per page
var _page_labels: Array = []           # leading "Bar N" label per row
var _active_page := 0
var _peeking := false                  # secondary page temporarily revealed
var _char_name := ""
var _user_modified := false

# Kept for backward compat with callers/tests that read the active page directly
# (e.g. autotest_driver reads hotbar._assignments[i]).
var _assignments: Array:
	get:
		return _assignments_pages[_active_page]

func _init():
	add_theme_constant_override("separation", 3)
	alignment = BoxContainer.ALIGNMENT_CENTER
	_assignments_pages.resize(PAGE_COUNT)
	for page in range(PAGE_COUNT):
		_assignments_pages[page] = []
		_assignments_pages[page].resize(SLOT_COUNT)
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 4)
		row.alignment = BoxContainer.ALIGNMENT_CENTER
		add_child(row)
		_row_boxes.append(row)
		var tag := Label.new()
		tag.text = "Bar %d" % (page + 1)
		tag.custom_minimum_size = Vector2(42, 0)
		tag.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		tag.add_theme_font_size_override("font_size", 11)
		tag.add_theme_color_override("font_color", Color(0.7, 0.78, 0.9))
		row.add_child(tag)
		_page_labels.append(tag)
		var slots: Array = []
		for i in range(SLOT_COUNT):
			var b := SlotButton.new(46)
			b.accept_kinds = ["action"]
			b.drop_handler = _make_drop_handler(page, i)
			b.drag_kind = "action"
			b.slot_clicked.connect(func(_alt, _ctrl): _trigger(page, i))
			b.slot_right_clicked.connect(func(): clear_assignment(page, i))
			b.clear_slot(_key_label(i))
			row.add_child(b)
			slots.append(b)
		_rows.append(slots)
	# Page 2 hidden until the player cycles to it or peeks.
	_update_page_visibility()

func _key_label(i: int) -> String:
	return str((i + 1) % 10)

func _make_drop_handler(page: int, i: int) -> Callable:
	return func(data: Dictionary):
		_assign(page, i, data, true)

func _save_path() -> String:
	return "user://hotbar_%s.json" % _char_name.to_lower()

func load_for(char_name: String) -> void:
	_char_name = char_name
	_user_modified = false
	for page in range(PAGE_COUNT):
		_assignments_pages[page] = []
		_assignments_pages[page].resize(SLOT_COUNT)
	if FileAccess.file_exists(_save_path()):
		var f := FileAccess.open(_save_path(), FileAccess.READ)
		if f:
			var data = JSON.parse_string(f.get_as_text())
			# New format: {"pages": [[...],[...]]}. Old format: a bare [...] (page 0).
			var pages_data: Array = []
			if data is Dictionary and data.get("pages") is Array:
				pages_data = data["pages"]
			elif data is Array:
				pages_data = [data]
			for page in range(min(PAGE_COUNT, pages_data.size())):
				var arr = pages_data[page]
				if arr is Array:
					for i in range(min(SLOT_COUNT, arr.size())):
						if arr[i] is Dictionary and not (arr[i] as Dictionary).is_empty():
							_assignments_pages[page][i] = arr[i]
							_user_modified = true
	_refresh_all()

func _persist() -> void:
	if _char_name.is_empty():
		return
	var pages_out: Array = []
	for page in range(PAGE_COUNT):
		var out: Array = []
		for a in _assignments_pages[page]:
			out.append(a if a is Dictionary else {})
		pages_out.append(out)
	var f := FileAccess.open(_save_path(), FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify({"pages": pages_out}))

func _assign(page: int, i: int, payload: Dictionary, by_user: bool = false) -> void:
	if page < 0 or page >= PAGE_COUNT or i < 0 or i >= SLOT_COUNT:
		return
	var clean := {
		"name": str(payload.get("name", "?")),
		"action": str(payload.get("action", "skill")),
		"book_slot": int(payload.get("book_slot", -1)),
		"icon": str(payload.get("icon", "")),
	}
	_assignments_pages[page][i] = clean
	if by_user:
		_user_modified = true
		_persist()
	_refresh_slot(page, i)

# Backward-compatible: assign on the active page.
func assign(i: int, payload: Dictionary, by_user: bool = false) -> void:
	_assign(_active_page, i, payload, by_user)

func clear_assignment(page: int, i: int) -> void:
	if page < 0 or page >= PAGE_COUNT or i < 0 or i >= SLOT_COUNT:
		return
	_assignments_pages[page][i] = null
	_user_modified = true
	_persist()
	_refresh_slot(page, i)

func default_fill_from_skills(abilities: Array, spells: Array = []) -> void:
	# Only when the player hasn't customized: mirror active skills then memorized
	# spells across BOTH pages (slots 0-9 = page 1, 10-19 = page 2), so a caster
	# with many spells spills onto the second bar instead of being truncated.
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
			if not bool(sp.get("castable", true)):
				continue
			fills.append({
				"name": str(sp.get("name", "?")),
				"action": "spell",
				"book_slot": int(sp.get("slot", 0)),
				"icon": str(sp.get("icon", "")),
			})
	for page in range(PAGE_COUNT):
		for i in range(SLOT_COUNT):
			var idx := page * SLOT_COUNT + i
			_assignments_pages[page][i] = fills[idx] if idx < fills.size() else null
	_refresh_all()

func prune_unknown(abilities: Array, spells_ready: bool, spells: Array) -> void:
	# Drop entries the server says this character doesn't actually have (saved
	# bars are keyed by name only, so a recreated character inherits the layout).
	var known_skills := {}
	for ab in abilities:
		if ab is Dictionary:
			known_skills[str(ab.get("name", ""))] = true
	var known_spells := {}
	for sp in spells:
		if sp is Dictionary:
			known_spells[str(sp.get("name", ""))] = true
	var changed := false
	var any_left := false
	for page in range(PAGE_COUNT):
		for i in range(SLOT_COUNT):
			var a = _assignments_pages[page][i]
			if not (a is Dictionary) or a.is_empty():
				continue
			var nm := str(a.get("name", ""))
			var stale := false
			if str(a.get("action", "skill")) == "skill":
				stale = not abilities.is_empty() and not known_skills.has(nm)
			else:
				stale = spells_ready and not known_spells.has(nm)
			if stale:
				_assignments_pages[page][i] = null
				_refresh_slot(page, i)
				changed = true
			else:
				any_left = true
	if changed:
		if not any_left:
			_user_modified = false  # let the default fill rebuild a sensible bar
		_persist()

# --- activation ------------------------------------------------------------
func _trigger(page: int, i: int) -> void:
	if page < 0 or page >= PAGE_COUNT or i < 0 or i >= SLOT_COUNT:
		return
	var a = _assignments_pages[page][i]
	if a is Dictionary and not a.is_empty():
		action_triggered.emit(a)

# Activate slot i. While peeking the secondary bar, route to the other page;
# otherwise the active page. (Keeps the old single-arg API for keyboard 1-0.)
func activate(i: int) -> void:
	var page := _secondary_page() if _peeking else _active_page
	_trigger(page, i)

func _secondary_page() -> int:
	return (_active_page + 1) % PAGE_COUNT

# --- paging ----------------------------------------------------------------
func cycle_page() -> void:
	_active_page = (_active_page + 1) % PAGE_COUNT
	_update_page_visibility()

func set_active_page(page: int) -> void:
	_active_page = clampi(page, 0, PAGE_COUNT - 1)
	_update_page_visibility()

func current_page() -> int:
	return _active_page

func set_secondary_peek(on: bool) -> void:
	if _peeking == on:
		return
	_peeking = on
	_update_page_visibility()

func _update_page_visibility() -> void:
	# Show the active page always; reveal the other one only while peeking. The
	# active page sits on the bottom row (closest to the player's hands).
	for page in range(PAGE_COUNT):
		var is_active := page == _active_page
		var visible_row := is_active or _peeking
		_row_boxes[page].visible = visible_row
		# Active bar bright; peeked secondary dimmer so it reads as "held".
		var col := Color(0.85, 0.95, 0.7) if is_active else Color(0.95, 0.85, 0.55)
		_page_labels[page].add_theme_color_override("font_color", col)
		_page_labels[page].text = "Bar %d%s" % [page + 1, "  ◄" if is_active else ""]
	# Keep the active page as the last (bottom) child so it's nearest the edge.
	move_child(_row_boxes[_active_page], get_child_count() - 1)

func update_cooldowns(abilities: Array, spells: Array) -> void:
	var skill_cd: Dictionary = {}
	for ab in abilities:
		if ab is Dictionary and bool(ab.get("cooldown_active", false)):
			skill_cd[str(ab.get("name", ""))] = int(ab.get("cooldown_seconds", 0))
	var spell_cd: Dictionary = {}
	for sp in spells:
		if sp is Dictionary and int(sp.get("recast_left", 0)) > 0:
			spell_cd[int(sp.get("slot", -1))] = int(sp.get("recast_left", 0))
	for page in range(PAGE_COUNT):
		for i in range(SLOT_COUNT):
			var a = _assignments_pages[page][i]
			var b: SlotButton = _rows[page][i]
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
	for page in range(PAGE_COUNT):
		for i in range(SLOT_COUNT):
			_refresh_slot(page, i)

func _refresh_slot(page: int, i: int) -> void:
	var b: SlotButton = _rows[page][i]
	var a = _assignments_pages[page][i]
	if not (a is Dictionary) or a.is_empty():
		b.clear_slot(_key_label(i))
		b.payload = {}
		return
	var icon := UIC.spell_icon(str(a.get("icon", "")))
	b.set_slot(icon, str(a.get("name", "?")).left(8), 0, _key_label(i))
	b.payload = a.duplicate(true)
	b.payload["action"] = a.get("action", "skill")
	b.tooltip_text = "%s\nBar %d slot %s • left-click or key to use • right-click to clear • drag to move" % [
		str(a.get("name", "?")), page + 1, _key_label(i)]
