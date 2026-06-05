extends CharacterBody3D
## First-person walk/run/jump controller for exploring a zone.
## WASD move, mouse look, Shift run, Space jump, Esc release mouse.

@export var walk_speed := 7.0
@export var run_mult := 2.0
@export var jump_velocity := 6.5
@export var gravity := 22.0
@export var mouse_sensitivity := 0.0024

## Headless demo: when true, moves forward automatically (no input needed).
var auto_forward := false

@onready var yaw: Node3D = $CameraYaw
@onready var pitch: Node3D = $CameraYaw/CameraPitch
@onready var camera: Camera3D = $CameraYaw/CameraPitch/Camera3D


func _ready() -> void:
	camera.current = true
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		yaw.rotate_y(-event.relative.x * mouse_sensitivity)
		pitch.rotation.x = clampf(pitch.rotation.x - event.relative.y * mouse_sensitivity, -1.4, 1.4)
	elif event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE if \
			Input.mouse_mode == Input.MOUSE_MODE_CAPTURED else Input.MOUSE_MODE_CAPTURED


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y -= gravity * delta
	elif Input.is_key_pressed(KEY_SPACE):
		velocity.y = jump_velocity

	var wish := Vector2.ZERO
	if Input.is_key_pressed(KEY_W) or auto_forward:
		wish.y += 1.0
	if Input.is_key_pressed(KEY_S):
		wish.y -= 1.0
	if Input.is_key_pressed(KEY_A):
		wish.x -= 1.0
	if Input.is_key_pressed(KEY_D):
		wish.x += 1.0

	var basis := yaw.global_transform.basis
	var dir := (-basis.z * wish.y) + (basis.x * wish.x)
	dir.y = 0.0
	if dir.length() > 0.001:
		dir = dir.normalized()
	var speed := walk_speed * (run_mult if Input.is_key_pressed(KEY_SHIFT) else 1.0)
	velocity.x = dir.x * speed
	velocity.z = dir.z * speed
	move_and_slide()
