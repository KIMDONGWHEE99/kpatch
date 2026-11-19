extends SceneTree

# 복원 이미지가 아니라 게임에 실제 포함된 텍스처를 펼칩니다.
func _initialize():
	var args = OS.get_cmdline_user_args()
	if not ProjectSettings.load_resource_pack(args[0]):
		quit(2)
		return
	var config = JSON.parse_string(FileAccess.get_file_as_string(args[1]))
	var report = []
	var failures = 0
	for entry in config.entries:
		var texture = load("res://" + entry.path)
		if texture == null or not texture is Texture2D:
			report.append({"path": entry.path, "status": "FAIL", "reason": "texture_load"})
			failures += 1
			continue
		var pixels = texture.get_image()
		if pixels == null:
			report.append({"path": entry.path, "status": "FAIL", "reason": "image_load"})
			failures += 1
			continue
		if pixels.is_compressed():
			if pixels.decompress() != OK:
				failures += 1
				report.append({"path": entry.path, "status": "FAIL", "reason": "decompress"})
				continue
		var result = pixels.save_png(entry.output)
		report.append({"path": entry.path, "status": "PASS" if result == OK else "FAIL", "width": pixels.get_width(), "height": pixels.get_height(), "output": entry.output})
		if result != OK:
			failures += 1
	FileAccess.open(config.report, FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	quit(0 if failures == 0 else 3)
