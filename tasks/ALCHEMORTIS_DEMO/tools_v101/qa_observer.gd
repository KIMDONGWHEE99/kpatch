extends Node

# 검수 사본에서만 읽기 전용 화면 상태와 글꼴·표시 문구를 기록합니다.
var output: String
var last_serial = -1
var timer = 0.0
func _ready():
	output = ProjectSettings.get_setting("korean_qa/output")

func _process(delta):
	timer += delta
	if timer < 0.5:
		return
	timer = 0.0
	var path = output + "/request.json"
	if not FileAccess.file_exists(path):
		return
	var request = JSON.parse_string(FileAccess.get_file_as_string(path))
	if request == null or int(request.serial) == last_serial:
		return
	last_serial = int(request.serial)
	var rows = []
	collect(get_tree().root, rows)
	FileAccess.open(output + "/tree_" + str(last_serial) + ".json",FileAccess.WRITE).store_string(JSON.stringify(rows,"\t"))
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(output + "/screen_" + str(last_serial) + ".png")

func collect(node: Node, rows: Array):
	var r = {"path":str(node.get_path()),"class":node.get_class()}
	if node is Control:
		r["visible"] = node.is_visible_in_tree()
		r["rect"] = [node.global_position.x,node.global_position.y,node.size.x,node.size.y]
		if node is Label or node is RichTextLabel or node is Button:
			r["text"] = node.text
			r["translated"] = node.tr(node.text)
			var font = node.get_theme_font("normal_font" if node is RichTextLabel else "font")
			r["font"] = font.resource_path
			r["font_size"] = node.get_theme_font_size("normal_font_size" if node is RichTextLabel else "font_size")
			var missing = []
			for c in r.translated:
				if c.unicode_at(0)>127 and not font.has_char(c.unicode_at(0)):
					missing.append(c)
			r["missing"] = missing
	rows.append(r)
	for child in node.get_children():
		collect(child,rows)
