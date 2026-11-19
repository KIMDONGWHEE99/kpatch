extends SceneTree

func hash_bytes(data: PackedByteArray) -> String:
	var context = HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(data)
	return context.finish().hex_encode()

func serialize_value(value):
	if value is PackedByteArray:
		return {"type": "bytes", "size": value.size(), "sha256": hash_bytes(value)}
	if value is Resource:
		return {"type": value.get_class(), "path": value.resource_path}
	return {"type": typeof(value), "value": var_to_str(value)}

func observe_font(path: String, characters: Array) -> Dictionary:
	var font = ResourceLoader.load(path, "FontFile", ResourceLoader.CACHE_MODE_IGNORE) as FontFile
	if font == null:
		return {"error": "font_load_failed", "path": path}
	var properties = {}
	for property in font.get_property_list():
		if int(property.usage) & PROPERTY_USAGE_STORAGE and property.name != "fallbacks":
			properties[property.name] = serialize_value(font.get(property.name))
	var fallbacks = []
	for fallback in font.fallbacks:
		var row = {"class": fallback.get_class()}
		if fallback is FontFile:
			row.data_sha256 = hash_bytes(fallback.data)
			row.antialiasing = fallback.antialiasing
		fallbacks.append(row)
	var missing = []
	for character in characters:
		if not font.has_char(String(character).unicode_at(0)):
			missing.append(character)
	return {"path": path, "font_data_sha256": hash_bytes(font.data), "properties": properties,
		"fallbacks": fallbacks, "missing": missing,
		"resource_info": ResourceCompatLoader.get_resource_info(path)}

# 실제 PCK에서 독립 추출한 FontFile을 재열고 모든 저장 속성을 비교할 자료를 읽는다.
func _initialize():
	var args = OS.get_cmdline_user_args()
	var config = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var fonts = []
	for row in config.fonts:
		fonts.append({"resource": row.resource,
			"original": observe_font(row.original, []),
			"candidate": observe_font(row.candidate, config.characters)})
	var title = FontFile.new()
	title.data = FileAccess.get_file_as_bytes(config.title)
	title.antialiasing = TextServer.FONT_ANTIALIASING_NONE
	var glyphs = []
	var missing = []
	for character in config.title_text:
		var code: int = character.unicode_at(0)
		var glyph = title.get_glyph_index(12, code, 0)
		if not title.has_char(code) or glyph == 0:
			missing.append(character)
		glyphs.append({"character": character, "code": code, "glyph": glyph})
	var result = {"fonts": fonts, "title": {"data_sha256": hash_bytes(title.data),
		"glyphs": glyphs, "missing": missing, "load_method": "FontFile.new + FileAccess bytes"}}
	FileAccess.open(config.report, FileAccess.WRITE).store_string(JSON.stringify(result, "\t"))
	quit()
