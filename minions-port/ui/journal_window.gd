class_name JournalWindow
extends GameWindow
## Quest journal. The legacy design keeps the journal client-side: the server
## pushes journal_entry events (topic/entry/text) as dialog actions fire, and
## the client accumulates them per character. Persisted to user:// so quests
## survive relogs, matching the original PLAYERSETTINGS behaviour.

var topics_list: ItemList
var entries_list: ItemList
var entry_text: RichTextLabel
var _journal: Dictionary = {}   # topic -> { entry_name: text } (insertion ordered)
var _char_name := ""

func _init():
	super._init("Quest Journal", Color(0.55, 0.45, 0.8))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	content.add_child(row)

	var topics_col := VBoxContainer.new()
	row.add_child(topics_col)
	var tl := Label.new()
	tl.text = "Topics"
	tl.add_theme_font_size_override("font_size", 12)
	topics_col.add_child(tl)
	topics_list = ItemList.new()
	topics_list.custom_minimum_size = Vector2(170, 240)
	topics_list.add_theme_font_size_override("font_size", 11)
	topics_list.item_selected.connect(_on_topic_selected)
	topics_col.add_child(topics_list)

	var entries_col := VBoxContainer.new()
	row.add_child(entries_col)
	var el := Label.new()
	el.text = "Entries"
	el.add_theme_font_size_override("font_size", 12)
	entries_col.add_child(el)
	entries_list = ItemList.new()
	entries_list.custom_minimum_size = Vector2(190, 240)
	entries_list.add_theme_font_size_override("font_size", 11)
	entries_list.item_selected.connect(_on_entry_selected)
	entries_col.add_child(entries_list)

	entry_text = RichTextLabel.new()
	entry_text.custom_minimum_size = Vector2(280, 240)
	entry_text.add_theme_font_size_override("normal_font_size", 13)
	entry_text.fit_content = false
	row.add_child(entry_text)

func _save_path() -> String:
	return "user://journal_%s.json" % _char_name.to_lower()

func load_for(char_name: String) -> void:
	_char_name = char_name
	_journal = {}
	if FileAccess.file_exists(_save_path()):
		var f := FileAccess.open(_save_path(), FileAccess.READ)
		if f:
			var data = JSON.parse_string(f.get_as_text())
			if data is Dictionary:
				_journal = data
	_refresh_topics()

func _persist() -> void:
	if _char_name.is_empty():
		return
	var f := FileAccess.open(_save_path(), FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(_journal))

func add_entry(topic: String, entry: String, text: String) -> bool:
	# Returns true when this is a new entry (caller may toast/log it).
	var t: Dictionary = _journal.get(topic, {})
	var is_new: bool = not t.has(entry)
	t[entry] = NpcWindow.clean_text(text)
	_journal[topic] = t
	_persist()
	_refresh_topics()
	return is_new

func _refresh_topics() -> void:
	var prev := topics_list.get_selected_items()
	var prev_topic := topics_list.get_item_text(prev[0]) if not prev.is_empty() else ""
	topics_list.clear()
	var idx := 0
	var reselect := -1
	for topic in _journal.keys():
		topics_list.add_item(str(topic))
		if str(topic) == prev_topic:
			reselect = idx
		idx += 1
	if topics_list.item_count > 0:
		topics_list.select(maxi(reselect, 0))
		_on_topic_selected(maxi(reselect, 0))
	else:
		entries_list.clear()
		entry_text.text = "No quest entries yet.\n\nTalk to NPCs around town — quests they give will be recorded here."

func _on_topic_selected(index: int) -> void:
	entries_list.clear()
	var topic := topics_list.get_item_text(index)
	for entry in _journal.get(topic, {}).keys():
		entries_list.add_item(str(entry))
	if entries_list.item_count > 0:
		entries_list.select(0)
		_on_entry_selected(0)

func _on_entry_selected(index: int) -> void:
	var tsel := topics_list.get_selected_items()
	if tsel.is_empty():
		return
	var topic := topics_list.get_item_text(tsel[0])
	var entry := entries_list.get_item_text(index)
	entry_text.text = str(_journal.get(topic, {}).get(entry, ""))
