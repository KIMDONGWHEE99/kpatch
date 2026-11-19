extends Node

# 검수 사본의 실제 실행 경로·저장 경로를 실행 중 관찰합니다.
func _ready():
	var report = {"user_data_dir": OS.get_user_data_dir(), "executable_path": OS.get_executable_path(),
		"process_id": OS.get_process_id(), "locale": TranslationServer.get_locale(),
		"time_utc": Time.get_datetime_string_from_system(true), "graphics_adapter": RenderingServer.get_video_adapter_name()}
	var path = ProjectSettings.get_setting("korean_qa/identity_path", "")
	if not path.is_empty():
		FileAccess.open(path, FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	print("KOREAN_QA_IDENTITY " + JSON.stringify(report))
