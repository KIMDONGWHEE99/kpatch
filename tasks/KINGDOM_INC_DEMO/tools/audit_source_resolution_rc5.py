"""원본·rc4 감사는 보존하고 rc5의 미디어 보완과 현재 출처 근거를 연결합니다."""
from common import *
from collections import Counter
from datetime import datetime, timezone
import re
import UnityPy
from PIL import Image

AUDIT = WORK / "audit"
INSPECT = ROOT / "extracted_private" / GAME_ID / "inspection"
CODE = INSPECT / "decompiled"
STATIC_PATH = WORK / "1.0.0_rc5/static_validation.json"
BUILD_PATH = WORK / "1.0.0_rc5/build.json"
OUTPUT = AUDIT / "source_resolution_rc5.json"
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
historical_rc4_path = AUDIT / "source_resolution_final.json"
historical_rc4_hash = digest(historical_rc4_path)
media_prepared_path = AUDIT / "media_resolution_icons32.json"
media_prepared = read(media_prepared_path)
media_reclassification = read(AUDIT / "media_reclassification_icons32.json")
check(media_prepared["status"] == "PASS", "새 아이콘 준비 검증")
check_hash(media_prepared["current_ledger"]["path"], media_prepared["current_ledger"]["sha256"],
           "미디어 분류 해결표와 현재 목록")
check_hash(media_prepared["prepared_evidence"]["path"], media_prepared["prepared_evidence"]["sha256"],
           "미디어 준비 픽셀 근거")
check_hash(media_prepared["reclassification_evidence"]["path"], media_prepared["reclassification_evidence"]["sha256"],
           "미디어 재분류 이력")
asset_summary = read(AUDIT / "asset_summary.json")
code_summary = read(AUDIT / "code_summary.json")
media_summary = read(AUDIT / "media_summary.json")
for item in summary["inputs"]:
    if Path(item["path"]).name == "media_classification.json":
        check_hash(AUDIT / "media_classification_before_icons32.json", item["sha256"],
                   "원래 출처 요약의 미디어 분류는 이전 목록 사본으로 보존")
    else:
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
historical_media = read(AUDIT / "media_classification_before_icons32.json")
historical_media_by_id = {r["id"]: r for r in historical_media}
media_record_changes = [r["id"] for r in media if r != historical_media_by_id[r["id"]]]
check(set(media_record_changes) == {"resources.assets/82", "sharedassets0.assets/11"},
      "미디어 분류 변경 경계")
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
            if parent["id"] == "sharedassets0.assets/11":
                rect = row["texture_rect"]
                overlaps = max(rect["x"], 35) < min(rect["x"] + rect["width"], 51)
                overlaps = overlaps and max(rect["y"], 205) < min(rect["y"] + rect["height"], 221)
                expected_treatment = "TRANSLATE" if overlaps else historical_media_by_id[row["id"]]["treatment"]
                check(parent.get("region_treatments", [])[0]["rect_unity_xywh"] == [35, 205, 16, 16],
                      row["id"] + ": 영역별 부모 처리 근거")
                check(row["treatment"] == expected_treatment, row["id"] + ": 영역별 부모 처리 분류")
                check(not overlaps or row["id"] == "resources.assets/82", row["id"] + ": 변경 셀 교차 범위")
            else:
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
check(static["status"] == "PASS", "rc5 정적 검증 실패")
check(static["build_id"] == "1.0.0_rc5", "후보 식별자")
check_hash(BUILD_PATH, static["build_sha256"], "rc5 제작 기록")
for item in static["verification_inputs"]:
    check_hash(item["path"], item["sha256"], "rc5 정적 검증 입력 최신성")
candidate = Path(static["candidate"])
candidate_mismatches = []
for row in build["files"]:
    path = candidate / row["path"]
    if not path.is_file() or digest(path) != row["sha256"] or path.stat().st_size != row["size"]:
        candidate_mismatches.append(row["path"])
check(not candidate_mismatches, "rc5 후보 파일 해시 불일치")
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
check(table_check["status"] == "PASS", "rc5 표 검증 단계")

# 정적 검증의 성공 표시와 별개로 후보의 실제 Sprite/Texture를 다시 읽습니다.
expected_sprite_path = Path(media_prepared["expected_sprite"]["path"])
expected_atlas_path = Path(media_prepared["expected_atlas"]["path"])
check_hash(expected_sprite_path, media_prepared["expected_sprite"]["sha256"], "확정 글 아이콘")
check_hash(expected_atlas_path, media_prepared["expected_atlas"]["sha256"], "확정 아이콘판")
expected_sprite = Image.open(expected_sprite_path).convert("RGBA")
expected_atlas = Image.open(expected_atlas_path).convert("RGBA")
source_texture_obj = UnityPy.load(str(DATA / "sharedassets0.assets")).file.objects[11]
candidate_texture_obj = UnityPy.load(str(candidate / DATA_NAME / "sharedassets0.assets")).file.objects[11]
candidate_sprite_obj = candidate_env.file.objects[82]
original_atlas = source_texture_obj.read().image.convert("RGBA")
candidate_atlas = candidate_texture_obj.read().image.convert("RGBA")
candidate_sprite = candidate_sprite_obj.read().image.convert("RGBA")
check(candidate_atlas.tobytes() == expected_atlas.tobytes(), "후보 아이콘판 전체 기대 픽셀")
check(candidate_sprite.tobytes() == expected_sprite.tobytes(), "후보 Icons_32 Sprite 기대 픽셀")
check(candidate_sprite_obj.get_raw_data() == source_env.file.objects[82].get_raw_data(),
      "Icons_32 Sprite 메타데이터 원본 보존")
outside_changed_pixels = [
    [x, y] for y in range(256) for x in range(256)
    if not (35 <= x < 51 and 35 <= y < 51)
    and candidate_atlas.getpixel((x, y)) != original_atlas.getpixel((x, y))
]
check(not outside_changed_pixels, "후보 아이콘 셀 밖 픽셀 변경")
media_candidate_resolution = {
    "status": "PASS" if candidate_atlas.tobytes() == expected_atlas.tobytes()
    and candidate_sprite.tobytes() == expected_sprite.tobytes() and not outside_changed_pixels else "FAIL",
    "source_ids": ["sharedassets0.assets/11", "resources.assets/82"],
    "prepared_evidence": reference(media_prepared_path),
    "reclassification_evidence": reference(AUDIT / "media_reclassification_icons32.json"),
    "expected_sprite": reference(expected_sprite_path),
    "expected_atlas": reference(expected_atlas_path),
    "candidate_texture_file": reference(candidate / DATA_NAME / "sharedassets0.assets"),
    "candidate_sprite_file": reference(candidate / DATA_NAME / "resources.assets"),
    "candidate_sprite_rgba_sha256": hashlib.sha256(candidate_sprite.tobytes()).hexdigest(),
    "outside_changed_pixels": len(outside_changed_pixels),
    "inspection": "후보 파일을 UnityPy로 다시 열어 실제 Sprite를 추출하고 기대 RGBA와 완전 대조했다.",
    "runtime_visual_retest": "이 출처 해결표에서는 판정하지 않음",
}

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
expected_media_counts = dict(media_summary["treatment_counts"])
expected_media_counts["KEEP"] -= 2
expected_media_counts["TRANSLATE"] += 2
check(media_counts == expected_media_counts, "원본 미디어 합계와 재분류 2개 변경의 합")
check(sha(summary_path) == summary_hash, "원본 출처 요약 변경 금지")
check(sha(historical_rc4_path) == historical_rc4_hash, "과거 rc4 해결표 변경 금지")
result = {
    "status": "PASS" if not issues else "FAIL",
    "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
    "scope": "G2의 추출·분류·근거 최신성과 rc5의 원본 누락 키/추가 픽셀 위치 해결. 엔진 공용 라이브러리 전체 문자열 전수조사나 G5·설치 완료 판정이 아닙니다.",
    "game_id": GAME_ID, "source_build": BUILD, "candidate_build": "1.0.0_rc5",
    "issues": issues,
    "historical_source_summary": reference(summary_path) | {
        "preserved": True, "original_missing_key_failures_preserved": 6},
    "historical_rc4_resolution": reference(historical_rc4_path) | {"preserved": True},
    "historical_media_summary": reference(AUDIT / "media_summary.json") | {
        "preserved": True, "counts_at_that_time": media_summary["treatment_counts"],
        "current_count_delta": {"KEEP": -2, "TRANSLATE": 2}},
    "classification": {
        "assets": {"locations": len(assets), "counts": asset_counts,
                   "unique_evidence_groups": len({r["evidence"] for r in assets})},
        "code": {"locations": len(code), "counts": code_counts,
                 "scope": "Assembly-CSharp.dll", "unique_evidence_groups": len({r["evidence"] for r in code})},
        "media": {"locations": len(media), "counts": media_counts,
                  "texture_count": 192, "sprite_count": 829,
                  "translated_logical_image_count": 2, "translated_object_locations": 4,
                  "review_images_hash_checked": len(media_links)},
        "unknown_locations": unknown, "unknown_count": len(unknown),
        "unsupported_keep_or_exclusion_locations": unsupported,
        "unsupported_keep_or_exclusion_count": len(unsupported),
        "evidence_review_note": "위치·원본 해시·원문 해시·소비 명령·미디어 연결을 재대조했다. 과거 분류와 다른 미디어 2개는 실제 rc4 화면 발견→원본 Sprite/소비 코드→imagegen 동일 출력 재사용→기대 픽셀→후보 재추출로 해결했다. 부모 atlas 처리는 영역별이며 관련 없는 자식 Sprite는 기존 KEEP 근거를 유지한다.",
    },
    "media_added_location_resolution": media_candidate_resolution,
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
        "direct_asset_locations": "해당 후보 static_validation의 위치별 검증 기록 참조",
        "table_locations": 1556, "added_keys": 6,
        "code_literal_locations": 4, "image_object_locations": 4,
        "related_static_checks": [row for row in static["checks"] if row["name"] in
                                 ["위치별 번역·서식·언어 표", "한국어 이미지 픽셀·필드", "DLL 모든 명령·메타데이터 재대조"]],
        "layout_change_note": "기술 카드 배치 및 rc5 입력창 표시 보완의 검사 범위는 현재 정적 검증에 연결한다. 이 해결표는 실제 화면 확인 완료를 선언하지 않는다.",
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
media_summary_rc5_path = AUDIT / "media_summary_rc5.json"
write_json(media_summary_rc5_path, {
    "status": result["status"],
    "scope": "출처 미디어 분류와 rc5 후보 픽셀 대조. 전체 실행·설치 완료가 아니다.",
    "historical_media_summary": reference(AUDIT / "media_summary.json"),
    "current_ledger": reference(AUDIT / "media_classification.json"),
    "media_input": reference(EXTRACT / "media.json"),
    "source_resolution": reference(OUTPUT),
    "type_counts": {"Texture2D": 192, "Sprite": 829},
    "treatment_counts": media_counts,
    "translation_locations": [r["id"] for r in media if r["treatment"] == "TRANSLATE"],
    "translated_logical_images": 2,
    "changed_records_from_original_audit": media_record_changes,
    "original_counts": media_summary["treatment_counts"],
    "count_delta": {"NO_TEXT": 0, "KEEP": -2, "TRANSLATE": 2},
    "unknown_count": sum(r.get("treatment") == "UNKNOWN" for r in media),
    "region_note": "Icons atlas의 16×16 셀만 번역하고 나머지 픽셀과 그 영역의 Sprite는 기존 판정을 유지한다.",
    "candidate_pixel_resolution": media_candidate_resolution,
})
write_json(AUDIT / "source_summary_rc5.json", {
    "status": result["status"],
    "scope": "G2 현재 수치·근거 연결표. 원래 source_summary와 rc4 해결표를 보존한다.",
    "historical_summary": reference(summary_path),
    "current_resolution": reference(OUTPUT),
    "candidate_build": "1.0.0_rc5",
    "asset_summary": reference(AUDIT / "asset_summary.json") | {
        "locations": len(assets), "counts": asset_counts, "unchanged": True},
    "code_summary": reference(AUDIT / "code_summary.json") | {
        "locations": len(code), "counts": code_counts, "unchanged": True},
    "media_summary": reference(media_summary_rc5_path) | {
        "locations": len(media), "counts": media_counts, "changed_records": media_record_changes},
    "unknown_count": len(unknown),
    "unsupported_keep_or_exclusion_count": len(unsupported),
    "unresolved_extraction_count": result["extraction_resolution"]["unresolved_count"],
    "original_missing_keys": {
        "original_fail_count_preserved": 6, "candidate_resolved_count": len(key_resolution),
        "evidence": reference(OUTPUT)},
    "excluded_or_unimplemented_scope": result["excluded_or_unimplemented_scope"],
    "runtime_and_installation": result["runtime_and_installation"],
})
print(json.dumps({"status": result["status"], "unknown": len(unknown),
                  "unsupported": len(unsupported),
                  "unresolved_extraction": result["extraction_resolution"]["unresolved_count"],
                  "missing_keys_resolved": len(key_resolution), "issues": issues},
                 ensure_ascii=False))
if issues:
    raise SystemExit(1)
