extends Node

# 이 파일은 저장과 Steam을 격리한 검수 사본에만 들어갑니다.
var elapsed: float = 0.0
var request_path: String = ""
var report_path: String = ""

func _ready():
	request_path = ProjectSettings.globalize_path("user://qa_request.json")
	report_path = ProjectSettings.globalize_path("user://qa_state.json")
	print("HEW QA user directory: ", OS.get_user_data_dir())
	process_mode = Node.PROCESS_MODE_ALWAYS

func _process(delta):
	elapsed += delta
	if elapsed < 1.0:
		return
	elapsed = 0.0
	if not FileAccess.file_exists(request_path):
		return
	var request = JSON.parse_string(FileAccess.get_file_as_string(request_path))
	DirAccess.remove_absolute(request_path)
	if request.get("action", "dump") == "call":
		var target = get_node_or_null(request.node)
		if is_instance_valid(target) and target.has_method(request.method):
			target.callv(request.method, request.get("args", []))
		else:
			push_error("QA requested method is unavailable: " + str(request))
	if request.get("action", "dump") == "hover":
		# 운영체제의 포인터를 이동하지 않고 이 검수 창에만 입력을 전달합니다.
		var motion = InputEventMouseMotion.new()
		motion.position = Vector2(request.position[0], request.position[1])
		motion.global_position = motion.position
		get_viewport().push_input(motion)
		await get_tree().create_timer(1.2).timeout
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	if request.has("capture"):
		var capture_path = ProjectSettings.globalize_path("user://" + request.capture + ".png")
		var bitmap = get_viewport().get_texture().get_image()
		bitmap.save_png(capture_path)
	var rows: Array = []
	walk(get_tree().root, rows)
	var report = {"nodes":rows,"locale":TranslationServer.get_locale(),"user_dir":OS.get_user_data_dir(),"loaded_locales":TranslationServer.get_loaded_locales(),"request":request}
	if is_instance_valid(Globals.progress) and is_instance_valid(Player.capital_area):
		report.progress = Globals.progress.save_state()
		report.systems = Globals.systems.save_state()
		report.money = Player.values.money.value
		report.military = Player.values.military.value
		report.capital_commands = Player.capital_area.commands.save_state()
	FileAccess.open(report_path, FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))

func walk(node: Node, rows: Array):
	var row = {"path":str(node.get_path()),"class":node.get_class(),"script":node.get_script().resource_path if node.get_script() != null else ""}
	if node is UIDefaultCommand and is_instance_valid(node.command):
		row.command_id = node.command.command_id
	if node is Control:
		row.visible = node.is_visible_in_tree()
		row.rect = [node.global_position.x,node.global_position.y,node.size.x,node.size.y]
		row.tooltip = node.tooltip_text
		row.tooltip_color = node.get_theme_color("font_color", "TooltipLabel").to_html()
		if node is Label or node is RichTextLabel or node is Button or node is LineEdit:
			row.text = node.text
			row.display_text = node.tr(node.text)
		if node is Label:
			row.line_count = node.get_line_count()
			row.visible_line_count = node.get_visible_line_count()
			row.clip_text = node.clip_text
			row.auto_translate = node.auto_translate_mode
			row.font_size = node.get_theme_font_size("font_size")
			row.autowrap_mode = node.autowrap_mode
			var active_font = node.get_theme_font("font")
			row.text_width = active_font.get_string_size(row.display_text, HORIZONTAL_ALIGNMENT_LEFT, -1, row.font_size).x
			var absent: Array = []
			for c in row.display_text:
				if c.unicode_at(0) >= 32 and not active_font.has_char(c.unicode_at(0)) and c not in absent:
					absent.append(c)
			row.missing_glyphs = absent
	if not (node is CanvasItem) or node.visible:
		rows.append(row)
	for child in node.get_children():
		walk(child, rows)
