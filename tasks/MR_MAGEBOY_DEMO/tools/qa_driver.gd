extends Node

# 이 스크립트는 검수 사본에만 추가하며 배포본에는 넣지 않습니다.
var config: Dictionary
var previous_id = ""
var busy = false
var elapsed = 0.0
var events: Array = []

func _ready():
	process_mode = Node.PROCESS_MODE_ALWAYS
	config = JSON.parse_string(FileAccess.get_file_as_string("res://korean_qa_config.json"))
	var info = {"pid": OS.get_process_id(), "executable": OS.get_executable_path(), "user_data_dir": OS.get_user_data_dir(), "engine": Engine.get_version_info(), "adapter": RenderingServer.get_video_adapter_name(), "device": RenderingServer.get_video_adapter_vendor(), "qa_pack": FileAccess.get_sha256(OS.get_executable_path().get_base_dir().path_join("MR MAGEBOY DEMO.pck"))}
	FileAccess.open(config.info, FileAccess.WRITE).store_string(JSON.stringify(info, "\t"))
	print("KOREAN_QA_RUNTIME ", JSON.stringify(info))

func _process(delta):
	elapsed += delta
	if busy or elapsed < 0.25:
		return
	elapsed = 0.0
	if not FileAccess.file_exists(config.command):
		return
	var command = JSON.parse_string(FileAccess.get_file_as_string(config.command))
	if command == null or command.get("id", "") == previous_id:
		return
	previous_id = command.id
	busy = true
	await _execute(command)
	busy = false

func _all_nodes(node: Node, output: Array):
	output.append(node)
	for child in node.get_children():
		_all_nodes(child, output)

func _method_node(method: String):
	var nodes = []
	_all_nodes(get_tree().root, nodes)
	for node in nodes:
		if node != self and node.has_method(method):
			return node
	return null

func _all_internal_nodes(node: Node, output: Array, trail: String = "0"):
	output.append({"node": node, "trail": trail})
	var index = 0
	for child in node.get_children(true):
		_all_internal_nodes(child, output, trail + "/" + str(index))
		index += 1

func _is_window_visible(node) -> bool:
	if not is_instance_valid(node):
		return false
	if node is Control:
		return node.is_visible_in_tree()
	if node is Window:
		return node.visible
	return false

func _picker_properties(picker: ColorPicker) -> Array:
	var output = []
	var nodes = []
	_all_internal_nodes(picker, nodes)
	for item in nodes:
		var node = item.node
		var base = {"path": str(node.get_path()), "trail": item.trail, "class": node.get_class(), "visible": _is_window_visible(node)}
		var fields = []
		if node is Control:
			fields.append("tooltip_text")
		if node is Label or node is Button or node is LinkButton or node is LineEdit or node is TextEdit:
			fields.append("text")
		if node is LineEdit or node is TextEdit:
			fields.append("placeholder_text")
		if node is Window:
			fields.append("title")
		for field in fields:
			var value = str(node.get(field))
			if not value.is_empty():
				var row = base.duplicate()
				row["field"] = field
				row["value"] = value
				row["node_tr"] = str(node.tr(value))
				row["auto_translate_mode"] = node.auto_translate_mode if node is Control or node is Window else null
				output.append(row)
		if node is PopupMenu or node is OptionButton:
			for index in range(node.item_count):
				for field in ["text", "tooltip_text"]:
					var value = node.get_item_text(index) if field == "text" else node.get_item_tooltip(index)
					if field == "text" or not value.is_empty():
						var row = base.duplicate()
						row["field"] = "item_%d/%s" % [index, field]
						row["value"] = value
						row["node_tr"] = str(node.tr(value))
						row["item_id"] = node.get_item_id(index)
						output.append(row)
	return output

func _color_picker_probe() -> Dictionary:
	var nodes = []
	_all_nodes(get_tree().root, nodes)
	var game_picker = null
	for node in nodes:
		if node is ColorPickerButton and node.is_visible_in_tree():
			game_picker = node.get_picker()
			break
	if game_picker == null:
		return {"status": "FAIL", "reason": "표시 중인 색상 버튼을 찾지 못함"}
	# 검수 전용 자식은 게임의 번역 순회 대상 밖에 두어 같은 엔진의 원문을 수집합니다.
	var reference_button = ColorPickerButton.new()
	reference_button.name = "KoreanQANativeColorReference"
	add_child(reference_button)
	reference_button.hide()
	var reference_picker = reference_button.get_picker()
	var original_mode = game_picker.color_mode
	var original_color = game_picker.color
	var modes = []
	for mode in range(4):
		game_picker.color_mode = mode
		reference_picker.color_mode = mode
		await get_tree().process_frame
		await get_tree().process_frame
		modes.append({"mode": mode, "native": _picker_properties(reference_picker), "game": _picker_properties(game_picker)})
	game_picker.color_mode = original_mode
	await get_tree().process_frame
	await get_tree().process_frame
	var unchanged = game_picker.color == original_color
	reference_button.queue_free()
	return {"status": "PASS" if unchanged else "FAIL", "engine": Engine.get_version_info(), "game_path": str(game_picker.get_path()), "game_popup_visible": _is_window_visible(game_picker), "color_unchanged": unchanged, "modes": modes}

func _input_display_probe() -> Dictionary:
	var rows = []
	for code in [KEY_LEFT, KEY_UP, KEY_RIGHT, KEY_DOWN, KEY_W, KEY_A, KEY_S, KEY_D, KEY_SPACE, KEY_ESCAPE, KEY_ENTER, KEY_TAB]:
		for physical in [false, true]:
			for modifiers in [0, KEY_MASK_SHIFT, KEY_MASK_CTRL, KEY_MASK_ALT, KEY_MASK_META, KEY_MASK_CTRL | KEY_MASK_SHIFT]:
				var event = InputEventKey.new()
				if physical:
					event.physical_keycode = code
				else:
					event.keycode = code
				event.shift_pressed = bool(modifiers & KEY_MASK_SHIFT)
				event.ctrl_pressed = bool(modifiers & KEY_MASK_CTRL)
				event.alt_pressed = bool(modifiers & KEY_MASK_ALT)
				event.meta_pressed = bool(modifiers & KEY_MASK_META)
				var raw = InputEventHelper.get_text(event)
				rows.append({"kind": "key", "code": code, "physical": physical, "modifiers": modifiers, "os_keycode_text": OS.get_keycode_string(code), "event_text": event.as_text(), "helper_text": raw, "display_text": InputEventHelper.localize_display_text(raw)})
	for index in range(1, 10):
		var event = InputEventMouseButton.new()
		event.button_index = index
		var raw = InputEventHelper.get_text(event)
		rows.append({"kind": "mouse", "button": index, "event_text": event.as_text(), "helper_text": raw, "display_text": InputEventHelper.localize_display_text(raw), "device_text": InputEventHelper.get_device_specific_text(event)})
	return {"status": "PASS", "engine": Engine.get_version_info(), "display_server": DisplayServer.get_name(), "rows": rows}

func _default_dialog_probe() -> Dictionary:
	var reference = AcceptDialog.new()
	add_child(reference)
	var raw = reference.get_ok_button().text
	var row = {"default_ok_text": raw, "node_tr": str(reference.get_ok_button().tr(raw)), "auto_translate_mode": reference.get_ok_button().auto_translate_mode, "engine": Engine.get_version_info()}
	reference.queue_free()
	return row

func _execute(command: Dictionary):
	var operation = command.get("operation", "capture")
	var outcome = "PASS"
	var detail = {}
	var window_owner = null
	var window_field = ""
	var window_expected = true
	var window_target = null
	match operation:
		"capture":
			pass
		"tab":
			var nodes = []
			_all_nodes(get_tree().root, nodes)
			for node in nodes:
				if node is TabContainer and node.is_visible_in_tree():
					node.current_tab = command.get("index", 0)
		"skill":
			var tip = _method_node("_show_skill")
			var nodes = []
			_all_nodes(get_tree().root, nodes)
			var selected = null
			for node in nodes:
				if node is PrestigeSkill and int(node.prestige_id) == command.get("skill", -1):
					selected = node
			if tip and selected:
				# 검수 상태에서 설명창의 실제 배치를 확인할 능력을 선택합니다.
				selected.show()
				var container = selected.get_parent_control().get_parent_control()
				container.scale = Vector2.ONE
				container.position = Vector2(80, 65) - selected.position
				tip.set("hovered_skill", selected)
				tip.call("_show_skill", selected)
			else:
				outcome = "FAIL"
		"companion_detail", "stage_detail":
			var nodes = []
			_all_nodes(get_tree().root, nodes)
			var button = null
			var selector = null
			for node in nodes:
				if operation == "companion_detail" and node is Animal_Button and int(node.animal) == command.get("index", 0):
					button = node
				if operation == "stage_detail" and node is Stage_Button and int(node.stage_level) == command.get("index", 0):
					button = node
				if node.has_method("level_pressed") and node.is_visible_in_tree():
					selector = node
			if selector and button:
				selector.call("level_pressed", button)
			else:
				outcome = "FAIL"
		"main_options":
			var node = _method_node("_hide_credits_if_unset")
			if node:
				node.call("_on_options_button_pressed")
				window_owner = node
				window_field = "sub_menu"
			else:
				outcome = "FAIL"
		"main_credits":
			# 메인 메뉴의 원래 버튼 동작으로 제작진 창을 엽니다.
			var node = _method_node("_hide_credits_if_unset")
			if node:
				node.call("_on_credits_button_pressed")
				window_owner = node
				window_field = "sub_menu"
			else:
				outcome = "FAIL"
		"main_close_options":
			var node = _method_node("_hide_credits_if_unset")
			if node:
				node.call("_close_sub_menu")
				window_owner = node
				window_field = "sub_menu"
				window_expected = false
			else:
				outcome = "FAIL"
		"main_exit":
			var node = _method_node("_hide_credits_if_unset")
			if node:
				# 원래 종료 버튼은 첫 클릭에 확인 질문으로 바뀝니다.
				node.call("_on_exit_button_pressed")
				detail["main_exit"] = {"owner": str(node.get_path()), "confirmed_exit": node.get("confirmed_exit")}
			else:
				outcome = "FAIL"
		"main_exit_confirm":
			var node = _method_node("_hide_credits_if_unset")
			if node:
				node.call("_on_exit_confirmation_confirmed")
				return
			else:
				outcome = "FAIL"
		"new_game":
			var node = _method_node("new_game")
			if node:
				node.call("new_game")
			else:
				outcome = "FAIL"
		"continue_game":
			var node = _method_node("_on_continue_game_button_pressed")
			if node:
				node.call("_on_continue_game_button_pressed")
			else:
				outcome = "FAIL"
		"main_menu":
			get_tree().paused = false
			SceneLoader.load_scene(AppConfig.main_menu_scene_path)
		"close_menus":
			var node = _method_node("close_menus")
			if node:
				node.call("close_menus")
			var result_screen = _method_node("close_end_of_stage_menu")
			if result_screen and _is_window_visible(result_screen):
				# 원래 close_menus에서 닫지 않는 결과창도 기존 닫기 메서드로 종료합니다.
				result_screen.call("close_end_of_stage_menu")
				window_target = result_screen
				window_expected = false
			get_tree().paused = false
		"prestige", "stages", "companions", "result", "inventory":
			var methods = {"prestige": "toggle_prestige", "stages": "toggle_stage_selection", "companions": "toggle_companion_selection", "result": "toggle_end_of_stage", "inventory": "toggle_inventory"}
			var node = _method_node(methods[operation])
			if node:
				node.call(methods[operation])
			else:
				outcome = "FAIL"
		"qa_state":
			var data = GameState.get_or_create_state()
			data.gold = command.get("gold", 999999)
			data.prestige_level = command.get("level", 3)
			data.prestige_skills[prestige_data.id.PORTAL_UNLOCK] = 1
			data.stage_died = command.get("died", false)
			data.stage_resources = command.get("resources", 12345)
			data.stage_resources_lost = 1234
			data.stage_cores = command.get("cores", 9876)
			data.show_stats = true
			if command.get("unlock_companions", false):
				for animal in companions_data.animals:
					GameState.add_animal_unlock(animal)
			StaticSignal.prestige_changed_signal.emit()
			StaticSignal.update_gold_visual_signal.emit(data.gold)
			GlobalState.save()
		"bag_state":
			var data = GameState.get_or_create_state()
			data.player_inventory_slots = 1
			data.player_inventory_item_amount = 4
			data.player_inventory = [{item_data.id.PLANT_I: command.get("amount", 4)}]
			# 시장과 같은 이름의 메서드를 피하고 실제 게임 HUD에만 가방 상태를 반영합니다.
			var node = _method_node("toggle_inventory")
			if node:
				node.call("refresh_inventory")
				node.call("update_full_label")
				detail["inventory_test_state"] = {"owner": str(node.get_path()), "slots": data.player_inventory_slots, "capacity_per_slot": data.player_inventory_item_amount, "amount": command.get("amount", 4), "original_visible_threshold": "used >= capacity * 0.75", "original_full_threshold": "used >= capacity"}
			else:
				outcome = "FAIL"
		"forest":
			get_tree().paused = false
			GameState.set_current_level_path("res://game/scenes/game_scene/levels/the_forest.tscn")
			# 게임 화면의 LevelManager는 체크포인트를 자동 로딩하므로 격리 상태도 같은 지역으로 맞춥니다.
			GameState.set_checkpoint_level_path("res://game/scenes/game_scene/levels/the_forest.tscn")
			# 원래 게임 화면이 HUD와 튜토리얼을 만들고 현재 지역을 불러오는 흐름을 사용합니다.
			SceneLoader.load_scene(AppConfig.game_scene_path)
		"prototype":
			get_tree().paused = false
			var number = int(command.get("level", 1))
			if number not in [1, 2, 3]:
				outcome = "FAIL"
			else:
				SceneLoader.load_scene("res://game/scenes/game_scene/levels/old_levels/level_%d.tscn" % number)
		"prototype_action":
			var aliases = {"win": "_on_win_button_pressed", "lose": "_on_lose_button_pressed", "tutorial": "_on_tutorial_button_pressed"}
			var action = command.get("action", "")
			var method = aliases.get(action, action)
			var scene = get_tree().current_scene
			var permitted = ["res://game/scenes/game_scene/levels/old_levels/level_1.tscn", "res://game/scenes/game_scene/levels/old_levels/level_2.tscn", "res://game/scenes/game_scene/levels/old_levels/level_3.tscn"]
			if method in aliases.values() and scene != null and scene.scene_file_path in permitted and scene.has_method(method):
				# 예비 레벨의 기존 세 버튼 동작만 허용합니다.
				detail["method"] = method
				detail["source_scene"] = scene.scene_file_path
				scene.call(method)
			else:
				outcome = "FAIL"
		"color_picker":
			var nodes = []
			_all_nodes(get_tree().root, nodes)
			var found = false
			for node in nodes:
				if node is ColorPickerButton and node.is_visible_in_tree():
					node.get_popup().popup()
					found = true
					break
			if not found:
				outcome = "FAIL"
		"color_picker_dump", "input_native_dump":
			pass
		"loading_error", "loading_dialog":
			var loading = _method_node("_show_scene_switching_error_message")
			if loading == null:
				loading = load("res://addons/maaacks_game_template/base/nodes/loading_screen/loading_screen.tscn").instantiate()
				loading.name = "KoreanQALoadingReference"
				add_child(loading)
			# 파일을 훼손하지 않고 기존 오류 표시 메서드만 검사합니다.
			loading.set_process(false)
			loading.get_node("LoadingTimer").stop()
			loading.show()
			loading.call("_show_scene_switching_error_message")
			window_target = loading.get_node("Control/ErrorMessage")
			detail["default_dialog_reference"] = _default_dialog_probe()
			detail["game_ok_text"] = window_target.get_ok_button().text
			detail["game_ok_node_tr"] = str(window_target.get_ok_button().tr(window_target.get_ok_button().text))
		"loading_error_close", "loading_dialog_close":
			var loading = _method_node("_show_scene_switching_error_message")
			if loading:
				loading.call("close")
				if loading.name == "KoreanQALoadingReference":
					loading.queue_free()
			else:
				outcome = "FAIL"
		"input_scroll":
			var nodes = []
			_all_nodes(get_tree().root, nodes)
			var found = false
			for node in nodes:
				if node is ScrollContainer and node.has_method("_get_action_readable_name") and node.is_visible_in_tree():
					node.scroll_vertical = int(command.get("scroll", 0))
					detail = {"path": str(node.get_path()), "requested_scroll": command.get("scroll", 0), "actual_scroll": node.scroll_vertical}
					found = true
					break
			if not found:
				outcome = "FAIL"
		"village":
			get_tree().paused = false
			GameState.set_current_level_path(GameState.DEFAULT_VILLAGE)
			GameState.set_checkpoint_level_path(GameState.DEFAULT_VILLAGE)
			SceneLoader.load_scene(AppConfig.game_scene_path)
		"demo":
			StaticSignal.show_demo_end_screen.emit()
		"tutorial":
			var node = _method_node("_show_part")
			if node:
				node.set("part", command.get("part", 0))
				node.call("_show_part")
			else:
				outcome = "FAIL"
		"tutorial_hide":
			var node = _method_node("_show_part")
			if node:
				node.hide()
		"pause":
			var node = _method_node("_refresh_exit_button")
			if node and node.has_method("show"):
				var layer = node.get_parent()
				if layer is CanvasLayer and layer.has_method("_on_pause_menu_hidden"):
					# 부모가 보이면 원래 visibility_changed 연결이 PauseMenu.show를 호출합니다.
					if not layer.visible:
						layer.show()
					else:
						node.call("show")
					detail["pause_layer"] = {"path": str(layer.get_path()), "entry": "CanvasLayer.show -> visibility_changed -> PauseMenu.show", "layer_visible": layer.visible}
					window_target = node
				else:
					outcome = "FAIL"
			else:
				outcome = "FAIL"
		"pause_options":
			var node = _method_node("_refresh_exit_button")
			if node:
				node.call("_on_options_button_pressed")
				window_owner = node
				window_field = "open_window"
			else:
				outcome = "FAIL"
		"pause_close", "pause_close_options":
			var node = _method_node("_refresh_exit_button")
			if node:
				node.call("close_window" if operation == "pause_close_options" else "close")
				window_expected = false
				if operation == "pause_close_options":
					window_owner = node
					window_field = "open_window"
				else:
					window_target = node
			else:
				outcome = "FAIL"
		"quit":
			get_tree().quit()
			return
		_:
			outcome = "FAIL"
	await get_tree().create_timer(command.get("wait", 1.2), true).timeout
	if operation == "skill":
		var tip = _method_node("_show_skill")
		if tip:
			var panels = []
			_all_nodes(tip, panels)
			for panel in panels:
				if panel is PanelContainer and panel.is_visible_in_tree():
					var rectangle = panel.get_global_rect()
					var viewport = panel.get_viewport_rect()
					detail["tooltip_layout"] = {"tip_path": str(tip.get_path()), "panel_path": str(panel.get_path()), "panel_rect": [rectangle.position.x, rectangle.position.y, rectangle.size.x, rectangle.size.y], "viewport_rect": [viewport.position.x, viewport.position.y, viewport.size.x, viewport.size.y], "z_index": tip.z_index}
					break
	if window_owner != null or window_target != null:
		var checked_window = window_owner.get(window_field) if window_owner != null else window_target
		var actual_visible = _is_window_visible(checked_window)
		detail["window_check"] = {"owner": str(window_owner.get_path()) if window_owner != null else "", "field": window_field, "target": str(checked_window.get_path()) if is_instance_valid(checked_window) else "", "expected_visible": window_expected, "actual_visible": actual_visible}
		if actual_visible != window_expected:
			outcome = "FAIL"
	if operation == "color_picker_dump" or operation == "input_native_dump":
		var dump = {}
		if operation == "color_picker_dump":
			dump = await _color_picker_probe()
		else:
			dump = _input_display_probe()
		var dump_path = config.screens.path_join(command.id + "_native.json")
		FileAccess.open(dump_path, FileAccess.WRITE).store_string(JSON.stringify(dump, "\t"))
		detail["native_dump"] = {"path": dump_path, "sha256": FileAccess.get_sha256(dump_path), "status": dump.status}
		if dump.status != "PASS":
			outcome = "FAIL"
	await RenderingServer.frame_post_draw
	var path = config.screens.path_join(command.id + ".png")
	var screenshot = get_viewport().get_texture().get_image()
	var error = screenshot.save_png(path)
	var texts = []
	var nodes = []
	_all_nodes(get_tree().root, nodes)
	for node in nodes:
		if (node is Label or node is RichTextLabel or node is Button) and node.is_visible_in_tree():
			var value = node.text
			if value.strip_edges().is_empty():
				continue
			var rect = node.get_global_rect()
			texts.append({"path": str(node.get_path()), "text": value, "node_tr": str(node.tr(value)), "auto_translate_mode": node.auto_translate_mode, "rect": [rect.position.x, rect.position.y, rect.size.x, rect.size.y], "class": node.get_class()})
	events.append({"id": command.id, "operation": operation, "status": outcome, "capture_error": error, "image": path, "sha256": FileAccess.get_sha256(path), "time": Time.get_unix_time_from_system(), "scene": get_tree().current_scene.scene_file_path if get_tree().current_scene else "", "texts": texts, "test_state": operation in ["qa_state", "bag_state"], "detail": detail})
	FileAccess.open(config.ledger, FileAccess.WRITE).store_string(JSON.stringify(events, "\t"))
