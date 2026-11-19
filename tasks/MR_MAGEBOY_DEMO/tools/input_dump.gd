extends SceneTree

# 입력 안내의 원문은 원본 helper와 엔진의 실제 서식 함수로 확인합니다.
func _initialize():
	var config = JSON.parse_string(FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]))
	var helper = load(config.helper)
	var rows = []
	for index in range(1, 10):
		var mouse = InputEventMouseButton.new()
		mouse.button_index = index
		rows.append({"kind": "mouse", "button_index": index, "as_text": mouse.as_text(),
			"get_text": helper.get_text(mouse), "device_specific": helper.get_device_specific_text(mouse)})
	for code in [KEY_A, KEY_SPACE, KEY_ENTER, KEY_ESCAPE, KEY_TAB, KEY_BACKSPACE, KEY_DELETE, KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN, KEY_F1]:
		for modifier in ["", "ctrl", "shift", "alt", "meta", "ctrl_shift"]:
			var key = InputEventKey.new()
			key.keycode = code
			key.ctrl_pressed = modifier in ["ctrl", "ctrl_shift"]
			key.shift_pressed = modifier in ["shift", "ctrl_shift"]
			key.alt_pressed = modifier == "alt"
			key.meta_pressed = modifier == "meta"
			rows.append({"kind": "key", "code": code, "modifier": modifier, "as_text": key.as_text(),
				"keycode_string": OS.get_keycode_string(key.get_keycode_with_modifiers()),
				"helper_get_text_status": "NOT_RUN_HEADLESS_PHYSICAL_MAPPING"})
	for index in range(0, 16):
		var button = InputEventJoypadButton.new()
		button.button_index = index
		button.device = -1
		var device_texts = {}
		for device in ["Generic", "Xbox", "Switch", "Playstation", "Steamdeck"]:
			device_texts[device] = helper.get_device_specific_text(button, device)
		rows.append({"kind": "joy_button", "button_index": index, "as_text": button.as_text(),
			"get_text": helper.get_text(button), "device_specific": device_texts})
	for axis in range(0, 6):
		for value in [-1.0, 0.0, 1.0]:
			var motion = InputEventJoypadMotion.new()
			motion.axis = axis
			motion.axis_value = value
			motion.device = -1
			var device_texts = {}
			for device in ["Generic", "Xbox", "Switch", "Playstation", "Steamdeck"]:
				device_texts[device] = helper.get_device_specific_text(motion, device)
			rows.append({"kind": "joy_axis", "axis": axis, "value": value, "as_text": motion.as_text(),
				"get_text": helper.get_text(motion), "device_specific": device_texts})
	FileAccess.open(config.output, FileAccess.WRITE).store_string(JSON.stringify({"engine": Engine.get_version_info(),
		"display_server": DisplayServer.get_name(), "rows": rows}, "\t"))
	quit()
