extends SceneTree

# 원본 폰트의 설정과 캐시를 유지하고 공용 한글 폴백만 연결합니다.
func _initialize():
	var args = OS.get_cmdline_user_args()
	if not ProjectSettings.load_resource_pack(args[0]):
		quit(2)
		return
	var config = JSON.parse_string(FileAccess.get_file_as_string(args[1]))
	var report = {"translations": [], "fonts": [], "svg": []}
	var extra = FontFile.new()
	extra.data = FileAccess.get_file_as_bytes(config.korean_font)
	var extras: Array[Font] = []
	for entry in config.extra_fonts:
		var support = FontFile.new()
		support.data = FileAccess.get_file_as_bytes(entry.source)
		if ResourceSaver.save(support, entry.output) != OK:
			quit(3)
			return
		support.take_over_path("res://" + entry.path)
		extras.append(support)
	extra.fallbacks = extras
	if ResourceSaver.save(extra, config.korean_output) != OK:
		quit(3)
		return
	extra.take_over_path("res://KoreanPatch/korean.fontdata")
	for entry in config.translations:
		var result = Translation.new()
		result.locale = "ko"
		for key in entry.messages:
			result.add_message(key, entry.messages[key])
		if ResourceSaver.save(result, entry.output) != OK:
			quit(4)
			return
		var reopened = ResourceLoader.load(entry.output, "Translation", ResourceLoader.CACHE_MODE_IGNORE)
		var failures = []
		for key in entry.messages:
			if reopened.get_message(key) != entry.messages[key]:
				failures.append(key)
		report.translations.append({"path":entry.path,"count":reopened.get_message_count(),"failures":failures})
	for entry in config.fonts:
		var font = load("res://" + entry.path) as FontFile
		var fallbacks = font.fallbacks.duplicate()
		fallbacks.push_front(extra)
		font.fallbacks = fallbacks
		if ResourceSaver.save(font, entry.output) != OK:
			quit(5)
			return
		var reopened = ResourceLoader.load(entry.output, "FontFile", ResourceLoader.CACHE_MODE_IGNORE)
		var missing = []
		for character in config.characters:
			if not reopened.has_char(character.unicode_at(0)):
				missing.append(character)
		report.fonts.append({"path":entry.path,"missing":missing,"fallback_count":reopened.fallbacks.size(),"base_data_bytes":reopened.data.size(),"supported_chars":reopened.get_supported_chars().length(),"cache_count":reopened.get_cache_count(),"allow_system_fallback":reopened.allow_system_fallback,"fallback_path":reopened.fallbacks[0].resource_path})
	for entry in config.svg:
		var bitmap = Image.new()
		var status = bitmap.load_svg_from_string(FileAccess.get_file_as_string(entry.source), 1.0)
		if status == OK:
			status = bitmap.save_png(entry.output)
		report.svg.append({"file":entry.file,"status":status})
	FileAccess.open(config.report, FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	quit()
