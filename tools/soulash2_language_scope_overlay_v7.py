"""en 슬롯 교체와 별도 내장 pl 언어 보존 범위를 표시 문구 분류에 연결한다."""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029"
SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
OUTPUT = BASE / "reference_language_scope_v7"
CORE = "data/mods/core_2/"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUTPUT.mkdir(exist_ok=False)
    baseline = {row["path"]: row["sha256"] for row in json.loads((BASE / "baseline_manifest.json").read_text(encoding="utf-8"))["files"]}
    metadata = {}
    for language, prefix in [("en", CORE), ("pl", CORE + "translations/pl/")]:
        relative = prefix + "language_metadata.json"
        assert digest(SOURCE / relative) == baseline[relative]
        obj = json.loads((SOURCE / relative).read_text(encoding="utf-8"))
        assert obj["id"] == language
        metadata[language] = {"file": relative, "source_file_sha256": baseline[relative], "id": obj["id"], "name": obj["name"]}
    native_path = ROOT / "working_private/SOULASH_2/rea/responses/pseudo_language_meta.json"
    native = json.loads(native_path.read_text(encoding="utf-8"))["result"]["structuredContent"]
    assert native["subject"]["digest"]["sha256"] == baseline["Soulash 2.exe"]
    code = native["normalized_result"].splitlines()
    ranges = [(105, 114), (154, 170), (211, 219), (329, 349)]
    excerpts = [{"line_start": start, "line_end": end, "source": "\n".join(code[start - 1:end])} for start, end in ranges]
    assert '"{}/translations/{}/language_metadata.json"' in "\n".join(code)
    assert '&DAT_1408bc40c' in "\n".join(code) and '&DAT_1408c06fc' in "\n".join(code)
    evidence = {"artifact": native_path.relative_to(ROOT).as_posix(), "artifact_sha256": digest(native_path),
                "evidence_id": native["evidence_id"], "subject_sha256": baseline["Soulash 2.exe"],
                "procedure_requested": native["parameters"]["procedure"], "excerpts": excerpts}
    policy = {"game_id": "SOULASH_2", "build_id": "0.10.4.0.1_20261029", "authority": "root 작업 지시의 본패치 범위",
              "korean_source_prefix": CORE, "korean_selected_language_id": "en", "metadata_id_preserved": "en",
              "metadata_name_intended": "한국어", "preserved_auxiliary_prefix": CORE + "translations/pl/",
              "preserved_auxiliary_language_id": "pl", "preserved_auxiliary_intent": "선택 가능한 별도 내장 폴란드어 원문을 그대로 보존",
              "unknown_auxiliary_fields": "UNKNOWN 유지. 표시분류가 확인된 문구와 언어 선택 이름만 VISIBLE_KEEP 처리",
              "korean_translation_from_polish": False, "metadata_evidence": metadata, "native_loader_evidence": evidence,
              "runtime_authority_note": "root가 G1 실제 실행에서 en 슬롯의 한글 출력 확인. 이번 도구는 해당 실행을 직접 관찰하지 않음"}
    policy_path = OUTPUT / "language_scope_policy.json"
    policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")
    policy_sha = digest(policy_path)
    counts, checked, output_rows = Counter(), set(), 0
    destination = OUTPUT / "classification_language_scope_overlay_v7.jsonl"
    with destination.open("x", encoding="utf-8") as stream:
        for line in (BASE / "json_strings.jsonl").open(encoding="utf-8"):
            row = json.loads(line)
            path = row["file"]
            target, reason, rule = None, None, None
            if path == metadata["en"]["file"] and row["field_path"] == "/name":
                target, rule = "VISIBLE_TRANSLATE", "korean_slot_display_name"
                reason = "en 식별자는 유지하고 등록되는 언어 표시 이름은 본패치 범위에 따라 한국어로 번역"
            elif path == metadata["pl"]["file"] and row["field_path"] == "/name":
                target, rule = "VISIBLE_KEEP", "preserved_polish_slot_display_name"
                reason = "별도 내장 pl 언어의 등록 표시 이름 Polski를 보존"
            elif row.get("role") == "auxiliary_translation" and path.startswith(CORE + "translations/pl/") and row["classification"] == "VISIBLE_TRANSLATE":
                target, rule = "VISIBLE_KEEP", "preserved_selectable_polish_display_text"
                reason = "번역대상은 en 원본이며 해당 문구는 metadata id=pl로 구분되는 별도 내장 선택 언어의 원문 보존 범위"
            if not target:
                continue
            if path not in checked:
                assert digest(SOURCE / path) == baseline[path]
                checked.add(path)
            result = {key: row[key] for key in ("location_id", "file", "field_path", "field_pattern", "source", "source_file_sha256", "source_value_sha256")}
            result.update(previous_classification=row["classification"], classification=target, rule_id=rule,
                          reason=reason, evidence_kind="explicit_patch_scope_and_separate_language_registration",
                          scope_evidence={"artifact": policy_path.relative_to(BASE).as_posix(), "artifact_sha256": policy_sha,
                                          "metadata": metadata["pl" if path.startswith(CORE + "translations/pl/") else "en"]},
                          runtime_observed=False)
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
            counts[rule] += 1
            output_rows += 1
    report = {"status": "PASS", "rows": output_rows, "rules": counts, "checked_source_files": len(checked),
              "tool_sha256": digest(Path(__file__)), "input_sha256": digest(BASE / "json_strings.jsonl"),
              "policy_sha256": policy_sha, "output_sha256": digest(destination),
              "native_loader_evidence_sha256": digest(native_path), "polish_unknown_blanket_exclusion": False,
              "source_game_files_changed": False, "translation_started": False}
    (OUTPUT / "language_scope_summary_v7.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
