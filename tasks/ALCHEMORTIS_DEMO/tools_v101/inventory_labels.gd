extends Node2D

# 한국어에서만 그림 속 영문 위에 게임의 실제 글꼴로 번역 문구를 표시합니다.
func _ready():
	_update_language()

func _notification(what):
	if what == NOTIFICATION_TRANSLATION_CHANGED:
		_update_language()

func _update_language():
	visible = TranslationServer.get_locale().begins_with("ko")
