"""REA가 확보한 소비 코드에서 확인한 필드 값만 별도 분류 기록으로 만든다."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029"
SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
RESPONSES = ROOT / "working_private/SOULASH_2/rea/responses"
OUTPUT = BASE / "reference_native_v6r3"
CORE = "data/mods/core_2/"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve(obj, path):
    for key in path.lstrip("/").split("/"):
        key = key.replace("~1", "/").replace("~0", "~")
        obj = obj[int(key)] if isinstance(obj, list) else obj[key]
    return obj


def main():
    OUTPUT.mkdir(exist_ok=False)
    expected = {row["path"]: row["sha256"] for row in json.loads((BASE / "baseline_manifest.json").read_text(encoding="utf-8"))["files"]}
    executable = (SOURCE / "Soulash 2.exe").read_bytes()
    assert hashlib.sha256(executable).hexdigest() == expected["Soulash 2.exe"]
    native = json.loads((BASE / "native/summary.json").read_text(encoding="utf-8"))
    image_base = int(native["image_base"], 16)
    aliases = {}
    for address, value in [(0x1408d4d08, "main"), (0x1408c6dc4, "map"), (0x1408c06fc, "id"), (0x1408bc40c, "name")]:
        rva = address - image_base
        section = next(row for row in native["sections"] if row["rva"] <= rva < row["rva"] + row["size"])
        offset = rva - section["rva"] + section["offset"]
        raw = value.encode("ascii") + b"\0"
        if executable[offset:offset + len(raw)] != raw:
            raise ValueError("소비 코드의 문자열 주소 별칭 불일치")
        aliases[hex(address)] = {"source": value, "file_offset": offset, "byte_sha256": hashlib.sha256(raw).hexdigest()}
    records, code = {}, {}
    for name in ("align", "chained_parse", "chained_read", "spawn_on", "equipment_load"):
        path = RESPONSES / ("pseudo_field_" + name + ".json")
        record = json.loads(path.read_text(encoding="utf-8"))["result"]["structuredContent"]
        if record["subject"]["digest"]["sha256"] != expected["Soulash 2.exe"]:
            raise ValueError("REA 분석 대상 해시 불일치")
        records[name] = {"artifact": path.relative_to(ROOT).as_posix(), "artifact_sha256": digest(path),
                         "evidence_id": record["evidence_id"], "subject_sha256": expected["Soulash 2.exe"],
                         "procedure_requested": record["parameters"]["procedure"],
                         "normalized_result_sha256": hashlib.sha256(record["normalized_result"].encode("utf-8")).hexdigest()}
        code[name] = record["normalized_result"].splitlines()
    path = RESPONSES / "pseudo_chained_marker_init.json"
    record = json.loads(path.read_text(encoding="utf-8"))["result"]["structuredContent"]
    assert record["subject"]["digest"]["sha256"] == expected["Soulash 2.exe"]
    records["marker_init"] = {"artifact": path.relative_to(ROOT).as_posix(), "artifact_sha256": digest(path),
                              "evidence_id": record["evidence_id"], "subject_sha256": expected["Soulash 2.exe"],
                              "procedure_requested": record["parameters"]["procedure"],
                              "normalized_result_sha256": hashlib.sha256(record["normalized_result"].encode("utf-8")).hexdigest()}
    code["marker_init"] = record["normalized_result"].splitlines()

    def proof(name, start, end, required):
        text = "\n".join(code[name][start - 1:end])
        if any(needle not in text for needle in required):
            raise ValueError("소비 코드 증거 구간 변경: " + name)
        return {**records[name], "normalized_result_line_start": start, "normalized_result_line_end": end, "source": text}

    proof_align = proof("align", 290, 341, ['&DAT_1408d4d08', '"align"', '"middle"', '"right"', 'local_a8[0] = 1', 'local_a8[0] = 2', '"format"'])
    proof_chained = proof("chained_parse", 1890, 2079, ['"chained"', '&DAT_1408c6dc4', 'local_370 != (char *****)0x0', 'DAT_140afe9f0', 'FUN_140022a00(pppppcStack_338,&local_380)'])
    proof_chained_read = proof("chained_read", 103, 119, ['"chained"', '&DAT_1408c6dc4', 'param_1 + 0x200'])
    proof_marker = proof("marker_init", 1, 9, ['DAT_140afe9f0', '"RESERVED_core_2_leader_tile"', '0x1b'])
    proof_spawn_context = proof("spawn_on", 482, 550, ['"scenarios"', '"spawns"', '"entities"', '"spawn_on"'])
    proof_spawn_store = proof("spawn_on", 733, 984, ['"spawn_on"', 'FUN_1402fe220(uVar7,&local_4e8)', 'local_a28 = &local_4e8', 'FUN_140523520'])
    proof_placement = proof("spawn_on", 711, 984, ['"placement"', '"random_spread"', '"random_spread_keep_close"', '"full_circle"', '"near_wall"', 'uVar6 = 0'])
    input_path = BASE / "effective_inventory/v3/unresolved_json_primary.jsonl"
    cache, counts, skipped, rows = {}, Counter(), Counter(), []
    definitions = {row["canonical_id"]: row["definitions"] for row in
                   map(json.loads, (BASE / "classification_reference_definitions.jsonl").open(encoding="utf-8")) if row["namespace"] == "entities"}
    for line in input_path.open(encoding="utf-8"):
        row = json.loads(line)["original_record"]
        file, field, value = row["file"], row["field_pattern"], row["source"]
        rule, evidence, reason = None, [], None
        if file == CORE + "messages.json" and field == "/main/*/align":
            rule, evidence = "native_message_alignment_enum", [proof_align]
            reason = "메시지 로더가 align을 middle=1/right=2/기타=0으로 변환하고 format 문자열과 별도 저장하는 배치 제어값"
        elif file.startswith(CORE + "entities/") and field == "/chained/map/*/*":
            if value.startswith("RESERVED") and value != "RESERVED_core_2_leader_tile":
                skipped["reserved_marker_global_initializer_pending"] += 1
                continue
            rule, evidence = "native_chained_layout_cell", [proof_chained, proof_chained_read]
            reason = "chained.map 2차원 배열의 빈 문자열은 건너뛰고 나머지 값은 상대좌표와 함께 부품 참조로 저장함. 표시 문구와 구분"
            if value == "RESERVED_core_2_leader_tile":
                rule, evidence = "native_chained_leader_marker", [proof_chained, proof_marker]
                reason = "정적 초기화 함수가 설정한 leader marker와 정확 비교하여 좌표 원점을 찾고 일반 부품 목록에서는 제외하는 제어값"
        elif file == CORE + "locations.json" and field == "/special/*/scenarios/*/spawns/*/spawn_on/*":
            skipped["spawn_on_final_reference_consumer_unobserved"] += 1
            continue
        elif file == CORE + "locations.json" and field == "/special/*/scenarios/*/spawns/*/placement":
            rule, evidence = "native_spawn_placement_enum", [proof_spawn_context, proof_placement]
            reason = "생성 배치 문자열을 random_spread=1/keep_close=2/full_circle=4/near_wall=5/기타0 등의 숫자 enum으로 변환함"
        if not rule:
            continue
        if file not in cache:
            if digest(SOURCE / file) != expected[file]:
                raise ValueError("원본 파일 지문 불일치")
            cache[file] = json.loads((SOURCE / file).read_text(encoding="utf-8-sig"))
        if resolve(cache[file], row["field_path"]) != value:
            raise ValueError("위치의 실제 값 불일치")
        result = {key: row[key] for key in ("location_id", "file", "field_path", "field_pattern", "source", "source_file_sha256", "source_value_sha256")}
        result.update(previous_classification="UNKNOWN", classification="INTERNAL", rule_id=rule, reason=reason,
                      evidence_kind="rea_native_consumer_code", native_evidence=evidence,
                      source_executable_sha256=expected["Soulash 2.exe"], runtime_observed=False)
        if rule == "native_chained_layout_cell" and value:
            targets = definitions.get(value, [])
            result["reference_diagnostic"] = {"status": "UNIQUE" if len(targets) == 1 else "AMBIGUOUS_OR_MISSING",
                                               "target_count": len(targets), "definitions": targets,
                                               "source_value_modified": False, "runtime_target_choice": "UNKNOWN"}
        rows.append(result)
        counts[rule] += 1
    with (OUTPUT / "classification_native_overlay_v6.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    report = {"status": "PASS", "new_internal": len(rows), "rules": counts, "skipped": skipped,
              "input_sha256": digest(input_path), "tool_sha256": digest(Path(__file__)), "alias_byte_evidence": aliases,
              "native_evidence_artifacts": records, "equipment_name_status": "UNKNOWN_HOLD_1847",
              "equipment_reason": "확보한 equipment_load 함수는 슬롯 항목 id 정규화만 확인. name 미참조만으로 다른 화면·함수에서 미사용이라고 단정하지 않음",
              "classification_overlay_sha256": digest(OUTPUT / "classification_native_overlay_v6.jsonl"),
              "supersedes_overlay_sha256": digest(BASE / "reference_native_v6r2/classification_native_overlay_v6.jsonl"),
              "review_correction": "독립 검토에서 spawn_on320은 배열 저장만 확인되어 승격 취소. 실제 참조/필터 소비 경로 확인 필요.",
              "limitations": ["실제 실행 관찰이 아닌 동일 EXE의 정적 소비 코드 분석", "다른 같은 이름 필드로 판정을 확대하지 않음", "Hydra 4개 참조의 중복 정의 선택은 별도 원본 동작 진단 유지", "spawn_on320은 실제 참조 소비 미확인으로 UNKNOWN 유지"]}
    (OUTPUT / "native_field_summary_v6.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ["status", "new_internal", "rules", "skipped", "equipment_name_status"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
