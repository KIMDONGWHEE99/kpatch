extends SceneTree

func hash_bytes(data: PackedByteArray) -> String:
	var context = HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(data)
	return context.finish().hex_encode()

# 실제 후보 안의 글꼴을 다시 읽고 필요한 글자가 실제 글리프로 연결되는지 검사합니다.
func _initialize():
	var args = OS.get_cmdline_user_args()
	if not ProjectSettings.load_resource_pack(args[0]):
		quit(2)
		return
	var config = JSON.parse_string(FileAccess.get_file_as_string(args[1]))
	var data = FileAccess.get_file_as_bytes("res://" + config.resource)
	if data.is_empty():
		quit(3)
		return
	var font = FontFile.new()
	font.data = data
	font.antialiasing = TextServer.FONT_ANTIALIASING_NONE
	var missing = []
	var glyphs = []
	for character in config.characters:
		var code = character.unicode_at(0)
		var glyph = font.get_glyph_index(12, code, 0)
		if not font.has_char(code) or glyph == 0:
			missing.append(character)
		glyphs.append({"character": character, "code": code, "glyph_index": glyph})
	var report = {"resource": config.resource, "load_method": "FontFile.new + FileAccess bytes", "font_data_sha256": hash_bytes(font.data), "missing": missing, "glyphs": glyphs}
	FileAccess.open(config.report, FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	quit(0 if missing.is_empty() and report.font_data_sha256 == config.expected_data_sha256 else 4)
