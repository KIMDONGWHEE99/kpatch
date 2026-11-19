extends SceneTree

# 원본 글꼴의 속성은 유지하고 한글용 대체 글꼴만 추가합니다.
func _initialize():
	var args = OS.get_cmdline_user_args()
	if not ProjectSettings.load_resource_pack(args[0]):
		push_error("PCK load failed")
		quit(2)
		return
	var config = JSON.parse_string(FileAccess.get_file_as_string(args[1]))
	var report = []
	for entry in config.fonts:
		var font = load("res://" + entry.path) as FontFile
		if font == null:
			quit(3)
			return
		var before = []
		for fallback in font.fallbacks:
			before.append(fallback.resource_path)
		var extra = FontFile.new()
		extra.data = FileAccess.get_file_as_bytes(entry.korean_font)
		extra.antialiasing = TextServer.FONT_ANTIALIASING_GRAY
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
		report.append({"path": entry.path, "original_fallbacks": before, "fallbacks_after": reopened.fallbacks.size(), "missing": missing, "antialiasing": font.antialiasing, "msdf": font.multichannel_signed_distance_field, "size": font.fixed_size})
	FileAccess.open(config.report, FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	quit()
