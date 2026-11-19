extends Node

# 검수 사본에만 들어가는 제어 파일이다. 배포 PCK에는 포함하지 않는다.
var command_path: String
var last_command: String = ""
var timer: float = 0.0

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
	match command:
		"finale":
			main.achievements.completion_time = 4517.0
			main.show_finale()
		"achievements":
			main.achievements_ui.open()
		"debug":
			main.debug_hud = true
			main.hud_label.visible = true
		"save":
			main.save_run()
		"closed":
			main.set_library_open(false)
		"open":
			main.set_library_open(true)
	print("KOREAN_QA_SCENARIO=" + command)
