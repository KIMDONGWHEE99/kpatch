"""첫 소규모 화면 시험의 실제 관찰과 파일 근거를 고정한다."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "working_private/SOULASH_2"


def evidence(path):
    data = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def main():
    report = {
        "game_id": "SOULASH_2", "check_id": "G1_GRAPHICS_PROBE_01", "status": "FAIL",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "candidate": "working_private/SOULASH_2/g1_probe_01", "font": "Galmuri11-Bold",
        "actual_graphics_execution": "PASS", "korean_sample_display": "PASS",
        "sampled_screens": ["첫 메뉴", "설정/그래픽", "설정/소리", "메뉴 종료"],
        "observed_korean": ["설정", "소리", "언어", "제작진", "종료"],
        "not_observed_sample_ids": [190, 191, 193, 427],
        "findings": [
            {"status": "FAIL", "kind": "glyph", "text": "Artur Śmiarowski", "detail": "Ś 위치에 대체 사각형이 표시됩니다."},
            {"status": "FAIL", "kind": "layout", "screen": "설정/그래픽", "detail": "1280 x 800, 32 x 32, Default 값의 줄바꿈이 인접 필드와 겹칩니다."},
            {"status": "PASS", "kind": "settings", "detail": "창 모드 1280x800 및 전체/음악/효과 음량 0을 화면에서 확인했습니다."},
        ],
        "process": evidence(PRIVATE / "qa_isolation/g1_process.json"),
        "qa_executable_boundary": evidence(PRIVATE / "qa_isolation/g1_isolation_manifest.json"),
        "screenshots": [evidence(p) for p in sorted((PRIVATE / "qa_isolation/screenshots").glob("g1_*_galmuri.png"))],
        "save_integrity": {"status": "PASS", "before": evidence(PRIVATE / "save_snapshots/g1_before_launch.json"),
                           "after": evidence(PRIVATE / "save_snapshots/g1_after_confirmed_exit.json"),
                           "result": "9개 사용자 저장 대상 파일 0개, 실행 전후 변경 없음"},
        "obsolete_snapshot": {"path": "working_private/SOULASH_2/save_snapshots/g1_after_exit.json", "status": "STALE", "reason": "종료 요청 뒤 프로세스 종료 확인 전 기록했으므로 최종 근거로 쓰지 않습니다."},
        "isolated_outputs": [evidence(PRIVATE / "g1_probe_01/data" / name) for name in ["game_language.json", "tutorial_values.json", "user_settings.json"]],
        "error_log": evidence(PRIVATE / "g1_probe_01/logs/errors.log"),
        "limitations": ["이 검사는 소규모 9개 번역 중 실제 표시된 화면에 한정합니다.", "오류 로그는 비었지만 화면에서 누락 글자가 있으므로 글리프 검사는 FAIL입니다.", "본편 HUD·대화·저장·결과 분기는 아직 NOT_RUN입니다."],
        "next": "Noto Sans KR 600 정적 글꼴을 사용한 새 검수 사본으로 재시험",
    }
    out = PRIVATE / "qa_isolation/g1_graphics_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "korean_sample": "PASS", "save_integrity": "PASS", "screenshots": len(report["screenshots"])}))


if __name__ == "__main__":
    main()
