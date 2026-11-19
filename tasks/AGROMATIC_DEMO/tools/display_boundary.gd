

var _korean_display_pairs: Dictionary = {}
var _korean_display_patterns: Array = []
var _korean_display_codes: Dictionary = {}
var _korean_display_codes_loaded: bool = false

func _translate_display_code(text: String, context: String) -> String:
	# 저장·검색에 쓰는 식별자 대신 화면에 전달할 복사본만 번역합니다.
	if not _korean_display_codes_loaded:
		_korean_display_codes_loaded = true
		var data = JSON.parse_string(FileAccess.get_file_as_string("res://data/translations/display_codes_ko.json"))
		if data is Dictionary:
			_korean_display_codes = data
	var values: Dictionary = _korean_display_codes.get(context, {})
	return str(values.get(text, text))

func translate_category(category: String, fallback: String = "") -> String:
	var result = _translate_display_code(category, "category")
	return fallback if result == category and not fallback.is_empty() else result

func translate_categories(categories: Array, separator: String = ", ") -> String:
	var translated: Array[String] = []
	for category in categories:
		translated.append(translate_category(str(category)))
	return separator.join(translated)

func translate_research_type(target_type: String) -> String:
	return _translate_display_code(target_type, "research_type")

func translate_worker_type(worker_type: String, short_format: bool = false, fallback: String = "") -> String:
	var result = _translate_display_code(worker_type, "worker_short" if short_format else "worker_full")
	return worker_type.capitalize() + fallback if result == worker_type else result

func translate_job_field(field: String) -> String:
	return _translate_display_code(field, "job_field")

func translate_loading_phase(phase: String) -> String:
	return _translate_display_code(phase, "loading_phase")

func translate_display(text: String) -> String:
	# 동작에 쓰는 원래 값은 보존하고 표시 사본만 바꿉니다.
	if _korean_display_pairs.is_empty():
		var data = JSON.parse_string(FileAccess.get_file_as_string("res://data/translations/display_ko.json"))
		if data is Dictionary:
			_korean_display_pairs = data
			var keys = data.keys()
			keys.sort_custom(func(a, b): return a.length() > b.length())
			for source in keys:
				if source.length() < 4:
					continue
				var pattern = RegEx.new()
				var escaped = ""
				for character in source:
					if character in "\\.^$|?*+()[]{}":
						escaped += "\\"
					escaped += character
				var left_guard = "(?<![A-Za-z0-9_])" if source.left(1) in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_" else ""
				var right_guard = "(?![A-Za-z0-9_])" if source.right(1) in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_" else ""
				if pattern.compile(left_guard + escaped + right_guard) == OK:
					_korean_display_patterns.append([pattern, data[source]])
	if _korean_display_pairs.has(text):
		return _korean_display_pairs[text]
	var result = text
	for entry in _korean_display_patterns:
		result = entry[0].sub(result, entry[1], true)
	return result
