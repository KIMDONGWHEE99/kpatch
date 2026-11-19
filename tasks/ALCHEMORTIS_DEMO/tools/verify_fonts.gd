extends SceneTree

# 원본과 저장된 후보를 각각 다시 열어 폴백 이외의 속성·원본 글꼴 데이터를 대조합니다.
func _initialize():
	var args = OS.get_cmdline_user_args()
	if not ProjectSettings.load_resource_pack(args[0]):
		quit(2)
		return
	var config = JSON.parse_string(FileAccess.get_file_as_string(args[1]))
	var rows = []
	for entry in config.fonts:
		var before = load("res://" + entry.path) as FontFile
		var after = ResourceLoader.load(entry.output, "FontFile", ResourceLoader.CACHE_MODE_IGNORE)
		var differences = []
		for property in before.get_property_list():
			var key = property.name
			if key in ["fallbacks", "resource_path", "resource_local_to_scene", "resource_scene_unique_id"] or not (property.usage & PROPERTY_USAGE_STORAGE):
				continue
			if before.get(key) != after.get(key):
				differences.append(key)
		var missing = []
		for character in config.characters:
			if not after.has_char(character.unicode_at(0)):
				missing.append(character)
		rows.append({"path": entry.path, "differences": differences, "missing": missing, "original_data_sha256": before.data.hex_encode().sha256_text(), "candidate_data_sha256": after.data.hex_encode().sha256_text(), "fallback_count": after.fallbacks.size()})
	FileAccess.open(args[2], FileAccess.WRITE).store_string(JSON.stringify(rows, "\t"))
	quit()
