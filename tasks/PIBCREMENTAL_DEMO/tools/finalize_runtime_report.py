"""실행 로그·화면 증거·사용자 저장 영역의 무결성을 최종 기록합니다."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VALIDATION = ROOT / "validation/PIBCREMENTAL_DEMO"
VIEWER = ROOT / "viewer_output/PIBCREMENTAL_DEMO/graphical_qa"
SAVE = Path("C:/Users/PC/AppData/LocalLow/Arcane Cabinet UG/Pibcremental")
QA = ROOT / "working_private/PIBCREMENTAL_DEMO/runtime_qa_final"
CANDIDATE = ROOT / "build_candidate/PIBCREMENTAL_DEMO"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    with (VALIDATION / "save_before_graphical_qa.csv").open(encoding="utf-8-sig", newline="") as stream:
        before = {
            row["RelativePath"]: (int(row["Size"]), row["SHA256"].lower())
            for row in csv.DictReader(stream)
        }
    after = {
        path.relative_to(SAVE).as_posix(): (path.stat().st_size, sha256(path))
        for path in sorted(SAVE.rglob("*"))
        if path.is_file()
    }
    differences = [
        {"path": name, "before": before.get(name), "after": after.get(name)}
        for name in sorted(set(before) | set(after))
        if before.get(name) != after.get(name)
    ]
    persistent_differences = [
        row for row in differences if row["path"] not in {"Player.log", "Player-prev.log"}
    ]
    if persistent_differences:
        raise RuntimeError(f"기존 저장 데이터가 바뀌었습니다: {persistent_differences}")

    with (VALIDATION / "save_final_after_graphical_qa.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["RelativePath", "Size", "SHA256"])
        writer.writerows((name, *values) for name, values in sorted(after.items()))

    log_reports = []
    patterns = {
        "missing_glyph_warnings": r"The character with Unicode value|missing.*glyph",
        "font_atlas_errors": r"Unable to add.*character|Font Asset.*(error|failed)|texture.*not readable",
        "exceptions": r"\b(?:NullReferenceException|MissingMethodException|TypeLoadException|InvalidProgramException|Exception:)\b",
        "catalog_loading_errors": r"(?:catalog|AssetBundle|Addressables).*(?:failed|exception|error)",
    }
    for name in ["runtime_qa_Player.log", "runtime_qa_final_v2_Player.log", "runtime_qa_completion_Player.log"]:
        log_path = VALIDATION / name
        content = log_path.read_text(encoding="utf-8-sig", errors="replace")
        counts = {
            key: len(re.findall(pattern, content, flags=re.IGNORECASE))
            for key, pattern in patterns.items()
        }
        if any(counts.values()):
            raise RuntimeError(f"실행 로그 오류: {name}: {counts}")
        log_reports.append({
            "file": name,
            "sha256": sha256(log_path),
            "korean_font_ready": "Korean font fallback ready." in content,
            **counts,
        })

    screenshots = {
        "첫 화면·버전": "24_final_main_menu.png",
        "그래픽 설정·창 모드·무제한 FPS": "25_graphics_settings_final.png",
        "언어 설정": "26_language_settings_final.png",
        "인트로": "09_gameplay_first_scene.png",
        "HUD·튜토리얼 대화": "10_gameplay_hud_or_dialogue.png",
        "게임 내 메뉴·저장 후 종료": "15_hover_tooltip_check.png",
        "피블 바위": "17_pibrock_selected.png",
        "최종 후보 HUD": "28_final_hud.png",
        "데모 완료·감사 표시": "29_final_quest.png",
    }
    screenshot_report = []
    for label, name in screenshots.items():
        path = VIEWER / name
        if not path.is_file():
            raise RuntimeError(f"증거 이미지가 없습니다: {name}")
        screenshot_report.append({"screen": label, "file": str(path.relative_to(ROOT)), "sha256": sha256(path)})

    differing_files = []
    for candidate_file in sorted(CANDIDATE.rglob("*")):
        if candidate_file.is_file():
            relative = candidate_file.relative_to(CANDIDATE)
            if sha256(candidate_file) != sha256(QA / relative):
                differing_files.append(relative.as_posix())
    expected_differences = [
        "Pibcremental_Data/Managed/Assembly-CSharp.dll",
        "Pibcremental_Data/data.unity3d",
    ]
    if sorted(differing_files) != expected_differences:
        raise RuntimeError(f"QA 복사본의 예상 밖 차이: {differing_files}")

    report = {
        "schema_version": 1,
        "representative_graphical_qa_passed": True,
        "all_playthroughs_verified": False,
        "actual_qa_executable_paths_observed": [str(QA / "Pibcremental.exe")],
        "observed_process_ids": [21468, 13308],
        "graphics_device": "NVIDIA GeForce RTX 4060 Ti / Direct3D 12",
        "candidate_qa_differences": differing_files,
        "qa_only_changes": [
            "제품명을 Pibcremental Korean QA로 바꿔 진행 데이터 경로 분리",
            "검수 저장 데이터의 나무 레벨을 7로 설정",
            "데모 완료 조건의 피블·의상 요구 수를 검수 실행 중에만 0으로 설정",
            "최종 화면 검수에서는 Steam 초기화·통계 전송 비활성화",
        ],
        "qa_changes_in_public_candidate": False,
        "screenshots": screenshot_report,
        "logs": log_reports,
        "save_integrity": {
            "original_root": str(SAVE),
            "before_file_count": len(before),
            "after_file_count": len(after),
            "persistent_data_differences": persistent_differences,
            "runtime_log_differences": differences,
            "note": "기존 진행·설정·Steam 자동 저장 메타데이터·분석 파일은 동일합니다. 초기 검수 실행에서 기본 Player.log가 갱신되고 Player-prev.log가 생겼습니다. 이후 실행은 로그 출력도 작업 폴더로 분리했습니다.",
        },
        "scope_notes": [
            "이전 후보에서 확인한 인트로·튜토리얼·종료 메뉴 화면과 최종 후보의 첫 화면·설정·HUD·데모 감사 표시를 합친 대표 흐름 검증입니다.",
            "데모 완료 조건을 낮춘 검수이므로 정상 진행 전체 플레이를 완료했다는 뜻은 아닙니다.",
            "독일어 언어 테이블도 전 항목 한국어로 정적 검증했지만 설정에서 실제 슬롯 전환은 확인되지 않았습니다.",
            "Event System 중복, GraphicRaycaster 미설정, DontDestroyOnLoad 관련 비치명적 경고는 관찰됐으며 로딩·카탈로그 오류나 한글 글리프 경고는 없었습니다.",
        ],
    }
    output = VALIDATION / "graphical_qa_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "representative_graphical_qa_passed": True,
        "screenshots": len(screenshot_report),
        "logs_checked": len(log_reports),
        "persistent_data_differences": len(persistent_differences),
        "runtime_log_differences": len(differences),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
