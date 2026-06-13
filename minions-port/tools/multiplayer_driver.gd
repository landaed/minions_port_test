extends SceneTree
## Multiplayer visual test driver. One of these runs per Godot client process.
## Each registers its OWN account, creates a character, enters the SAME world,
## then performs a role-specific behaviour and saves screenshots that prove the
## clients can see each other (movement, equipment, pets) replicated live.
##
## Run (one process per client, all pointing at the same proxy):
##   MOM_MP_NAME=Bravo MOM_MP_CLASS=Warrior MOM_MP_ROLE=equip \
##   MOM_SHOT_DIR=/tmp/mp_b MOM_SHOT_PREFIX=B \
##   xvfb-run -a godot --path minions-port --script res://tools/multiplayer_driver.gd \
##       --resolution 960x540
##
## Roles:
##   observer - find the nearest OTHER player, walk up, face them, screenshot
##              repeatedly (captures their live movement + equipment changes).
##   equip    - move aside, then cheat-equip weapon/shield/helm/armour and stand
##              so observers can see the gear appear on this avatar.
##   summoner - cheat-learn + cast a summon, screenshot the pet following.

var control: Control = null
var driver: Node = null

func _initialize() -> void:
	var dir := OS.get_environment("MOM_SHOT_DIR")
	if dir.is_empty():
		dir = "/tmp/mp_shots"
	DirAccess.make_dir_recursive_absolute(dir)
	var scene: PackedScene = load("res://control.tscn")
	control = scene.instantiate()
	root.add_child(control)
	driver = MPDriver.new(control, dir)
	root.add_child(driver)


class MPDriver:
	extends Node

	var control: Control
	var shot_dir: String
	var prefix: String
	var view: Control = null
	var state := "connect"
	var state_t := 0.0
	var total_t := 0.0
	var shot_idx := 0
	var username := ""
	var charname := ""
	var want_class := ""
	var role := ""
	var _did := {}
	var _busy := false
	var _walk_entity_id := 0
	var _walk_target := Vector3.ZERO
	var _walk_next_state := ""
	var _walk_deadline := 0.0
	var _walk_stop_dist := 4.0
	var _shot_timer := 0.0
	var _equipped := false

	func _init(c: Control, dir: String):
		control = c
		shot_dir = dir
		prefix = OS.get_environment("MOM_SHOT_PREFIX")
		if prefix.is_empty():
			prefix = "C"
		var nm := OS.get_environment("MOM_MP_NAME")
		if nm.is_empty():
			nm = "Player"
		# Unique, valid (4-11 alpha) character + account names per process.
		var salt := "abcdefghijklmnopqrstuvwxyz"
		var tag := ""
		for i in range(3):
			tag += salt[randi() % salt.length()]
		charname = (nm + tag).substr(0, 11)
		username = "Mp" + nm + tag + str(Time.get_unix_time_from_system() as int % 10000)
		want_class = OS.get_environment("MOM_MP_CLASS")
		if want_class.is_empty():
			want_class = "Warrior"
		role = OS.get_environment("MOM_MP_ROLE")
		if role.is_empty():
			role = "observer"
		print("[MP:%s] name=%s class=%s role=%s" % [prefix, charname, want_class, role])

	func _shot(tag: String) -> void:
		shot_idx += 1
		var path := "%s/%s_%02d_%s.png" % [shot_dir, prefix, shot_idx, tag]
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		img.save_png(path)
		print("[MP:%s] shot -> %s   visible_players=%s" % [prefix, path, _player_names()])

	func _key(code: Key, pressed: bool) -> void:
		var ev := InputEventKey.new()
		ev.keycode = code
		ev.physical_keycode = code
		ev.pressed = pressed
		Input.parse_input_event(ev)

	func _goto(s: String) -> void:
		print("[MP:%s] state %s -> %s (t=%.1f)" % [prefix, state, s, total_t])
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
			view.camera.far = 600.0
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

	func _other_players() -> Array:
		var out: Array = []
		if view == null:
			return out
		for e in view.replicated_entities:
			if e is Dictionary and bool(e.get("is_player", false)) and not bool(e.get("is_self", false)):
				out.append(e)
		return out

	func _player_names() -> String:
		var bits: Array = []
		for e in _other_players():
			var mounts: Dictionary = e.get("mounts", {}) if e.get("mounts") else {}
			bits.append("%s(d=%.0f,mounts=%d)" % [str(e.get("name", "?")), _server_dist_to(e), mounts.size()])
		return "[" + ", ".join(bits) + "]"

	func _entity_by_id(id: int) -> Dictionary:
		if view == null:
			return {}
		for e in view.replicated_entities:
			if e is Dictionary and int(e.get("id", 0)) == id:
				return e
		return {}

	func _nearest_other_player() -> Dictionary:
		var best: Dictionary = {}
		var best_d := 1e9
		for e in _other_players():
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

	func _begin_walk_to_entity(e: Dictionary, next_state: String, stop_dist := 4.0, deadline := 30.0) -> void:
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
		if d <= _walk_stop_dist or total_t > _walk_deadline:
			_key(KEY_W, false)
			print("[MP:%s] walk done: d=%.2f" % [prefix, d])
			_goto(_walk_next_state)

	func _request(cmd: String, args := {}) -> void:
		view._request_server_command(cmd, args)

	func _process(delta: float) -> void:
		if _busy:
			return
		state_t += delta
		total_t += delta
		if total_t > 300.0 and state != "done":
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
					control._on_login_button_pressed()
					_goto("logging_in")
				elif state_t > 20.0 and _once("login2"):
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
					if _once("create_char") or (_status().begins_with("Create character failed") and state_t > 6.0 and _once("retry_char")):
						control.get_node("VBoxContainer/CharacterNameField").text = charname
						for ci in range(control.class_option.item_count):
							if control.class_option.get_item_text(ci).nocasecmp_to(want_class) == 0:
								control.class_option.select(ci)
								break
						control._on_create_character_button_pressed()
						state_t = 0.0
				elif _once("enter_world"):
					_busy = true
					await _shot("char_select")
					control.character_list.select(0)
					control._on_enter_world_button_pressed()
					_goto("entering_world")
					_busy = false
			"entering_world":
				view = control.gameplay_view
				if view != null and view.visible and view._has_spawned:
					_speed_tweaks()
					_goto("spawned")
			"spawned":
				if state_t > 3.0 and _once("spawn"):
					_busy = true
					_speed_tweaks()
					# The login flow leaves a LineEdit focused; gameplay_view's
					# _typing_in_ui() then suppresses WASD. Release focus so the
					# synthetic movement keys actually drive the character.
					get_viewport().gui_release_focus()
					await _shot("spawned")
					_goto(role)
					_busy = false
			# ---- roles ----
			"equip":
				_role_equip(delta)
			"equip_combat":
				_role_equip_combat(delta)
			"summoner":
				_role_summoner(delta)
			"observer":
				_role_observer(delta)
			"finish":
				if _once("finish"):
					_busy = true
					await _shot("final")
					print("[MP:%s] COMPLETE — %d shots in %s" % [prefix, shot_idx, shot_dir])
					get_tree().quit()
					_busy = false
			"done":
				pass

	# ---------------------------------------------------------------
	func _closeup_camera(on: bool) -> void:
		# Orbit the third-person camera to the FRONT of our own avatar and zoom
		# in, so equipped weapon/shield/helm are clearly visible (same technique
		# as the single-client autotest closeup).
		var cam_yaw: Node3D = view.player_body.get_node_or_null("CameraYaw")
		if on:
			if cam_yaw:
				cam_yaw.rotation.y = PI
			if view.camera_pitch:
				view.camera_pitch.rotation.x = 0.18
			view._camera_base_local_offset = Vector3(0, 0.6, 3.2)
			view._camera_zoom = 3.2
		else:
			if cam_yaw:
				cam_yaw.rotation.y = 0.0
		view._apply_camera_zoom()

	func _role_equip(delta: float) -> void:
		# Walk a few units out from the shared spawn so the observer has a clean
		# line of sight, equip a full set (observer watches the gear appear),
		# turn back to face the observer, then optionally fight the skeleton.
		if _once("walk_out"):
			view.player_body.rotation.y = 0.0   # face +Z (north), walk away from spawn
			_key(KEY_W, true)
		if state_t > 0.7 and _once("stop_out"):
			_key(KEY_W, false)   # ~5-6 units of separation
		if state_t > 3.0 and not _equipped and _once("equip"):
			_busy = true
			await _shot("before_equip")
			_request("cheat", {"action": "set_level", "params": {"level": 14}})
			await get_tree().create_timer(1.0).timeout
			for item in ["Tower Shield", "Plain Helm", "Longsword"]:
				_request("cheat", {"action": "give_item", "params": {"name": item, "equip": true}})
				await get_tree().create_timer(1.0).timeout
			_request("cheat", {"action": "full_heal", "params": {}})
			await get_tree().create_timer(2.0).timeout
			_equipped = true
			view.player_body.rotation.y = PI   # turn back to face the observer at spawn
			await get_tree().create_timer(1.0).timeout
			await _shot("equipped_facing")
			_busy = false
		# Stand and let the observer photograph us; optional combat tail.
		if _equipped:
			_shot_timer += delta
			if _shot_timer > 6.0:
				_shot_timer = 0.0
				_busy = true
				view.player_body.rotation.y = PI
				await _shot("equipped_stand")
				_busy = false
			if OS.get_environment("MOM_MP_COMBAT") == "1" and total_t > 40.0 and _once("to_combat"):
				_goto("equip_combat")
			elif total_t > 78.0:
				_goto("finish")

	func _role_equip_combat(delta: float) -> void:
		# Fight the nearby test skeleton so observers see two players + combat.
		if _once("attack"):
			var mob := _nearest_enemy()
			if not mob.is_empty():
				_face_towards(_entity_godot_pos(mob))
				_request("target_entity", {"entity_id": int(mob.get("id", 0))})
				_request("attack_toggle")
				print("[MP:%s] attacking '%s'" % [prefix, mob.get("name", "?")])
		var mob := _nearest_enemy()
		if not mob.is_empty():
			_face_towards(_entity_godot_pos(mob))
		_shot_timer += delta
		if _shot_timer > 5.0:
			_shot_timer = 0.0
			_busy = true
			await _shot("combat")
			_busy = false
		if total_t > 75.0:
			_goto("finish")

	func _nearest_enemy() -> Dictionary:
		var best: Dictionary = {}
		var best_d := 1e9
		if view == null:
			return best
		for e in view.replicated_entities:
			if not (e is Dictionary) or bool(e.get("is_self", false)):
				continue
			if not bool(e.get("is_enemy", false)):
				continue
			if bool(e.get("dead", false)) or float(e.get("health", 1.0)) <= 0.0:
				continue
			var d := _server_dist_to(e)
			if d < best_d:
				best_d = d
				best = e
		return best

	func _role_summoner(delta: float) -> void:
		# Learn the class spell list, cast the first summon, watch the pet follow.
		if _once("learn"):
			_busy = true
			_request("cheat", {"action": "set_level", "params": {"level": 12}})
			await get_tree().create_timer(1.0).timeout
			_request("cheat", {"action": "learn_class_spells", "params": {}})
			await get_tree().create_timer(1.5).timeout
			_request("get_spellbook")
			await get_tree().create_timer(1.0).timeout
			# Cast first spell on the hotbar (summons for Tempest/Necromancer).
			var slot := -1
			for i in range(10):
				var a = view.hotbar._assignments[i]
				if a is Dictionary and str(a.get("action", "")) == "spell":
					slot = i
					break
			if slot >= 0:
				view.player_body.rotate_y(PI)
				view.hotbar.activate(slot)
			await get_tree().create_timer(1.0).timeout
			await _shot("summon_cast")
			_busy = false
		if state_t > 14.0 and _once("after_summon"):
			_busy = true
			await _shot("summoned")
			# Walk forward so we can see the pet heel behind us.
			_key(KEY_W, true)
			await get_tree().create_timer(3.0).timeout
			_key(KEY_W, false)
			await get_tree().create_timer(1.0).timeout
			await _shot("pet_follow")
			_busy = false
			_goto("observer")  # then also observe other players

	func _role_observer(delta: float) -> void:
		# Stay put (the equip client walks out to a viewing distance); keep facing
		# the other player and screenshot on a timer, capturing their live
		# movement + the weapon/shield/helm appearing on them.
		if _once("frame"):
			view._camera_zoom = 2.8
			view._apply_camera_zoom()
		var other := _nearest_other_player()
		if not other.is_empty():
			_face_towards(_entity_godot_pos(other))
		_shot_timer += delta
		if _shot_timer > 4.0 and state_t > 1.0:
			_shot_timer = 0.0
			_busy = true
			await _shot("observe")
			_busy = false
		if total_t > 85.0:
			_goto("finish")
