extends Control

var socket = WebSocketPeer.new()

func _ready():
	socket.connect_to_url("ws://localhost:9000")

func _process(_delta):
	socket.poll()
	if socket.get_ready_state() == WebSocketPeer.STATE_OPEN:
		while socket.get_available_packet_count():
			var data = JSON.parse_string(socket.get_packet().get_string_from_utf8())
			handle_response(data)

func _on_login_button_pressed():
	var msg = {"type": "login", "username": "test", "password": "test"}
	socket.send_text(JSON.stringify(msg))

func handle_response(data):
	if data["type"] == "world_list":
		$VBoxContainer/Label.text = str(data["worlds"])
