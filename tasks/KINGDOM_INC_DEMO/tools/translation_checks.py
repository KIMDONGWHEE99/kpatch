"""위치·토큰·강조·태그·줄바꿈을 비교하고 결함 탐지 자체도 시험합니다."""
from common import *
from collections import Counter
import re

def controls(source, target):
    if source.strip() and not target.strip():
        raise ValueError("빈 번역")
    tokens = r"(?<!\{)\{[^{}]*\}(?!\})"
    if Counter(re.findall(tokens, source)) != Counter(re.findall(tokens, target)):
        raise ValueError("자리표시자 불일치")
    if re.findall(r"\\n|\r\n|\r|\n", source) != re.findall(r"\\n|\r\n|\r|\n", target):
        raise ValueError("제어 줄바꿈 불일치")
    # # 강조는 Translation.Translate의 정규식이 소비합니다.
    if source.count("#") != target.count("#") or target.count("#") % 2:
        raise ValueError("강조 구분자 불일치")
    tag_pattern = r"<(/?)([A-Za-z][A-Za-z0-9]*)([^>]*)>"
    a = re.findall(tag_pattern, source)
    b = re.findall(tag_pattern, target)
    if a != b:
        raise ValueError("태그·속성·순서 불일치")
    for text in (source, target):
        stack = []
        for closing, name, attrs in re.findall(tag_pattern, text):
            if name.lower() in ("sprite", "br", "space", "page", "pos") or attrs.endswith("/"):
                continue
            if closing:
                if not stack or stack.pop() != name.lower():
                    raise ValueError("태그 중첩 오류")
            else:
                stack.append(name.lower())
        if stack:
            raise ValueError("닫히지 않은 태그")

def check_rows(rows, expected):
    if len(rows) != len(expected):
        raise ValueError("위치 개수 불일치")
    for row, old in zip(rows, expected):
        if any(row[k] != old[k] for k in ("index", "key", "source")):
            raise ValueError("번역 위치 교환 또는 원본 불일치")
        controls(row["source"], row["target"])

def self_test():
    good = {"index":0,"key":"test","source":"<b>#{0}#</b>\\nA","target":"<b>#{0}#</b>\\n가"}
    check_rows([good], [good])
    bad = ["", "<b>#{1}#</b>\\n가", "<b>#{0}#</b>가", "<i>#{0}#</i>\\n가",
           "<b>{0}</b>\\n가"]
    for target in bad:
        try:
            check_rows([{**good,"target":target}], [good])
        except ValueError:
            pass
        else:
            raise AssertionError(target)
    try:
        controls("<b><i>X</b></i>", "<b><i>가</b></i>")
    except ValueError:
        pass
    else:
        raise AssertionError("동일한 잘못된 중첩도 거부해야 합니다")
    return {"normal":"PASS","mutations_rejected":len(bad)+1}

if __name__ == "__main__":
    print(self_test())
