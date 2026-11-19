extends SceneTree

# 복원된 CSV의 키를 실제 원본 번역 자산에서 독립 조회합니다.
func _initialize():
	var args = OS.get_cmdline_user_args()
	var config = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	if not ProjectSettings.load_resource_pack(config.pack):
		quit(2)
		return
	var keys = JSON.parse_string(FileAccess.get_file_as_string(config.keys))
	var report = {}
	for locale in config.locales:
		var resource = load("res://" + config.locales[locale])
		if resource == null:
			quit(3)
			return
		var values = {}
		for key in keys:
			values[key] = str(resource.get_message(key))
		report[locale] = {"resource_class": resource.get_class(), "locale": resource.locale, "values": values}
	FileAccess.open(config.output, FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	quit()
