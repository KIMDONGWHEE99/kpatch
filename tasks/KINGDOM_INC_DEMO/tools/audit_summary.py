"""출처 감사의 실제 범위와 후속 후보 검증 항목을 한 기록에 모읍니다."""
from common import *
from collections import Counter

AUDIT = WORK / "audit"


def main():
    sources = ["asset_classification.json", "code_classification.json", "media_classification.json",
               "key_coverage_original.json", "asset_summary.json", "code_summary.json", "media_summary.json"]
    assets = json.loads((AUDIT/"asset_classification.json").read_text(encoding="utf-8"))
    code = json.loads((AUDIT/"code_classification.json").read_text(encoding="utf-8"))
    media = json.loads((AUDIT/"media_classification.json").read_text(encoding="utf-8"))
    refs = json.loads((AUDIT/"key_coverage_original.json").read_text(encoding="utf-8"))
    objects = json.loads((EXTRACT/"objects.json").read_text(encoding="utf-8"))
    records = {
        "game_id": GAME_ID, "build_id": BUILD,
        "status": "PASS" if all(r["classification"] != "UNKNOWN" for r in assets+code) and
                           all(r["treatment"] != "UNKNOWN" for r in media) else "FAIL",
        "status_scope": "추출한 게임 자산 문자열·Assembly-CSharp 코드 문자열·Texture2D/Sprite 미디어 분류. 후보 번역/글꼴/실행 통과 아님.",
        "asset_locations": len(assets), "code_locations": len(code), "media_locations": len(media),
        "inputs": [{"path": str(AUDIT/name), "sha256": sha(AUDIT/name)} for name in sources],
        "resolved_extraction_errors": {"path": str(EXTRACT/"error_resolutions.json"),
                                       "sha256": sha(EXTRACT/"error_resolutions.json")},
        "direct_asset_translation_count": sum(r["classification"] == "VISIBLE_TRANSLATE" and "expected" in r for r in assets),
        "direct_code_translation_count": sum(r["classification"] == "VISIBLE_TRANSLATE" for r in code),
        "pixel_translation": "sharedassets1.assets/27 Texture2D와 /105 Sprite의 동일 글상자 아이콘",
        "media_review": "텍스처 192개 중 이미지189개를 검수판10장으로 육안 판독. 작은 스프라이트시트3개/글상자아이콘 확대, 빈 동적 글꼴3개는 크기·데이터0 확인.",
        "media_video": {"status": "NOT_APPLICABLE", "evidence": "전체 추출 객체 목록에 VideoClip 형식 0개.", "object_count": len(objects)},
        "visible_keep": ["Kingdom Inc./Leaping Turtle 로고·제작사명·Tom 서명",
                         "원본 생성 인명(문화별 이름 조각·라틴 철자 정리 규칙)",
                         "키보드/마우스 물리 키 식별 표시",
                         "자동저장 실제 파일명",
                         "1000진 큰 수 단위 K/M/B/T/Qa/Qi/Sx/Sp/Oc/Xx",
                         "숫자·좌표·색상채널·정보/경고 아이콘·글리프 아틀라스"],
        "original_missing_keys": [r for r in refs if r["status"] == "FAIL"],
        "library_scope": {
            "status": "제외 근거 기록",
            "full_library_literal_inventory": "NOT_RUN",
            "observed_libraries": [p.name for p in (DATA/"Managed").glob("*.dll") if p.name != "Assembly-CSharp.dll"],
            "evidence": "별도 사용자 게임 로직 DLL 없이 Unity·.NET·Steamworks 라이브러리. 게임 UI의 표시 소비는 Assembly-CSharp/TMP로 추적. InputSystem 표시 키 명칭은 명시적 유지.",
            "urp_debug_evidence": {"path": str(EXTRACT/"trees/globalgamemanagers.assets/2641.json"),
                                   "sha256": sha(EXTRACT/"trees/globalgamemanagers.assets/2641.json"),
                                   "supportRuntimeDebugDisplay": 0, "m_StripDebugVariants": 1},
        },
        "remaining": ["번역표1556키 전체 한국어·독립 후보 재추출 검사",
                      "원본에 누락된 표시 키의 후보 추가/불필요 조합 소비 근거 확인",
                      "직접 문구154위치·코드4위치·글상자아이콘 후보 대조",
                      "실제 생성 인명·큰 수 단위·물리 키 표시의 유지 범위를 결과 안내에 명시",
                      "전체 글꼴·실제 게임 화면 검증"],
    }
    write_json(AUDIT/"source_summary.json", records)
    print({k: records[k] for k in ["status", "asset_locations", "code_locations", "media_locations",
                                  "direct_asset_translation_count", "direct_code_translation_count"]})


if __name__ == "__main__":
    main()
