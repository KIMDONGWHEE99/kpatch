extends SceneTree

# 후보에서 꺼낸 이진 장면(.scn)을 글자 형식(.tscn)으로 풀어 독립 비교에 씁니다. 실행은 하지 않습니다.
func _initialize():
	var args = OS.get_cmdline_user_args()
	var config = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var report = []
	for entry in config.scenes:
		var error = ResourceCompatLoader.to_text(entry.source, entry.output)
		report.append({"source": entry.source, "error": error, "info": ResourceCompatLoader.get_resource_info(entry.source)})
	FileAccess.open(config.report, FileAccess.WRITE).store_string(JSON.stringify(report))
	quit()
