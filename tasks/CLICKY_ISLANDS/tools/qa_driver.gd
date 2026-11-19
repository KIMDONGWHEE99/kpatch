extends Node

# 이 파일은 저장과 Steam을 분리한 검수 사본에만 들어갑니다. 배포본에는 넣지 않습니다.
# 요청 파일(user://qa_request.json)을 읽어 화면을 옮기고, 게임 화면을 PNG로 직접 저장합니다.
# 운영체제의 마우스·키보드는 건드리지 않습니다. HOW_EMPIRES_WORK의 qa_driver.gd를 이 게임에 맞게 고쳤습니다.
var elapsed: float = 0.0
var request_path: String = ""
var report_path: String = ""
var video_layer: CanvasLayer = null

func _ready():
	request_path = ProjectSettings.globalize_path("user://qa_request.json")
	report_path = ProjectSettings.globalize_path("user://qa_state.json")
	print("KOREAN QA user directory: ", OS.get_user_data_dir())
	print("KOREAN QA executable: ", OS.get_executable_path())
	process_mode = Node.PROCESS_MODE_ALWAYS

func _process(delta):
	elapsed += delta
	if elapsed < 0.5:
		return
	elapsed = 0.0
	if not FileAccess.file_exists(request_path):
		return
	var request = JSON.parse_string(FileAccess.get_file_as_string(request_path))
	DirAccess.remove_absolute(request_path)
	var action = request.get("action", "dump")
	var note = ""
	if action == "call":
		var target = get_node_or_null(request.node)
		if is_instance_valid(target) and target.has_method(request.method):
			target.callv(request.method, request.get("args", []))
		else:
			note = "method unavailable"
	elif action == "press":
		var button = get_node_or_null(request.node)
		if is_instance_valid(button) and button is BaseButton:
			button.pressed.emit()
		else:
			note = "button unavailable"
	elif action == "set":
		var owner_node = get_node_or_null(request.node)
		if is_instance_valid(owner_node):
			owner_node.set(request.property, request.value)
		else:
			note = "node unavailable"
	elif action == "locale":
		GameSettings.set_setting("misc", "locale", request.locale)
	elif action == "click" or action == "hover":
		# 이 창의 뷰포트에만 입력 이벤트를 넣습니다(운영체제 포인터는 움직이지 않음).
		var where = Vector2(request.position[0], request.position[1])
		var motion = InputEventMouseMotion.new()
		motion.position = where
		motion.global_position = where
		get_viewport().push_input(motion)
		if action == "click":
			for pressed in [true, false]:
				var click = InputEventMouseButton.new()
				click.button_index = int(request.get("button", 1))
				click.pressed = pressed
				click.position = where
				click.global_position = where
				get_viewport().push_input(click)
				await get_tree().process_frame
	elif action == "video":
		# 영상 속 글자를 판독하려고 여러 영상을 격자로 한꺼번에 재생합니다(소리 없음).
		if is_instance_valid(video_layer):
			video_layer.queue_free()
		video_layer = CanvasLayer.new()
		video_layer.layer = 120
		var back = ColorRect.new()
		back.color = Color(0.2, 0.2, 0.25)
		back.set_anchors_preset(Control.PRESET_FULL_RECT)
		video_layer.add_child(back)
		var grid = GridContainer.new()
		grid.columns = int(request.get("columns", 4))
		video_layer.add_child(grid)
		add_child(video_layer)
		var sizes = []
		for path in request.paths:
			var player = VideoStreamPlayer.new()
			player.stream = load(path)
			player.expand = true
			player.custom_minimum_size = Vector2(request.cell[0], request.cell[1])
			player.volume_db = -80.0
			player.loop = true
			grid.add_child(player)
			player.play()
			sizes.append([path.get_file(), player.get_video_texture().get_width(), player.get_video_texture().get_height(), player.get_stream_length()])
		note = JSON.stringify(sizes)
	elif action == "video_clear":
		if is_instance_valid(video_layer):
			video_layer.queue_free()
	elif action == "quit":
		get_tree().quit()
		return
	await get_tree().create_timer(float(request.get("wait", 0.8))).timeout
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var capture_ok = null
	if request.has("capture"):
		var capture_path = ProjectSettings.globalize_path("user://" + request.capture + ".png")
		var bitmap = get_viewport().get_texture().get_image()
		capture_ok = bitmap.save_png(capture_path) == OK
	var rows: Array = []
	walk(get_tree().root, rows, request.get("all", false))
	var fonts = {}
	for name in ["main_font", "main_bold_font", "main_heading_font", "black_font", "pixel_font"]:
		var font = FontLocaleResolver.get(name)
		var chain = []
		for fallback in font.fallbacks:
			chain.append(fallback.resource_path)
		fonts[name] = {"path": font.resource_path, "fallbacks": chain}
	var scene = get_tree().current_scene
	var report = {"request": request, "note": note, "capture_ok": capture_ok, "nodes": rows,
		"locale": TranslationServer.get_locale(), "loaded_locales": TranslationServer.get_loaded_locales(),
		"os_locale": OS.get_locale(), "user_dir": OS.get_user_data_dir(), "executable": OS.get_executable_path(),
		"current_scene": scene.scene_file_path if scene != null else "", "window_size": [get_window().size.x, get_window().size.y],
		"rendering_device": RenderingServer.get_video_adapter_name(), "rendering_method": RenderingServer.get_current_rendering_method(),
		"steam_initialized": GodotSteam.steam_initialized, "fonts": fonts, "engine": Engine.get_version_info().string}
	FileAccess.open(report_path, FileAccess.WRITE).store_string(JSON.stringify(report))

func chain_has(font: Font, code: int, depth: int = 0) -> bool:
	if font == null or depth > 6:
		return false
	if font.has_char(code):
		return true
	for fallback in font.fallbacks:
		if chain_has(fallback, code, depth + 1):
			return true
	return false

func walk(node: Node, rows: Array, everything: bool):
	if node is CanvasItem and not node.visible:
		return
	if node is Control and node.is_visible_in_tree():
		var shown = ""
		var raw = ""
		var font: Font = null
		if node is Label or node is Button or node is LineEdit:
			raw = node.text
			shown = node.atr(raw) if node.auto_translate_mode != Node.AUTO_TRANSLATE_MODE_DISABLED else raw
			font = node.get_theme_font("font")
		elif node is RichTextLabel:
			raw = node.text
			shown = node.get_parsed_text()
			font = node.get_theme_font("normal_font")
		if shown != "" or node.tooltip_text != "" or everything:
			var row = {"path": str(node.get_path()), "class": node.get_class(), "raw": raw, "shown": shown,
				"rect": [node.global_position.x, node.global_position.y, node.size.x, node.size.y]}
			if node.tooltip_text != "":
				row.tooltip = node.atr(node.tooltip_text)
			if font != null:
				row.font = font.resource_path
				var absent: Array = []
				for c in shown:
					var code = c.unicode_at(0)
					if code > 32 and not chain_has(font, code) and c not in absent:
						absent.append(c)
				row.missing_glyphs = absent
			if node is Label:
				row.clipped = node.get_visible_line_count() < node.get_line_count() or (node.clip_text and font != null and font.get_string_size(shown, HORIZONTAL_ALIGNMENT_LEFT, -1, node.get_theme_font_size("font_size")).x > node.size.x + 1)
			if node is BaseButton:
				row.disabled = node.disabled
			rows.append(row)
	for child in node.get_children():
		walk(child, rows, everything)
