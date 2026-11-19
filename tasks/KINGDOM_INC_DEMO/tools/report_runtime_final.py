"""독립된 실행·육안 판독 기록을 최종 후보의 대표 화면 G5 판정으로 연결합니다."""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from common import ROOT, WORK, sha, write_json
from qa_steps import process_running

AUDIT = WORK / "audit"
FINAL = WORK / "final_rc5/qa_final_rc5"
EXTRA = WORK / "extra_rc5/qa_extra_rc5"
ORIGINAL_EXTRA = WORK / "extra_original/qa_extra_original"
RC4 = WORK / "full_rc4/qa_full_rc4"
BASE = WORK / "original_qa/qa_original_qa"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ev(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def resolve(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


issues = []
reports = {}
image_index = {}
image_rows = {}
review_names = [
    "visual_rc4_batch1.json", "visual_rc4_big_cards.json", "visual_rc4_batch2.json",
    "visual_rc4_batch3.json", "visual_rc4_batch3_additional.json", "visual_rc4_root_final.json",
    "visual_rc5_final.json", "visual_rc5_extra.json",
]
for name in review_names:
    report = read(AUDIT / name)
    reports[name] = report
    for row in report.get("rows", report.get("images", [])):
        path = resolve(row.get("image", row.get("path")))
        expected = row.get("image_sha256", row.get("sha256"))
        if sha(path) != expected:
            issues.append("판독 이미지 해시 불일치: " + str(path))
        if row.get("capture_json_sha256") and sha(path.with_suffix(".json")) != row["capture_json_sha256"]:
            issues.append("판독 텍스트 해시 불일치: " + str(path))
        if row.get("text_json_sha256") and sha(path.with_suffix(".json")) != row["text_json_sha256"]:
            issues.append("판독 텍스트 해시 불일치: " + str(path))
        image_index[path.name] = {
            "image": ev(path), "capture": ev(path.with_suffix(".json")),
            "status": row["status"], "review_report": ev(AUDIT / name),
            "action": row.get("action", read(path.with_suffix(".json")).get("action")),
            "observation": row.get("observation", row.get("observations")),
        }
        image_rows[str(path)] = image_index[path.name]


def image(name):
    row = image_index[name]
    assert row["status"] == "PASS", name
    return row


build = read(WORK / "1.0.0_rc5/build.json")
candidate = Path(build["candidate"])
final_manifest = {row["path"]: {"size": row["size"], "sha256": row["sha256"]} for row in build["files"]}
for relative, record in final_manifest.items():
    path = candidate / relative
    if path.stat().st_size != record["size"] or sha(path) != record["sha256"]:
        issues.append("현재 최종 후보 해시 불일치: " + relative)
for session in [FINAL, EXTRA]:
    if read(session / "candidate-manifest.json") != final_manifest:
        issues.append("검수 입력과 최종 후보 불일치: " + session.name)

sessions = {}
for session in [RC4, FINAL, EXTRA, BASE, ORIGINAL_EXTRA]:
    runtime, launch = read(session / "runtime.json"), read(session / "launch.json")
    prep, check = read(session / "preparation.json"), read(session / "session-check.json")
    prepared = read(session / "prepared-manifest.json")
    before, after = read(session / "user-before.json"), read(session / "user-after.json")
    boundary = read(session / "assembly-boundary.json")
    linked = {
        "actual_path_matches_requested": runtime["executable"] == launch["requested_executable"],
        "pid_matches_launch": runtime["pid"] == launch["pid"],
        "manifest_matches_launch": sha(session / "prepared-manifest.json") == launch["prepared_manifest_sha256"],
        "manifest_matches_preparation": sha(session / "prepared-manifest.json") == prep["prepared_manifest_sha256"],
        "candidate_matches_preparation": sha(session / "candidate-manifest.json") == prep["candidate_manifest_sha256"],
        "exe_matches_prepared_manifest": sha(Path(runtime["executable"])) == prepared["KingdomInc.exe"]["sha256"],
        "support_matches_preparation": sha(session.parent / "game/KingdomInc_Data/Managed/KoreanQA.dll") == prep["support_sha256"],
        "game_assembly_matches_prepared_manifest": sha(session.parent / "game/KingdomInc_Data/Managed/Assembly-CSharp.dll") ==
            prepared["KingdomInc_Data/Managed/Assembly-CSharp.dll"]["sha256"],
        "save_state_equal": before["state"] == after["state"],
        "half_monitor_width": runtime["width"] + max(0, runtime["windowX"]) <= runtime["monitorWidth"] / 2,
        "windowed": not runtime["fullScreen"],
        "steam_off": not runtime["steamInitialized"],
        "two_method_boundary": boundary["status"] == "PASS" and len(boundary["allowed"]) == 2,
        "exited": not process_running(runtime["pid"]),
    }
    if not all(linked.values()):
        issues.append("실행 연결 검사 실패: " + session.name + " " + str(linked))
    if any(check[key] != 0 for key in ["glyph_warnings", "font_warnings", "errors"]):
        issues.append("오류·글꼴 경고 잔존: " + session.name)
    if session != RC4 and check["status"] != "PASS":
        issues.append("최종/원본 실행 검사 실패: " + session.name)
    log = (session / "Player.log").read_text(encoding="utf-8-sig")
    sessions[session.name] = {
        "runtime": runtime, "link_checks": linked, "session_result": check,
        "support_sha256": prep["support_sha256"],
        "evidence": {name: ev(session / name) for name in [
            "runtime.json", "launch.json", "preparation.json", "candidate-manifest.json",
            "prepared-manifest.json", "assembly-boundary.json", "session-check.json",
            "user-before.json", "user-after.json", "Player.log", "messages.jsonl"]},
        "exit_evidence": [ev(path) for path in sorted(session.glob("*.exit.json"))],
        "common_log_counts": {
            "ComputeBuffer disposal": log.count("GarbageCollector disposing of ComputeBuffer."),
            "D3D12 info queue": log.count("d3d12: failed to query info queue interface (0x80004002)."),
        },
    }
assert sessions[EXTRA.name]["support_sha256"] == sessions[ORIGINAL_EXTRA.name]["support_sha256"]
assert sessions[RC4.name]["support_sha256"] == sessions[FINAL.name]["support_sha256"] == sessions[BASE.name]["support_sha256"]

delta = read(WORK / "1.0.0_rc5/rc4_delta.json")
assert delta["status"] == "PASS"
assert delta["from_build_sha256"] == sha(WORK / "1.0.0_rc4/build.json")
assert delta["to_build_sha256"] == sha(WORK / "1.0.0_rc5/build.json")
assert {(row["file"], row["path_id"]) for row in delta["objects"]} == {("resources.assets", 21), ("sharedassets0.assets", 11)}
assert delta["objects"][0]["translations"] == [{"key": "AppraiserValue", "before": "가치", "after": "값"}]
assert read(WORK / "1.0.0_rc5/static_validation.json")["status"] == "PASS"
extension = read(AUDIT / "support_extension_boundary.json")
assert extension["status"] == "PASS" and extension["unchangedExistingMethods"] == 123
assert extension["changedExistingMethods"][0]["originalInstructionsUnchangedOutsideInsertion"]

fonts_path = FINAL / "233533_4089200_font_check.fonts.json"
fonts = read(fonts_path)
assert fonts["status"] == "PASS" and fonts["requestedScalars"] == 828 and fonts["checkedFonts"] == 4
assert fonts["sourceSha256"] == sha(WORK / "translation/required_characters.txt")
assert all(row["fallbackMissingCount"] == 0 and row["status"] == "PASS" for row in fonts["rows"])
craft = read(FINAL / "233546_9229800_manual_craft.craft.json")
assert craft["before"]["blackout"] and not craft["after"]["blackout"] and craft["after"]["outputItems"] > craft["before"]["outputItems"]

plan = read(AUDIT / "runtime_plan.json")
step_results = {step["order"]: {"order": step["order"], "screen": step["screen"], "action": step["action"],
                               "status": "NOT_RUN", "evidence": []} for step in plan["steps"]}


def set_step(order, status, evidence):
    step_results[order].update(status=status, evidence=evidence)


for name in ["visual_rc4_batch1.json", "visual_rc4_batch3.json"]:
    for row in reports[name]["rows"]:
        order = row.get("plan_step", 0)
        if order:
            set_step(order, row["status"], [ev(resolve(row["image"]))])
for i, row in enumerate(reports["visual_rc4_big_cards.json"]["rows"], 38):
    set_step(i, row["status"], [ev(resolve(row["image"]))])
for row in reports["visual_rc4_batch2.json"]["step_results"]:
    set_step(row["order"], row["status"], [ev(RC4 / name) for name in row["image_files"]])
for row in reports["visual_rc4_batch1.json"]["nonvisual_steps"]:
    set_step(row["plan_step"], row["execution"], [ev(AUDIT / "visual_rc4_batch1.json")])
root_rows = reports["visual_rc4_root_final.json"]["rows"]
for step in plan["steps"]:
    if 105 <= step["order"] <= 122:
        matching = [row for row in root_rows if read(resolve(row["image"]).with_suffix(".json"))["action"] == step["action"]]
        assert matching, step
        row = matching[0]
        set_step(step["order"], row["status"], [ev(resolve(row["image"]))])
set_step(63, "PASS", [image("233556_4041600_tech_list.png")["image"], image("233619_0934800_scroll.png")["image"]])
set_step(99, "PASS", [image("233627_0449900_appraiser.png")["image"]])
set_step(101, "PASS", [image("233630_1413400_accountant.png")["image"]])
set_step(115, "PASS", [image("233633_7913800_demo_end.png")["image"]])
set_step(123, "PASS", sessions[FINAL.name]["exit_evidence"])
missing_steps = [row for row in step_results.values() if row["status"] != "PASS"]
if missing_steps:
    issues.append("필수 계획의 미완료 단계: " + str(missing_steps))

group_definitions = [
    ("로고·첫 화면·버전", ["233532_7419100_main_menu.png"],
     "로딩·첫 메뉴·데모 버전·유지 로고. 텍스트 레이어와 작은 글상자 이미지의 처리는 구분한다."),
    ("메뉴·설정·언어", ["233536_2995300_options.png", "233538_1557500_keybindings.png", "232230_0797700_scroll.png", "232232_3466200_scroll.png"],
     "메인/게임 중 설정과 키 목록 상·하단을 확인했다. 별도 언어 전환 화면은 코드/자산 근거로 N/A. 모든 해상도·표시 배율 조합을 시험하지 않았다."),
    ("새 게임·이어하기·저장", ["233541_1303300_new_game.png", "233546_9229800_manual_craft.png", "233638_3947500_save_menu.png", "233641_0078600_ingame_load.png", "233645_5923700_load_latest.png"],
     "첫 제련은 원본 수동 제작 동작으로 결과 생성과 HUD 개방을 확인했다. 격리 저장의 한국어 이름·목록·복원을 확인했다."),
    ("HUD·시설·툴팁·기술", ["233551_0531900_economy_fixture.png", "231654_3879500_focus_tech.png", "231736_7922000_recipe.png", "232010_2129100_resources.png",
                        "232013_5466600_forest.png", "232443_1761100_tooltip.png", "232446_2083800_tooltip.png", "233627_0449900_appraiser.png", "233630_1413400_accountant.png",
                        "233554_0579100_focus_tech.png", "233619_0934800_scroll.png"],
     "대표 재화·시설/제작법·14개 큰 기술 카드·자원·산림·병사/장비·긴 설명·숫자 안내·이미지 아이콘을 확인했다. 시설/재화/전쟁 해금은 제한된 검수 상태를 포함한다."),
    ("대화·선택지", ["232248_8301900_alert.png", "234431_2863100_alert_query.png"],
     "오류 안내·예비 공용 예/아니요 UI는 실제 표시 확인. 스토리 대화/분기 시스템은 N/A. 예/아니요 결과 콜백이 없는 표시 시험으로, 스토리 선택 결과 검증이 아니다."),
    ("일시정지·도움말·접근성", ["233636_6407800_pause.png", "232213_2029800_ingame_options.png", "232215_8703600_ingame_keys.png", "232446_2083800_tooltip.png"],
     "일시정지·설정·키 안내·체력 도움말을 확인했다. 별도 접근성 창은 N/A이며 존재하는 UI 크기/키 설정은 옵션 화면 검수에 포함된다."),
    ("사망·결과·종료", ["234443_9241800_human_dead.png", "232102_5335700_war_fixture.png", "232104_0011900_war_fixture.png",
                       "232106_9026800_war_fixture.png", "232107_5433000_war_fixture.png", "233633_7913800_demo_end.png"],
     "독립 인물 사망 표시, 전쟁 진행/점령/방어/상실, 알림 없는 데모 감사 본문, 프로세스 종료를 확인했다. 정상 전투 사망·전쟁 완주 검증은 아니다."),
]
groups = [{"screen_group": title, "status": "PASS", "scope": scope, "evidence": [image(name) for name in names]}
          for title, names, scope in group_definitions]

resolved = [
    ("rc3 기술 목록 비활성 부모 오류", "FAIL", "PASS", "검수 부모 UI 활성화만 보완하고 rc4/rc5 실제 목록·스크롤 및 오류 0을 확인.",
     ["runtime_access_diagnosis_rc3.json", "visual_rc5_final.json"], ["233556_4041600_tech_list.png"]),
    ("rc3 시설 툴팁/산림 탭 접근", "FAIL", "PASS", "실제 시설 본체의 설명 공급자 사용 및 탭 토글 동기화. rc4 제작법·산림 실제 UI로 확인.",
     ["runtime_access_diagnosis_rc3.json", "visual_rc4_batch1.json", "visual_rc4_batch2.json"], ["231736_7922000_recipe.png", "232013_5466600_forest.png"]),
    ("원본 기술 카드 그림·설명 겹침", "FAIL", "PASS", "공용 카드 3필드만 수정하여 14개 카드 실제 판독. rc4→rc5에서 동일 객체 보존.",
     ["runtime_access_diagnosis_rc3.json", "visual_rc4_big_cards.json", "baseline_comparison.json"], ["231654_3879500_focus_tech.png"]),
    ("환전/농장·던전 미구현 접근", "FAIL", "NOT_APPLICABLE", "환전 참조 null/인스턴스 0, 데모 고단계·eastern 전쟁 미등록 근거로 실행 경로에서 제외. 잔존 문구 정적 번역·전체 글자 생성은 유지.",
     ["runtime_access_diagnosis_rc3.json", "runtime_plan.json"], []),
    ("rc4 자원·산림 창 가림", "FAIL", "PASS", "기술 목록을 닫아 단독 창을 재촬영하고 직접 판독.",
     ["visual_rc4_batch2.json"], ["232010_2129100_resources.png", "232013_5466600_forest.png"]),
    ("rc4 작은 글상자 영문 이미지 잔존", "FAIL", "PASS", "작은 아이콘 16×16셀만 수정. rc5 카드·목록·꾸미기에서 재검수.",
     ["visual_rc4_batch2.json", "visual_rc5_final.json"], ["233554_0579100_focus_tech.png", "233619_0934800_scroll.png", "233622_0435300_deco.png"]),
    ("rc4 감정사·회계사 숫자 입력 안내", "FAIL", "PASS", "AppraiserValue 가치→값 교정 후 두 창 모두 실제 판독.",
     ["visual_rc4_batch3.json", "visual_rc5_final.json"], ["233627_0449900_appraiser.png", "233630_1413400_accountant.png"]),
    ("rc4 감사 본문 위 알림 가림", "BLOCKED", "PASS", "원본에도 있는 알림 겹침을 확인한 뒤 rc5에서는 알림 없는 상태로 본문 전체 재촬영.",
     ["visual_rc4_root_final.json", "baseline_comparison.json", "visual_rc5_final.json"], ["233633_7913800_demo_end.png"]),
    ("rc4 @soldier 중복 선택자", "FAIL", "PASS", "실제 인물 슬롯 id로 복구 후 전문화 툴팁 판독. 기존 세션 FAIL은 보존.",
     ["runtime_rc4_resolution.json", "visual_rc4_batch3_additional.json"], ["232443_1761100_tooltip.png"]),
    ("rc4 종료 권한 확인 실패", "FAIL", "PASS", "프로세스 목록 열거로 이미 종료된 PID를 읽기 전용 확인. 추가 종료 명령 없이 이전 오류 보존.",
     ["runtime_rc4_resolution.json"], []),
]
resolution_rows = [{"issue": title, "historical_status": old, "resolved_status": current, "resolution": note,
                    "reports": [ev(AUDIT / name) for name in names], "images": [image(name)["image"] for name in images]}
                   for title, old, current, note, names, images in resolved]

extra_comparison = []
for action, a, b in [
    ("alert_query", "234431_2863100_alert_query", "234551_6258500_alert_query"),
    ("human_dead", "234443_9241800_human_dead", "234603_6908300_human_dead"),
]:
    row = {"action": action, "status": "PASS", "review_method": "root와 inspect_engine이 양쪽 PNG를 각각 view_image로 실제 판독",
           "candidate": {"image": ev(EXTRA / (a + ".png")), "capture": ev(EXTRA / (a + ".json"))},
           "original": {"image": ev(ORIGINAL_EXTRA / (b + ".png")), "capture": ev(ORIGINAL_EXTRA / (b + ".json"))},
           "observation": "두 UI 구조와 표시 상태가 같고 Yes/No/DEAD 및 제목·본문의 번역 차이를 확인했다. 후보 문구의 잘림·겹침·글리프 누락 없음."}
    if action == "human_dead":
        row["candidate"]["fixture"] = ev(EXTRA / (a + ".fixture.json"))
        row["original"]["fixture"] = ev(ORIGINAL_EXTRA / (b + ".fixture.json"))
        row["limitation"] = "독립 미리보기는 기본 능력치가 0인 병사이므로 원래부터 CurrentHealth도 0이다. Health01을 0으로 바꾼 사망 문구 표시 검사이며 살아 있는 병사의 실제 사망 전환을 검증한 것이 아니다."
    extra_comparison.append(row)

coverage = read(AUDIT / "runtime_translation_coverage.json")
for row in coverage["review_report_inputs"]:
    assert sha(resolve(row["path"])) == row["sha256"]
for name in ["visual_rc5_final.json", "visual_rc5_extra.json"]:
    assert reports[name]["status"] == "PASS"
    session = FINAL if name == "visual_rc5_final.json" else EXTRA
    for key, filename in [("runtime_sha256", "runtime.json"), ("prepared_manifest_sha256", "prepared-manifest.json"),
                          ("candidate_manifest_sha256", "candidate-manifest.json"), ("session_check_sha256", "session-check.json")]:
        assert reports[name][key] == sha(session / filename)

na = read(AUDIT / "na_screens.json")
additional_screens = []
for row in na["screens"]:
    current = dict(row)
    if row["id"] in ["generic_yes_no_dialog", "human_dead_state"]:
        current["historical_status"] = row["status"]
        current["status"] = "PASS"
        current["resolution"] = ev(AUDIT / "visual_rc5_extra.json")
    additional_screens.append(current)

report = {
    "status": "PASS" if not issues else "FAIL",
    "gate": "G5", "scope": "기재된 필수 대표 화면군의 실제 그래픽·한글 출력·저장 격리·오류·종료 검수. 전체 문구 실화면 관찰·전체 회차·정상 해금 완주·사용자 설치본 재실행은 포함하지 않는다.",
    "utc": datetime.now(timezone.utc).isoformat(), "issues": issues,
    "final_candidate": {"build_id": "1.0.0_rc5", "steam_build": "25631786", "path": str(candidate),
                        "file_count": len(final_manifest), "current_file_hashes_checked": True,
                        "build": ev(WORK / "1.0.0_rc5/build.json"), "static_validation": ev(WORK / "1.0.0_rc5/static_validation.json")},
    "sessions": sessions,
    "review_integrity": {"status": "PASS" if not issues else "FAIL", "unique_reviewed_images": len(image_rows),
                         "image_statuses": dict(Counter(row["status"] for row in image_rows.values())),
                         "all_image_hashes_verified": True,
                         "reports": [ev(AUDIT / name) for name in review_names],
                         "note": "판독은 각 보고서의 제작자가 실제 PNG를 열어 수행했다. 이 통합 작업은 판독 기록과 현재 파일 해시를 대조했으며 미판독 캡처 5개를 추가 PASS로 세지 않는다."},
    "required_screen_groups": groups,
    "runtime_plan_resolution": {"plan": ev(AUDIT / "runtime_plan.json"), "required_steps": len(step_results),
                                "status": "PASS" if not missing_steps else "FAIL", "missing": missing_steps,
                                "steps": list(step_results.values()),
                                "note": "계획 실행/화면 접근의 유효 증거 집계. 상태 준비 명령과 종료 명령은 해당 실행 기록으로 확인하며 모든 단계가 독립 화면이라는 의미는 아니다."},
    "rc4_evidence_reuse": {
        "status": "PASS", "delta": ev(WORK / "1.0.0_rc5/rc4_delta.json"),
        "exact_difference": delta, "valid_rule": "rc4에서 실제 판독 PASS인 화면 중 두 변경 대상 밖의 문구·UI·글꼴·재질·게임 코드가 동일하다는 객체 비교 근거를 적용한다. 옛 FAIL/BLOCKED 6장은 재사용에서 제외한다.",
        "changed_targets_rechecked": [image(name)["image"] for name in ["233554_0579100_focus_tech.png", "233619_0934800_scroll.png", "233622_0435300_deco.png", "233627_0449900_appraiser.png", "233630_1413400_accountant.png"]],
        "support_extension": ev(AUDIT / "support_extension_change.json"), "support_boundary": ev(AUDIT / "support_extension_boundary.json"),
        "support_rule": "rc4/최종 rc5/원본 대표 비교는 동일 구 지원 DLL. 추가 2화면은 동일 신 지원 DLL로 후보·원본을 다시 실행했다. 기존 123개 메서드와 ActAccess 기존 본문 보존을 별도로 검사했다.",
    },
    "font_check": {"status": "PASS", "evidence": ev(fonts_path), "required_characters": fonts["requestedScalars"],
                   "font_count": fonts["checkedFonts"], "all_fallback_missing": 0,
                   "font_rows": [{key: row[key] for key in ["name", "status", "populationMode", "directMissingCount", "fallbackMissingCount",
                                      "atlasCountBefore", "atlasCountAfter", "shaderSupported", "materialUsesFirstAtlas"]} for row in fonts["rows"]],
                   "note": "정적 원래 글꼴의 직접 미지원 732자는 한글 대체 글꼴로 출력된다. 동적 3개는 실제 글자 생성, 정적 1개는 대체 흐름을 검사했다."},
    "first_native_craft": {"status": "PASS", "evidence": ev(FINAL / "233546_9229800_manual_craft.craft.json")},
    "historical_failures_preserved": True, "resolution_table": resolution_rows,
    "baseline": {"representative_comparison": ev(AUDIT / "baseline_comparison.json"), "extra_comparison": extra_comparison,
                 "patch_specific_game_errors": 0, "glyph_warnings": 0, "font_warnings": 0,
                 "common_warning_scope": "ComputeBuffer 종료 정리 경고 및 D3D12 정보 큐 기록은 원본의 같은 환경에서도 재현된다. 정확한 엔진/게임/지원 코드 소유자를 단정하지 않는다."},
    "availability": {"evidence": ev(AUDIT / "na_screens.json"), "screens": additional_screens,
                    "demo_unimplemented": plan["not_applicable"], "plan_evidence": ev(AUDIT / "runtime_plan.json")},
    "translation_runtime_coverage": {"evidence": ev(AUDIT / "runtime_translation_coverage.json"),
                                      "denominator": coverage["denominator"], "counts": coverage["counts"],
                                      "limitations": coverage["limitations"],
                                      "unobserved_status": "NOT_RUN", "unobserved_static_validation": "PASS",
                                      "note": "193위치 연결은 실제 판독 PASS 이미지의 화면 내 텍스트와 현재 번역값의 정확한 일치 근거다. 모든 해당 문장의 개별 가림 판정이나 전체 번역 문구 실관찰 완료를 뜻하지 않는다."},
    "not_run": [
        "번역 목록의 미관찰 1,523위치 개별 실화면 판독",
        "전체 회차·모든 분기·모든 조합",
        "정상 재화 획득·기술 해금·전쟁 승리 완주",
        "실제 전투에서 살아 있는 병사의 사망 전환",
        "모든 해상도·표시 배율 조합",
        "사용자 Steam 설치본의 설치 후 실제 그래픽 재실행",
    ],
    "user_installation": "이 G5 보고서는 격리 후보 검수다. 설치 파일 검증·최종 ZIP·사용자 설치 적용은 다른 단계에서 판정한다.",
}
write_json(AUDIT / "runtime_final_resolution.json", report)
assert not issues, issues
print(json.dumps({"status": report["status"], "steps": len(step_results), "screen_groups": len(groups),
                  "reviewed_images": len(image_rows), "counts": report["review_integrity"]["image_statuses"]}))
