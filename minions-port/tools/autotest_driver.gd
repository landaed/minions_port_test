extends SceneTree
## End-to-end visual test driver. Boots the real client, registers a fresh
## account, logs in, creates a character, enters the world, then runs a scripted
## gameplay tour (movement, NPC dialog, combat, looting, inventory/spellbook/
## journal windows), saving numbered screenshots along the way.
##
## Run (needs a display; software Vulkan is fine):
##   xvfb-run godot --path minions-port --script res://tools/autotest_driver.gd \
##       --resolution 960x540
## Output: /tmp/shots/NN_name.png   (override with MOM_SHOT_DIR)

var control: Control = null
var driver: Node = null

func _initialize() -> void:
	var dir := OS.get_environment("MOM_SHOT_DIR")
	if dir.is_empty():
		dir = "/tmp/shots"
	DirAccess.make_dir_recursive_absolute(dir)
	var scene: PackedScene = load("res://control.tscn")
	control = scene.instantiate()
	root.add_child(control)
	driver = AutotestDriver.new(control, dir)
	root.add_child(driver)


class AutotestDriver:
	extends Node

	const PREFERRED_NPCS := ["Chancellor Tolip", "Guard Soithar", "Frizzle Fry"]

	var control: Control
	var shot_dir: String
	var view: Control = null
	var state := "connect"
	var state_t := 0.0
	var total_t := 0.0
	var shot_idx := 0
	var username := ""
	var _did := {}
	var _busy := false               # an awaited step is in flight; skip _process
	var _walk_entity_id := 0         # when walking to an entity, re-aim each tick
	var _walk_target := Vector3.ZERO
	var _walk_next_state := ""
	var _walk_deadline := 0.0
	var _walk_stop_dist := 2.0
	var _npc_entity: Dictionary = {}
	var _interact_tries := 0

	func _init(c: Control, dir: String):
		control = c
		shot_dir = dir
		username = "bot%d" % (Time.get_unix_time_from_system() as int % 1000000)

	func _shot(name_tag: String) -> void:
		shot_idx += 1
		var path := "%s/%02d_%s.png" % [shot_dir, shot_idx, name_tag]
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		img.save_png(path)
		print("[AUTOTEST] shot -> ", path)

	func _key(code: Key, pressed: bool) -> void:
		var ev := InputEventKey.new()
		ev.keycode = code
		ev.physical_keycode = code
		ev.pressed = pressed
		Input.parse_input_event(ev)

	func _goto(s: String) -> void:
		print("[AUTOTEST] state: %s -> %s (t=%.1f)" % [state, s, total_t])
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

	func _log_tail() -> String:
		return "\n".join(view.combat_log) if view else ""

	func _speed_tweaks() -> void:
		for light in _find_all(get_tree().root, "DirectionalLight3D"):
			light.shadow_enabled = false
		if view and view.camera:
			view.camera.attributes = null
			view.camera.far = 700.0
		# Software rendering runs at a few FPS; let physics catch up to wall time
		# each frame so client prediction keeps pace with the server's wall-clock
		# movement integration (otherwise held keys overshoot massively).
		Engine.max_physics_steps_per_frame = 240

	func _find_all(n: Node, klass: String) -> Array:
		var out: Array = []
		if n.get_class() == klass:
			out.append(n)
		for c in n.get_children():
			out += _find_all(c, klass)
		return out

	func _self_pos() -> Vector3:
		return view.player_body.global_position if view and view.player_body else Vector3.ZERO

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

	func _entity_by_id(id: int) -> Dictionary:
		if view == null:
			return {}
		for e in view.replicated_entities:
			if e is Dictionary and int(e.get("id", 0)) == id:
				return e
		return {}

	func _nearest_entity(want_enemy: bool, want_dead: bool = false, prefer_names: Array = []) -> Dictionary:
		var best: Dictionary = {}
		var best_d := 1e9
		var best_pref: Dictionary = {}
		var best_pref_d := 1e9
		if view == null:
			return best
		for e in view.replicated_entities:
			if not (e is Dictionary) or bool(e.get("is_self", false)):
				continue
			var dead: bool = bool(e.get("dead", false)) or float(e.get("health", 1.0)) <= 0.0
			if dead != want_dead:
				continue
			if bool(e.get("is_enemy", false)) != want_enemy:
				continue
			var d := _server_dist_to(e)
			if d < best_d:
				best_d = d
				best = e
			if prefer_names.has(str(e.get("name", ""))) and d < best_pref_d:
				best_pref_d = d
				best_pref = e
		return best_pref if not best_pref.is_empty() else best

	func _entity_godot_pos(e: Dictionary) -> Vector3:
		return view._server_to_godot(e.get("position", []))

	func _face_towards(target: Vector3) -> void:
		var dx := target.x - _self_pos().x
		var dz := target.z - _self_pos().z
		if absf(dx) + absf(dz) < 0.01:
			return
		view.player_body.rotation.y = atan2(-dx, -dz)

	func _begin_walk_to_entity(e: Dictionary, next_state: String, stop_dist: float = 1.6, deadline: float = 45.0) -> void:
		_walk_entity_id = int(e.get("id", 0))
		_walk_target = _entity_godot_pos(e)
		_walk_next_state = next_state
		_walk_stop_dist = stop_dist
		_walk_deadline = total_t + deadline
		_key(KEY_W, true)
		_goto("walking")

	func _begin_walk_to_point(target: Vector3, next_state: String, stop_dist: float = 2.0, deadline: float = 45.0) -> void:
		_walk_entity_id = 0
		_walk_target = target
		_walk_next_state = next_state
		_walk_stop_dist = stop_dist
		_walk_deadline = total_t + deadline
		_key(KEY_W, true)
		_goto("walking")

	func _walk_tick() -> void:
		var d := 1e9
		if _walk_entity_id > 0:
			var e := _entity_by_id(_walk_entity_id)
			if not e.is_empty():
				_walk_target = _entity_godot_pos(e)
				d = _server_dist_to(e)  # what the server's range check will see
				_did["walk_lost_since"] = -1.0
			else:
				# Target entity left the snapshot; don't keep marching blind.
				var lost := float(_did.get("walk_lost_since", -1.0))
				if lost < 0.0:
					_did["walk_lost_since"] = total_t
				elif total_t - lost > 3.0:
					_key(KEY_W, false)
					print("[AUTOTEST] walk target lost; aborting walk")
					_goto(_walk_next_state)
					return
		if _walk_entity_id == 0:
			d = Vector2(_walk_target.x - _self_pos().x, _walk_target.z - _self_pos().z).length()
		_face_towards(_walk_target)
		var d_client := Vector2(_walk_target.x - _self_pos().x, _walk_target.z - _self_pos().z).length()
		if d <= _walk_stop_dist or (d > 1e8 and d_client <= _walk_stop_dist) or total_t > _walk_deadline:
			_key(KEY_W, false)
			print("[AUTOTEST] walk done: server_d=%.2f client_d=%.2f" % [d, d_client])
			_goto(_walk_next_state)

	func _dump_entities() -> void:
		if view == null:
			return
		var bits: Array = []
		for e in view.replicated_entities:
			if e is Dictionary and not bool(e.get("is_self", false)):
				bits.append("%s%s d=%.0f" % [
					str(e.get("name", "?")),
					"[E]" if bool(e.get("is_enemy", false)) else "",
					_server_dist_to(e)])
		print("[AUTOTEST] entities: ", "; ".join(bits))

	func _process(delta: float) -> void:
		if _busy:
			return
		state_t += delta
		total_t += delta
		if total_t > 540.0 and state != "done" and state != "finish":
			print("[AUTOTEST] global timeout; finishing")
			_goto("finish")
		match state:
			"connect":
				if state_t > 2.0 and _once("register"):
					var u: LineEdit = control.get_node("VBoxContainer/UsernameField")
					var e: LineEdit = control.get_node("VBoxContainer/EmailField")
					var p: LineEdit = control.get_node("VBoxContainer/PasswordField")
					u.text = username
					e.text = username + "@example.com"
					p.text = "testpass1"
					control._on_register_button_pressed()
					_goto("registering")
			"registering":
				if _status().begins_with("Registered!") and _once("login"):
					_step_login()
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
						var n: LineEdit = control.get_node("VBoxContainer/CharacterNameField")
						var cname := ""
						for i in range(8):
							cname += letters[randi() % letters.length()]
						n.text = cname.capitalize()
						control._on_create_character_button_pressed()
						state_t = 0.0
				elif _once("enter_world"):
					_step_enter_world()
			"entering_world":
				view = control.gameplay_view
				if view != null and view.visible and view._has_spawned:
					_speed_tweaks()
					_goto("spawned")
			"spawned":
				if state_t > 4.0 and _once("spawn_shots"):
					_step_spawn_shots()
			"npc_first":
				# Dialog-focused capture: go straight to an NPC from the fresh
				# spawn (set MOM_AT_SKIP_COMBAT=1), before combat moves the player.
				_goto("find_npc")
			"find_npc":
				_npc_entity = _nearest_entity(false, false, PREFERRED_NPCS)
				if not _npc_entity.is_empty():
					_dump_entities()
					print("[AUTOTEST] walking to NPC '%s'" % _npc_entity.get("name", "?"))
					_begin_walk_to_entity(_npc_entity, "at_npc", 1.6, 30.0)
				elif state_t > 10.0:
					_goto("inventory_check")
			"walking":
				_walk_tick()
			"at_npc":
				_step_at_npc()
			"dialog_open":
				if state_t > 2.5 and _once("dialog_shots"):
					_step_dialog_shots()
			"dialog_chosen":
				if state_t > 4.0 and _once("after_choice"):
					_step_after_choice()
			"journal_check":
				if state_t > 1.0 and _once("journal"):
					_step_journal()
			"combat_start":
				_step_combat_start()
			"combat_attack":
				_step_combat_attack()
			"loot_corpse":
				_step_loot()
			"inventory_check":
				if state_t > 1.0 and _once("inventory"):
					_step_inventory()
			"spellbook_check":
				if state_t > 1.0 and _once("spellbook"):
					_step_spellbook()
			"tower_walk":
				if _once("tower_walk"):
					# Stop short of the guard tower so the camera stays outside.
					var p: Vector3 = view._server_to_godot([40.982, -254.041, 127.0])
					_begin_walk_to_point(p, "tower_arrived", 9.0, 40.0)
			"tower_arrived":
				if state_t > 1.0 and _once("tower_shots"):
					_step_tower_shots()
			"finish":
				if _once("finish"):
					_step_finish()
			"done":
				pass

	# --- awaited steps (each sets _busy so _process can't re-enter) ---

	func _step_login() -> void:
		_busy = true
		await _shot("login")
		control._on_login_button_pressed()
		_goto("logging_in")
		_busy = false

	func _step_enter_world() -> void:
		_busy = true
		await _shot("character_select")
		control.character_list.select(0)
		control._on_enter_world_button_pressed()
		_goto("entering_world")
		_busy = false

	func _step_spawn_shots() -> void:
		_busy = true
		_speed_tweaks()
		await _shot("spawn")
		view.player_body.rotate_y(PI / 2.0)
		await _shot("spawn_turned")
		view.player_body.rotate_y(-PI / 2.0)
		if OS.get_environment("MOM_AT_SKIP_COMBAT") == "1":
			_goto("find_npc")  # dialog-focused capture from the fresh spawn
		else:
			_goto("combat_start")  # the test mob spawns beside us; fight first
		_busy = false

	func _step_at_npc() -> void:
		# Wait for the server position to settle, then interact; if the server
		# still says "too far away", nudge closer and retry.
		if state_t < 2.0:
			return
		if _once("interact_try_%d" % _interact_tries):
			var fresh := _entity_by_id(int(_npc_entity.get("id", 0)))
			if not fresh.is_empty():
				_face_towards(_entity_godot_pos(fresh))
			view._request_server_command("target_entity", {"entity_id": int(_npc_entity.get("id", 0))})
			await get_tree().create_timer(0.8).timeout
			view._request_server_command("interact")
			print("[AUTOTEST] interact try %d (server_d=%.2f)" % [_interact_tries, _server_dist_to(_entity_by_id(int(_npc_entity.get("id", 0))))])
			return
		if view.npc_window and view.npc_window.visible:
			_goto("dialog_open")
			return
		if _log_tail().contains("too far away") and state_t > 4.0 and _interact_tries < 3:
			_interact_tries += 1
			view.combat_log.clear()
			var fresh := _entity_by_id(int(_npc_entity.get("id", 0)))
			if fresh.is_empty():
				_goto("journal_check")
				return
			_begin_walk_to_entity(fresh, "at_npc", maxf(0.8, 1.6 - 0.4 * _interact_tries))
			return
		if state_t > 14.0:
			print("[AUTOTEST] npc window never opened; log: ", _log_tail())
			_goto("journal_check")

	func _step_dialog_shots() -> void:
		_busy = true
		await _shot("npc_dialog")
		var buttons: Array = view.npc_window.choices_box.get_children()
		var clicked := false
		for b in buttons:
			if b is Button and not b.disabled:
				b.emit_signal("pressed")
				clicked = true
				break
		if clicked:
			_goto("dialog_chosen")
		else:
			view.npc_window.close_window()
			_goto("journal_check")
		_busy = false

	func _step_after_choice() -> void:
		_busy = true
		await _shot("dialog_after_choice")
		view.npc_window.close_window()
		_goto("journal_check")
		_busy = false

	func _step_journal() -> void:
		_busy = true
		view._toggle_journal()
		await get_tree().create_timer(0.5).timeout
		await _shot("journal")
		view.journal_window.close_window()
		_goto("inventory_check")
		_busy = false

	func _step_combat_start() -> void:
		var mob := _nearest_entity(true)
		if mob.is_empty():
			if state_t > 12.0 and _once("no_enemy"):
				_dump_entities()
				print("[AUTOTEST] no enemy found; skipping combat")
				_goto("find_npc")
			return
	# Don't chase enemies on other floors of the tower (big vertical offsets).
		var sp := _self_server_pos()
		var ep = mob.get("position", [0, 0, 0])
		if absf(float(ep[2]) - float(sp[2])) > 5.0:
			if state_t > 12.0 and _once("no_reachable_enemy"):
				_dump_entities()
				_goto("find_npc")
			return
		if _server_dist_to(mob) > 4.0:
			if _once("walk_to_mob_%d" % int(mob.get("id", 0))):
				print("[AUTOTEST] walking to enemy '%s'" % mob.get("name", "?"))
				_begin_walk_to_entity(mob, "combat_start", 3.0, 30.0)
			return
		if _once("attack"):
			_did["combat_mob"] = mob
			view._request_server_command("target_entity", {"entity_id": int(mob.get("id", 0))})
			_face_towards(_entity_godot_pos(mob))
			view._request_server_command("attack_toggle")
			_goto("combat_attack")

	func _step_combat_attack() -> void:
		var mob: Dictionary = _did.get("combat_mob", {})
		var fresh := _entity_by_id(int(mob.get("id", 0)))
		if not fresh.is_empty():
			_face_towards(_entity_godot_pos(fresh))
		if state_t > 5.0 and _once("combat_shot"):
			_busy = true
			await _shot("combat")
			_busy = false
		var dead: bool = (not fresh.is_empty()) and (bool(fresh.get("dead", false)) or float(fresh.get("health", 1.0)) <= 0.0)
		if fresh.is_empty() and state_t > 10.0:
			dead = true
		if dead:
			_goto("loot_corpse")
		elif state_t > 150.0:
			print("[AUTOTEST] combat too slow; log: ", _log_tail())
			_goto("find_npc")

	func _step_loot() -> void:
		if state_t < 2.5:
			return
		if _once("loot_click"):
			var corpse := _nearest_entity(true, true)
			if corpse.is_empty():
				corpse = _did.get("combat_mob", {})
			var cp := _entity_godot_pos(corpse)
			_face_towards(cp)
			view._request_server_command("select_entity", {"entity_id": int(corpse.get("id", 0)), "double_click": true})
			return
		if view.loot_window and view.loot_window.visible and _once("loot_shots"):
			_busy = true
			await _shot("loot_window")
			for i in range(6):
				view._request_server_command("loot_item", {"slot": 0, "alt": true})
				await get_tree().create_timer(0.7).timeout
			await _shot("loot_after_take")
			if view.loot_window.visible:
				view.loot_window.close_window()
			_goto("find_npc")
			_busy = false
			return
		if state_t > 14.0 and _once("loot_skip"):
			print("[AUTOTEST] loot window never opened; log: ", _log_tail())
			_goto("find_npc")

	func _step_inventory() -> void:
		_busy = true
		view._toggle_inventory()
		await get_tree().create_timer(1.5).timeout
		await _shot("inventory")
		view.inventory_window.close_window()
		_goto("spellbook_check")
		_busy = false

	func _step_spellbook() -> void:
		_busy = true
		view._toggle_spellbook()
		await get_tree().create_timer(1.5).timeout
		await _shot("spellbook")
		view.spellbook_window.close_window()
		_goto("tower_walk")
		_busy = false

	func _step_tower_shots() -> void:
		_busy = true
		var tower: Vector3 = view._server_to_godot([40.982, -254.041, 127.0])
		_face_towards(tower)
		await _shot("tower_area")
		view.player_body.rotate_y(PI)
		await _shot("tower_area_back")
		_goto("finish")
		_busy = false

	func _step_finish() -> void:
		_busy = true
		_key(KEY_W, false)
		await _shot("final")
		print("[AUTOTEST] COMPLETE — %d screenshots in %s" % [shot_idx, shot_dir])
		get_tree().quit()
		_goto("done")
		_busy = false
