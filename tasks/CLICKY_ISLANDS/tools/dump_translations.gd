extends SceneTree

# 압축 언어표(OptimizedTranslation)의 해시 표·묶음 표와 칸 순서대로의 문구를 그대로 내보냅니다.
# 이 형식은 키 이름을 저장하지 않으므로, 키 이름 대신 "칸 위치"를 기준으로 삼습니다.
func _initialize():
	var args = OS.get_cmdline_user_args()
	if not ProjectSettings.load_resource_pack(args[0]):
		quit(2)
		return
	var config = JSON.parse_string(FileAccess.get_file_as_string(args[1]))
	var report = {}
	for path in config.translations:
		var table = ResourceLoader.load(path, "Translation", ResourceLoader.CACHE_MODE_IGNORE)
		if table == null:
			report[path] = {"error": "load failed"}
			continue
		var strings: PackedByteArray = table.get("strings")
		report[path] = {"class": table.get_class(), "locale": table.locale,
			"hash_table": Array(table.get("hash_table")), "bucket_table": Array(table.get("bucket_table")),
			"strings_size": strings.size(), "strings_hex": strings.hex_encode(),
			"messages": Array(table.get_translated_message_list())}
	FileAccess.open(config.report, FileAccess.WRITE).store_string(JSON.stringify(report))
	quit()
