"""문서화된 참조 필드의 용도와 원본 참조 해석 상태를 별도로 기록한다."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import soulash2_reference_audit as common

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029"
SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
OUTPUT = BASE / "reference_v5"
CORE = "data/mods/core_2/"


def read_rows(relative):
    for line in (BASE / relative).open(encoding="utf-8"):
        yield json.loads(line)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve(obj, pointer):
    for key in pointer.lstrip("/").split("/"):
        key = key.replace("~1", "/").replace("~0", "~")
        obj = obj[int(key)] if isinstance(obj, list) else obj[key]
    return obj


def main():
    OUTPUT.mkdir(exist_ok=False)
    input_name = "effective_inventory/v2/unresolved_json_primary.jsonl"
    remaining = {row["location_id"]: row["original_record"] for row in read_rows(input_name)}
    expected = {row["path"]: row["sha256"] for row in json.loads((BASE / "baseline_manifest.json").read_text(encoding="utf-8"))["files"]}
    checked, cache = {}, {}

    def load(relative):
        if relative not in cache:
            checked[relative] = digest(SOURCE / relative)
            if checked[relative] != expected[relative]:
                raise ValueError("원본 파일 지문 불일치")
            cache[relative] = json.loads((SOURCE / relative).read_text(encoding="utf-8-sig"))
        return cache[relative]

    rules_v1_doc = json.loads((BASE / "classification_reference_rules.json").read_text(encoding="utf-8"))
    rules_v1 = {row["id"]: row for row in rules_v1_doc["rules"]}
    rules_v3 = {row["id"]: row for row in json.loads((BASE / "reference_v3/classification_rules_v3.json").read_text(encoding="utf-8"))}
    proof_v3 = json.loads((BASE / "reference_v3/supporting_evidence_v3.json").read_text(encoding="utf-8"))
    doc_path = SOURCE / common.DOC
    if digest(doc_path) != expected[common.DOC]:
        raise ValueError("동봉 문서 해시 불일치")
    doc_lines = doc_path.read_text(encoding="utf-8").splitlines()

    def doc_proof(key):
        needle, before, after = common.DOC_ANCHORS[key]
        positions = [i for i, line in enumerate(doc_lines) if needle in line]
        if len(positions) != 1:
            raise ValueError("동봉 문서 근거 위치 불일치")
        index = positions[0]
        return {"file": common.DOC, "source_file_sha256": expected[common.DOC], "line_start": index + before + 1,
                "line_end": index + after + 1, "source": "\n".join(doc_lines[index + before:index + after + 1])}

    selected = {}
    for row in read_rows("classification_reference_unresolved.jsonl"):
        if row["location_id"] not in remaining or row.get("reason") not in {"definition_missing", "definition_ambiguous"}:
            continue
        rule = rules_v1[row["attempted_rule"]]
        selected[row["location_id"]] = {"prior_record": row, "rule": rule, "kind": "v1",
                                         "evidence": [doc_proof(key) for key in rule["docs"]], "diagnostic": row["reason"]}
    for row in read_rows("reference_v3/classification_reference_unresolved_v3.jsonl"):
        rule_id = row.get("attempted_v3_rule")
        if row["location_id"] not in remaining or not rule_id or rule_id == "chained_entity_cell":
            continue
        if row.get("v3_reason") not in {"definition_missing", "definition_ambiguous", "target_component_missing"}:
            continue
        rule = rules_v3[rule_id]
        selected[row["location_id"]] = {"prior_record": row, "rule": rule, "kind": "v3",
                                         "evidence": [proof_v3[key] for key in rule["evidence"]], "diagnostic": row["v3_reason"]}
    for row in read_rows("reference_followup_v4/classification_followup_unresolved_v4.jsonl"):
        if row["location_id"] not in remaining:
            continue
        selected[row["location_id"]] = {"prior_record": row, "rule": {"id": row["rule_id"]}, "kind": "v4",
                                         "evidence": row["document_evidence"], "diagnostic": "documented_reference_unresolved_in_prior_index"}
    counts, diagnostics, rejected = Counter(), Counter(), []
    output_rows = []
    for location, item in sorted(selected.items()):
        original = remaining[location]
        source = load(original["file"])
        if resolve(source, original["field_path"]) != original["source"] or expected[original["file"]] != original["source_file_sha256"]:
            raise ValueError("원본 위치/값 불일치")
        rule = item["rule"]
        if rule.get("component") and rule["component"] not in source.get("components", []):
            rejected.append({"location_id": location, "reason": "source_component_not_declared"})
            continue
        if rule.get("pattern") and not re.fullmatch(rule["pattern"], original["field_pattern"]):
            raise ValueError("문서화된 구조 패턴 불일치")
        state = item["diagnostic"]
        if original["source"] == "":
            state = "EMPTY_REFERENCE_VALUE_SEMANTICS_UNOBSERVED"
        elif original["source"] == "-1":
            state = "SENTINEL_REFERENCE_VALUE_SEMANTICS_UNOBSERVED"
        result = {key: original[key] for key in ("location_id", "file", "field_path", "field_pattern", "source", "source_file_sha256", "source_value_sha256")}
        result.update(previous_classification="UNKNOWN", classification="INTERNAL", runtime_observed=False,
                      rule_id="documented_reference_semantics:" + rule["id"],
                      evidence_kind="explicit_reference_field_semantics_independent_of_target_resolution",
                      reason="문서가 참조·선택 설정임을 명시한 필드. 대상 정의 해석 상태와 번역 표시 분류를 분리하며 원문은 변경하지 않음.",
                      document_evidence=item["evidence"], reference_diagnostic={"status": state, "prior_diagnostic": item["diagnostic"],
                          "source_record": item["prior_record"], "source_value_modified": False, "runtime_effect": "UNKNOWN"})
        output_rows.append(result)
        counts[rule["id"]] += 1
        diagnostics[state] += 1
    with (OUTPUT / "classification_reference_overlay_v5.jsonl").open("x", encoding="utf-8") as stream:
        for row in output_rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    hold = []
    for row in read_rows("reference_v3/display_field_review_v3.jsonl"):
        if row["location_id"] in remaining and re.fullmatch(r"/equipment/[^/]+/\*/name", row["field_pattern"]):
            hold.append({**row, "classification": "UNKNOWN", "translation_status": "HOLD_USAGE_UNCONFIRMED",
                         "hold_reason": "대상 엔티티 name과 같다는 사실만으로 화면 표시 또는 식별자 용도를 추론하지 않음",
                         "required_evidence": "equipment loader/editor의 name 읽기와 실제 표시 또는 저장 사용 경로"})
    with (OUTPUT / "equipment_name_translation_hold.jsonl").open("x", encoding="utf-8") as stream:
        for row in hold:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    report = {"status": "PASS", "input_sha256": digest(BASE / input_name), "tool_sha256": digest(Path(__file__)),
              "new_internal": len(output_rows), "rule_counts": counts, "reference_diagnostics": diagnostics,
              "equipment_name_hold": len(hold), "rejected": rejected, "g1_status": "FAIL", "translation_started": False,
              "limitations": ["참조를 고치거나 원본 ID를 바꾸지 않음", "빈 chained/map 칸은 필드 자체의 명시 근거가 부족해 UNKNOWN 유지",
                              "장비 name의 이름 일치만으로 번역·유지를 확정하지 않음", "원본의 미해결 참조 진단은 추출 실패와 별개"],
              "outputs": {path.name: digest(path) for path in OUTPUT.iterdir()}}
    (OUTPUT / "reference_semantics_summary_v5.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
