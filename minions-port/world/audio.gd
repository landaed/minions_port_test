extends Node
## Game audio manager (autoloaded as GameAudio).
##
## Ports the original client's audio systems:
##  - Music jukebox (mud/client/jukebox.py): the title track on the login
##    screen, then a shuffled bag of the full soundtrack in-world with the
##    original 30-180 s of quiet between songs.
##  - Zone ambience: the mission file's AudioEmitter loops (fireplaces, wind,
##    forest beds...) extracted to assets/<zone>/audio.json and played as
##    looping AudioStreamPlayer3D nodes.
##  - UI feedback sounds (the original Menu_Accept / Menu_Cancel cues).
## Server-driven combat/spell/vocal sounds arrive separately as play_sound /
## sound3d events and are played by VFX onto the same SFX bus.

const SOUND_DIR := "res://assets/sound/"
const MUSIC_DIR := "res://assets/sound/music/"
const TITLE_TRACK := "38 - Minions_of_Mirth_Title_Track.ogg"
const MUSIC_GAP_MIN := 30.0
const MUSIC_GAP_MAX := 180.0
const MUSIC_DB := -10.0    # soundtrack sits under gameplay, like the original mix
const AMBIENCE_DB := 0.0
const UI_DB := -6.0

var _music_player: AudioStreamPlayer = null
var _music_bag: Array[String] = []     # shuffled queue of tracks not yet played
var _all_tracks: Array[String] = []
var _music_gap_timer: SceneTreeTimer = null
var _in_world := false
var _ambience_root: Node3D = null

func _ready() -> void:
	_ensure_buses()
	_music_player = AudioStreamPlayer.new()
	_music_player.bus = "Music"
	_music_player.volume_db = 0.0
	add_child(_music_player)
	_music_player.finished.connect(_on_song_finished)
	_scan_tracks()

func _ensure_buses() -> void:
	# Dedicated buses so music/ambience/sfx can be balanced (and later exposed
	# as user settings) without touching each player.
	for bus_name in ["Music", "Ambience", "SFX"]:
		if AudioServer.get_bus_index(bus_name) == -1:
			var idx := AudioServer.bus_count
			AudioServer.add_bus(idx)
			AudioServer.set_bus_name(idx, bus_name)
			AudioServer.set_bus_send(idx, "Master")
	AudioServer.set_bus_volume_db(AudioServer.get_bus_index("Music"), MUSIC_DB)
	AudioServer.set_bus_volume_db(AudioServer.get_bus_index("Ambience"), AMBIENCE_DB)

func _scan_tracks() -> void:
	_all_tracks.clear()
	var dir := DirAccess.open(MUSIC_DIR)
	if dir == null:
		push_warning("GameAudio: no music directory at " + MUSIC_DIR)
		return
	dir.list_dir_begin()
	var f := dir.get_next()
	while f != "":
		if not dir.current_is_dir() and f.to_lower().ends_with(".ogg"):
			_all_tracks.append(f)
		f = dir.get_next()
	dir.list_dir_end()
	_all_tracks.sort()
	print("[GameAudio] %d music tracks available" % _all_tracks.size())

func _load_stream(path: String, loop: bool = false) -> AudioStream:
	var global := ProjectSettings.globalize_path(path)
	if not FileAccess.file_exists(path) and not FileAccess.file_exists(global):
		return null
	var stream := AudioStreamOggVorbis.load_from_file(path)
	if stream != null:
		stream.loop = loop
	return stream

# ------------------------------------------------------------------ music --
func start_menu_music() -> void:
	# Title theme on the login/character screens.
	_in_world = false
	_cancel_music_gap()
	var stream := _load_stream(MUSIC_DIR + TITLE_TRACK, true)
	if stream == null and not _all_tracks.is_empty():
		stream = _load_stream(MUSIC_DIR + _all_tracks[0], true)
	if stream == null:
		return
	_music_player.stream = stream
	_music_player.play()
	print("[GameAudio] menu music: " + TITLE_TRACK)

func start_world_music() -> void:
	# In-game jukebox: shuffled full soundtrack with long quiet gaps between
	# songs (the original waited 30-180 s after each track ended).
	if _in_world:
		return
	_in_world = true
	_cancel_music_gap()
	_play_next_song()

func stop_music() -> void:
	_in_world = false
	_cancel_music_gap()
	_music_player.stop()

func _play_next_song() -> void:
	if not _in_world:
		return
	if _all_tracks.is_empty():
		return
	if _music_bag.is_empty():
		_music_bag = _all_tracks.duplicate()
		_music_bag.shuffle()
	var song: String = _music_bag.pop_back()
	var stream := _load_stream(MUSIC_DIR + song, false)
	if stream == null:
		_play_next_song()
		return
	_music_player.stream = stream
	_music_player.play()
	print("[GameAudio] now playing: " + song)

func _on_song_finished() -> void:
	if not _in_world:
		return
	var gap := randf_range(MUSIC_GAP_MIN, MUSIC_GAP_MAX)
	print("[GameAudio] song finished; next in %.0f s" % gap)
	_music_gap_timer = get_tree().create_timer(gap)
	_music_gap_timer.timeout.connect(_play_next_song)

func _cancel_music_gap() -> void:
	if _music_gap_timer != null and _music_gap_timer.timeout.is_connected(_play_next_song):
		_music_gap_timer.timeout.disconnect(_play_next_song)
	_music_gap_timer = null

# --------------------------------------------------------------- ambience --
func attach_zone_ambience(zone_node: Node3D, zone: String) -> void:
	# Recreate the mission file's looping AudioEmitters as positional loops
	# parented to the zone art (so they inherit the server-origin offset).
	clear_zone_ambience()
	var path := "res://assets/" + zone + "/audio.json"
	var emitters: Array = []
	var f := FileAccess.open(path, FileAccess.READ)
	if f != null:
		var data = JSON.parse_string(f.get_as_text())
		if data is Dictionary:
			emitters = data.get("emitters", [])
	if emitters.is_empty():
		# Fall back to the basic entries inside scene.json (no distances).
		var sf := FileAccess.open("res://assets/" + zone + "/scene.json", FileAccess.READ)
		if sf != null:
			var sdata = JSON.parse_string(sf.get_as_text())
			if sdata is Dictionary:
				for a in sdata.get("audio", []):
					emitters.append({"pos": a.get("pos", [0, 0, 0]),
						"file": str(a.get("file", "")).split("data/sound/")[-1],
						"volume": 1.0, "reference_distance": 5.0, "max_distance": 30.0})
	if emitters.is_empty():
		print("[GameAudio] no ambience emitters for zone " + zone)
		return

	_ambience_root = Node3D.new()
	_ambience_root.name = "ZoneAmbience"
	zone_node.add_child(_ambience_root)
	var placed := 0
	for e in emitters:
		if not (e is Dictionary):
			continue
		var rel := str(e.get("file", ""))
		# Mission files keep the artists' original casing; the files on disk
		# are mostly lowercase — resolve case-insensitively like VFX sounds.
		var resolved := VFX.resolve_sound(rel)
		var stream := _load_stream(resolved if not resolved.is_empty() else SOUND_DIR + rel, true)
		if stream == null:
			push_warning("GameAudio: missing ambience file " + rel)
			continue
		var p := AudioStreamPlayer3D.new()
		p.stream = stream
		p.bus = "Ambience"
		var pos = e.get("pos", [0, 0, 0])
		p.position = Vector3(pos[0], pos[1], pos[2])
		p.unit_size = maxf(float(e.get("reference_distance", 5.0)), 1.0)
		p.max_distance = maxf(float(e.get("max_distance", 30.0)), 8.0)
		p.volume_db = linear_to_db(clampf(float(e.get("volume", 1.0)), 0.05, 1.0))
		p.attenuation_model = AudioStreamPlayer3D.ATTENUATION_INVERSE_DISTANCE
		p.autoplay = true
		_ambience_root.add_child(p)
		p.play()
		placed += 1
	print("[GameAudio] placed %d ambience emitters for zone %s" % [placed, zone])

func clear_zone_ambience() -> void:
	if _ambience_root != null and is_instance_valid(_ambience_root):
		_ambience_root.queue_free()
	_ambience_root = null

# --------------------------------------------------------------------- ui --
func ui_accept() -> void:
	_play_ui("sfx/Menu_Accept.ogg")

func ui_cancel() -> void:
	_play_ui("sfx/Menu_Cancel01.ogg")

func _play_ui(rel: String) -> void:
	var stream := _load_stream(SOUND_DIR + rel, false)
	if stream == null:
		return
	var p := AudioStreamPlayer.new()
	p.stream = stream
	p.bus = "SFX"
	p.volume_db = UI_DB
	add_child(p)
	p.play()
	p.finished.connect(p.queue_free)
