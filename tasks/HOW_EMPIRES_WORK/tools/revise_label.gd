extends SceneTree

func _initialize():
	var args = OS.get_cmdline_user_args()
	ProjectSettings.load_resource_pack(args[0])
	var actual = load("res://" + args[1]) as Translation
	actual.add_message("PROVINCE_INITIAL", "주: ")
	var status = ResourceSaver.save(actual, args[2])
	quit(0 if status == OK else 2)
