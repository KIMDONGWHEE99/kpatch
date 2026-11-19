"""원본 감사는 보존하고 rc4의 출처·추출·누락 키 해결 근거를 연결합니다."""
from common import *
from collections import Counter
from datetime import datetime, timezone
import re
import UnityPy

AUDIT = WORK / "audit"
INSPECT = ROOT / "extracted_private" / GAME_ID / "inspection"
CODE = INSPECT / "decompiled"
STATIC_PATH = WORK / "1.0.0_rc4/static_validation.json"
BUILD_PATH = WORK / "1.0.0_rc4/build.json"
OUTPUT = AUDIT / "source_resolution_final.json"
issues = []
hash_checks = []
hash_cache = {}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    path = Path(path).resolve()
    if str(path) not in hash_cache:
        hash_cache[str(path)] = sha(path)
    return hash_cache[str(path)]


def check(condition, message):
    if not condition:
        issues.append(message)
    return bool(condition)


def check_hash(path, expected, purpose):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    actual = digest(path) if path.is_file() else None
    valid = check(actual == expected, purpose + ": " + str(path))
    hash_checks.append({"path": str(path), "expected_sha256": expected,
                        "observed_sha256": actual, "purpose": purpose,
                        "status": "PASS" if valid else "STALE"})
    return valid


def reference(path):
    return {"path": str(path), "sha256": digest(path)}


summary_path = AUDIT / "source_summary.json"
summary_hash = digest(summary_path)
summary = read(summary_path)
asset_summary = read(AUDIT / "asset_summary.json")
code_summary = read(AUDIT / "code_summary.json")
media_summary = read(AUDIT / "media_summary.json")
for item in summary["inputs"]:
    check_hash(item["path"], item["sha256"], "출처 감사 입력 동일성")
item = summary["resolved_extraction_errors"]
check_hash(item["path"], item["sha256"], "추출 해결 기록 동일성")
input_map = [
    (EXTRACT / "strings.json", asset_summary["input_sha256"]),
    (EXTRACT / "additional_strings.json", asset_summary["additional_sha256"]),
    (INSPECT / "code_strings.json", code_summary["code_inventory_sha256"]),
    (EXTRACT / "media.json", media_summary["media_input_sha256"]),
]
for path, expected in input_map:
    check_hash(path, expected, "추출 목록 동일성")
for name, details in [("assets", asset_summary), ("code", code_summary), ("media", media_summary)]:
    check_hash(Path(__file__).with_name(f"audit_{name}.py"), details["tool_sha256"], "분류 도구 동일성")
assembly = DATA / "Managed/Assembly-CSharp.dll"
check_hash(assembly, code_summary["assembly_sha256"], "코드 소비 근거의 원본 DLL")
assets = read(AUDIT / "asset_classification.json")
code = read(AUDIT / "code_classification.json")
media = read(AUDIT / "media_classification.json")
asset_inputs = read(EXTRACT / "strings.json") + read(EXTRACT / "additional_strings.json")
asset_original = {row["id"]: row for row in asset_inputs}
code_inputs = read(INSPECT / "code_strings.json")
code_original = {(row["method"], row["offset"]): row for row in code_inputs}
media_original = {row["id"]: row for row in read(EXTRACT / "media.json")}
check(len(assets) == len(asset_original) == 29399, "자산 문자열 위치 수")
check(len(code) == len(code_original) == 3136, "코드 문자열 위치 수")
check(len(media) == len(media_original) == 1021, "미디어 위치 수")
check({row["id"] for row in assets} == set(asset_original), "자산 위치 누락/추가")
check({(row["method"], row["offset"]) for row in code} == set(code_original), "코드 위치 누락/추가")
check({row["id"] for row in media} == set(media_original), "미디어 위치 누락/추가")
unknown = []
unsupported = []
source_files_checked = set()
for row in assets + media:
    original_row = (asset_original if "source" in row else media_original)[row["id"]]
    for field in ("file", "file_sha256", "path_id", "object_sha256"):
        check(row[field] == original_row[field], row["id"] + ": 추출 위치 연결 " + field)
    path = DATA / row["file"]
    if str(path) not in source_files_checked:
        check_hash(path, row["file_sha256"], "분류 위치의 원본 자산")
        source_files_checked.add(str(path))
    check(row.get("evidence", "").strip(), row["id"] + ": 분류 근거 없음")
    if row.get("classification") == "UNKNOWN" or row.get("treatment") == "UNKNOWN":
        unknown.append(row["id"])
    if not row.get("evidence", "").strip():
        unsupported.append(row["id"])
    if "source" in row:
        check(row["source"] == original_row["source"], row["id"] + ": 원문 연결")
        check(hashlib.sha256(row["source"].encode("utf-8")).hexdigest() == row["source_sha256"],
              row["id"] + ": 원문 해시")
for row in code:
    original_row = code_original[(row["method"], row["offset"])]
    check(row["source"] == original_row["source"] and row["context"] == original_row["context"],
          row["id"] + ": 코드 원문/소비 명령 연결")
    check(row["assembly_sha256"] == code_summary["assembly_sha256"], row["id"] + ": DLL 연결")
    check(hashlib.sha256(row["source"].encode("utf-8")).hexdigest() == row["source_sha256"],
          row["id"] + ": 코드 원문 해시")
    if row.get("classification") == "UNKNOWN":
        unknown.append(row["id"])
    if not row.get("evidence", "").strip():
        unsupported.append(row["id"])
media_by_id = {row["id"]: row for row in media}
media_links = set()
for row in media:
    for path_key, sha_key in [("image", "image_sha256"), ("review_sheet", "review_sheet_sha256")]:
        if row.get(path_key) and row.get(sha_key) and row[path_key] not in media_links:
            check_hash(row[path_key], row[sha_key], "육안 검토 이미지 연결")
            media_links.add(row[path_key])
    if row["type"] == "Sprite":
        parent = media_by_id.get(row.get("texture_id"))
        check(bool(parent), row["id"] + ": 부모 텍스처 없음")
        if parent:
            check(row.get("parent_image_sha256") == parent.get("image_sha256"),
                  row["id"] + ": 부모 픽셀 해시")
            check(bool(row.get("parent_evidence")), row["id"] + ": 부모 분류 근거")
            check(row["treatment"] == parent["treatment"], row["id"] + ": 부모 처리 분류")
check(not unknown, "미분류 위치가 남음")
check(not unsupported, "유지/제외 근거 없는 위치가 남음")
check(read(AUDIT / "asset_unknown.json") == [] and read(AUDIT / "code_unknown.json") == [],
      "미분류 보조 목록이 비어 있지 않음")

errors = read(EXTRACT / "errors.json")
resolutions = read(EXTRACT / "error_resolutions.json")
check({r["id"] for r in errors} == {r["id"] for r in resolutions}, "추출 오류 해결표 위치 불일치")
error_results = []
environments = {}
for row in resolutions:
    check_hash(DATA / row["file"], row["file_sha256"], "추출 오류 대상 원본")
    if row["file"] not in environments:
        environments[row["file"]] = load_asset(DATA / row["file"])
    obj = environments[row["file"]].file.objects[row["path_id"]]
    check(hashlib.sha256(obj.get_raw_data()).hexdigest() == row["object_sha256"],
          row["id"] + ": 추출 오류 객체 해시")
    detail = {"id": row["id"], "historical_classification": row["classification"],
              "resolution": row["resolution"]}
    try:
        tree = read_tree(obj)
        if row["type"] == "Texture2D":
            state = {"width": tree["m_Width"], "height": tree["m_Height"],
                     "image_bytes": len(tree["image data"]), "stream": tree["m_StreamData"]}
            valid = state["width"] == state["height"] == state["image_bytes"] == 0
            valid = valid and state["stream"]["size"] == 0 and not state["stream"]["path"]
            detail["empty_dynamic_texture"] = state
        else:
            valid = isinstance(tree, dict) and bool(tree)
            detail["parsed_fields"] = len(tree)
        valid = valid and row["status"] == "PASS"
        check(valid, row["id"] + ": 해결 조건 재확인 실패")
        detail["status"] = "PASS" if valid else "FAIL"
    except Exception as error:
        issues.append(row["id"] + ": 재해석 실패 " + str(error))
        detail["status"] = "FAIL"
        detail["error"] = str(error)
    error_results.append(detail)

object_inventory = read(EXTRACT / "objects.json")
actual_object_types = Counter()
actual_object_ids = set()
for path in asset_files():
    env = environments.get(path.name) or UnityPy.load(str(path))
    for obj in env.objects:
        actual_object_types[obj.type.name] += 1
        actual_object_ids.add((path.name, obj.path_id))
check(len(object_inventory) == summary["media_video"]["object_count"] == len(actual_object_ids),
      "전체 객체 목록 수")
check({(row["file"], row["path_id"]) for row in object_inventory} == actual_object_ids,
      "전체 객체 목록 위치 연결")
check(actual_object_types["VideoClip"] == 0, "VideoClip 제외 근거")

static = read(STATIC_PATH)
build = read(BUILD_PATH)
check(static["status"] == "PASS", "rc4 정적 검증 실패")
check(static["build_id"] == "1.0.0_rc4", "후보 식별자")
check_hash(BUILD_PATH, static["build_sha256"], "rc4 제작 기록")
for item in static["verification_inputs"]:
    check_hash(item["path"], item["sha256"], "rc4 정적 검증 입력 최신성")
candidate = Path(static["candidate"])
candidate_mismatches = []
for row in build["files"]:
    path = candidate / row["path"]
    if not path.is_file() or digest(path) != row["sha256"] or path.stat().st_size != row["size"]:
        candidate_mismatches.append(row["path"])
check(not candidate_mismatches, "rc4 후보 파일 해시 불일치")
canonical_path = WORK / "translation/canonical.json"
canonical = read(canonical_path)


def parse_language(text):
    pairs = [line.split("=", 1) for line in text.splitlines()
             if line.strip() and not line.lstrip().startswith(";")]
    result = {key.strip(): value.strip() for key, value in pairs}
    check(len(result) == len(pairs), "언어 표 중복 키")
    return result


source_env = UnityPy.load(str(DATA / "resources.assets"))
candidate_env = UnityPy.load(str(candidate / DATA_NAME / "resources.assets"))
original_table = parse_language(source_env.file.objects[21].read_typetree()["m_Script"])
candidate_table = parse_language(candidate_env.file.objects[21].read_typetree()["m_Script"])
check(len(original_table) == 1556 and len(candidate_table) == 1562, "원본/후보 언어 키 수")
key_resolution = []
for row in summary["original_missing_keys"]:
    key = row["key"]
    expected = canonical["additions"][key]
    actual = candidate_table.get(key)
    valid = key not in original_table and actual == expected and bool(actual)
    check(valid, "원본 누락 키 후보 해결: " + key)
    key_resolution.append({"key": key, "original_status": row["status"],
                           "original_evidence": row, "expected": expected, "actual": actual,
                           "candidate_location": "KingdomInc_Data/resources.assets/21/m_Script:" + key,
                           "status": "PASS" if valid else "FAIL"})
check(set(canonical["additions"]) == {r["key"] for r in key_resolution}, "추가 키 해결 범위")
for row in canonical["rows"]:
    check(candidate_table.get(row["key"]) == row["target"], "후보 번역 위치 값: " + row["key"])
table_check = next(row for row in static["checks"] if row["name"] == "위치별 번역·서식·언어 표")
check(table_check["status"] == "PASS", "rc4 표 검증 단계")

plan_path = AUDIT / "runtime_plan.json"
plan = read(plan_path)
for item in plan["evidence"]:
    check_hash(item["path"], item["sha256"], "데모 화면 범위 근거")
urp = summary["library_scope"]["urp_debug_evidence"]
check_hash(urp["path"], urp["sha256"], "URP 디버그 제외 근거")
urp_tree = read(urp["path"])
check("supportRuntimeDebugDisplay" in json.dumps(urp_tree), "URP 디버그 필드 근거")
demo_evidence = []
for filename, observations in [
    ("Assets.Source.Player/TechNode.cs", ["CostTier > 4", 'node.Identifier != "turtle_statue"', "node.Hidden = (GamePlayer ply) => true"]),
    ("Assets.Source.Items/ItemType.cs", ["new Tier1();", "new Tier2();", "new Tier3();", "new Tier4();"]),
    ("Assets.Source.Player.Tech/T7Farm.cs", ["CostTier = 7"]),
    ("Assets.Source.Player.Tech/T8Dungeon.cs", ["CostTier = 8"]),
    ("Assets.Behaviour.UI/GameUI.cs", ["public void UpdateFarmButton()", "public void UpdateDungeonButton()"]),
]:
    path = CODE / filename
    text = path.read_text(encoding="utf-8-sig")
    check(all(value in text for value in observations), "데모 범위 코드 근거: " + filename)
    demo_evidence.append(reference(path) | {"observed_conditions": observations})
absent_files = ["Assets.Source.Flow.Elements/Farm.cs", "Assets.Source.Flow.Elements/Dungeon.cs",
                "Assets.Behaviour.UI.Farm/FarmMenu.cs", "Assets.Behaviour.UI.Dungeon/DungeonMenu.cs"]
for name in absent_files:
    check(not (CODE / name).exists(), "미구현 화면으로 분류한 클래스 존재: " + name)

asset_counts = dict(Counter(row["classification"] for row in assets))
code_counts = dict(Counter(row["classification"] for row in code))
media_counts = dict(Counter(row["treatment"] for row in media))
check(asset_counts == asset_summary["counts"], "자산 분류 합계")
check(code_counts == code_summary["counts"], "코드 분류 합계")
check(media_counts == media_summary["treatment_counts"], "미디어 분류 합계")
check(sha(summary_path) == summary_hash, "원본 출처 요약 변경 금지")
result = {
    "status": "PASS" if not issues else "FAIL",
    "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
    "scope": "G2의 기존 추출·분류·근거 최신성 및 rc4에 의한 원본 누락 키 해결. 엔진 공용 라이브러리 전체 문자열 전수조사나 G5·설치 완료 판정이 아닙니다.",
    "game_id": GAME_ID, "source_build": BUILD, "candidate_build": "1.0.0_rc4",
    "issues": issues,
    "historical_source_summary": reference(summary_path) | {
        "preserved": True, "original_missing_key_failures_preserved": 6},
    "classification": {
        "assets": {"locations": len(assets), "counts": asset_counts,
                   "unique_evidence_groups": len({r["evidence"] for r in assets})},
        "code": {"locations": len(code), "counts": code_counts,
                 "scope": "Assembly-CSharp.dll", "unique_evidence_groups": len({r["evidence"] for r in code})},
        "media": {"locations": len(media), "counts": media_counts,
                  "texture_count": 192, "sprite_count": 829,
                  "translated_logical_image_count": 1, "translated_object_locations": 2,
                  "review_images_hash_checked": len(media_links)},
        "unknown_locations": unknown, "unknown_count": len(unknown),
        "unsupported_keep_or_exclusion_locations": unsupported,
        "unsupported_keep_or_exclusion_count": len(unsupported),
        "evidence_review_note": "위치·원본 파일/객체 해시·원문 해시·소비 명령·이미지/부모 텍스처 연결이 현재도 일치합니다. 이전에 검토한 38개 자산 근거군·52개 코드 근거군과 미디어 판정 근거를 재사용했습니다.",
    },
    "extraction_resolution": {
        "original_errors": reference(EXTRACT / "errors.json"),
        "resolution_evidence": reference(EXTRACT / "error_resolutions.json"),
        "original_error_count": len(errors),
        "resolved_count": sum(r["status"] == "PASS" for r in error_results),
        "unresolved_count": sum(r["status"] != "PASS" for r in error_results),
        "records": error_results,
        "historical_unknown_note": "오류 원문과 해결 기록의 classification=UNKNOWN은 당시 원문입니다. 최종 재해석/빈 동적 텍스처 확인을 PASS로 연결했고 과거 기록을 덮어쓰지 않았습니다.",
    },
    "missing_key_resolution": {
        "original_evidence": reference(AUDIT / "key_coverage_original.json"),
        "canonical": reference(canonical_path),
        "static_validation": reference(STATIC_PATH),
        "static_validation_check": table_check,
        "candidate_resources": reference(candidate / DATA_NAME / "resources.assets"),
        "independent_candidate_reextract": "PASS" if all(r["status"] == "PASS" for r in key_resolution) else "FAIL",
        "original_key_count": len(original_table), "candidate_key_count": len(candidate_table),
        "records": key_resolution,
    },
    "candidate_source_to_patch": {
        "build": reference(BUILD_PATH),
        "current_candidate_file_count": len(build["files"]),
        "candidate_hash_mismatches": candidate_mismatches,
        "direct_asset_locations": 154, "table_locations": 1556, "added_keys": 6,
        "code_literal_locations": 4, "image_object_locations": 2,
        "related_static_checks": [row for row in static["checks"] if row["name"] in
                                 ["위치별 번역·서식·언어 표", "한국어 이미지 픽셀·필드", "DLL 모든 명령·메타데이터 재대조"]],
        "layout_change_note": "rc4 기술 카드 3개 필드 변경의 정적 검사는 별도 PASS이며 시각 확인 완료를 이 문서에서 선언하지 않습니다.",
    },
    "retained_visible_content": summary["visible_keep"],
    "excluded_or_unimplemented_scope": {
        "shared_library_literal_inventory": {
            "status": "NOT_RUN",
            "library_count": len(summary["library_scope"]["observed_libraries"]),
            "evidence": summary["library_scope"]["evidence"],
            "urp_debug_evidence": urp,
            "claim_limit": "위 UNKNOWN=0은 기록된 게임 자산·Assembly-CSharp·Texture2D/Sprite 범위입니다. 모든 DLL의 모든 영문을 추출했다는 주장은 하지 않습니다.",
        },
        "videos": summary["media_video"] | {
            "object_inventory": reference(EXTRACT / "objects.json"),
            "current_original_object_count": len(actual_object_ids),
            "current_original_videoclip_count": actual_object_types["VideoClip"],
            "rechecked_from_original_assets": True,
        },
        "demo_screens": {
            "status": "NOT_APPLICABLE",
            "plan": reference(plan_path), "plan_decisions": plan["not_applicable"],
            "current_code_evidence": demo_evidence, "absent_dedicated_class_paths": absent_files,
            "scope_note": "농장·던전의 실제 시설/전용 화면 및 미등록 후반 인물 상태의 실행 검수 제외입니다. 남아 있는 설명·도움말·선행 조건은 번역표 전체에 포함되어 정적 대조했습니다.",
        },
    },
    "hash_checks": hash_checks,
    "runtime_and_installation": {
        "G5": "이 해결표에서는 판정하지 않음",
        "installation": "이 해결표에서는 판정하지 않음",
        "release": "이 해결표에서는 판정하지 않음",
        "static_report_runtime_qa_value": static["runtime_qa"],
    },
}
write_json(OUTPUT, result)
print(json.dumps({"status": result["status"], "unknown": len(unknown),
                  "unsupported": len(unsupported),
                  "unresolved_extraction": result["extraction_resolution"]["unresolved_count"],
                  "missing_keys_resolved": len(key_resolution), "issues": issues},
                 ensure_ascii=False))
if issues:
    raise SystemExit(1)
