extends Node

# 검수 사본 전용 자동 불러오기입니다. 배포본에는 파일·등록 항목 모두 넣지 않습니다.
# F6은 실제 게임 창을 순서대로 열고 F5는 현재 글자·글꼴·배치 측정값을 기록합니다.
# 이 기록만으로 화면 검수를 통과시키지 않습니다. 제작자가 실제 화면을 판독합니다.
const OUTPUT_DIR = "user://qa_diagnostics"
const STEPS = [
	"hud", "settings", "tutorial", "store_list", "store_detail", "hiring",
	"worker_list", "worker_stats", "crafting", "research_warning", "research_list",
	"contract_demo", "mail_list", "mail_detail", "story_dialogue", "pipeline", "overview",
	"building", "objectives", "storage", "monument_demo", "exit_menu"
]
var step_index = -1
var capture_index = 0
var busy = false
var enabled = false
var ui: Control
var modal: Control
var modal_close_method = ""
var history: Array = []
var mutations: Array = []
var seed_storage_pos = Vector2i(-999, -999)
var seed_craft_pos = Vector2i(-999, -999)
var seed_research_pos = Vector2i(-999, -999)
var research_seed_created = false
var guide_open = false
var story_state: Dictionary = {}

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	enabled = OS.get_environment("AGROMATIC_QA_DRIVER") == "1"
	set_process_input(enabled)
	if enabled:
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUTPUT_DIR))
		print("[KO-QA] 검수 도우미: F6 다음 화면 / F5 현재 화면 진단")
	else:
		print("[KO-QA] AGROMATIC_QA_DRIVER=1 환경값이 없어 검수 도우미를 비활성화했습니다.")

func _input(event: InputEvent) -> void:
	if not enabled or busy or not event is InputEventKey or not event.pressed or event.echo:
		return
	if event.keycode == KEY_F5:
		get_viewport().set_input_as_handled()
		capture_visible_ui()
	elif event.keycode == KEY_F6:
		get_viewport().set_input_as_handled()
		next_screen()

func _manager(name: String) -> Node:
	return get_tree().root.get_node_or_null(name)

func _game_manager(name: String) -> Node:
	var game = _manager("GameManager")
	return game.get(name) if game != null else null

func _by_script(node: Node, suffix: String) -> Node:
	var script = node.get_script()
	if script != null:
		var path = str(script.resource_path)
		if path.ends_with(".gdc"):
			path = path.trim_suffix("c")
		if path.ends_with(suffix):
			return node
	for child in node.get_children():
		var found = _by_script(child, suffix)
		if found != null:
			return found
	return null

func _is_hud_ready() -> bool:
	var scene = get_tree().current_scene
	if scene == null:
		return false
	ui = scene.get_node_or_null("CanvasLayer/UI") as Control
	return ui != null and (ui.is_visible_in_tree() or is_instance_valid(modal)) and _game_manager("worker_manager") != null

func next_screen() -> void:
	busy = true
	if not _is_hud_ready():
		var menu = _by_script(get_tree().current_scene, "MainMenu.gd") if get_tree().current_scene != null else null
		if menu != null and menu.is_visible_in_tree() and menu.has_method("show_guide_modal"):
			if guide_open:
				var guide = menu.get_node_or_null("CanvasLayer/GuideModal")
				if guide != null:
					guide.visible = false
				guide_open = false
				_record("mainmenu_guide_close", "PASS", "MainMenu 실제 도움말 닫기. 제작자가 새 게임을 시작한 뒤 F6을 사용합니다.")
			else:
				menu.call("show_guide_modal")
				guide_open = true
				_record("mainmenu_guide", "OPENED", "MainMenu.gd:1511 show_guide_modal()")
		else:
			_record("waiting_hud", "BLOCKED", "메인 메뉴에서 제작자가 새 게임을 시작하고 HUD까지 이동해야 합니다.")
		busy = false
		return
	await _close_previous()
	await get_tree().process_frame
	await get_tree().process_frame
	# 시간 진행·자동 저장을 멈추는 검수 전용 객체 필드입니다.
	if not get_tree().paused:
		_mutation("/root", "SceneTree.paused", false, true, "화면 순회 중 게임 시간을 고정")
	get_tree().paused = true
	step_index = (step_index + 1) % STEPS.size()
	var step: String = STEPS[step_index]
	var result = _open_step(step)
	await get_tree().process_frame
	await get_tree().process_frame
	_record(step, result.get("status", "BLOCKED"), result.get("evidence", ""))
	capture_visible_ui()
	busy = false

func _close_previous() -> void:
	if is_instance_valid(modal):
		if modal.has_method(modal_close_method):
			modal.call(modal_close_method)
		elif modal_close_method == "close_button_signal":
			var button = modal.get_node_or_null("ModalContainer/HeaderContainer/CloseButton")
			if button is BaseButton:
				button.pressed.emit()
			elif is_instance_valid(ui):
				ui.call("close_modal", modal)
		elif is_instance_valid(ui):
			ui.call("close_modal", modal)
		if not story_state.is_empty():
			# 원래 StoryUI의 닫기 애니메이션과 HUD 복원을 기다립니다.
			await get_tree().create_timer(0.5, true).timeout
			var manager = _game_manager("story_manager")
			for field in story_state:
				manager.set(field, story_state[field])
			story_state.clear()
	modal = null
	modal_close_method = ""

func _open_original(scene_name: String, args: Array, close_method: String) -> Control:
	var path = "res://scenes/" + scene_name + ".tscn"
	if not ResourceLoader.exists(path) or not is_instance_valid(ui):
		return null
	if str(ui.get("current_opened_modal")) != "":
		# 제작자가 직접 열어 둔 창이 있다면 그 게임 창의 공개 닫기 함수로 닫습니다.
		for child in ui.get_parent().get_children():
			if child is Control and child != ui and child.is_visible_in_tree() and child.scene_file_path.ends_with(str(ui.get("current_opened_modal")) + ".tscn"):
				for method in ["close_modal", "close_store", "close_mail_modal", "close_storage", "close_research_ui", "close"]:
					if child.has_method(method):
						child.call(method)
						break
	if str(ui.get("current_opened_modal")) != "":
		return null
	var packed: PackedScene = load(path)
	var instance = packed.instantiate() as Control
	if instance == null or not instance.has_method("open_modal"):
		if instance != null:
			instance.queue_free()
		return null
	ui.get_parent().add_child(instance)
	instance.process_mode = Node.PROCESS_MODE_ALWAYS
	# UI.gd:1218 _spawn_modal의 소유권 기록과 동일한 필드만 설정합니다.
	ui.set("current_opened_modal", scene_name)
	_mutation(str(ui.get_path()), "current_opened_modal", "", scene_name, "원래 모달의 공개 open_modal()을 호출하기 위한 소유권 기록")
	instance.callv("open_modal", args)
	modal = instance
	modal_close_method = close_method
	return instance

func _opened(instance: Node, evidence: String) -> Dictionary:
	var shown = instance != null and (not instance is CanvasItem or instance.is_visible_in_tree())
	return {"status": "OPENED" if shown else "BLOCKED", "evidence": evidence + (" / 원래 객체 또는 보이는 부모가 없어 표시되지 않음" if not shown else "")}

func _open_step(step: String) -> Dictionary:
	match step:
		"hud":
			return {"status": "OPENED", "evidence": "game.tscn CanvasLayer/UI의 실제 HUD. 시간만 고정"}
		"settings":
			var menu = _open_original("gamemenu_ui", [Vector2i.ZERO], "close_modal")
			if menu != null:
				var settings = menu.get_node_or_null("SettingsModal")
				if settings != null and settings.has_method("open_modal"):
					settings.call("open_modal")
					return _opened(settings, "GamemenuUI.gd:109 / SettingsModalUI.gd:68 open_modal(). 적용·저장 버튼을 누르지 않음")
			return _opened(null, "설정 모달 열기 실패")
		"tutorial":
			var tutorial = _by_script(get_tree().current_scene, "TutorialUI.gd")
			if tutorial != null:
				tutorial.call("show_tutorial")
				return _opened(tutorial, "TutorialUI.gd:142 show_tutorial(). 활성 튜토리얼 데이터가 없으면 부모는 숨김 상태")
			return {"status": "BLOCKED", "evidence": "HUD 도움말 독립 모달은 없음. 튜토리얼 UI 객체도 현재 장면에 없음. 메인메뉴 도움말은 별도 F6 경로"}
		"store_list":
			return _opened(_open_original("store_ui", [], "close_store"), "StoreUI.gd:149 open_modal() 실제 상점 목록")
		"store_detail":
			var store = _open_original("store_ui", [], "close_store")
			var stores = _manager("StoreDataManager").call("get_available_stores")
			if store != null and stores.size() > 0:
				store.call("show_store_detail", stores[0])
				return _opened(store, "StoreUI.gd:175 show_store_detail(실제 이용 가능한 첫 상점). visited_stores는 원래 열기 함수가 기록")
			return _opened(null, "데모에서 이용 가능한 상점 상세가 없음")
		"hiring":
			return _opened(_open_original("hiring_ui", [], "close_button_signal"), "HiringUI.gd:674 open_modal(). 원래 모집 광고/지원자/대기 분기. 광고·채용 실행은 하지 않음")
		"worker_list", "worker_stats":
			var worker = _ensure_worker()
			if step == "worker_list":
				return _opened(_open_original("worker_ui", [], "close_button_signal"), "WorkerUI.gd:214 open_modal(). 필요할 때 농사 일꾼 하나만 실제 spawn_worker()로 생성")
			if worker == null:
				return _opened(null, "일꾼 객체 생성 실패")
			ui.call("open_worker_stats_modal", worker)
			modal = _by_script(ui.get_parent(), "WorkerStatsUI.gd") as Control
			modal_close_method = "close"
			return _opened(modal, "UI.gd:1247 open_worker_stats_modal(worker) / WorkerStatsUI.gd:142 open_modal_with_worker()")
		"crafting":
			seed_craft_pos = _ensure_crafting()
			if seed_craft_pos == Vector2i(-999, -999):
				return _opened(null, "실제 제작 작업대가 없고 소유 구역에 검수용 campfire 하나를 놓을 공간이 없음")
			return _opened(_open_original("crafting_ui", [seed_craft_pos], "close"), "CraftingUI.gd:492 open_modal(실제 작업대 위치), 원래 레시피 목록/진행 분기")
		"research_warning", "research_list":
			seed_research_pos = _ensure_research(step == "research_list")
			if seed_research_pos == Vector2i(-999, -999):
				return _opened(null, "연구 UI 입력 위치를 준비할 수 없음")
			return _opened(_open_original("research_ui", [seed_research_pos], "close_research_ui"), "ResearchUI.gd:87 open_modal(). QA 입력 컴퓨터 사전 하나만 기록하여 경고/연구 목록 분기를 표시. 실제 연구 완료 기능 시험과 구분")
		"contract_demo":
			return _opened(_open_original("contract_ui", [], "close_modal"), "ContractUI.gd:229 IS_DEMO → info_panel. 상세 show_contract_detail:251은 데모에서 반환")
		"mail_list", "mail_detail":
			var message_manager = _manager("MessageManager")
			if message_manager.call("get_all_messages").is_empty():
				var message = message_manager.call("create_temporary_message_from_template", "zone_transfer_guide", {})
				_mutation(str(message_manager.get_path()), "messages/unread_count", null, {"template": "zone_transfer_guide", "is_temporary": true, "created": message != null}, "원본 번역 대상 편지 템플릿을 임시 편지로 생성. 저장되는 일반 편지 데이터와 구분")
			var mail = _open_original("message_ui", [], "close_mail_modal")
			if mail != null and step == "mail_detail":
				var messages = _manager("MessageManager").call("get_all_messages")
				for message in messages:
					if str(message.metadata.get("story_scene_id", "")) == "":
						mail.call("show_message_detail", message)
						return _opened(mail, "MessageUI.gd:447 show_message_detail()의 실제 일반 편지. 답장·수령·삭제하지 않음")
				return {"status": "BLOCKED", "evidence": "현재 일반 편지가 없어 상세를 임의 문구로 채우지 않음. 편지 목록은 실제 객체로 열림"}
			return _opened(mail, "MessageUI.gd:698 open_modal() 실제 받은 편지 목록")
		"story_dialogue":
			var manager = _game_manager("story_manager")
			var scene_id = "sarah_composter_quest"
			if manager == null or not manager.call("has_scene", scene_id):
				return _opened(null, "원본 대표 대화 sarah_composter_quest가 없음")
			story_state = {"current_scene_id": manager.get("current_scene_id"), "is_story_active": manager.get("is_story_active")}
			manager.set("current_scene_id", scene_id)
			manager.set("is_story_active", true)
			_mutation(str(manager.get_path()), "current_scene_id/is_story_active", story_state.duplicate(), {"current_scene_id": scene_id, "is_story_active": true}, "원본 대표 대화 열기 입력 두 필드. 선택지를 누르지 않고 닫을 때 이전 값 복원")
			return _opened(_open_original("story_ui", [Vector2i.ZERO], "close_modal"), "StoryUI.gd:104 open_modal() 실제 대화·선택지. 타자 효과 완료 뒤 F5 재기록 필요")
		"pipeline":
			return _opened(_open_original("pipeline_ui", [], "close_modal"), "PipelineUI.gd:72 open_modal() 실제 생산 흐름도")
		"overview":
			return _opened(_open_original("overview_ui", [], "close_overview"), "OverviewUI.gd:206 open_modal() 실제 생산 현황")
		"building":
			return _opened(_open_original("building_ui", [], "close_modal"), "BuildingUI.gd:32 open_modal() 실제 건물 목록")
		"objectives":
			return _opened(_open_original("objectives_ui", [], "close_modal"), "ObjectivesUI.open_modal() 실제 목표 목록")
		"storage":
			seed_storage_pos = _ensure_storage()
			if seed_storage_pos == Vector2i(-999, -999):
				return _opened(null, "실제 보관함을 찾거나 생성할 수 없음")
			return _opened(_open_original("storage_ui", [seed_storage_pos], "close_storage"), "StorageUI.gd:184 open_modal(실제 보관함 위치). 배터리만 연구 목록 검수용 입력으로 넣을 수 있음")
		"monument_demo":
			var manager = _game_manager("building_manager")
			for pos in manager.get("active_buildings"):
				var data: Dictionary = manager.get("active_buildings")[pos]
				if data.get("building_id", "") == "the_monument":
					return _opened(_open_original("building_purchase_ui", [pos, "the_monument", manager.call("get_building_purchase_modal_data", pos)], "close_modal"), "BuildingPurchaseUI.gd:41 공개 open_modal(). IS_DEMO에서 구매·포인트 결과 기능 차단 안내를 표시")
			return {"status": "BLOCKED", "evidence": "현재 지도에 기념비가 없음. 별도 game_over/result 장면·열기 함수는 원본에 없음"}
		"exit_menu":
			return _opened(_open_original("gamemenu_ui", [Vector2i.ZERO], "close_modal"), "GamemenuUI.gd:386 open_modal(). 종료 버튼을 표시. _on_quit_pressed:194 실제 종료는 제작자가 마지막에 수행")
	return {"status": "BLOCKED", "evidence": "알 수 없는 화면"}

func _owned_origin() -> Vector2i:
	var grid = _manager("GridManager")
	var zones: Dictionary = grid.get("owned_zones")
	if zones.is_empty():
		return Vector2i(-999, -999)
	var bounds: Rect2i = grid.call("get_zone_bounds", zones.keys()[0])
	return bounds.position + Vector2i(4, 4)

func _place_seed(manager: Node, item_id: String) -> Vector2i:
	var grid = _manager("GridManager")
	var state = _manager("GridStateManager")
	var zones: Dictionary = grid.get("owned_zones")
	for zone in zones:
		var bounds: Rect2i = grid.call("get_zone_bounds", zone)
		for y in range(bounds.position.y + 2, bounds.end.y - 3):
			for x in range(bounds.position.x + 2, bounds.end.x - 3):
				var pos = Vector2i(x, y)
				var cell: Dictionary = state.call("get_cell_data", pos)
				# 기존 풀·작물·객체를 제거하지 않는 빈 칸만 사용합니다.
				if cell.get("entity_category", "") != "":
					continue
				var before = cell.duplicate(true)
				if state.call("can_place_entity_at", pos, item_id) and manager.call("place_object_entity", pos, item_id):
					var after: Dictionary = state.call("get_cell_data", pos)
					_mutation(str(state.get_path()), "cell@" + str(pos), before, after.duplicate(true), "빈 칸 한 개에 정상 배치한 검수 객체의 원래 셀 필드 차이")
					var data: Dictionary = manager.call("get_station_data", pos) if manager.has_method("get_station_data") else manager.call("get_storage_data", pos)
					_mutation(str(manager.get_path()), "place_object_entity", null, {"grid_position": str(pos), "item_id": item_id, "object_data": data.duplicate(true)}, "소유 구역에서 정상 배치가 가능한 검수용 객체 하나. 돈·아이템·해금 값을 바꾸지 않음")
					return pos
	return Vector2i(-999, -999)

func _ensure_storage() -> Vector2i:
	var manager = _manager("StorageManager")
	var positions = manager.call("get_all_storage_positions")
	if positions.size() > 0:
		return positions[0]
	return _place_seed(manager, "wooden_storage")

func _ensure_crafting() -> Vector2i:
	var manager = _game_manager("crafting_station_manager")
	var active: Dictionary = manager.get("active_stations")
	if not active.is_empty():
		return active.keys()[0]
	return _place_seed(manager, "campfire")

func _ensure_worker() -> Node:
	var manager = _game_manager("worker_manager")
	var workers: Array = manager.get("active_workers")
	if not workers.is_empty():
		return workers[0]
	var pos = _owned_origin()
	if pos == Vector2i(-999, -999):
		return null
	var worker = manager.call("spawn_worker", pos, "farm", {"name": "검수 일꾼", "salary": 20, "shift": "day"})
	_mutation(str(manager.get_path()), "spawn_worker", null, {"position": str(pos), "type": "farm", "name": "검수 일꾼", "salary": 20, "shift": "day"}, "WorkerManager.gd:123의 정상 초기화. 검수 사본에 일꾼 하나만 추가")
	return worker

func _ensure_research(show_list: bool) -> Vector2i:
	var manager = _game_manager("research_manager")
	var computers: Dictionary = manager.get("active_computers")
	var pos = _owned_origin()
	if not computers.is_empty():
		pos = computers.keys()[0]
	elif pos != Vector2i(-999, -999):
		# 연구 경고·목록에 필요한 입력 객체만 추가합니다. 세계 지도/건물/전력망을 변경하지 않습니다.
		var seed = {"computer_type": "computer", "current_research_id": "", "research_progress": 0.0,
			"required_progress": 0.0, "is_researching": false, "power_value": 0.0, "wants_power": false,
			"worker_assigned": false, "target_research_id": "", "stationed_worker_present": false,
			"stationed_worker_id": -1, "requires_presence": true, "assigned_worker_persistent_id": -1}
		computers[pos] = seed
		research_seed_created = true
		_mutation(str(manager.get_path()), "active_computers[" + str(pos) + "]", null, seed.duplicate(true), "ResearchManager.gd:346 기본 입력 사전 한 개. 시각 컴퓨터·기능 연구 검증과 구분")
	if show_list and pos != Vector2i(-999, -999):
		var storage_pos = _ensure_storage()
		if storage_pos != Vector2i(-999, -999):
			var storage = _manager("StorageManager")
			var before_count = int(storage.call("get_item_count", storage_pos, "battery"))
			var requested = maxi(10 - before_count, 0)
			if requested > 0:
				var remaining = storage.call("add_item_by_id", storage_pos, "battery", requested)
				_mutation(str(storage.get_path()), "battery_count@" + str(storage_pos), before_count, {"requested": requested, "remaining": remaining, "after_count": storage.call("get_item_count", storage_pos, "battery")}, "연구 목록 분기용 배터리를 총 10개까지만 정상 보관 API로 추가")
		var workers = _game_manager("worker_manager")
		var zone = _manager("GridManager").call("grid_to_zone", pos)
		var exists = false
		for worker in workers.get("active_workers"):
			if worker.worker_type == "researcher" and worker.call("get_assigned_zone") == zone:
				exists = true
		if not exists:
			workers.call("spawn_worker", pos, "researcher", {"name": "검수 연구 일꾼", "salary": 20, "shift": "day"})
			_mutation(str(workers.get_path()), "spawn_worker", null, {"position": str(pos), "type": "researcher", "name": "검수 연구 일꾼", "salary": 20, "shift": "day"}, "연구 목록의 원래 필요 조건을 충족할 일꾼 하나만 추가")
	return pos

func _mutation(object_path: String, field: String, before: Variant, after: Variant, reason: String) -> void:
	mutations.append({"object": object_path, "field_or_method": field, "before": before, "after": after, "reason": reason, "qa_only": true})
	_write_json("mutations.json", mutations)

func _record(step: String, status: String, evidence: String) -> void:
	history.append({"step": step, "status": status, "evidence": evidence, "ticks_ms": Time.get_ticks_msec(), "visual_review": "NOT_RUN"})
	_write_json("screen_history.json", history)
	print("[KO-QA] ", step_index + 1, "/", STEPS.size(), " ", step, " ", status, " ", evidence)

func _write_json(name: String, value: Variant) -> void:
	var file = FileAccess.open(OUTPUT_DIR + "/" + name, FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(value, "\t"))
	else:
		push_error("[KO-QA] 진단 파일 저장 실패: " + name)

func capture_visible_ui() -> void:
	var rows: Array = []
	_collect_text(get_tree().root, rows)
	capture_index += 1
	var output = {"format_version": 1, "capture_index": capture_index,
		"step": STEPS[step_index] if step_index >= 0 else "manual",
		"scene_path": get_tree().current_scene.scene_file_path if get_tree().current_scene != null else "",
		"executable_path": OS.get_executable_path(), "ticks_ms": Time.get_ticks_msec(),
		"viewport_rect": _rect(get_viewport().get_visible_rect()), "paused": get_tree().paused,
		"rows": rows, "visual_review": "NOT_RUN",
		"note": "글꼴 has_char와 기하 측정은 보조 근거. 픽셀 판독·폰트 경고 로그·후보 해시 확인은 별도 수행"}
	var filename = "%03d_%s.json" % [capture_index, output.step]
	_write_json(filename, output)
	print("[KO-QA] F5 기록: ", ProjectSettings.globalize_path(OUTPUT_DIR + "/" + filename), " / 글자 객체 ", rows.size())

func _collect_text(node: Node, rows: Array) -> void:
	if node is Window and not node.visible:
		return
	if node is CanvasItem and (not node.is_visible_in_tree() or node.modulate.a <= 0.01 or node.self_modulate.a <= 0.01):
		return
	if node is PopupMenu:
		var popup_font = node.get_theme_font("font")
		for index in range(node.item_count):
			var popup_text = node.get_item_text(index)
			var popup_missing: Array = []
			for character in popup_text:
				var code = character.unicode_at(0)
				if code > 32 and (popup_font == null or not popup_font.has_char(code)):
					popup_missing.append({"codepoint": code, "character": character})
			rows.append({"node": str(node.get_path()), "class": "VisiblePopupMenuItem", "item_index": index,
				"text": popup_text, "font_resource": popup_font.resource_path if popup_font != null else "",
				"missing_has_char": popup_missing, "window_position": [node.position.x, node.position.y],
				"window_size": [node.size.x, node.size.y], "pixel_review": "NOT_RUN"})
	if node is Control:
		var text = ""
		var role = "font"
		if node is RichTextLabel:
			text = node.get_parsed_text()
			role = "normal_font"
		elif node is Label or node is Button or node is LineEdit or node is TextEdit:
			text = node.text
			if node is LineEdit and text.is_empty():
				text = node.placeholder_text
		if not text.is_empty():
			rows.append(_text_row(node, text, role))
		if node is OptionButton:
			var options: Array = []
			for i in range(node.item_count):
				options.append({"index": i, "text": node.get_item_text(i), "disabled": node.is_item_disabled(i)})
			rows.append({"node": str(node.get_path()), "class": "OptionButtonOptions", "options": options, "selected": node.selected, "visibility": "dropdown_inventory"})
	for child in node.get_children():
		_collect_text(child, rows)

func _text_row(control: Control, text: String, role: String) -> Dictionary:
	var font = control.get_theme_font(role)
	var font_size = control.get_theme_font_size("normal_font_size" if control is RichTextLabel else "font_size")
	var rect = control.get_global_rect()
	var clip = get_viewport().get_visible_rect()
	var clip_sources: Array = []
	var ancestor = control.get_parent()
	while ancestor != null:
		if ancestor is Control and ancestor.clip_contents:
			clip = clip.intersection(ancestor.get_global_rect())
			clip_sources.append(str(ancestor.get_path()))
		ancestor = ancestor.get_parent()
	var missing: Array = []
	var seen: Dictionary = {}
	for i in range(text.length()):
		var code = text.unicode_at(i)
		if code > 32 and not seen.has(code):
			seen[code] = true
			if font == null or not font.has_char(code):
				missing.append({"codepoint": code, "character": String.chr(code)})
	var suspects: Array = []
	if not clip.encloses(rect):
		suspects.append("control_rect_partially_outside_clip")
	var visible_rect = rect.intersection(clip)
	var row = {"node": str(control.get_path()), "class": control.get_class(), "text": text,
		"rect": _rect(rect), "local_size": [control.size.x, control.size.y], "visible_rect": _rect(visible_rect),
		"intersects_viewport": visible_rect.has_area(), "clip_ancestors": clip_sources,
		"font_role": role, "font_resource": font.resource_path if font != null else "",
		"font_name": font.get_font_name() if font != null else "", "font_size": font_size,
		"missing_has_char": missing, "geometry_suspects": suspects, "pixel_review": "NOT_RUN"}
	if control is Label:
		row.merge({"line_count": control.get_line_count(), "visible_line_count": control.get_visible_line_count(),
			"autowrap_mode": control.autowrap_mode, "clip_text": control.clip_text,
			"text_overrun_behavior": control.text_overrun_behavior, "max_lines_visible": control.max_lines_visible})
		if control.get_visible_line_count() < control.get_line_count():
			suspects.append("label_lines_not_all_visible")
		if font != null and control.autowrap_mode == TextServer.AUTOWRAP_OFF:
			var longest = 0.0
			for line in text.split("\n"):
				longest = maxf(longest, font.get_string_size(line, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x)
			row["unwrapped_longest_line_width"] = longest
			if longest > control.size.x + 1.0:
				suspects.append("unwrapped_text_wider_than_control")
	elif control is RichTextLabel:
		row.merge({"raw_bbcode": control.text, "content_height": control.get_content_height(),
			"content_width": control.get_content_width(), "line_count": control.get_line_count(),
			"autowrap_mode": control.autowrap_mode, "scroll_active": control.scroll_active,
			"fit_content": control.fit_content, "visible_characters": control.visible_characters,
			"threaded": control.threaded, "finished": control.is_finished()})
		if not control.scroll_active and control.get_content_height() > control.size.y + 1.0:
			suspects.append("richtext_height_exceeds_control_without_scroll")
		# BBCode 스타일 글꼴도 기록하되 전체 글자가 각 스타일을 쓴다고 판정하지 않습니다.
		var style_fonts: Array = []
		for style in ["normal_font", "bold_font", "italics_font", "bold_italics_font", "mono_font"]:
			var style_font = control.get_theme_font(style)
			style_fonts.append({"role": style, "resource": style_font.resource_path if style_font != null else "", "name": style_font.get_font_name() if style_font != null else ""})
		row["style_fonts"] = style_fonts
	return row

func _rect(rect: Rect2) -> Array:
	return [rect.position.x, rect.position.y, rect.size.x, rect.size.y]
