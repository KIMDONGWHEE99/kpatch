extends SceneTree

# 한국어 언어표와 한글 글꼴 자원을 원본과 같은 형식(Godot 4.5 이진 자원)으로 만들고 다시 열어 확인합니다.
# HOW_EMPIRES_WORK의 build_resources.gd와 AGROMATIC_DEMO의 resource_convert.gd를 합쳐 고쳤습니다.
func _initialize():
	var args = OS.get_cmdline_user_args()
	if not ProjectSettings.load_resource_pack(args[0]):
		quit(2)
		return
	var config = JSON.parse_string(FileAccess.get_file_as_string(args[1]))
	var report = {"fonts": [], "translation": {}, "scenes": []}

	# 1. 글꼴: 게임의 일본어 글꼴(NotoSansJP)과 같은 출력 설정을 복사합니다.
	var template = load(config.font_template) as FontFile
	var template_info = ResourceCompatLoader.get_resource_info(config.font_template_file)
	for entry in config.fonts:
		var font = FontFile.new()
		font.data = FileAccess.get_file_as_bytes(entry.source)
		for property in ["antialiasing", "hinting", "subpixel_positioning", "multichannel_signed_distance_field",
				"generate_mipmaps", "force_autohinter", "oversampling", "disable_embedded_bitmaps",
				"keep_rounding_remainders", "msdf_pixel_range", "msdf_size", "allow_system_fallback"]:
			font.set(property, template.get(property))
		var info = ResourceInfo.from_dict(template_info)
		info.set_on_resource(font)
		var error = ResourceCompatLoader.save_custom(font, entry.output, 0, template_info.ver_major, template_info.ver_minor)
		if error != OK:
			push_error("font save failed")
			quit(3)
			return
		var reopened = ResourceLoader.load(entry.output, "FontFile", ResourceLoader.CACHE_MODE_IGNORE) as FontFile
		var missing = []
		for character in config.characters:
			if not reopened.has_char(character.unicode_at(0)):
				missing.append(character)
		report.fonts.append({"path": entry.path, "output_info": ResourceCompatLoader.get_resource_info(entry.output),
			"font_name": reopened.get_font_name(), "style_name": reopened.get_font_style_name(),
			"data_bytes": reopened.data.size(), "data_matches_source": reopened.data == FileAccess.get_file_as_bytes(entry.source),
			"antialiasing": reopened.antialiasing, "hinting": reopened.hinting,
			"subpixel_positioning": reopened.subpixel_positioning, "msdf": reopened.multichannel_signed_distance_field,
			"allow_system_fallback": reopened.allow_system_fallback, "fallbacks": reopened.fallbacks.size(),
			"missing_from_this_font": missing})

	# 2. 언어표: 원본 kr 표의 형식 정보를 그대로 쓰고 세 표(해시·묶음·문자열)만 새로 넣습니다.
	# 새 객체를 GDRE 저장기로 저장하면 형식 이름이 바뀌고 내용이 빠지므로(2026-11-19 시험),
	# 원본 kr 표를 실행 없이 연 틀(fake_load)에 세 표만 바꿔 넣습니다. 형식·버전·식별자·압축이 원본과 같게 남습니다.
	var table_info = ResourceCompatLoader.get_resource_info(config.translation.original)
	var table = ResourceCompatLoader.fake_load(config.translation.original)
	if table == null or String(table.get("locale")) != "kr":
		push_error("original kr translation not available")
		quit(4)
		return
	var hash_table = PackedInt32Array()
	for value in config.translation.hash_table:
		hash_table.append(int(value))
	var bucket_table = PackedInt32Array()
	for value in config.translation.bucket_table:
		bucket_table.append(int(value))
	table.set("hash_table", hash_table)
	table.set("bucket_table", bucket_table)
	table.set("strings", String(config.translation.strings_hex).hex_decode())
	var table_meta = ResourceInfo.from_dict(table_info)
	table_meta.set_on_resource(table)
	if ResourceCompatLoader.save_custom(table, config.translation.output, 0, table_info.ver_major, table_info.ver_minor) != OK:
		push_error("translation save failed")
		quit(4)
		return
	var reopened_table = ResourceLoader.load(config.translation.output, "Translation", ResourceLoader.CACHE_MODE_IGNORE)
	var key_failures = []
	for key in config.translation.expect_by_key:
		if String(reopened_table.get_message(key)) != config.translation.expect_by_key[key]:
			key_failures.append(key)
	report.translation = {"output_info": ResourceCompatLoader.get_resource_info(config.translation.output),
		"class": reopened_table.get_class(), "locale": reopened_table.locale,
		"messages": Array(reopened_table.get_translated_message_list()), "key_failures": key_failures,
		"checked_keys": config.translation.expect_by_key.size()}

	# 3. 장면: 글자로 된 장면(.tscn)을 원본과 같은 형식의 이진 장면(.scn)으로 바꾸고, 다시 글자로 풀어 둡니다.
	for entry in config.scenes:
		var resource = ResourceCompatLoader.fake_load(entry.source)
		if resource == null:
			push_error("scene load failed: " + entry.source)
			quit(5)
			return
		var original_info = ResourceCompatLoader.get_resource_info(entry.original)
		var scene_meta = ResourceInfo.from_dict(original_info)
		scene_meta.set_on_resource(resource)
		var error = ResourceCompatLoader.save_custom(resource, entry.output, 0, original_info.ver_major, original_info.ver_minor)
		if error == OK:
			error = ResourceCompatLoader.to_text(entry.output, entry.roundtrip)
		report.scenes.append({"source": entry.source, "output": entry.output, "error": error,
			"original_info": original_info, "output_info": ResourceCompatLoader.get_resource_info(entry.output) if error == OK else {}})
		if error != OK:
			FileAccess.open(config.report, FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
			quit(6)
			return
	FileAccess.open(config.report, FileAccess.WRITE).store_string(JSON.stringify(report))
	quit()
