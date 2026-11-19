extends SceneTree

# 새 벡터를 엔진으로 렌더링하고 엔진의 무손실 텍스처 형식으로 저장합니다.
func _initialize():
	var args = OS.get_cmdline_user_args()
	var config = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var report = []
	for entry in config.entries:
		var image = Image.new()
		if image.load_svg_from_string(FileAccess.get_file_as_string(entry.source)) != OK:
			quit(2)
			return
		image.convert(Image.FORMAT_RGBA8)
		image.save_png(entry.png)
		var png = "PNG ".to_utf8_buffer()
		png.append_array(image.save_png_to_buffer())
		var file = FileAccess.open(entry.output, FileAccess.WRITE)
		file.store_buffer("GST2".to_utf8_buffer())
		file.store_32(1)
		file.store_32(image.get_width())
		file.store_32(image.get_height())
		file.store_32(0)
		file.store_32(0xFFFFFFFF)
		file.store_32(0)
		file.store_32(0)
		file.store_32(0)
		file.store_32(1)
		file.store_16(image.get_width())
		file.store_16(image.get_height())
		file.store_32(0)
		file.store_32(Image.FORMAT_RGBA8)
		file.store_32(png.size())
		file.store_buffer(png)
		file.close()
		var texture = CompressedTexture2D.new()
		var result = texture.load(entry.output)
		var observed = texture.get_image()
		if result != OK or observed == null or observed.get_data() != image.get_data():
			quit(3)
			return
		report.append({"source": entry.source, "output": entry.output, "width": image.get_width(), "height": image.get_height(), "pixel_roundtrip": "PASS"})
	FileAccess.open(config.report, FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	quit()
