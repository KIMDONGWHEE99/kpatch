extends SceneTree

# 최종 묶음에서 직접 읽은 번역·글꼴·테마를 입력 명세와 독립적으로 대조합니다.
func _initialize():
	var args = OS.get_cmdline_user_args()
	if not ProjectSettings.load_resource_pack(args[0]):
		quit(2)
		return
	var config = JSON.parse_string(FileAccess.get_file_as_string(args[1]))
	var report = {"translations": [], "fonts": [], "themes": []}
	for entry in config.translations:
		var actual = ResourceLoader.load("res://" + entry.path, "Translation", ResourceLoader.CACHE_MODE_IGNORE)
		var failures = []
		for key in entry.messages:
			if actual.get_message(key) != entry.messages[key]:
				failures.append(key)
		report.translations.append({"path":entry.path,"count":actual.get_message_count(),"expected_count":entry.messages.size(),"locale":actual.locale,"failures":failures})
	for entry in config.fonts:
		var actual = ResourceLoader.load("res://" + entry.path, "FontFile", ResourceLoader.CACHE_MODE_IGNORE)
		var missing = []
		for character in config.characters:
			if not actual.has_char(character.unicode_at(0)):
				missing.append(character)
		var fallback_paths = []
		for fallback in actual.fallbacks:
			fallback_paths.append(fallback.resource_path)
		report.fonts.append({"path":entry.path,"missing":missing,"fallback_paths":fallback_paths,"base_data_bytes":actual.data.size(),"cache_count":actual.get_cache_count(),"system_fallback":actual.allow_system_fallback})
	for path in config.themes:
		var actual = load("res://" + path) as Theme
		report.themes.append({"path":path,"tooltip_color":actual.get_color("font_color", "TooltipLabel").to_html()})
	FileAccess.open(args[2], FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	quit()
