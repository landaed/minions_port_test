extends SceneTree
## Bug-fix proof driver. Boots the real client against the live local server
## stack, then walks the exact flows this session changed and captures
## screenshots + [PROOF] log lines for each:
##
##   1. Character-select roster BEFORE any gear (racial default skin).
##   2. Enter world, cheat-equip chest/leg armor + helm + shield, closeup shot
##      (in-world clothing textures).
##   3. Entity-stream audit: prints every replicated entity's server distance —
##      mobs beyond the old 60u bubble prove the new stream radius works.
##   4. Esc menu -> REAL synthesized mouse click on "Character Select" ->
##      asserts Input.mouse_mode is VISIBLE (the lost-cursor bug) and that the
##      roster now wears the equipped clothing (the missing-clothing bug).
##
## Run:
##   xvfb-run -a godot --path minions-port --script res://tools/proof_driver.gd \
##       --resolution 1280x720
## Output: /tmp/proof_shots/NN_name.png  (override with MOM_SHOT_DIR)

var control: Control = null
var driver: Node = null

func _initialize() -> void:
	var dir := OS.get_environment("MOM_SHOT_DIR")
	if dir.is_empty():
		dir = "/tmp/proof_shots"
	DirAccess.make_dir_recursive_absolute(dir)
	var scene: PackedScene = load("res://control.tscn")
	control = scene.instantiate()
	root.add_child(control)
	driver = ProofDriver.new(control, dir)
	root.add_child(driver)


class ProofDriver:
	extends Node

	var control: Control
	var shot_dir: String
	var view: Control = null
	var state := "connect"
	var state_t := 0.0
	var total_t := 0.0
	var shot_idx := 0
	var username := ""
	var _did := {}
	var _busy := false

	func _init(c: Control, dir: String):
		control = c
		shot_dir = dir
		username = "proof%d" % (Time.get_unix_time_from_system() as int % 1000000)

	func _shot(name_tag: String) -> void:
		shot_idx += 1
		var path := "%s/%02d_%s.png" % [shot_dir, shot_idx, name_tag]
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		img.save_png(path)
		print("[PROOFDRV] shot -> ", path)

	func _key(code: Key, pressed: bool) -> void:
		var ev := InputEventKey.new()
		ev.keycode = code
		ev.physical_keycode = code
		ev.pressed = pressed
		Input.parse_input_event(ev)

	func _click_at(pos: Vector2) -> void:
		# Real click through the whole input pipeline (_input -> GUI), exactly
		# like a player's mouse — this is what used to re-capture the cursor.
		for pressed in [true, false]:
			var ev := InputEventMouseButton.new()
			ev.button_index = MOUSE_BUTTON_LEFT
			ev.pressed = pressed
			ev.position = pos
			ev.global_position = pos
			Input.parse_input_event(ev)

	func _goto(s: String) -> void:
		print("[PROOFDRV] state: %s -> %s (t=%.1f)" % [state, s, total_t])
		state = s
		state_t = 0.0

	func _once(tag: String) -> bool:
		if _did.has(tag):
			return false
		_did[tag] = true
		return true

	func _status() -> String:
		# control reparents the form into a PanelContainer at runtime, so use its
		# @onready references instead of scene paths.
		var lbl: Label = control.status_label
		return lbl.text if lbl else ""

	func _speed_tweaks() -> void:
		for light in _find_all(get_tree().root, "DirectionalLight3D"):
			light.shadow_enabled = false
		if view and view.camera:
			view.camera.attributes = null
			view.camera.far = 700.0
		Engine.max_physics_steps_per_frame = 240

	func _find_all(n: Node, klass: String) -> Array:
		var out: Array = []
		if n.get_class() == klass:
			out.append(n)
		for c in n.get_children():
			out += _find_all(c, klass)
		return out

	func _self_server_pos() -> Array:
		var se: Dictionary = view._self_entity() if view else {}
		var p = se.get("position", [0, 0, 0])
		return p if p is Array and p.size() >= 3 else [0, 0, 0]

	func _server_dist_to(e: Dictionary) -> float:
		var sp := _self_server_pos()
		var ep = e.get("position", [0, 0, 0])
		if not (ep is Array) or ep.size() < 3:
			return 1e9
		return Vector2(float(ep[0]) - float(sp[0]), float(ep[1]) - float(sp[1])).length()

	func _cheat(action: String, params: Dictionary) -> void:
		view._request_server_command("cheat", {"action": action, "params": params})

	func _wait_until(cond: Callable, timeout_s: float) -> bool:
		# Frame-based wait with a wall-clock deadline: under software rendering
		# the game can run at ~1 fps, so fixed 1s timers are single frames.
		var deadline := Time.get_ticks_msec() + int(timeout_s * 1000.0)
		while Time.get_ticks_msec() < deadline:
			if cond.call():
				return true
			await get_tree().process_frame
		return false

	func _process(delta: float) -> void:
		if _busy:
			return
		state_t += delta
		total_t += delta
		if total_t > 420.0 and state != "done":
			print("[PROOFDRV] global timeout; quitting")
			_goto("done")
			get_tree().quit(1)
		match state:
			"connect":
				if state_t > 2.0 and _once("register"):
					control.username_field.text = username
					control.email_field.text = username + "@example.com"
					control.password_field.text = "testpass1"
					control._on_register_button_pressed()
					_goto("registering")
			"registering":
				if _status().begins_with("Registered!") and _once("login"):
					control._on_login_button_pressed()
					_goto("logging_in")
				elif state_t > 25.0 and _once("login"):
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
					if _once("create_char") or (_status().begins_with("Create character failed") and state_t > 6.0 and _once("create_char_retry")):
						var letters := "abcdefghijklmnopqrstuvwxyz"
						var cname := ""
						for i in range(8):
							cname += letters[randi() % letters.length()]
						control.character_name_field.text = cname.capitalize()
						for ci in range(control.class_option.item_count):
							if control.class_option.get_item_text(ci) == "Warrior":
								control.class_option.select(ci)
								break
						control._on_create_character_button_pressed()
						state_t = 0.0
				elif _once("enter_world"):
					_step_roster_before()
			"entering_world":
				view = control.gameplay_view
				if view != null and view.visible and view._has_spawned:
					_speed_tweaks()
					_goto("spawned")
			"spawned":
				if state_t > 4.0 and _once("equip"):
					_step_equip()
			"equipped_shot":
				if state_t > 5.0 and _once("equipped_shot"):
					_step_equipped_shot()
			"entity_audit":
				if state_t > 1.0 and _once("entity_audit"):
					_step_entity_audit()
			"esc_menu":
				if state_t > 1.0 and _once("esc_menu"):
					_step_esc_menu()
			"back_at_roster":
				_step_back_at_roster()
			"done":
				pass

	# --- steps ------------------------------------------------------------

	func _step_roster_before() -> void:
		_busy = true
		# Let the camera glide to the selected character first.
		await get_tree().create_timer(2.0).timeout
		await _shot("charselect_fresh_default_skin")
		print("[PROOF] roster BEFORE gear: characters[0].tex = ",
			str(control.characters[0].get("tex", {})) if not control.characters.is_empty() else "<none>")
		control.character_list.select(0)
		control._on_enter_world_button_pressed()
		_goto("entering_world")
		_busy = false

	func _step_equip() -> void:
		_busy = true
		# Daylight so the screenshots are readable.
		_cheat("set_time", {"hour": 12, "minute": 0})
		await _shot("ingame_spawn")
		_cheat("set_level", {"level": 10})
		await get_tree().create_timer(1.0).timeout
		for item_name in ["Apprentice's Chain Hauberk of the Bear",
				"Apprentice's Plate Leggings of the Bear",
				"Plain Helm", "Tower Shield"]:
			_cheat("give_item", {"name": item_name, "equip": true})
			await get_tree().create_timer(1.0).timeout
		_cheat("full_heal", {})
		# Wait until the new appearance actually streams down (server static
		# resync is 2-4s; body texture 88 = the chain hauberk).
		var hauberk_streamed := func() -> bool:
			var t = view._self_entity().get("tex", {})
			return t is Dictionary and int((t as Dictionary).get("body", 0)) == 88
		await _wait_until(hauberk_streamed, 15.0)
		_goto("equipped_shot")
		_busy = false

	func _step_equipped_shot() -> void:
		_busy = true
		# Orbit the camera to the front of the avatar for the clothing closeup.
		var cam_yaw: Node3D = view.player_body.get_node("CameraYaw")
		cam_yaw.rotation.y = PI
		view.camera_pitch.rotation.x = 0.22
		view._camera_base_local_offset = Vector3(0, 0.5, 3.0)
		view._camera_zoom = 3.0
		view._apply_camera_zoom()
		await get_tree().create_timer(2.0).timeout
		var se: Dictionary = view._self_entity()
		print("[PROOF] in-world self tex = ", str(se.get("tex", {})),
			" mounts = ", str(se.get("mounts", {})))
		await _shot("ingame_equipped_closeup")
		cam_yaw.rotation.y = 0.0
		view.camera_pitch.rotation.x = -0.35
		view._camera_base_local_offset = Vector3(0, 2.2, 6.0)
		view._camera_zoom = 6.0
		view._apply_camera_zoom()
		_goto("entity_audit")
		_busy = false

	func _step_entity_audit() -> void:
		_busy = true
		# Give the wider stream a moment, then log every entity's server distance.
		await get_tree().create_timer(2.0).timeout
		var dists: Array = []
		var far_e: Dictionary = {}
		var far_d := 0.0
		for e in view.replicated_entities:
			if not (e is Dictionary) or bool(e.get("is_self", false)):
				continue
			var d := _server_dist_to(e)
			dists.append("%s d=%.0f" % [str(e.get("name", "?")), d])
			if d < 1e8 and d > far_d:
				far_d = d
				far_e = e
		var beyond := 0
		for e in view.replicated_entities:
			if e is Dictionary and not bool(e.get("is_self", false)) and _server_dist_to(e) > 60.0:
				beyond += 1
		print("[PROOF] entity stream: %d entities; %d beyond the old 60u cap; farthest %.0fu (%s)" % [
			view.replicated_entities.size() - 1, beyond, far_d, str(far_e.get("name", "?"))])
		print("[PROOF] distances: ", "; ".join(dists))
		# Face the farthest entity and show the F3 overlay for the shot.
		if not far_e.is_empty():
			var t: Vector3 = view._server_to_godot(far_e.get("position", []))
			var dx: float = t.x - view.player_body.global_position.x
			var dz: float = t.z - view.player_body.global_position.z
			if absf(dx) + absf(dz) > 0.01:
				view.player_body.rotation.y = atan2(-dx, -dz)
		if view._perf_overlay:
			view._perf_overlay.visible = true
		await get_tree().create_timer(1.5).timeout
		await _shot("ingame_distant_mobs")
		_goto("esc_menu")
		_busy = false

	func _step_esc_menu() -> void:
		_busy = true
		print("[PROOF] mouse_mode before Esc = %d (2=CAPTURED)" % Input.mouse_mode)
		_key(KEY_ESCAPE, true)
		_key(KEY_ESCAPE, false)
		var menu_visible := func() -> bool:
			return view._game_menu != null and view._game_menu.visible
		var menu_ok: bool = await _wait_until(menu_visible, 20.0)
		print("[PROOF] Esc menu open = ", menu_ok, "  mouse_mode = %d (0=VISIBLE)" % Input.mouse_mode)
		await _shot("esc_menu")
		if not menu_ok:
			print("[PROOF] FAIL: Esc menu never opened")
			get_tree().quit(1)
			return
		# Find the real "Character Select" button and click it like a player,
		# retrying (the click needs the menu to have had a layout pass).
		var target_btn: Button = null
		for b in view._game_menu.find_children("*", "Button", true, false):
			if b is Button and b.text == "Character Select":
				target_btn = b
				break
		if target_btn == null:
			print("[PROOF] FAIL: Character Select button not found")
			get_tree().quit(1)
			return
		var world_left := func() -> bool:
			return control.gameplay_view == null
		var left := false
		for attempt in range(4):
			_click_at(target_btn.get_global_rect().get_center())
			left = await _wait_until(world_left, 8.0)
			if left:
				break
			print("[PROOF] click attempt %d didn't leave world yet; retrying" % (attempt + 1))
		if not left:
			print("[PROOF] FAIL: Character Select click never left the world")
			get_tree().quit(1)
			return
		_goto("back_at_roster")
		_busy = false

	func _step_back_at_roster() -> void:
		if not _once("roster_checks"):
			return
		_busy = true
		var mode := Input.mouse_mode
		var pass_mouse := mode == Input.MOUSE_MODE_VISIBLE
		print("[PROOF] mouse after Esc->Character Select: mouse_mode=%d -> %s" % [
			mode, "PASS (visible)" if pass_mouse else "FAIL (still captured!)"])
		# Wait for the refreshed character_list (with worn-gear tex) that the
		# proxy re-queries after leave_world, then let the camera glide in.
		var roster_has_tex := func() -> bool:
			if control.characters.is_empty():
				return false
			var t = control.characters[0].get("tex", {})
			return t is Dictionary and not (t as Dictionary).is_empty()
		var pass_tex: bool = await _wait_until(roster_has_tex, 20.0)
		await get_tree().create_timer(2.0).timeout
		var tex: Dictionary = {}
		if not control.characters.is_empty():
			var t = control.characters[0].get("tex", {})
			if t is Dictionary:
				tex = t
		print("[PROOF] roster AFTER gear: characters[0].tex = %s -> %s" % [
			str(tex), "PASS (clothing streamed)" if pass_tex else "FAIL (no clothing data)"])
		print("[PROOF] roster mounts = ", str(control.characters[0].get("mounts", {})) if not control.characters.is_empty() else "<none>")
		await _shot("charselect_after_gear")
		# Zoom the camera right up to the rig for a clothing closeup.
		if not control._select_rigs.is_empty() and control._select_rigs[0] != null:
			var rig: Node3D = control._select_rigs[0]
			var world_pos: Vector3 = control.PED_SELECT + Vector3(rig.position.x, 0, 0)
			control._cam_target_pos = world_pos + Vector3(0.0, 1.1, 2.0)
			control._cam_target_look = world_pos + Vector3(0.0, 1.0, 0.0)
			await get_tree().create_timer(2.0).timeout
			await _shot("charselect_clothing_closeup")
		var ok := pass_mouse and pass_tex
		print("[PROOF] OVERALL: ", "PASS" if ok else "FAIL")
		_goto("done")
		get_tree().quit(0 if ok else 1)
		_busy = false
