extends SceneTree
## Focused verification for two fixes:
##   1. Enemy corpses must NOT slide after death (client freezes them).
##   2. A dead player must be able to respawn at their bind point WITHOUT
##      relogging (death overlay -> "respawn" command -> alive again).
##
## Boots the real client, registers + logs in + creates a character + enters the
## world (same path as autotest_driver), then:
##   - screenshots the live player, kills it with the `suicide` cheat, confirms
##     the death overlay appears, sends `respawn`, confirms it clears.
##   - levels up + full-heals, kills a nearby enemy, then samples the corpse's
##     world position for ~3s and asserts it does not move.
##
## Run: xvfb-run godot --path minions-port \
##        --script res://tools/death_corpse_test.gd --resolution 1280x720
## Output: /tmp/shots_death/NN_name.png  (override with MOM_SHOT_DIR)

var control: Control = null
var driver: Node = null

func _initialize() -> void:
	var dir := OS.get_environment("MOM_SHOT_DIR")
	if dir.is_empty():
		dir = "/tmp/shots_death"
	DirAccess.make_dir_recursive_absolute(dir)
	var scene: PackedScene = load("res://control.tscn")
	control = scene.instantiate()
	root.add_child(control)
	driver = DeathDriver.new(control, dir)
	root.add_child(driver)


class DeathDriver:
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
	var _walk_entity_id := 0
	var _walk_target := Vector3.ZERO
	var _walk_next_state := ""
	var _walk_deadline := 0.0
	var _walk_stop_dist := 2.0
	# corpse-watch state
	var _corpse_id := 0
	var _corpse_samples: Array = []
	var _death_pos_before := Vector3.ZERO

	func _init(c: Control, dir: String):
		control = c
		shot_dir = dir
		username = "death%d" % (Time.get_unix_time_from_system() as int % 1000000)

	func _shot(name_tag: String) -> void:
		shot_idx += 1
		var path := "%s/%02d_%s.png" % [shot_dir, shot_idx, name_tag]
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		img.save_png(path)
		print("[DEATHTEST] shot -> ", path)

	func _key(code: Key, pressed: bool) -> void:
		var ev := InputEventKey.new()
		ev.keycode = code
		ev.physical_keycode = code
		ev.pressed = pressed
		Input.parse_input_event(ev)

	func _goto(s: String) -> void:
		print("[DEATHTEST] state: %s -> %s (t=%.1f)" % [state, s, total_t])
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

	func _nearest_entity(want_enemy: bool, want_dead: bool = false) -> Dictionary:
		var best: Dictionary = {}
		var best_d := 1e9
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
		return best

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

	func _walk_tick() -> void:
		var d := 1e9
		if _walk_entity_id > 0:
			var e := _entity_by_id(_walk_entity_id)
			if not e.is_empty():
				_walk_target = _entity_godot_pos(e)
				d = _server_dist_to(e)
		_face_towards(_walk_target)
		var d_client := Vector2(_walk_target.x - _self_pos().x, _walk_target.z - _self_pos().z).length()
		if d <= _walk_stop_dist or (d > 1e8 and d_client <= _walk_stop_dist) or total_t > _walk_deadline:
			_key(KEY_W, false)
			_goto(_walk_next_state)

	func _process(delta: float) -> void:
		if _busy:
			return
		state_t += delta
		total_t += delta
		if total_t > 420.0 and state != "done":
			print("[DEATHTEST] global timeout; finishing")
			_goto("finish")
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
						var cname := ""
						for i in range(8):
							cname += letters[randi() % letters.length()]
						control.get_node("VBoxContainer/CharacterNameField").text = cname.capitalize()
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
				# Death/respawn test first; the ~20s it takes also gives the test
				# skeleton time to enter the client's canSee for the corpse test.
				if state_t > 4.0 and _once("alive_shot"):
					_step_alive_then_die()
			"dying":
				_step_dying()
			"respawning":
				_step_respawning()
			"buff_up":
				if state_t > 1.0 and _once("buff"):
					_step_buff_up()
			"corpse_combat":
				_step_corpse_combat()
			"walking":
				_walk_tick()
			"corpse_attack":
				_step_corpse_attack()
			"corpse_watch":
				_step_corpse_watch(delta)
			"finish":
				if _once("finish"):
					_step_finish()
			"done":
				pass

	func _step_login() -> void:
		_busy = true
		await _shot("login")
		control._on_login_button_pressed()
		_goto("logging_in")
		_busy = false

	func _step_enter_world() -> void:
		_busy = true
		control.character_list.select(0)
		control._on_enter_world_button_pressed()
		_goto("entering_world")
		_busy = false

	# --- Death / respawn ---------------------------------------------------
	func _step_alive_then_die() -> void:
		_busy = true
		_speed_tweaks()
		await _shot("alive")
		_death_pos_before = _self_pos()
		print("[DEATHTEST] player pos before death: ", _death_pos_before)
		print("[DEATHTEST] casting suicide cheat...")
		view._request_server_command("cheat", {"action": "suicide", "params": {}})
		_goto("dying")
		_busy = false

	func _step_dying() -> void:
		if view._is_dead:
			if _once("death_shot"):
				_busy = true
				await get_tree().create_timer(0.6).timeout
				await _shot("death_overlay")
				print("[DEATHTEST] PASS: death overlay shown (_is_dead=true)")
				print("[DEATHTEST] sending respawn...")
				view._do_respawn()
				_goto("respawning")
				_busy = false
		elif state_t > 15.0 and _once("death_timeout"):
			print("[DEATHTEST] FAIL: never entered death state after suicide")
			_goto("buff_up")

	func _step_respawning() -> void:
		if not view._is_dead:
			if _once("respawn_shot"):
				_busy = true
				await get_tree().create_timer(1.5).timeout
				await _shot("respawned")
				var after := _self_pos()
				var moved := _death_pos_before.distance_to(after)
				var ri = view._rapid_info()
				print("[DEATHTEST] PASS: respawned (_is_dead=false). pos after=", after,
					" moved=%.1f" % moved,
					" HP=", ri.get("health", "?"), "/", ri.get("maxhealth", "?"))
				_goto("buff_up")
				_busy = false
		elif state_t > 15.0 and _once("respawn_timeout"):
			print("[DEATHTEST] FAIL: still dead 15s after respawn command")
			_goto("buff_up")

	# --- Corpse freeze -----------------------------------------------------
	func _step_buff_up() -> void:
		_busy = true
		view._request_server_command("cheat", {"action": "set_level", "params": {"level": 30}})
		await get_tree().create_timer(1.0).timeout
		view._request_server_command("cheat", {"action": "full_heal", "params": {}})
		await get_tree().create_timer(1.0).timeout
		print("[DEATHTEST] buffed to level 30 + full heal; hunting an enemy")
		_goto("corpse_combat")
		_busy = false

	func _step_corpse_combat() -> void:
		var mob := _nearest_entity(true)
		if mob.is_empty():
			if state_t > 20.0 and _once("no_enemy"):
				print("[DEATHTEST] no enemy found to test corpse; moving to death test")
				_goto("finish")
			return
		var sp := _self_server_pos()
		var ep = mob.get("position", [0, 0, 0])
		if absf(float(ep[2]) - float(sp[2])) > 5.0:
			if state_t > 20.0 and _once("no_reach"):
				_goto("finish")
			return
		if _server_dist_to(mob) > 3.5:
			if _once("walk_%d" % int(mob.get("id", 0))):
				print("[DEATHTEST] walking to enemy '%s'" % mob.get("name", "?"))
				_begin_walk_to_entity(mob, "corpse_combat", 3.0, 30.0)
			return
		if _once("attack_%d" % int(mob.get("id", 0))):
			_did["combat_mob"] = mob
			view._request_server_command("target_entity", {"entity_id": int(mob.get("id", 0))})
			_face_towards(_entity_godot_pos(mob))
			view._request_server_command("attack_toggle")
			_goto("corpse_attack")

	func _step_corpse_attack() -> void:
		var mob: Dictionary = _did.get("combat_mob", {})
		var id := int(mob.get("id", 0))
		var fresh := _entity_by_id(id)
		if not fresh.is_empty():
			_face_towards(_entity_godot_pos(fresh))
		var dead: bool = (not fresh.is_empty()) and (bool(fresh.get("dead", false)) or float(fresh.get("health", 1.0)) <= 0.0)
		if dead and _once("corpse_capture"):
			_busy = true
			_corpse_id = id
			# Use the game's own key derivation (str of the float id, e.g. "2.0").
			var key: String = view._entity_key(fresh)
			print("[DEATHTEST] enemy '%s' (id %d) died. body keys=%s want=%s" % [
				mob.get("name", "?"), id, str(view.replicated_entity_nodes.keys()), key])
			# Sample the corpse position frame-by-frame the moment it dies (before
			# any despawn), so we can prove it doesn't slide.
			var samples: Array = []
			for i in range(28):
				await get_tree().process_frame
				var b = view.replicated_entity_nodes.get(key)
				if b != null and is_instance_valid(b):
					samples.append(b.global_position)
					if i == 1:
						await _shot("corpse_fresh")
			await _shot("corpse_after")
			if samples.size() >= 2:
				var first: Vector3 = samples[0]
				var max_drift := 0.0
				for p in samples:
					max_drift = maxf(max_drift, first.distance_to(p))
				print("[DEATHTEST] corpse samples=%d  max_drift=%.4f units" % [samples.size(), max_drift])
				if max_drift < 0.05:
					print("[DEATHTEST] PASS: corpse stayed put (drift %.4f < 0.05u)" % max_drift)
				else:
					print("[DEATHTEST] WARN: corpse drifted %.4f units" % max_drift)
			else:
				print("[DEATHTEST] WARN: corpse body not present to sample (key %s)" % key)
			_goto("finish")
			_busy = false
		elif state_t > 120.0 and _once("combat_slow"):
			print("[DEATHTEST] combat too slow; moving to death test")
			_goto("finish")

	func _step_corpse_watch(delta: float) -> void:
		var body = view.replicated_entity_nodes.get(str(_corpse_id))
		if body == null or not is_instance_valid(body):
			if state_t > 4.0 and _once("corpse_gone"):
				print("[DEATHTEST] corpse body despawned before sampling finished")
				_goto("finish")
			return
		_corpse_samples.append(body.global_position)
		if _once("corpse_shot_start"):
			_busy = true
			await _shot("corpse_fresh")
			_busy = false
		# Sample for ~3 seconds, then evaluate drift.
		if state_t >= 3.0 and _once("corpse_eval"):
			_busy = true
			await _shot("corpse_after_3s")
			var first: Vector3 = _corpse_samples[0]
			var max_drift := 0.0
			for p in _corpse_samples:
				max_drift = maxf(max_drift, first.distance_to(p))
			print("[DEATHTEST] corpse samples=%d  max_drift=%.3f units over %.1fs" % [
				_corpse_samples.size(), max_drift, state_t])
			if max_drift < 0.05:
				print("[DEATHTEST] PASS: corpse stayed put (drift < 0.05u)")
			else:
				print("[DEATHTEST] WARN: corpse drifted %.3f units" % max_drift)
			_goto("finish")
			_busy = false

	func _step_finish() -> void:
		_busy = true
		# Populate both hotbar pages with the character's class abilities/spells so
		# the 2-bar demo has content to show.
		view._request_server_command("cheat", {"action": "learn_class_spells", "params": {}})
		await get_tree().create_timer(1.0).timeout
		view._request_server_command("cheat", {"action": "raise_skills", "params": {}})
		await get_tree().create_timer(1.0).timeout
		view._request_server_command("get_spellbook")
		await get_tree().create_timer(1.0).timeout
		await _shot("hotbar_bar1")
		print("[DEATHTEST] hotbar page after fill: %d (peek=%s)" % [view.hotbar._active_page, view.hotbar._peeking])
		# Cycle to Bar 2 (the "R" / Y-button action).
		view.hotbar.cycle_page()
		await get_tree().create_timer(0.4).timeout
		await _shot("hotbar_bar2_cycled")
		print("[DEATHTEST] cycled to page %d" % view.hotbar._active_page)
		view.hotbar.cycle_page()  # back to Bar 1
		await get_tree().create_timer(0.4).timeout
		# Hold the secondary modifier (Shift / left bumper) to peek BOTH bars. Drive
		# it as a real key hold so the per-frame poll in _physics_process picks it up.
		_key(KEY_SHIFT, true)
		await get_tree().create_timer(0.5).timeout
		await _shot("hotbar_secondary_peek")
		print("[DEATHTEST] secondary peek: bar1 visible=%s bar2 visible=%s" % [
			view.hotbar._row_boxes[0].visible, view.hotbar._row_boxes[1].visible])
		_key(KEY_SHIFT, false)
		# --- Buff replication. Apply via the test cheat and read the values the
		# server now streams + the avatar's rendered state. Order matters for the
		# screenshots: do the model/scale buffs (visible) before invisibility.
		var base_scale := float(view._self_entity().get("scale", 1.0))
		view._request_server_command("cheat", {"action": "apply_spell", "params": {"name": "Enlarge"}})
		await get_tree().create_timer(3.0).timeout
		await _shot("ability_enlarge")
		var big_scale := float(view._self_entity().get("scale", 1.0))
		print("[DEATHTEST] Enlarge: scale %.2f -> %.2f (rig scale %.2f) %s" % [
			base_scale, big_scale, view._player_rig.scale.x,
			"PASS" if big_scale > base_scale + 0.01 else "WARN"])
		# Transmutation of Volsh -> blue dragon (illusion) + haste/str/offense.
		view._request_server_command("cheat", {"action": "apply_spell", "params": {"name": "Transmutation of Volsh"}})
		await get_tree().create_timer(3.0).timeout
		await _shot("ability_volsh_dragon")
		var model_now := str(view._self_entity().get("model", ""))
		print("[DEATHTEST] Transmutation of Volsh: model='%s' rig='%s' %s" % [
			model_now, view._player_model_key,
			"PASS" if "dragon" in model_now.to_lower() or "dragon" in view._player_model_key.to_lower() else "WARN"])
		view._request_server_command("cheat", {"action": "apply_spell", "params": {"name": "Urug's Sandals Fly"}})
		await get_tree().create_timer(3.0).timeout
		await _shot("ability_flying")
		var fly := float(view._self_entity().get("flying", 0.0))
		print("[DEATHTEST] Urug's Sandals Fly: flying=%.2f %s" % [
			fly, "PASS" if fly > 0.0 else "WARN"])
		view._request_server_command("cheat", {"action": "apply_spell", "params": {"name": "Erar Invisibility"}})
		await get_tree().create_timer(3.0).timeout
		await _shot("ability_invisible")
		var vis := float(view._self_entity().get("visibility", 1.0))
		print("[DEATHTEST] Erar Invisibility: visibility=%.2f (rig fade=%.2f) %s" % [
			vis, view._player_rig._fade_signature, "PASS" if vis < 0.99 else "WARN"])
		# Buff bar should now show the applied timed effects.
		await get_tree().create_timer(0.6).timeout
		var chips: int = view._buff_bar.get_child_count()
		print("[DEATHTEST] buff bar chips=%d %s" % [chips, "PASS" if chips > 0 else "WARN"])
		await _shot("buff_bar")
		await _shot("final")
		print("[DEATHTEST] done.")
		await get_tree().create_timer(0.3).timeout
		get_tree().quit()
