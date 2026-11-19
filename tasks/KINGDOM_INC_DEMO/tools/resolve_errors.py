"""초기 추출 오류를 대체 해석과 빈 동적 텍스처 근거로 해결합니다."""
from common import *
from inventory import walk
errors = json.loads((EXTRACT/"errors.json").read_text(encoding="utf-8"))
results, added = [], []
for row in errors:
    try:
        env = load_asset(DATA / row["file"])
        obj = env.file.objects[row["path_id"]]
        tree = read_tree(obj)
        if row["type"] == "Texture2D":
            assert tree["m_Width"] == tree["m_Height"] == tree["m_CompleteImageSize"] == 0
            assert not tree["image data"] and tree["m_StreamData"]["size"] == 0
            result = "폭·높이·이미지·스트림이 모두 0인 실행 시 생성 글꼴 텍스처. 픽셀 원문 없음."
        else:
            write_json(EXTRACT/"trees"/row["file"]/f'{row["path_id"]}.json', tree)
            for field, value in walk(tree):
                added.append({**row, "id":row["id"]+field, "field":field, "source":value, "classification":"UNKNOWN"})
            result = "실제 관리 어셈블리 또는 Unity 6.3 추가 필드로 객체 전체 길이 해석 성공."
        results.append({**row, "status":"PASS", "resolution":result})
    except Exception as exc:
        results.append({**row, "status":"FAIL", "resolution_error":str(exc)})
write_json(EXTRACT/"error_resolutions.json", results)
write_json(EXTRACT/"additional_strings.json", added)
print(json.dumps(results, ensure_ascii=False))
