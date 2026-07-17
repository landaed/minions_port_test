extends Control
## Auto-updating launcher for the Minions of Mirth Godot client.
##
## Flow (the standard launcher pattern):
##   1. GET a small JSON manifest from MANIFEST_URL:
##        {"version","url","sha256","exe","notes"}
##   2. Compare manifest.version to the locally installed version.
##   3. If different (or not installed): download manifest.url (a zip of the
##      build), verify its SHA-256, extract it into the install dir, and record
##      the new version.
##   4. Launch <install_dir>/<exe>.
##
## So players only ever run the launcher; they never hand-copy a new .exe.
## Point it at your host: edit user://launcher.cfg or the DEFAULT_* below (e.g.
## a raw GitHub URL to dist/version.json, or a GitHub Release asset / Google
## Drive direct-download link).

const DEFAULT_MANIFEST_URL := "https://raw.githubusercontent.com/landaed/minions_port_test/main/dist/version.json"
const CFG_PATH := "user://launcher.cfg"
const INSTALLED_PATH := "user://installed.json"

var _http: HTTPRequest
var _status: Label
var _notes: Label
var _bar: ProgressBar
var _button: Button
var _manifest: Dictionary = {}
var _manifest_url := ""
var _install_dir := ""
var _tmp_zip := ""
var _state := "init"          # init -> checking -> up_to_date | update | error | installing | ready
var _autotest := false

func _ready() -> void:
	_manifest_url = OS.get_environment("MOM_LAUNCHER_MANIFEST")
	if _manifest_url.is_empty():
		var cfg := ConfigFile.new()
		if cfg.load(CFG_PATH) == OK:
			_manifest_url = str(cfg.get_value("launcher", "manifest_url", DEFAULT_MANIFEST_URL))
		else:
			_manifest_url = DEFAULT_MANIFEST_URL
	if _manifest_url == DEFAULT_MANIFEST_URL:
		_manifest_url = _platform_manifest_url(_manifest_url)
	_install_dir = OS.get_environment("MOM_LAUNCHER_INSTALL")
	if _install_dir.is_empty():
		# Default: a "game" folder next to the launcher executable (a user-writable
		# install). In the editor/headless this falls back to user://game.
		_install_dir = ProjectSettings.globalize_path("user://game")
	_tmp_zip = ProjectSettings.globalize_path("user://_download.zip")
	_autotest = OS.get_environment("MOM_LAUNCHER_AUTOTEST") == "1"

	_build_ui()
	_http = HTTPRequest.new()
	_http.use_threads = true
	add_child(_http)
	_http.request_completed.connect(_on_manifest_received)
	_check_for_updates()

func _build_ui() -> void:
	var bg := ColorRect.new()
	bg.color = Color(0.08, 0.09, 0.12)
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(bg)
	var box := VBoxContainer.new()
	box.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	box.add_theme_constant_override("separation", 14)
	box.alignment = BoxContainer.ALIGNMENT_CENTER
	box.offset_left = 30; box.offset_right = -30
	add_child(box)
	var title := Label.new()
	title.text = "Minions of Mirth"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 30)
	box.add_child(title)
	_status = Label.new()
	_status.text = "Checking for updates..."
	_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(_status)
	_bar = ProgressBar.new()
	_bar.min_value = 0; _bar.max_value = 100; _bar.value = 0
	_bar.custom_minimum_size = Vector2(0, 18)
	box.add_child(_bar)
	_notes = Label.new()
	_notes.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_notes.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_notes.add_theme_color_override("font_color", Color(0.7, 0.75, 0.85))
	_notes.add_theme_font_size_override("font_size", 12)
	box.add_child(_notes)
	_button = Button.new()
	_button.text = "..."
	_button.custom_minimum_size = Vector2(0, 44)
	_button.disabled = true
	_button.pressed.connect(_on_button)
	box.add_child(_button)

func _platform_manifest_url(base_url: String) -> String:
	match OS.get_name():
		"Windows": return base_url.replace("version.json", "version-windows.json")
		"macOS": return base_url.replace("version.json", "version-macos.json")
		_: return base_url.replace("version.json", "version-linux.json")

func _installed_data() -> Dictionary:
	if not FileAccess.file_exists(INSTALLED_PATH): return {}
	var file := FileAccess.open(INSTALLED_PATH, FileAccess.READ)
	if file == null: return {}
	var data = JSON.parse_string(file.get_as_text())
	return data if data is Dictionary else {}

func _installed_version() -> String:
	if not FileAccess.file_exists(INSTALLED_PATH):
		return ""
	var f := FileAccess.open(INSTALLED_PATH, FileAccess.READ)
	if f == null:
		return ""
	var d = JSON.parse_string(f.get_as_text())
	return str(d.get("version", "")) if d is Dictionary else ""

func _set_state(s: String, msg: String) -> void:
	_state = s
	if _status:
		_status.text = msg
	print("[Launcher] %s: %s" % [s, msg])

func _check_for_updates() -> void:
	_set_state("checking", "Checking for updates...")
	_button.disabled = true
	_http.download_file = ""  # manifest comes back in-memory
	var err := _http.request(_manifest_url)
	if err != OK:
		if not _installed_version().is_empty():
			_manifest = _installed_data()
			_offer_play("Offline — could not check for updates. Playing the installed version.")
		else:
			_fail("Could not reach the update server (error %d). Check your connection." % err)

func _on_manifest_received(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	if result != HTTPRequest.RESULT_SUCCESS or code != 200:
		# Offline but already installed? Let the player play what they have.
		if not _installed_version().is_empty():
			_manifest = _installed_data()
			_offer_play("Offline — couldn't check for updates. You can still play the installed version.")
		else:
			_fail("Update check failed (HTTP %d). Game not installed yet." % code)
		return
	var data = JSON.parse_string(body.get_string_from_utf8())
	if not (data is Dictionary) or not data.has("version"):
		_fail("Update manifest was malformed.")
		return
	_manifest = data
	if str(_manifest.get("notes", "")) != "":
		_notes.text = str(_manifest.get("notes", ""))
	var installed := _installed_version()
	var latest := str(_manifest.get("version", ""))
	if installed == latest and _game_exe_exists():
		_offer_play("Up to date (version %s)." % latest)
	else:
		var label := "Update available: %s" % latest if not installed.is_empty() else "Install %s" % latest
		_set_state("update", label)
		_button.text = "Updating…"
		_button.disabled = true
		_begin_download()

func _game_exe_exists() -> bool:
	var exe := str(_manifest.get("exe", ""))
	if exe.is_empty():
		return false
	return FileAccess.file_exists(_install_dir.path_join(exe))

func _on_button() -> void:
	match _state:
		"update":
			_begin_download()
		"ready", "up_to_date":
			_launch_game()
		"error":
			_prepare_manifest_request()
			_check_for_updates()

func _prepare_manifest_request() -> void:
	if _http.request_completed.is_connected(_on_download_complete):
		_http.request_completed.disconnect(_on_download_complete)
	if not _http.request_completed.is_connected(_on_manifest_received):
		_http.request_completed.connect(_on_manifest_received)

# --- download + verify + extract ------------------------------------------
func _begin_download() -> void:
	var url := str(_manifest.get("url", ""))
	if url.is_empty():
		_fail("Manifest has no download URL.")
		return
	_set_state("installing", "Downloading %s..." % str(_manifest.get("version", "")))
	_button.disabled = true
	# Swap the manifest handler for the download handler.
	if _http.request_completed.is_connected(_on_manifest_received):
		_http.request_completed.disconnect(_on_manifest_received)
	if not _http.request_completed.is_connected(_on_download_complete):
		_http.request_completed.connect(_on_download_complete)
	_http.download_file = _tmp_zip
	var err := _http.request(url)
	if err != OK:
		_fail("Download could not start (error %d)." % err)

func _process(_dt: float) -> void:
	if _state == "installing" and _http != null:
		var total := _http.get_body_size()
		var got := _http.get_downloaded_bytes()
		if total > 0:
			_bar.value = clampf(float(got) / float(total) * 100.0, 0.0, 100.0)

func _on_download_complete(result: int, code: int, _headers: PackedStringArray, _body: PackedByteArray) -> void:
	if result != HTTPRequest.RESULT_SUCCESS or code != 200:
		_fail("Download failed (HTTP %d)." % code)
		return
	_bar.value = 100
	# Verify checksum (skip only if the manifest didn't publish one).
	var want := str(_manifest.get("sha256", "")).to_lower()
	if not want.is_empty():
		var got := _sha256_file(_tmp_zip)
		if got != want:
			_fail("Downloaded file failed its integrity check — not installing.")
			DirAccess.remove_absolute(_tmp_zip)
			return
	_set_state("installing", "Installing...")
	if not _extract_zip(_tmp_zip, _install_dir):
		_fail("Could not unpack the update.")
		return
	DirAccess.remove_absolute(_tmp_zip)
	if OS.get_name() != "Windows":
		FileAccess.set_unix_permissions(_install_dir.path_join(str(_manifest.get("exe", ""))), 493)
	_write_installed(str(_manifest.get("version", "")))
	_offer_play("Updated to %s." % str(_manifest.get("version", "")))
	if _autotest:
		print("[Launcher] AUTOTEST: installed version=%s exe_exists=%s" % [_installed_version(), _game_exe_exists()])
		get_tree().quit()

func _sha256_file(path: String) -> String:
	var ctx := HashingContext.new()
	ctx.start(HashingContext.HASH_SHA256)
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return ""
	while not f.eof_reached():
		ctx.update(f.get_buffer(1 << 20))
	return ctx.finish().hex_encode()

func _extract_zip(zip_path: String, dest_dir: String) -> bool:
	var reader := ZIPReader.new()
	if reader.open(zip_path) != OK:
		return false
	DirAccess.make_dir_recursive_absolute(dest_dir)
	for name in reader.get_files():
		var clean_name := name.replace("\\", "/").simplify_path()
		if clean_name.is_absolute_path() or clean_name == ".." or clean_name.begins_with("../"):
			reader.close()
			return false
		var out_path := dest_dir.path_join(clean_name)
		if name.ends_with("/"):
			DirAccess.make_dir_recursive_absolute(out_path)
			continue
		DirAccess.make_dir_recursive_absolute(out_path.get_base_dir())
		var data := reader.read_file(name)
		var f := FileAccess.open(out_path, FileAccess.WRITE)
		if f == null:
			reader.close()
			return false
		f.store_buffer(data)
		f.close()
	reader.close()
	return true

func _write_installed(version: String) -> void:
	var f := FileAccess.open(INSTALLED_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify({"version": version, "install_dir": _install_dir, "exe": str(_manifest.get("exe", ""))}))

func _offer_play(msg: String) -> void:
	_set_state("ready", msg)
	_button.text = "Play"
	_button.disabled = false

func _fail(msg: String) -> void:
	_set_state("error", msg)
	_button.text = "Retry"
	_button.disabled = false

func _launch_game() -> void:
	var exe := str(_manifest.get("exe", ""))
	var path := _install_dir.path_join(exe)
	if exe.is_empty() or not FileAccess.file_exists(path):
		_fail("Game executable not found — try Update again.")
		return
	var pid := OS.create_process(path, [])
	if pid <= 0:
		_fail("The game could not be started.")
		return
	get_tree().quit()
