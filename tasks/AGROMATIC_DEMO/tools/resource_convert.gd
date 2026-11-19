extends SceneTree

# GDRE의 호환 로더를 써서 스크립트 실행 없이 자산을 재저장합니다.
func _initialize():
	var args = OS.get_cmdline_user_args()
	var config = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var report = []
	for entry in config.entries:
		var error: int
		var original_info: Dictionary = {}
		if entry.get("mode", "binary") == "text":
			error = ResourceCompatLoader.to_text(entry.source, entry.output)
		elif entry.has("original"):
			var resource = ResourceCompatLoader.fake_load(entry.source)
			if resource == null:
				quit(3)
				return
			# 원본의 엔진 버전·자산 식별자·파일 형식을 유지합니다.
			original_info = ResourceCompatLoader.get_resource_info(entry.original)
			var info = ResourceInfo.from_dict(original_info)
			info.set_on_resource(resource)
			error = ResourceCompatLoader.save_custom(resource, entry.output, 0, original_info.ver_major, original_info.ver_minor)
		else:
			error = ResourceCompatLoader.to_binary(entry.source, entry.output)
		var output_info = ResourceCompatLoader.get_resource_info(entry.output) if error == OK else {}
		report.append({"source": entry.source, "output": entry.output, "error": error,
			"original_info": original_info, "output_info": output_info})
		if error != OK:
			FileAccess.open(config.report, FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
			quit(2)
			return
	FileAccess.open(config.report, FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	quit()
