class_name UIC
extends RefCounted
## Shared helpers for the in-game windows (inventory, loot, NPC dialog, journal,
## spellbook, hotbar): panel styles, MoM money formatting, item tooltips and the
## original game's icon art (base .jpg + sibling .alpha.jpg mask composited).

const ITEM_ICON_ROOT := "res://assets/ui/items/"
const SPELL_ICON_ROOT := "res://assets/ui/spellicons/"

const SLOT_NAMES := {
	0: "Head", 1: "L.Ear", 2: "R.Ear", 3: "Neck", 4: "Shoulders", 5: "Back",
	6: "Chest", 7: "Arms", 8: "Hands", 9: "L.Finger", 10: "R.Finger",
	11: "Primary", 12: "Secondary", 13: "Ranged", 14: "Ammo", 15: "Waist",
	16: "Legs", 17: "Feet", 18: "L.Wrist", 19: "R.Wrist", 20: "Shield", 21: "Light",
}
const WORN_BEGIN := 0
const WORN_END := 22
const CARRY_BEGIN := 22
const CARRY_COUNT := 60
const SLOT_CURSOR := 138

static var _icon_cache: Dictionary = {}

static func panel_style(accent: Color = Color(0.45, 0.5, 0.6)) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.08, 0.10, 0.93)
	sb.border_color = accent
	sb.set_border_width_all(1)
	sb.set_corner_radius_all(5)
	sb.content_margin_left = 8
	sb.content_margin_right = 8
	sb.content_margin_top = 6
	sb.content_margin_bottom = 8
	return sb

static func quality_color(quality: int) -> Color:
	match quality:
		0: return Color(0.65, 0.6, 0.55)   # cruddy
		2: return Color(0.55, 0.85, 0.55)  # good
		3: return Color(0.45, 0.65, 1.0)   # excellent
		4: return Color(0.85, 0.55, 1.0)   # exceptional
		_: return Color(0.92, 0.92, 0.92)  # normal

static func money_text(tin: int) -> String:
	var plat := tin / 100000000
	var gold := (tin / 1000000) % 100
	var silver := (tin / 10000) % 100
	var copper := (tin / 100) % 100
	var t := tin % 100
	var bits: Array = []
	if plat > 0: bits.append("%dp" % plat)
	if gold > 0: bits.append("%dg" % gold)
	if silver > 0: bits.append("%ds" % silver)
	if copper > 0: bits.append("%dc" % copper)
	bits.append("%dt" % t)
	return " ".join(bits)

static func _composite(base_path: String, alpha_path: String) -> Texture2D:
	var base_img := Image.load_from_file(ProjectSettings.globalize_path(base_path))
	if base_img == null:
		return null
	if FileAccess.file_exists(alpha_path):
		var alpha_img := Image.load_from_file(ProjectSettings.globalize_path(alpha_path))
		if alpha_img != null:
			base_img.convert(Image.FORMAT_RGBA8)
			alpha_img.convert(Image.FORMAT_RGBA8)
			if alpha_img.get_size() != base_img.get_size():
				alpha_img.resize(base_img.get_width(), base_img.get_height())
			for y in range(base_img.get_height()):
				for x in range(base_img.get_width()):
					var px := base_img.get_pixel(x, y)
					px.a = alpha_img.get_pixel(x, y).r
					base_img.set_pixel(x, y, px)
	return ImageTexture.create_from_image(base_img)

static func item_icon(bitmap: String) -> Texture2D:
	# bitmap is the DB path like "EQUIPMENT/CHEST/28" or "STUFF/1"; the art lives
	# in a per-icon folder as 0_0_0.jpg (+ 0_0_0.alpha.jpg cutout mask).
	if bitmap.is_empty():
		return null
	var key := "item:" + bitmap
	if _icon_cache.has(key):
		return _icon_cache[key]
	var dir := ITEM_ICON_ROOT + bitmap.to_lower() + "/"
	var tex := _composite(dir + "0_0_0.jpg", dir + "0_0_0.alpha.jpg")
	_icon_cache[key] = tex
	return tex

static func spell_icon(pic: String) -> Texture2D:
	if pic.is_empty():
		return null
	var key := "spell:" + pic
	if _icon_cache.has(key):
		return _icon_cache[key]
	var base := SPELL_ICON_ROOT + pic.to_lower()
	var tex := _composite(base + ".jpg", base + ".alpha.jpg")
	_icon_cache[key] = tex
	return tex

static func slots_text(equip_slots: Array) -> String:
	var names: Array = []
	for s in equip_slots:
		if SLOT_NAMES.has(int(s)):
			var n: String = SLOT_NAMES[int(s)]
			if not names.has(n):
				names.append(n)
	return ", ".join(names)

static func item_tooltip(item: Dictionary) -> String:
	if item.is_empty():
		return ""
	var lines: Array = [str(item.get("name", "Item"))]
	var lvl := int(item.get("level", 0))
	if lvl > 1:
		lines.append("Level %d" % lvl)
	var slots := slots_text(item.get("equip_slots", []))
	if not slots.is_empty():
		lines.append("Worn: %s" % slots)
	var armor := int(item.get("armor", 0))
	if armor != 0:
		lines.append("Armor: %d" % armor)
	var dmg := float(item.get("damage", 0))
	if dmg > 0:
		lines.append("Damage: %.0f   Delay: %.1f" % [dmg, float(item.get("delay", 0))])
	for st in item.get("stats", []):
		if st is Array and st.size() >= 2:
			lines.append("%s %+d" % [str(st[0]).capitalize(), int(st[1])])
	var skill := str(item.get("skill", ""))
	if not skill.is_empty():
		lines.append("Skill: %s" % skill)
	var spell := str(item.get("spell", ""))
	if not spell.is_empty():
		lines.append("Effect: %s" % spell)
	var classes: Array = item.get("classes", [])
	if not classes.is_empty():
		lines.append("Classes: %s" % ", ".join(classes))
	var charges := int(item.get("use_charges", 0))
	if int(item.get("use_max", 0)) > 1:
		lines.append("Charges: %d" % charges)
	var worth := int(item.get("worth_tin", 0))
	if worth > 0:
		lines.append("Value: %s" % money_text(worth))
	var desc := str(item.get("desc", ""))
	if not desc.is_empty():
		lines.append(desc)
	return "\n".join(lines)

static func style_button(button: Button, filled: bool = true) -> void:
	var normal := StyleBoxFlat.new()
	normal.bg_color = Color(0.13, 0.15, 0.19, 0.92) if filled else Color(0.08, 0.09, 0.11, 0.8)
	normal.border_color = Color(0.45, 0.62, 0.85) if filled else Color(0.22, 0.24, 0.28)
	normal.set_border_width_all(1)
	normal.set_corner_radius_all(4)
	var hover: StyleBoxFlat = normal.duplicate()
	hover.bg_color = Color(0.20, 0.24, 0.30, 0.95)
	button.add_theme_stylebox_override("normal", normal)
	button.add_theme_stylebox_override("hover", hover)
	button.add_theme_stylebox_override("pressed", hover)
	button.add_theme_stylebox_override("disabled", normal)
	button.add_theme_font_size_override("font_size", 12)
	button.add_theme_color_override("font_color", Color(0.92, 0.94, 0.98) if filled else Color(0.45, 0.48, 0.54))
