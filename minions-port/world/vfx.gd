class_name VFX
extends RefCounted
## Spawns the port's stand-ins for the original engine's spell/skill visuals:
## particle emitters (fire/smoke/sparkle presets picked from the legacy emitter
## datablock name), explosions, the zodiac casting ring, and 3D positional
## sounds. Textures come from the original game art copied to assets/vfx/
## (jpg + .alpha.jpg mask pairs) and sounds from assets/sound/.

const PARTICLE_DIR := "res://assets/vfx/particles/"
const ZODIAC_TEX := "res://assets/vfx/zodiacs/zode_symbols.png"
const SOUND_DIR := "res://assets/sound/"
# Optional editor-authored override prefabs. Drop a .tscn here to replace the
# code preset for an effect with a scene you can edit visually (GPUParticles3D,
# ShaderMaterial, sub-emitters, ...). See assets/vfx/emitters/README.md.
const EMITTER_SCENE_DIR := "res://assets/vfx/emitters/"

static var _tex_cache: Dictionary = {}
static var _sound_index: Dictionary = {}  # lowercase rel path -> real res path
static var _sound_indexed := false

# ---------------------------------------------------------------- textures --
static func particle_texture(name: String) -> Texture2D:
	if name.is_empty():
		return null
	var key := name.to_lower()
	if _tex_cache.has(key):
		return _tex_cache[key]
	var base := PARTICLE_DIR + key
	var tex: Texture2D = null
	# UIC.load_image works in exported builds (loads the packed/imported resource);
	# the old Image.load_from_file(globalize_path(...)) only worked in the editor,
	# which is why particles showed up as grey untextured squares in the .exe.
	var img := UIC.load_image(base + ".jpg")
	if img != null:
		var alpha_path := base + ".alpha.jpg"
		img.convert(Image.FORMAT_RGBA8)
		var aimg := UIC.load_image(alpha_path)
		if aimg != null:
			aimg.convert(Image.FORMAT_RGBA8)
			if aimg.get_size() != img.get_size():
				aimg.resize(img.get_width(), img.get_height())
			for y in range(img.get_height()):
				for x in range(img.get_width()):
					var px := img.get_pixel(x, y)
					px.a = aimg.get_pixel(x, y).r
					img.set_pixel(x, y, px)
		else:
			# No explicit mask: use luminance so black backgrounds vanish
			# (legacy additive-blend particle art).
			for y in range(img.get_height()):
				for x in range(img.get_width()):
					var px := img.get_pixel(x, y)
					px.a = maxf(px.r, maxf(px.g, px.b))
					img.set_pixel(x, y, px)
		tex = ImageTexture.create_from_image(img)
	_tex_cache[key] = tex
	return tex

# ---------------------------------------------------------------- emitters --
static func _emitter_override_path(emitter_name: String) -> String:
	# An editor-authored prefab that replaces the code preset for this effect.
	# Tried most- to least-specific so one "casting.tscn" can cover every
	# *Casting* emitter while "castingemitter.tscn" can target just one:
	#   assets/vfx/emitters/<emittername>.tscn   (exact, e.g. castingemitter.tscn)
	#   assets/vfx/emitters/<keyword>.tscn        (casting / begin / smoke / fire)
	if emitter_name.is_empty():
		return ""
	var lname := emitter_name.to_lower()
	var exact := EMITTER_SCENE_DIR + lname + ".tscn"
	if ResourceLoader.exists(exact):
		return exact
	for kw in ["casting", "begin", "smoke", "fire"]:
		if kw in lname and ResourceLoader.exists(EMITTER_SCENE_DIR + kw + ".tscn"):
			return EMITTER_SCENE_DIR + kw + ".tscn"
	return ""

static func emitter(parent: Node3D, offset: Vector3, emitter_name: String,
		texture_name: String, duration: float) -> Node3D:
	# If you've authored an override prefab for this effect, use it verbatim so
	# you can iterate in the editor (and add shaders) without touching this file.
	# A prefab may optionally implement `configure(texture_name, duration)` to
	# react to the server-chosen texture/lifetime.
	var override_path := _emitter_override_path(emitter_name)
	if not override_path.is_empty():
		var scene = load(override_path)
		if scene != null:
			var inst: Node3D = scene.instantiate()
			inst.position = offset
			if inst.has_method("configure"):
				inst.call("configure", texture_name, duration)
			parent.add_child(inst)
			var ttl0 := maxf(duration, 0.1)
			if ttl0 < 1800.0:
				ttl0 = minf(ttl0, 30.0)
			_free_later(inst, ttl0 + 1.0)
			return inst

	# Preset from the legacy emitter datablock name: ChimneyFire/DragonFire ->
	# rising fire; *Smoke* -> slow gray billows; Casting -> tight inward swirl;
	# SpellBegin -> burst on the target; anything else -> gentle sparkle.
	var p := CPUParticles3D.new()
	var lname := emitter_name.to_lower()
	p.position = offset
	p.amount = 24
	p.lifetime = 0.9
	p.spread = 25.0
	p.gravity = Vector3.ZERO
	p.initial_velocity_min = 0.6
	p.initial_velocity_max = 1.4
	p.scale_amount_min = 0.18
	p.scale_amount_max = 0.38
	p.direction = Vector3(0, 1, 0)
	var color := Color(1.0, 0.85, 0.5)
	if "fire" in lname:
		p.amount = 36
		color = Color(1.0, 0.55, 0.15)
		p.initial_velocity_min = 1.2
		p.initial_velocity_max = 2.2
		p.scale_amount_min = 0.25
		p.scale_amount_max = 0.5
	elif "smoke" in lname:
		p.amount = 14
		color = Color(0.45, 0.45, 0.48, 0.5)
		p.initial_velocity_min = 0.4
		p.initial_velocity_max = 0.9
		p.lifetime = 1.6
		p.scale_amount_min = 0.35
		p.scale_amount_max = 0.7
	elif "casting" in lname:
		p.amount = 30
		color = Color(0.55, 0.7, 1.0)
		p.emission_shape = CPUParticles3D.EMISSION_SHAPE_SPHERE
		p.emission_sphere_radius = 0.7
		p.initial_velocity_min = 0.2
		p.initial_velocity_max = 0.5
		p.direction = Vector3(0, 1, 0)
	elif "begin" in lname:
		p.amount = 40
		p.explosiveness = 0.9
		p.spread = 180.0
		p.initial_velocity_min = 1.5
		p.initial_velocity_max = 3.0
		color = Color(1.0, 0.8, 0.35)
	p.color = color
	var mat := StandardMaterial3D.new()
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	mat.vertex_color_use_as_albedo = true
	var tex := particle_texture(texture_name)
	if tex != null:
		mat.albedo_texture = tex
	var quad := QuadMesh.new()
	quad.size = Vector2(0.5, 0.5)
	quad.material = mat
	p.mesh = quad
	p.emitting = true
	parent.add_child(p)
	# Defensive ceiling: server events are seconds, but a malformed duration
	# must never leave a permanent emitter behind. Persistent equipped-weapon
	# effects (duration >= 1800) are exempt — they're cleared on re-equip.
	var ttl := maxf(duration, 0.1)
	if ttl < 1800.0:
		ttl = minf(ttl, 30.0)
	_free_later(p, ttl + p.lifetime)
	return p

static func stop_emitters(parent: Node3D, tag: String) -> void:
	# Stop (fade out, then free) every tagged effect under *parent* —
	# CPUParticles3D emitters and ring meshes alike.
	for c in parent.get_children():
		if not (c is Node3D) or str(c.get_meta("vfx_tag", "")) != tag:
			continue
		if c is CPUParticles3D:
			c.emitting = false
			_free_later(c, c.lifetime)
		else:
			c.queue_free()

static func tag_emitter(node: Node3D, tag: String) -> void:
	if node != null:
		node.set_meta("vfx_tag", tag)

static func explosion(parent: Node3D, offset: Vector3, name: String) -> void:
	var lname := name.to_lower()
	var color := Color(1.0, 0.6, 0.2)
	if "water" in lname:
		color = Color(0.4, 0.65, 1.0)
	elif "ground" in lname or "dirt" in lname:
		color = Color(0.75, 0.6, 0.4)
	var p := CPUParticles3D.new()
	p.position = offset
	p.one_shot = true
	p.explosiveness = 1.0
	p.amount = 52 if "major" in lname or "big" in lname else 28
	p.lifetime = 0.7
	p.spread = 180.0
	p.gravity = Vector3(0, -3.0, 0)
	p.initial_velocity_min = 2.0
	p.initial_velocity_max = 4.5
	p.scale_amount_min = 0.2
	p.scale_amount_max = 0.45
	p.color = color
	var mat := StandardMaterial3D.new()
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	mat.vertex_color_use_as_albedo = true
	var tex := particle_texture("burst")
	if tex != null:
		mat.albedo_texture = tex
	var quad := QuadMesh.new()
	quad.size = Vector2(0.5, 0.5)
	quad.material = mat
	p.mesh = quad
	p.emitting = true
	parent.add_child(p)
	# Quick light flash to sell the hit.
	var light := OmniLight3D.new()
	light.position = offset
	light.light_color = color
	light.light_energy = 3.0
	light.omni_range = 5.0
	parent.add_child(light)
	var tween := light.create_tween()
	tween.tween_property(light, "light_energy", 0.0, 0.35)
	tween.tween_callback(light.queue_free)
	_free_later(p, 1.2)

static func casting_ring(parent: Node3D, duration: float) -> Node3D:
	# The iconic MoM zodiac circle under a casting character.
	var mi := MeshInstance3D.new()
	var quad := QuadMesh.new()
	quad.size = Vector2(2.4, 2.4)
	var mat := StandardMaterial3D.new()
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = Color(0.8, 0.85, 1.0, 0.85)
	var zimg := UIC.load_image(ZODIAC_TEX)
	if zimg != null:
		mat.albedo_texture = ImageTexture.create_from_image(zimg)
	quad.material = mat
	mi.mesh = quad
	mi.rotation_degrees.x = -90.0
	mi.position = Vector3(0, 0.08, 0)
	parent.add_child(mi)
	var spin := mi.create_tween().set_loops()
	spin.tween_property(mi, "rotation_degrees:z", 360.0, 4.0).as_relative()
	_free_later(mi, maxf(duration, 0.4))
	return mi

# ------------------------------------------------------------------- sound --
static func _index_sounds() -> void:
	if _sound_indexed:
		return
	_sound_indexed = true
	_index_sound_dir("sfx")
	_index_sound_dir("character")
	_index_sound_dir("vocalsets")
	_index_sound_dir("environment")
	if _sound_index.is_empty():
		# Exported builds can't DirAccess imported .ogg; use the committed manifest
		# (see GameAudio.SOUND_MANIFEST) so combat/spell/vocal sounds still resolve.
		var path := SOUND_DIR + "sound_manifest.json"
		if FileAccess.file_exists(path):
			var data = JSON.parse_string(FileAccess.get_file_as_string(path))
			if data is Array:
				for rel in data:
					_sound_index[String(rel).to_lower().replace("\\", "/")] = SOUND_DIR + String(rel)

static func _index_sound_dir(rel: String) -> void:
	var dir := DirAccess.open(SOUND_DIR + rel)
	if dir == null:
		return
	dir.list_dir_begin()
	var f := dir.get_next()
	while f != "":
		if dir.current_is_dir():
			if not f.begins_with("."):
				_index_sound_dir(rel + "/" + f)
		elif f.to_lower().ends_with(".ogg"):
			_sound_index[(rel + "/" + f).to_lower()] = SOUND_DIR + rel + "/" + f
		f = dir.get_next()
	dir.list_dir_end()

static func resolve_sound(sound: String) -> String:
	# Server paths arrive lowercased ("sfx/pencil_writeonpaper2.ogg"); the art
	# on disk keeps original casing, so look up case-insensitively.
	_index_sounds()
	return _sound_index.get(sound.to_lower().replace("\\", "/"), "")

static func sound3d(parent: Node3D, pos: Vector3, sound: String, big: bool = false) -> void:
	var path := resolve_sound(sound)
	if path.is_empty():
		return
	var stream: AudioStream = UIC.load_audio(path)
	if stream == null:
		return
	var player := AudioStreamPlayer3D.new()
	player.stream = stream
	player.position = pos
	player.unit_size = 22.0 if big else 11.0
	player.max_distance = 80.0 if big else 45.0
	if AudioServer.get_bus_index("SFX") != -1:
		player.bus = "SFX"
	parent.add_child(player)
	player.play()
	player.finished.connect(player.queue_free)

static func sound_ui(parent: Node, sound: String) -> void:
	var path := resolve_sound(sound)
	if path.is_empty():
		return
	var stream: AudioStream = UIC.load_audio(path)
	if stream == null:
		return
	var player := AudioStreamPlayer.new()
	player.stream = stream
	if AudioServer.get_bus_index("SFX") != -1:
		player.bus = "SFX"
	parent.add_child(player)
	player.play()
	player.finished.connect(player.queue_free)

# ------------------------------------------------------------------- utils --
static func _free_later(node: Node, seconds: float) -> void:
	var timer := node.get_tree().create_timer(seconds) if node.is_inside_tree() else null
	if timer == null:
		# Not in tree yet (same frame): defer once.
		node.ready.connect(func():
			node.get_tree().create_timer(seconds).timeout.connect(func():
				if is_instance_valid(node):
					node.queue_free()))
		return
	timer.timeout.connect(func():
		if is_instance_valid(node):
			node.queue_free())
