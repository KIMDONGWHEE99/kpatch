extends SceneTree

# 게임을 실행하지 않고 완성 PCK의 실제 번역 리소스만 다시 읽습니다.
func _initialize():
	var config = JSON.parse_string(FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]))
	if not ProjectSettings.load_resource_pack(config.pack):
		quit(2)
		return
	var output = {}
	for locale in config.locales:
		var resource = load("res://" + config.locales[locale])
		if resource == null:
			quit(3)
			return
		var values = {}
		var keys = config.keys[locale] if resource is OptimizedTranslation else resource.get_message_list()
		for key in keys:
			values[str(key)] = str(resource.get_message(key))
		output[locale] = {"class": resource.get_class(), "locale": resource.locale, "values": values,
			"enumeration": not (resource is OptimizedTranslation)}
	FileAccess.open(config.output, FileAccess.WRITE).store_string(JSON.stringify(output, "\t"))
	quit()
