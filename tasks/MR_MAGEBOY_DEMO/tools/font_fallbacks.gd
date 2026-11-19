extends SceneTree

func hash_bytes(data: PackedByteArray) -> String:
	var context = HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(data)
	return context.finish().hex_encode()

# 본문·굵은 글꼴의 원본 속성을 보존하고 한글 대체 글꼴만 연결합니다.
func _initialize():
	var args = OS.get_cmdline_user_args()
	if not ProjectSettings.load_resource_pack(args[0]):
		quit(2)
		return
	var config = JSON.parse_string(FileAccess.get_file_as_string(args[1]))
	var report = []
	for entry in config.fonts:
		var font = load("res://" + entry.path) as FontFile
		if font == null:
			quit(3)
			return
		var original_data = hash_bytes(font.data)
		var original_info = ResourceCompatLoader.get_resource_info("res://" + entry.path)
		var properties = {"antialiasing": font.antialiasing, "msdf": font.multichannel_signed_distance_field,
			"fixed_size": font.fixed_size, "hinting": font.hinting, "subpixel_positioning": font.subpixel_positioning,
			"force_autohinter": font.force_autohinter, "generate_mipmaps": font.generate_mipmaps}
		var before = []
		for existing in font.fallbacks:
			before.append(existing.resource_path)
		var extra = FontFile.new()
		extra.data = FileAccess.get_file_as_bytes(entry.korean_font)
		extra.antialiasing = TextServer.FONT_ANTIALIASING_GRAY
		var fallbacks = font.fallbacks.duplicate()
		fallbacks.append(extra)
		font.fallbacks = fallbacks
		ResourceInfo.from_dict(original_info).set_on_resource(font)
		if ResourceCompatLoader.save_custom(font, entry.output, 0, original_info.ver_major, original_info.ver_minor) != OK:
			quit(4)
			return
		var reopened = ResourceLoader.load(entry.output, "FontFile", ResourceLoader.CACHE_MODE_IGNORE)
		if reopened == null or hash_bytes(reopened.data) != original_data:
			quit(5)
			return
		var missing = []
		for character in config.characters:
			if not reopened.has_char(character.unicode_at(0)):
				missing.append(character)
		var observed = {"antialiasing": reopened.antialiasing, "msdf": reopened.multichannel_signed_distance_field,
			"fixed_size": reopened.fixed_size, "hinting": reopened.hinting, "subpixel_positioning": reopened.subpixel_positioning,
			"force_autohinter": reopened.force_autohinter, "generate_mipmaps": reopened.generate_mipmaps}
		if observed != properties or reopened.fallbacks.size() != before.size() + 1:
			quit(6)
			return
		report.append({"path": entry.path, "original_font_data_sha256": original_data,
			"original_properties": properties, "reopened_properties": observed,
			"original_fallbacks": before, "fallbacks_after": reopened.fallbacks.size(), "missing": missing,
			"original_resource_info": original_info, "output_resource_info": ResourceCompatLoader.get_resource_info(entry.output)})
	FileAccess.open(config.report, FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	quit()
