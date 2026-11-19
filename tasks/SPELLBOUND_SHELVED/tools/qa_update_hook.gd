extends Node

# 검수 사본에서만 사용한다. 배포 후보에는 넣지 않는다.
var command_path: String
var last_command: String = ""
var timer: float = 0.0
const Settings = preload("res://scripts/game_settings.gd")

func _ready() -> void:
	command_path = OS.get_executable_path().get_base_dir().path_join("scenario.txt")
	print("KOREAN_QA_USER_DIR=" + OS.get_user_data_dir())
	print("KOREAN_QA_EXE=" + OS.get_executable_path())
	print("KOREAN_QA_STEAM=" + str(Engine.has_singleton("Steam")))

func _process(delta: float) -> void:
	timer += delta
	if timer < 0.5:
		return
	timer = 0.0
	if not FileAccess.file_exists(command_path):
		return
	var command = FileAccess.get_file_as_string(command_path).strip_edges()
	if command == "" or command == last_command:
		return
	var main = get_tree().root.get_node_or_null("Main")
	if main == null or main.achievements == null:
		return
	last_command = command
	match command.get_slice(":", 0):
		"finale":
			main.achievements.completion_time = 4517.0
			main.show_finale()
		"debug":
			main.debug_hud = true
			main.hud_label.visible = true
		"save":
			main.save_run()
		"inspect":
			print("KOREAN_QA_STATE=" + JSON.stringify({"more_stats": Settings.more_stats, "hide_gnome_chat": Settings.hide_gnome_chat, "floor_text": main._floor_label.text, "hover_text": main.hover_label.text, "credits": main.credits, "menu": main.menu_mode, "playlog": "" if main.playlog == null else main.playlog.path}))
		"quiet_probe":
			var before: int = main._chat_box.get_child_count()
			main.chat_log("검수 노움", "잡담 숨김 시험", Color.WHITE, false, "gnome")
			print("KOREAN_QA_QUIET=" + JSON.stringify({"enabled": Settings.hide_gnome_chat, "added": main._chat_box.get_child_count() - before}))
	print("KOREAN_QA_SCENARIO=" + command)
