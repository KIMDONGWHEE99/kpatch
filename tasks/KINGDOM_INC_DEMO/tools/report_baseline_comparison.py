"""실제로 판독한 원본/rc4 화면과 종료 기록의 비교 근거를 묶습니다."""
from datetime import datetime, timezone
from collections import Counter
import json
from common import ROOT, WORK, SOURCE, sha, write_json

BASE = WORK / "original_qa/qa_original_qa"
RC4 = WORK / "full_rc4/qa_full_rc4"


def evidence(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def identity(session):
    preparation = read(session / "preparation.json")
    game = session.parent / "game"
    return {
        "runtime": read(session / "runtime.json"),
        "evidence": {name: evidence(session / name) for name in [
            "runtime.json", "preparation.json", "candidate-manifest.json",
            "prepared-manifest.json", "assembly-boundary.json", "session-check.json",
            "Player.log", "messages.jsonl", "user-before.json", "user-after.json"]},
        "support": evidence(game / "KingdomInc_Data/Managed/KoreanQA.dll"),
        "support_matches_preparation": sha(game / "KingdomInc_Data/Managed/KoreanQA.dll") == preparation["support_sha256"],
        "prepared_manifest_matches_preparation": sha(session / "prepared-manifest.json") == preparation["prepared_manifest_sha256"],
        "session_result": read(session / "session-check.json"),
    }


def image_evidence(session, stem):
    return {kind: evidence(session / (stem + ext)) for kind, ext in
            [("image", ".png"), ("capture", ".json"), ("command_result", ".result.json")]}


pairs = [
    ("첫 메뉴", "232603_7519700_main_menu", "231437_4173200_main_menu", "PASS",
     "메뉴 5개와 데모 버전 표시가 같은 위치에서 정상 출력된다. 원본 픽셀 글꼴과 후보 한글 글꼴의 외형 차이는 의도된 변경이다."),
    ("첫 수동 제련", "232618_7743700_manual_craft", "231456_8609800_manual_craft", "PASS",
     "양쪽 모두 철 주괴 1개 생산 뒤 격자와 하단 HUD가 나타났다. 제련소/제련 버튼만 번역되며 화면 구조가 같다. 재화가 0일 때 상단 숫자가 없는 현상도 같다."),
    ("아이템 상점 기술 카드", "232708_5921700_focus_tech", "231654_3879500_focus_tech", "PASS",
     "원본 영문 설명도 오른쪽 상점 그림 위에 겹친다. rc4는 설명 폭·높이·줄 간격의 공용 수정으로 문구와 그림이 분리되어 정상 출력된다. 화면 가장자리의 다른 카드는 검수 대상이 아니다."),
    ("잠긴 숲", "232834_9991700_forest_select", "231851_1860100_forest_select", "PASS",
     "양쪽 모두 가동률 999%와 숲 통제권 회복 조건을 표시한다. 이는 잠긴 상태에서 원본도 보이는 값이며 패치 고유 오류가 아니다. 원본 첫 탭 Hunters 오기는 후보에서 채집꾼으로 의미 교정되어 있다."),
    ("전쟁 진행", "232853_8855500_war_fixture", "232102_5335700_war_fixture", "PASS",
     "양쪽 모두 밀려나는 전황과 비르겐발트 학술원 탈환 57%, 병사 3명을 표시한다. 실제 전쟁 승리 과정이 아니라 같은 격리 상태의 출력 비교다."),
    ("전쟁 점령 완료", "232854_3660900_war_fixture", "232104_0011900_war_fixture", "PASS",
     "양쪽 모두 지역 장악도 100%, 적 병력 감소, 엔스머스 확보 알림을 표시한다."),
    ("전쟁 방어", "232856_0224100_war_fixture", "232106_9026800_war_fixture", "PASS",
     "양쪽 모두 적 재집결 안내와 엔스머스 적 발견 알림을 표시한다."),
    ("전쟁 통제권 상실", "232857_0120300_war_fixture", "232107_5433000_war_fixture", "PASS",
     "양쪽 모두 비르겐발트 학술원 통제권 상실 알림과 현재 작전 49%를 표시한다. 실시간 병사 체력·훈장 수의 소폭 차이는 진행 시점 차이다."),
    ("감정사 숫자 입력 안내", "232924_9547000_appraiser", "232145_9621000_appraiser", "FAIL",
     "원본 Value는 능력치 비교를 위한 숫자 입력 안내다. rc4 가치 번역은 문맥에 맞지 않으므로 값으로 교정해야 한다. 기존 결함 기록을 유지하며 rc5 재검수가 필요하다."),
    ("회계사 숫자 입력 안내", "232927_8043800_accountant", "232148_4749300_accountant", "FAIL",
     "원본 Value는 비교 조건의 숫자 입력 안내다. 감정사와 같은 AppraiserValue 공용 번역을 사용하므로 rc4 가치 오류와 수정 범위가 같다."),
    ("데모 감사 화면", "232948_8992800_demo_end", "232251_0635500_demo_end", "PASS",
     "양쪽 모두 데모 감사·출시 예정일·메뉴/계속 버튼을 표시한다. 전쟁 알림이 본문 위에 겹치는 현상도 동일하다. 이 비교 PASS는 가려진 본문 전체 판독 PASS가 아니며 rc5에서 알림 없는 상태를 다시 확인해야 한다."),
]

base_identity, rc4_identity = identity(BASE), identity(RC4)
base_manifest = read(BASE / "candidate-manifest.json")
original_mismatches = []
for relative, expected in base_manifest.items():
    original = SOURCE / relative
    if not original.is_file() or sha(original) != expected["sha256"]:
        original_mismatches.append(relative)
base_log = (BASE / "Player.log").read_text(encoding="utf-8-sig")
rc4_log = (RC4 / "Player.log").read_text(encoding="utf-8-sig")
messages = [
    ("d3d12: failed to query info queue interface (0x80004002).", "그래픽 초기화",
     "두 실행의 같은 그래픽 초기화 단계에서 각 1회 발생한다. 동일 GPU/드라이버 환경의 공통 기록이며 패치 고유 로딩 오류로 분류하지 않는다."),
    ("GarbageCollector disposing of ComputeBuffer. Please use ComputeBuffer.Release() or .Dispose() to manually release the buffer.",
     "정상 종료 후",
     "두 실행 모두 EXITING 및 입력 시스템 Shutdown 뒤 마지막 줄에서 각 1회 발생한다. 같은 원본+검수 지원 환경에서 재현되는 종료 자원 정리 경고다. 이 비교만으로 경고를 일으키는 원본/엔진/지원 코드의 정확한 소유자를 단정하지 않는다."),
]
common_messages = []
for message, phase, note in messages:
    lines = {}
    for label, content in [("original", base_log), ("rc4", rc4_log)]:
        lines[label] = [i for i, line in enumerate(content.splitlines(), 1) if message in line]
    common_messages.append({"message": message, "phase": phase, "line_numbers": lines,
                            "counts": {"original": base_log.count(message), "rc4": rc4_log.count(message)},
                            "classification": "BASELINE_COMMON", "reason": note})

def message_summary(session):
    rows = [json.loads(line) for line in (session / "messages.jsonl").read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    return {"types": dict(Counter(row["type"] for row in rows)),
            "messages": [{"type": row["type"], "message": row["message"], "stack": row["stack"]} for row in rows]}

report = {
    "status": "PASS",
    "scope": "동일 지원 DLL을 사용한 원본 영문과 rc4의 대표 화면 11쌍을 실제 view_image로 판독하고 로그 원인을 분리한 비교 작업. rc4 번역 결함 2개와 최종 G5는 별도 판정한다.",
    "utc": datetime.now(timezone.utc).isoformat(),
    "build": "25631786",
    "original": base_identity,
    "rc4": rc4_identity,
    "comparability": {
        "status": "PASS",
        "original_candidate_equals_frozen_source": not original_mismatches,
        "original_file_mismatches": original_mismatches,
        "same_support_dll": base_identity["support"]["sha256"] == rc4_identity["support"]["sha256"],
        "same_graphics_device": base_identity["runtime"]["graphicsDevice"] == rc4_identity["runtime"]["graphicsDevice"],
        "same_window": [base_identity["runtime"][field] for field in ["width", "height", "windowX", "windowY"]] ==
                       [rc4_identity["runtime"][field] for field in ["width", "height", "windowX", "windowY"]],
        "isolated_save_products": base_identity["runtime"]["product"] != rc4_identity["runtime"]["product"],
        "original_font_check": "NOT_APPLICABLE",
        "original_font_check_reason": "원본 영문 글꼴의 한글 지원은 비교 목적이 아니므로 해당 명령만 제외했다. 후보의 828자 × 4글꼴 검사는 별도 수행되었다.",
        "sequence_note": "원본은 runtime_plan의 font_check를 제외한 대표 흐름을 수행했다. rc4에는 추가 툴팁·상태 확인 캡처가 있어 캡처 수는 121과 153으로 다르다. 두 결과가 전체 분기 동등 테스트임을 뜻하지 않는다.",
    },
    "visual_comparison": [
        {"screen": screen, "status": status, "actual_view_image_review": True,
         "original": image_evidence(BASE, a), "rc4": image_evidence(RC4, b), "observation": note}
        for screen, a, b, status, note in pairs
    ],
    "manual_craft": {
        "status": "PASS",
        "original": {"evidence": evidence(BASE / "232618_7743700_manual_craft.craft.json"),
                     "result": read(BASE / "232618_7743700_manual_craft.craft.json")},
        "rc4": {"evidence": evidence(RC4 / "231456_8609800_manual_craft.craft.json"),
                "result": read(RC4 / "231456_8609800_manual_craft.craft.json")},
    },
    "log_comparison": {
        "status": "PASS", "patch_specific_game_errors": 0,
        "glyph_warnings": {"original": 0, "rc4": 0}, "font_warnings": {"original": 0, "rc4": 0},
        "common_messages": common_messages,
        "messages_jsonl": {"original": message_summary(BASE), "rc4": message_summary(RC4)},
        "differences": "경로, 조립체 로딩/자원 해제 시간, 로딩·해제 객체 수는 글꼴·번역 자산 및 검수 실행량 차이에 따라 달랐다. 메시지 수집 기록은 양쪽 모두 정상 종료 Log 1개이다.",
        "rc4_command_failure": {
            "count": 1, "classification": "QA_SELECTOR_AMBIGUITY",
            "resolution": evidence(WORK / "audit/runtime_rc4_resolution.json"),
            "note": "중복 @soldier 제목 선택 실패는 검수 명령 선택자 문제로 분리했고 실제 인물 슬롯 id로 복구하여 판독했다. 원래 rc4 session-check FAIL을 수정하지 않았다.",
        },
    },
    "exit": {
        "status": "PASS",
        "original": {"evidence": evidence(BASE / "233005_3720800_quit.exit.json"), "result": read(BASE / "233005_3720800_quit.exit.json")},
        "rc4": {"evidence": evidence(RC4 / "232453_6731700_quit.exit.json"), "result": read(RC4 / "232453_6731700_quit.exit.json")},
    },
    "remaining": [
        {"status": "FAIL", "item": "rc4 AppraiserValue 가치 → 값", "evidence": evidence(WORK / "audit/visual_rc4_batch3.json"), "next": "rc5 감정사·회계사 실제 화면 재검수"},
        {"status": "NOT_RUN", "item": "알림이 없는 데모 감사 화면 본문 전체", "next": "rc5 알림 없는 화면 재촬영·판독"},
        {"status": "NOT_RUN", "item": "최종 G5 통합 판정", "next": "rc5 실제 수정 화면 재검수와 rc4 영향 외 증거 재사용 경계 보고서를 연결"},
    ],
}
assert not original_mismatches
assert report["comparability"]["same_support_dll"]
assert all(row["counts"] == {"original": 1, "rc4": 1} for row in common_messages)
assert all(read(s / "session-check.json")["user_unchanged"] for s in [BASE, RC4])
write_json(WORK / "audit/baseline_comparison.json", report)
print(json.dumps({"status": "PASS", "pairs": len(pairs), "path": str(WORK / "audit/baseline_comparison.json")}, ensure_ascii=False))
