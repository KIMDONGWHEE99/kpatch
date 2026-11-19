extends SceneTree

# 엔진으로 언어표와 글꼴을 다시 저장하고 즉시 다시 열어 확인합니다.
func _initialize():
	var args = OS.get_cmdline_user_args()
	if not ProjectSettings.load_resource_pack(args[0]):
		quit(2)
		return
	var config = JSON.parse_string(FileAccess.get_file_as_string(args[1]))
	var report = {"translations": [], "fonts": []}
	for entry in config.translations:
		var original = load("res://" + entry.path) as Translation
		var result = original.duplicate() as Translation
		for key in entry.messages:
			result.add_message(key, entry.messages[key])
		if ResourceSaver.save(result, entry.output) != OK:
			quit(3)
			return
		var reopened = ResourceLoader.load(entry.output, "Translation", ResourceLoader.CACHE_MODE_IGNORE)
		var failures = []
		for key in original.get_message_list():
			var expected = entry.messages.get(key, original.get_message(key))
			if reopened.get_message(key) != expected:
				failures.append(key)
		report.translations.append({"path":entry.path, "count":reopened.get_message_count(), "failures":failures})
	for entry in config.fonts:
		var font = load("res://" + entry.path) as FontFile
		var extra = FontFile.new()
		extra.data = FileAccess.get_file_as_bytes(config.korean_font)
		var fallbacks = font.fallbacks.duplicate()
		fallbacks.append(extra)
		font.fallbacks = fallbacks
		if ResourceSaver.save(font, entry.output) != OK:
			quit(4)
			return
		var reopened = ResourceLoader.load(entry.output, "FontFile", ResourceLoader.CACHE_MODE_IGNORE)
		var missing = []
		for character in config.characters:
			if not reopened.has_char(character.unicode_at(0)):
				missing.append(character)
		report.fonts.append({"path":entry.path, "missing":missing, "fallback_count":reopened.fallbacks.size()})
	FileAccess.open(config.report, FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	quit()
