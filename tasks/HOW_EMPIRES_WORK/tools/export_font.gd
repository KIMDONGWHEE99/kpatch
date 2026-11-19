extends SceneTree

func _initialize():
	var args = OS.get_cmdline_user_args()
	var font = FontFile.new()
	font.data = FileAccess.get_file_as_bytes(args[0])
	if not font.has_char("简".unicode_at(0)):
		quit(2)
		return
	if ResourceSaver.save(font, args[1]) != OK:
		quit(3)
		return
	quit()
