extends SceneTree

# 기존 언어 슬롯의 키를 그대로 보존하며 번역 자산을 만듭니다.
func _initialize():
	var config = JSON.parse_string(FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]))
	var values = JSON.parse_string(FileAccess.get_file_as_string(config.values))
	var source = Translation.new()
	source.locale = config.locale
	for key in values:
		source.add_message(key, values[key])
	var resource = source
	var original_info = ResourceCompatLoader.get_resource_info(config.original)
	original_info.type = "Translation"
	ResourceInfo.from_dict(original_info).set_on_resource(resource)
	if ResourceCompatLoader.save_custom(resource, config.output, 0, original_info.ver_major, original_info.ver_minor) != OK:
		quit(2)
		return
	var observed = ResourceLoader.load(config.output, "Translation", ResourceLoader.CACHE_MODE_IGNORE)
	var actual = {}
	for key in values:
		actual[key] = str(observed.get_message(key))
	FileAccess.open(config.report, FileAccess.WRITE).store_string(JSON.stringify({"locale": observed.locale,
		"values": actual, "keys": values.size(), "resource_class": observed.get_class(),
		"output_resource_info": ResourceCompatLoader.get_resource_info(config.output)}, "\t"))
	quit()
