extends SceneTree

# 후보 자산을 읽기만 하며 스크립트 실행 없이 표시 속성을 복원합니다.
func _initialize():
	var args = OS.get_cmdline_user_args()
	if args.size() != 1:
		quit(2)
		return
	var config = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var report = []
	for entry in config.entries:
		var error = ResourceCompatLoader.to_text(entry.source, entry.output)
		report.append({"source": entry.source, "output": entry.output, "error": error})
		if error != OK:
			FileAccess.open(config.report, FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
			quit(3)
			return
	FileAccess.open(config.report, FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	quit()
