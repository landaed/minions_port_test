extends SceneTree
## Focused movement-sync probe. Boots the real client, registers a fresh
## account, enters the world, then runs a scripted movement pattern (run /
## strafe / stop) while sampling, every physics tick:
##   raw_d   - raw XZ distance between predicted player and server snapshot pos
##   drift   - latency-compensated reconcile error (what the client corrects)
##   step    - frame-to-frame XZ displacement (jitter shows up as variance)
## Prints aggregate stats at the end so reconcile tuning is comparable.
##
## Run (servers must be up):
##   xvfb-run godot --path minions-port --script res://tools/drift_test_driver.gd
## Optional: MOM_SHOT_DIR for screenshots (default /tmp/drift_shots).

var control: Control = null
var driver: Node = null

func _initialize() -> void:
	var dir := OS.get_environment("MOM_SHOT_DIR")
	if dir.is_empty():
		dir = "/tmp/drift_shots"
	DirAccess.make_dir_recursive_absolute(dir)
	var scene: PackedScene = load("res://control.tscn")
	control = scene.instantiate()
	root.add_child(control)
	driver = DriftProbe.new(control, dir)
	root.add_child(driver)


class DriftProbe:
	extends Node

	var control: Control
	var shot_dir: String
	var view: Control = null
	var state := "connect"
	var state_t := 0.0
	var total_t := 0.0
	var username := ""
	var _did := {}
	var _busy := false

	# measurement
	var phase := ""              # run / stop / strafe / settle
	var samples: Dictionary = {} # phase -> {raw: [], drift: [], step: []}
	var _last_pos := Vector3.ZERO
	var _have_last := false

	func _init(c: Control, dir: String):
		control = c
		shot_dir = dir
		username = "drift%d" % (Time.get_unix_time_from_system() as int % 1000000)

	func _shot(name_tag: String) -> void:
		var path := "%s/%s.png" % [shot_dir, name_tag]
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png(path)
		print("[DRIFT] shot -> ", path)

	func _key(code: Key, pressed: bool) -> void:
		var ev := InputEventKey.new()
		ev.keycode = code
		ev.physical_keycode = code
		ev.pressed = pressed
		Input.parse_input_event(ev)

	func _goto(s: String) -> void:
		print("[DRIFT] state: %s -> %s (t=%.1f)" % [state, s, total_t])
		state = s
		state_t = 0.0

	func _once(tag: String) -> bool:
		if _did.has(tag):
			return false
		_did[tag] = true
		return true

	func _status() -> String:
		var lbl: Label = control.get_node_or_null("VBoxContainer/StatusLabel")
		return lbl.text if lbl else ""

	func _speed_tweaks() -> void:
		if view and view.camera:
			view.camera.attributes = null
		Engine.max_physics_steps_per_frame = 240

	func _self_server_godot_pos() -> Vector3:
		var se: Dictionary = view._self_entity() if view else {}
		var p = se.get("position", [])
		if p is Array and p.size() >= 3:
			return view._server_to_godot(p)
		return Vector3.INF

	func _begin_phase(p: String) -> void:
		phase = p
		samples[p] = {"raw": [], "drift": [], "step": []}
		_have_last = false

	func _physics_process(delta: float) -> void:
		if phase == "" or view == null or not view._has_spawned:
			return
		var pos: Vector3 = view.player_body.global_position
		var sp := _self_server_godot_pos()
		if sp != Vector3.INF:
			samples[phase]["raw"].append(Vector2(sp.x - pos.x, sp.z - pos.z).length())
		var drift_v = view.get("_reconcile_error")
		if drift_v != null:
			samples[phase]["drift"].append(Vector3(drift_v).length())
		if _have_last:
			samples[phase]["step"].append(Vector2(pos.x - _last_pos.x, pos.z - _last_pos.z).length() / maxf(delta, 0.0001))
		_last_pos = pos
		_have_last = true

	func _stats(arr: Array) -> Dictionary:
		if arr.is_empty():
			return {"n": 0, "mean": 0.0, "max": 0.0, "stddev": 0.0}
		var s := 0.0
		var mx := 0.0
		for v in arr:
			s += v
			mx = maxf(mx, v)
		var mean := s / arr.size()
		var var_s := 0.0
		for v in arr:
			var_s += (v - mean) * (v - mean)
		return {"n": arr.size(), "mean": mean, "max": mx, "stddev": sqrt(var_s / arr.size())}

	func _report() -> void:
		print("[DRIFT] ====== RESULTS ======")
		for p in samples.keys():
			var raw: Dictionary = _stats(samples[p]["raw"])
			var dr: Dictionary = _stats(samples[p]["drift"])
			var st: Dictionary = _stats(samples[p]["step"])
			print("[DRIFT] phase=%-8s raw_desync mean=%.2f max=%.2f | drift mean=%.2f max=%.2f | speed mean=%.2f stddev=%.2f (n=%d)" % [
				p, raw["mean"], raw["max"], dr["mean"], dr["max"], st["mean"], st["stddev"], raw["n"]])
		print("[DRIFT] ======================")

	func _process(delta: float) -> void:
		if _busy:
			return
		state_t += delta
		total_t += delta
		if total_t > 420.0 and state != "done":
			print("[DRIFT] global timeout")
			_report()
			get_tree().quit()
			return
		match state:
			"connect":
				if state_t > 2.0 and _once("register"):
					control.get_node("VBoxContainer/UsernameField").text = username
					control.get_node("VBoxContainer/EmailField").text = username + "@example.com"
					control.get_node("VBoxContainer/PasswordField").text = "testpass1"
					control._on_register_button_pressed()
					_goto("registering")
			"registering":
				if _status().begins_with("Registered!") and _once("login"):
					control._on_login_button_pressed()
					_goto("logging_in")
			"logging_in":
				if control._current_phase == "world" and not control.worlds.is_empty() and _once("join"):
					control.world_list.select(0)
					control._on_join_world_button_pressed()
					_goto("joining_world")
			"joining_world":
				if control._current_phase == "character":
					_goto("character_phase")
			"character_phase":
				if state_t < 1.5:
					return
				if control.characters.is_empty():
					if _once("create_char"):
						var letters := "abcdefghijklmnopqrstuvwxyz"
						var cname := ""
						for i in range(8):
							cname += letters[randi() % letters.length()]
						control.get_node("VBoxContainer/CharacterNameField").text = cname.capitalize()
						control._on_create_character_button_pressed()
						state_t = 0.0
				elif _once("enter_world"):
					control.character_list.select(0)
					control._on_enter_world_button_pressed()
					_goto("entering_world")
			"entering_world":
				view = control.gameplay_view
				if view != null and view.visible and view._has_spawned:
					_speed_tweaks()
					_goto("warmup")
			"warmup":
				# Let spawn reconcile settle before measuring.
				if state_t > 4.0:
					_begin_phase("run")
					_key(KEY_W, true)
					_goto("run")
			"run":
				if state_t > 6.0:
					_key(KEY_W, false)
					_begin_phase("stop")
					_goto("stop")
			"stop":
				if state_t > 3.0:
					_begin_phase("strafe")
					_key(KEY_A, true)
					_goto("strafe")
			"strafe":
				# Strafe + turn: a curved path, the worst case for latency error.
				if view:
					view.player_body.rotate_y(delta * 0.9)
				if state_t > 6.0:
					_key(KEY_A, false)
					_begin_phase("settle")
					_goto("settle")
			"settle":
				if state_t > 3.0:
					phase = ""
					_goto("shots")
			"shots":
				if _once("shots"):
					_step_shots()
			"done":
				pass

	func _step_shots() -> void:
		_busy = true
		await _shot("drift_final")
		_report()
		print("[DRIFT] COMPLETE")
		get_tree().quit()
		_goto("done")
		_busy = false
