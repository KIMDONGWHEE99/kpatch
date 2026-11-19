"""사용자가 추가 검수를 생략한 최종 자산을 깨끗한 배포 후보와 명시적 생략 기록으로 묶는다."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil

from soulash2_release_package import ROOT, BASELINE, WORK, FONT_ROOT, BUILD, GAME, sha, write_json, file_map


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--native-dir", type=Path, required=True)
    parser.add_argument("--candidate-id", default="release_20261031_v1")
    parser.add_argument("--evidence-id", default="release_finish_20261031_v1")
    args = parser.parse_args()
    candidate = ROOT / "build_candidate/SOULASH_2" / args.candidate_id
    evidence = WORK / args.evidence_id
    candidate.resolve().relative_to((ROOT / "build_candidate/SOULASH_2").resolve())
    evidence.resolve().relative_to(WORK.resolve())
    assert not candidate.exists() and not evidence.exists(), "기존 후보를 덮어쓰지 않습니다."
    stage = args.stage.resolve()
    native = args.native_dir.resolve()
    stage.relative_to((ROOT / "build_candidate/SOULASH_2").resolve())
    native.relative_to(WORK.resolve())
    baseline_path = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029/baseline_manifest.json"
    baseline = read(baseline_path)
    originals = {row["path"]: row for row in baseline["files"]}
    stage_path = stage / "stage_report.json"
    stage_report = read(stage_path)
    assert stage_report["generation_status"] == "PASS" and stage_report["status"] == "PASS"
    assert stage_report["missing_rows"] == stage_report["held_rows"] == 0
    assert sha(stage / "canonical.jsonl") == stage_report["canonical_sha256"]
    font_report_path = FONT_ROOT / "build_report.json"
    fonts = read(font_report_path)
    native_report_path = native / "generation_manifest.json"
    if not native_report_path.exists():
        native_report_path = native / "manifest.json"
    native_validation_path = native / "independent_validation.json"
    native_exe = native / "Soulash 2.exe"
    native_report, native_validation = read(native_report_path), read(native_validation_path)
    native_hash = sha(native_exe)
    assert native_report["source_sha256"] == originals["Soulash 2.exe"]["sha256"]
    if "source_sha256" in native_validation:
        assert native_validation["source_sha256"] == native_report["source_sha256"]
    if "base_sha256" in native_report:
        assert native_validation["base_sha256"] == native_report["base_sha256"]
    assert native_report["candidate_sha256"] == native_validation["candidate_sha256"] == native_hash
    assert native_validation["status"] == "PASS"
    if "candidate_size" in native_report:
        assert native_report["candidate_size"] == native_exe.stat().st_size
    if "section" in native_report:
        assert native_report["section"]["raw"] + native_report["section"]["raw_size"] == native_exe.stat().st_size
    dependencies = {}

    def remember(path, expected=None):
        path = path.resolve()
        path.relative_to(ROOT)
        actual = sha(path)
        if expected:
            assert actual == expected, str(path)
        dependencies[path.relative_to(ROOT).as_posix()] = actual

    for path in (baseline_path, stage_path, stage / "canonical.jsonl", font_report_path, native_report_path, native_validation_path, native_exe, Path(__file__), ROOT / "tools/soulash2_release_package.py"):
        remember(path)
    for item in stage_report["inputs"]:
        remember(ROOT / item["path"], item["sha256"])
    if "culture_mapping" in native_report:
        earlier = ROOT / "build_candidate/SOULASH_2/complete_stage_01/canonical.jsonl"
        remember(earlier, native_report["binding"]["canonical_sha256"])
        def race_names(path):
            selected = {}
            for line in path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if row["file"] == "data/mods/core_2/character.json" and row.get("field_path", "").startswith("/races/") and row["field_path"].endswith("/name"):
                    selected[row["location_id"]] = row["target"]
            return selected
        before_names, final_names = race_names(earlier), race_names(stage / "canonical.jsonl")
        final_rows = {row["location_id"]: row for row in (json.loads(line) for line in (stage / "canonical.jsonl").read_text(encoding="utf-8").splitlines())}
        undead = final_rows["data/mods/core_2/messages.json#/tag/4"]
        assert undead["source"] == "Undead" and undead["target"] == "언데드"
        assert before_names == final_names and all(target in set(final_names.values()) or (culture == "undead" and target == undead["target"]) for culture, target in native_report["culture_mapping"]), "문화명 후크와 최종 종족명·집합명 번역 불일치"
    candidate.mkdir(parents=True)
    evidence.mkdir(parents=True)
    tasks = []
    for name, item in originals.items():
        source, target = BASELINE / name, candidate / name
        target.parent.mkdir(parents=True, exist_ok=True)
        tasks.append((source, target, item))

    def copy_original(task):
        source, target, expected = task
        assert source.stat().st_size == expected["size"] and sha(source) == expected["sha256"]
        shutil.copyfile(source, target)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(copy_original, tasks))
    print(json.dumps({"original_files_copied": len(tasks)}), flush=True)
    expected = {name: row["sha256"] for name, row in originals.items()}
    for item in stage_report["files"]:
        name = item["file"]
        assert name in expected and expected[name] == item["source_sha256"]
        source = stage / "payload" / name
        remember(source, item["candidate_sha256"])
        shutil.copyfile(source, candidate / name)
        expected[name] = item["candidate_sha256"]
    for item in fonts["files"]:
        name = "data/mods/core_2/assets/fonts/" + item["source"]
        source = FONT_ROOT / "fonts" / item["output"]
        assert name in expected
        remember(source, item["sha256"])
        shutil.copyfile(source, candidate / name)
        expected[name] = item["sha256"]
    shutil.copyfile(native_exe, candidate / "Soulash 2.exe")
    expected["Soulash 2.exe"] = native_hash
    actual_files = file_map(candidate)
    assert set(actual_files) == set(originals), "원본·번역·글꼴·승인된 실행 파일 외 새 파일이 없어야 합니다."
    with ThreadPoolExecutor(max_workers=8) as pool:
        actual = dict(zip(actual_files, pool.map(sha, actual_files.values())))
    assert actual == expected, "배포 후보 복사 경계 불일치"
    frozen = {"game_id": GAME, "steam_build": BUILD, "candidate_id": args.candidate_id, "files": [{"path": name, "size": actual_files[name].stat().st_size, "sha256": actual[name]} for name in sorted(actual)]}
    freeze_path = evidence / "candidate_manifest.json"
    write_json(freeze_path, frozen)
    freeze_hash = sha(freeze_path)
    waiver = {"authorization": "EXPLICIT_USER_REQUEST", "user_instruction": "토큰 부족, 검수 패스하고 패치를 마무리. 이상 시 사용자가 캡처를 제공. 인게임 위주, 메뉴 창 검수 패스.", "candidate_manifest_sha256": freeze_hash, "waived_checks": ["G2", "G4_FINAL_RECHECK", "G5", "G7_EXTENDED_INSTALLER_QA"], "mechanical_checks_retained": ["원본 빌드 지문", "허용 파일 복사 경계", "차이 파일 정·역 복원", "ZIP 허용목록·내용 지문"]}
    waiver_path = evidence / "user_requested_review_omissions.json"
    write_json(waiver_path, waiver)
    statuses = {
        "G2": ("FAIL", "전체 표시·비표시 분류와 미디어 조사에 미해결 항목이 남아 있으며 사용자 요청으로 추가 조사를 중단함."),
        "G4": ("NOT_RUN", "기존 complete_stage_03 로스터32,239개 독립 대조는 PASS. 최종 저장형식 키78개 원문복원 후 전체 독립 재추출은 사용자 요청으로 생략. 최종 파일 복사·지문 경계만 확인."),
        "G5": ("NOT_RUN", "최종 실행 파일·저장키 수정 후보의 추가 인게임·메뉴·전체 분기 검수와 영문 저장 불러오기 검수는 사용자 요청으로 생략. 앞선 후보의 부분 관찰을 최종 후보 전체 PASS로 승계하지 않음."),
        "G7": ("NOT_RUN", "최종 ZIP에서 꺼낸 설치기의 확장 설치·제거·중단 복구 시나리오 검사는 사용자 요청으로 생략. 앞선 합성자료 시험은 이 최종 ZIP 검수와 구분함.")}
    checks = {}
    for key, (status, scope) in statuses.items():
        path = evidence / (key + "_scope.json")
        write_json(path, {"status": status, "scope": scope, "candidate_manifest_sha256": freeze_hash})
        checks[key] = {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path), "status": status}
    changed = [name for name in sorted(actual) if actual[name] != originals[name]["sha256"]]
    gate = {"game_id": GAME, "steam_build": BUILD, "candidate_id": args.candidate_id, "status": "USER_WAIVER", "candidate_manifest": {"path": freeze_path.relative_to(ROOT).as_posix(), "sha256": freeze_hash}, "allowed_changes": changed, "checks": checks, "waiver": {"path": waiver_path.relative_to(ROOT).as_posix(), "sha256": sha(waiver_path)}, "dependencies": [{"path": name, "sha256": value} for name, value in sorted(dependencies.items())]}
    write_json(evidence / "release_gate.json", gate)
    readme = """Soulash 2 한국어 패치 1.0.0 (2026-10-31)

지원: Windows Steam 앱 2399160 / 빌드 25967323 / 게임 0.10.4.0.1
다른 빌드와 변조된 원본 파일에는 설치하지 않습니다.

설치: 게임을 종료하고 ZIP을 모두 푼 뒤 Install.cmd를 실행하세요.
Soulash 2.exe가 있는 폴더를 선택하고 완료 안내 후 Steam에서 실행하세요.
제거: 게임을 종료하고 Remove.cmd에서 같은 폴더를 선택하세요.
설치·제거 중 중단되면 같은 설치기를 다시 실행해 복구하세요.
완료 전 %LOCALAPPDATA%\\Soulash2KoreanPatch\\working_private의 복구 기록을 지우지 마세요.
게임 업데이트 뒤에는 해당 빌드용 패치가 필요합니다.

번역과 보존 범위
현재 JSON·이름 TXT 로스터 32,239개 위치를 처리했습니다. 한글 글꼴3종을 적용합니다.
게임 동작에 쓰이는 코드·자리표시자·저장형식 키78개는 원문으로 보존합니다.
English/en 언어 슬롯에 적용하며 Polski는 별도로 유지합니다.
변경 이력·모딩 안내 등 개발 문서, 원본 이미지 문구·로고·음향은 보존합니다.
기존 저장에 이미 생성된 영어 이름은 소급해서 바꾸지 않습니다.
로고·미디어·코드 조합 문구 등 모든 축의 조사 완료를 뜻하지 않습니다.

검수 생략 안내
2026-10-31 사용자 요청에 따라 추가 화면 검수·전체 미분류 조사·
최종 ZIP 확장 설치 시험을 생략하고 패키지를 만들었습니다.
최종 후보의 전체 인게임·메뉴·영문 저장 불러오기, 모든 분기와
최종 ZIP 설치·제거·중단 복구 확장 시험을 완료한 패키지가 아닙니다.
G2는 미해결 항목이 남아 FAIL, 최종 추가 G4/G5/G7 검수는 NOT_RUN입니다.
기존 후보의 로스터 대조와 합성 설치 시험 결과를 최종 후보 전체 통과로 표시하지 않습니다.
원본 지문·허용 변경 경계·차이 정방향/역방향 복원·ZIP 내용 지문은 확인합니다.
상세 범위는 REVIEW_STATUS.json에 기록했습니다.
이상 현상이 있으면 화면과 상황을 캡처해 전달할 수 있습니다.

구성과 라이선스
게임 원본 실행 파일·DLL·게임 자산·검수 코드·저장 파일을 배포하지 않습니다.
설치·제거 도구, 변경 차이 파일, 문서와 라이선스만 들어 있습니다.
글꼴은 Lato 및 Noto 계열을 바탕으로 한 Patch Hangul이며 SIL OFL 1.1입니다.
Romulus의 원본 글자 윤곽은 수정 기본 글꼴에 포함하지 않습니다.
xdelta3 3.2.0은 Apache License 2.0입니다. licenses 폴더의 전문을 확인하세요.
"""
    (evidence / "README.txt").write_text(readme, encoding="utf-8")
    write_json(evidence / "preparation.json", {"status": "PASS", "scope": "MECHANICAL_CANDIDATE_ASSEMBLY_ONLY", "candidate": candidate.relative_to(ROOT).as_posix(), "stage": stage.relative_to(ROOT).as_posix(), "native": native.relative_to(ROOT).as_posix(), "files": len(actual), "changed_files": len(changed), "accepted_locations": stage_report["accepted_rows"], "gates": {key: value[0] for key, value in statuses.items()}, "qa_only_changes_included": False, "actual_installation_modified": False, "user_review_waiver": True})
    print(json.dumps({"candidate": candidate.relative_to(ROOT).as_posix(), "gate": (evidence / "release_gate.json").relative_to(ROOT).as_posix(), "readme": (evidence / "README.txt").relative_to(ROOT).as_posix(), "changes": len(changed)}))


if __name__ == "__main__":
    main()
