extends SceneTree

# 원본 자원의 형식·엔진 버전과 언어표·글꼴의 실제 속성을 읽기만 합니다.
func _initialize():
	var args = OS.get_cmdline_user_args()
	if not ProjectSettings.load_resource_pack(args[0]):
		quit(2)
		return
	var config = JSON.parse_string(FileAccess.get_file_as_string(args[1]))
	var report = {"engine": Engine.get_version_info(), "resources": [], "translations": [], "fonts": []}
	for path in config.resources:
		report.resources.append({"path": path, "info": ResourceCompatLoader.get_resource_info("res://" + path)})
	for path in config.translations:
		var table = load("res://" + path) as Translation
		if table == null:
			report.translations.append({"path": path, "error": "load failed"})
			continue
		var filled = 0
		var probe = {}
		for key in config.keys:
			var value = table.get_message(key)
			probe[key] = String(value)
			if String(value) != "":
				filled += 1
		report.translations.append({"path": path, "class": table.get_class(), "locale": table.locale,
			"message_count": table.get_message_count(), "probe_filled": filled, "probe": probe if config.keys.size() <= 12 else {}})
	for path in config.fonts:
		var font = load("res://" + path) as FontFile
		if font == null:
			report.fonts.append({"path": path, "error": "load failed"})
			continue
		var fallbacks = []
		for fallback in font.fallbacks:
			fallbacks.append(fallback.resource_path)
		report.fonts.append({"path": path, "font_name": font.get_font_name(), "style_name": font.get_font_style_name(),
			"data_bytes": font.data.size(), "antialiasing": font.antialiasing, "hinting": font.hinting,
			"subpixel_positioning": font.subpixel_positioning, "msdf": font.multichannel_signed_distance_field,
			"generate_mipmaps": font.generate_mipmaps, "allow_system_fallback": font.allow_system_fallback,
			"force_autohinter": font.force_autohinter, "oversampling": font.oversampling,
			"fixed_size": font.fixed_size, "disable_embedded_bitmaps": font.disable_embedded_bitmaps,
			"keep_rounding_remainders": font.keep_rounding_remainders, "msdf_pixel_range": font.msdf_pixel_range,
			"msdf_size": font.msdf_size, "cache_count": font.get_cache_count(), "fallbacks": fallbacks,
			"has_hangul": font.has_char(0xD55C), "has_latin": font.has_char(0x41)})
	FileAccess.open(config.report, FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	quit()
