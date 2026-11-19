"""분리된 분류 근거를 원행과 함께 보존하고 여섯 조사 축의 유효 목록을 만든다."""

from collections import Counter, defaultdict
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
BUILD = "0.10.4.0.1_20261029"
BASE = ROOT / "extracted_private/SOULASH_2" / BUILD
SOURCE = ROOT / "source_original/SOULASH_2" / BUILD
OUTPUT = BASE / "effective_inventory"
CORE = "data/mods/core_2/"
AXES = {
    "json_value": "json_strings.jsonl",
    "json_key": "json_property_keys.jsonl",
    "text_line": "text_lines.jsonl",
    "map_name": "map_names.jsonl",
    "media": "media_inventory.jsonl",
    "native_string": "native/strings.jsonl",
}
OVERLAYS = [
    "classification_reference_overlay.jsonl",
    "reference_v2/classification_reference_overlay_v2.jsonl",
    "reference_v3/classification_reference_overlay_v3.jsonl",
    "reference_portraits/classification_portrait_overlay.jsonl",
]
SUPPORT = [
    "baseline_manifest.json", "inventory_summary.json", "json_files.jsonl",
    "extraction_errors.jsonl", "classification_reference_rules.json",
    "classification_reference_summary.json", "classification_reference_definitions.jsonl",
    "reference_v2/documentation_evidence_v2.json", "reference_v2/classification_reference_summary_v2.json",
    "reference_v3/supporting_evidence_v3.json", "reference_v3/classification_rules_v3.json",
    "reference_v3/classification_reference_summary_v3.json",
    "reference_portraits/portrait_audit_summary.json",
    "reference_portraits/official_sources/manifest.json", "native/summary.json",
    "translation_batch_candidates/manifest.json",
]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def read_rows(path):
    with path.open("rb") as stream:
        for number, raw in enumerate(stream, 1):
            yield number, json.loads(raw), sha(raw)


def write_row(stream, value):
    stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


class Pairs(list):
    """중복 JSON 속성도 각 등장 위치를 보존한다."""


def pointer(parts):
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def walk(value, path=(), occurrences=()):
    if isinstance(value, Pairs):
        seen = Counter()
        for ordinal, (key, child) in enumerate(value):
            seen[key] += 1
            child_occurrences = occurrences + ({"key": key, "occurrence": seen[key], "pair_ordinal": ordinal},)
            yield "json_key", {"parent_path": pointer(path), "key": key, "occurrence_path": child_occurrences}
            yield from walk(child, path + (key,), child_occurrences)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, path + (index,), occurrences + ({"index": index},))
    elif isinstance(value, str):
        yield "json_value", {"field_path": pointer(path), "source": value, "occurrence_path": occurrences}


def position_signature(axis, row):
    fields = ("field_path", "source") if axis == "json_value" else ("parent_path", "key")
    data = {key: row[key] for key in fields}
    if "occurrence_path" in row:
        data["occurrence_path"] = row["occurrence_path"]
    return bytes.fromhex(sha(canonical(data)))


def group_name(row):
    relative = row.get("file", "")
    if relative.startswith(CORE):
        return relative[len(CORE):].split("/")[0]
    return relative.split("/")[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", choices=["initial", "v2", "v3", "v4"], default="initial")
    args = parser.parse_args()
    global OUTPUT
    if args.revision != "initial":
        OUTPUT = OUTPUT / args.revision
        OVERLAYS.append("reference_followup_v4/classification_followup_overlay_v4.jsonl")
        SUPPORT.append("reference_followup_v4/followup_summary.json")
    if args.revision in {"v3", "v4"}:
        OVERLAYS.append("reference_v5/classification_reference_overlay_v5.jsonl")
        SUPPORT.extend(["reference_v5/reference_semantics_summary_v5.json", "reference_v5/equipment_name_translation_hold.jsonl"])
    if args.revision == "v4":
        OVERLAYS.extend(["reference_native_v6r3/classification_native_overlay_v6.jsonl",
                         "reference_language_scope_v7/classification_language_scope_overlay_v7.jsonl"])
        SUPPORT.extend(["reference_native_v6r3/native_field_summary_v6.json",
                        "reference_language_scope_v7/language_scope_policy.json", "reference_language_scope_v7/language_scope_summary_v7.json"])
    gate = "G1_FONT_LAYOUT_FAIL_RETEST_PENDING" if args.revision != "initial" else "G1_ACTUAL_RUNTIME_NOT_RUN"
    g1_status = "FAIL" if args.revision != "initial" else "NOT_RUN"
    if args.revision == "v4":
        gate, g1_status = "CURRENT_G1_OWNER_FINAL_REPORT_REQUIRED", "STALE"
    OUTPUT.mkdir(exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    (OUTPUT / "state.json").write_text(json.dumps({"status": "NOT_RUN", "started": started}), encoding="utf-8")
    official_manifest = json.loads((BASE / "reference_portraits/official_sources/manifest.json").read_text(encoding="utf-8"))
    official_paths = ["reference_portraits/official_sources/" + row["local_file"] for row in official_manifest]
    artifacts = {relative: {"path": relative, "sha256": digest(BASE / relative)}
                 for relative in [*AXES.values(), *OVERLAYS, *SUPPORT, *official_paths]}
    for item in official_manifest:
        if artifacts["reference_portraits/official_sources/" + item["local_file"]]["sha256"] != item["sha256"]:
            raise ValueError("고정된 공식 문서 해시 불일치")
    baseline = json.loads((BASE / "baseline_manifest.json").read_text(encoding="utf-8"))
    expected = {row["path"]: row["sha256"] for row in baseline["files"]}
    checked_files = {}
    external_artifacts = {}

    def verify_artifact_tree(value):
        if isinstance(value, dict):
            if "artifact" in value and "artifact_sha256" in value:
                named = Path(value["artifact"])
                candidate = (ROOT / named).resolve()
                if not candidate.is_file():
                    candidate = (BASE / named).resolve()
                if not candidate.is_relative_to(ROOT) or not candidate.is_file():
                    raise ValueError("근거 파일 경로 오류: " + str(named))
                relative = candidate.relative_to(ROOT).as_posix()
                claimed = value["artifact_sha256"]
                if relative not in external_artifacts:
                    if digest(candidate) != claimed:
                        raise ValueError("근거 파일 지문 불일치: " + relative)
                    external_artifacts[relative] = claimed
                    if candidate.suffix == ".json":
                        verify_artifact_tree(json.loads(candidate.read_text(encoding="utf-8")))
                elif external_artifacts[relative] != claimed:
                    raise ValueError("같은 근거 파일에 서로 다른 지문")
            for item in value.values():
                verify_artifact_tree(item)
        elif isinstance(value, list):
            for item in value:
                verify_artifact_tree(item)

    def verify_file(relative, claimed):
        if relative not in expected or expected[relative] != claimed:
            raise ValueError("기준선과 행의 파일 해시 불일치: " + relative)
        if relative not in checked_files:
            checked_files[relative] = digest(SOURCE / relative)
        if checked_files[relative] != claimed:
            raise ValueError("실제 원본 파일 해시 불일치: " + relative)

    overlays = defaultdict(list)
    overlay_counts = Counter()
    support_v3 = json.loads((BASE / "reference_v3/supporting_evidence_v3.json").read_text(encoding="utf-8"))
    for relative in OVERLAYS:
        for number, row, row_sha in read_rows(BASE / relative):
            verify_artifact_tree(row)
            entry = {"artifact": relative, "artifact_sha256": artifacts[relative]["sha256"],
                     "row_number": number, "row_sha256": row_sha, "record": row}
            if "supporting_evidence_ids" in row:
                entry["supporting_evidence_artifact"] = artifacts["reference_v3/supporting_evidence_v3.json"]
                entry["resolved_supporting_evidence"] = {key: support_v3[key] for key in row["supporting_evidence_ids"]}
            overlays[row["location_id"]].append(entry)
            overlay_counts[relative] += 1
    error_rows = [row for _, row, _ in read_rows(BASE / "extraction_errors.jsonl")]
    recovered = {row["path"] for row in error_rows if row.get("alternate_extraction") == "PASS_LOSSLESS_PROPERTY_PAIRS"}
    coverage = {axis: defaultdict(list) for axis in ("json_value", "json_key")}
    counts, roles, media_treatments = defaultdict(Counter), defaultdict(Counter), Counter()
    primary_groups, unknown_fields = defaultdict(Counter), Counter()
    unknown_samples = defaultdict(list)
    axis_counts, work_counts = Counter(), Counter()
    work_unique, work_chars, work_words = set(), Counter(), Counter()
    work_groups = defaultdict(Counter)
    conflicts, applied_counts, seen_overlays = [], Counter(), set()
    native_data = (SOURCE / "Soulash 2.exe").read_bytes()
    text_cache = {}
    with (OUTPUT / "effective_classification_ledger.jsonl").open("x", encoding="utf-8", newline="\n") as ledger, \
            (OUTPUT / "overlay_application_ledger.jsonl").open("x", encoding="utf-8", newline="\n") as history, \
            (OUTPUT / "translation_work_v2.jsonl").open("x", encoding="utf-8", newline="\n") as work, \
            (OUTPUT / "unresolved_json_primary.jsonl").open("x", encoding="utf-8", newline="\n") as unresolved:
        for axis, relative in AXES.items():
            for number, original, row_sha in read_rows(BASE / relative):
                row = dict(original)
                file = row.get("file", "Soulash 2.exe")
                file_sha = row.get("source_file_sha256", row.get("file_sha256", row.get("sha256")))
                verify_file(file, file_sha)
                location = row.get("location_id")
                if axis == "json_key":
                    location_data = {key: row[key] for key in ("parent_path", "key", "occurrence_path") if key in row}
                    location = file + "#key/" + sha(canonical(location_data))
                    value = row["key"]
                else:
                    value = row.get("source")
                value_sha = sha(value.encode("utf-8")) if isinstance(value, str) else None
                if "source_value_sha256" in row and value_sha != row["source_value_sha256"]:
                    raise ValueError("원본 값 해시 불일치: " + location)
                if axis == "native_string":
                    payload = native_data[row["file_offset"]:row["file_offset"] + row["byte_length"]]
                    if sha(payload) != row["source_sha256"] or payload.decode(row["encoding"]) != value:
                        raise ValueError("실행 파일 바이트 위치 불일치: " + location)
                elif axis == "map_name":
                    if (SOURCE / file).read_text(encoding="utf-8-sig").split("|", 2)[1] != value:
                        raise ValueError("맵 헤더 위치 불일치: " + location)
                elif axis == "text_line":
                    if file not in text_cache:
                        text_cache[file] = (SOURCE / file).read_text(encoding="utf-8-sig").splitlines()
                    if text_cache[file][row["line"] - 1] != value:
                        raise ValueError("텍스트 줄 위치 불일치: " + location)
                if axis in coverage:
                    coverage[axis][file].append(position_signature(axis, row))
                current = row["classification"]
                chain, record_conflicts = [], []
                if axis == "json_value":
                    for entry in overlays.get(location, []):
                        patch = entry["record"]
                        identity_fields = ("file", "field_path", "field_pattern", "source", "source_file_sha256", "source_value_sha256")
                        mismatch = [key for key in identity_fields if patch.get(key) != row.get(key)]
                        if "occurrence_path" in patch and patch["occurrence_path"] != row.get("occurrence_path"):
                            mismatch.append("occurrence_path")
                        proposed = patch["classification"]
                        if mismatch:
                            disposition = "REJECTED_IDENTITY_MISMATCH"
                        elif current != patch["previous_classification"] and current != proposed:
                            disposition = "REJECTED_CLASSIFICATION_CONFLICT"
                        else:
                            disposition = "APPLIED" if current != proposed else "CORROBORATES_OR_RETAINS"
                            current = proposed
                        entry_id = entry["artifact"] + ":" + str(entry["row_number"])
                        application = {**entry, "entry_id": entry_id, "disposition": disposition, "mismatched_fields": mismatch}
                        write_row(history, application)
                        applied_counts[disposition] += 1
                        seen_overlays.add(entry_id)
                        chain.append({"entry_id": entry_id, "classification": proposed, "disposition": disposition,
                                      "artifact_sha256": entry["artifact_sha256"], "row_sha256": entry["row_sha256"]})
                        if disposition.startswith("REJECTED"):
                            record_conflicts.append({"location_id": location, "entry_id": entry_id,
                                                     "classification_before": current, "proposed": proposed,
                                                     "disposition": disposition, "mismatched_fields": mismatch})
                if record_conflicts:
                    current = "UNKNOWN"
                    conflicts.extend(record_conflicts)
                effective = {"axis": axis, "record_id": axis + ":" + location, "location_id": location,
                             "source_file_sha256": file_sha, "source_value_sha256": value_sha,
                             "classification": current, "classification_status": "CONFLICT" if record_conflicts else "PASS",
                             "inventory_origin": {"artifact": relative, "artifact_sha256": artifacts[relative]["sha256"],
                                                  "row_number": number, "row_sha256": row_sha},
                             "original_record": original, "overlay_history": chain}
                if axis == "media":
                    effective["treatment"] = row["treatment"]
                    media_treatments[row["treatment"]] += 1
                write_row(ledger, effective)
                axis_counts[axis] += 1
                counts[axis][current] += 1
                roles[axis + ":" + row.get("role", "unspecified")][current] += 1
                primary = axis == "json_value" and row.get("role") == "primary_english"
                if primary:
                    primary_groups[group_name(row)][current] += 1
                    if current == "UNKNOWN":
                        write_row(unresolved, effective)
                        field = (group_name(row), row["field_pattern"])
                        unknown_fields[field] += 1
                        if len(unknown_samples[field]) < 2:
                            unknown_samples[field].append({"location_id": location, "source": value})
                eligible = primary or (axis == "text_line" and file.startswith(CORE) and "/translations/" not in file)
                if eligible and current == "VISIBLE_TRANSLATE":
                    candidate = {**original, "axis": axis, "record_id": effective["record_id"], "classification": current,
                                 "original_classification": original["classification"], "inventory_origin": effective["inventory_origin"],
                                 "overlay_history": chain, "translation_status": "NOT_RUN",
                                 "translation_gate": gate, "target": None}
                    write_row(work, candidate)
                    work_counts[axis] += 1
                    work_unique.add(value)
                    work_chars[axis] += len(value)
                    work_words[axis] += len(re.findall(r"\S+", value))
                    work_groups[axis + ":" + group_name(row)]["locations"] += 1
                    work_groups[axis + ":" + group_name(row)]["characters"] += len(value)
                    work_groups[axis + ":" + group_name(row)]["words"] += len(re.findall(r"\S+", value))
    for relative in OVERLAYS:
        missing = overlay_counts[relative] - sum(entry.startswith(relative + ":") for entry in seen_overlays)
        if missing:
            conflicts.append({"artifact": relative, "orphan_overlay_count": missing})

    # 별도 원본 재열거로 문자열과 모든 속성 키의 누락·중복·위치 교환을 확인한다.
    coverage_counts, coverage_failures, recovered_positions = Counter(), [], defaultdict(dict)
    json_files = sorted(path for path in expected if path.lower().endswith(".json"))
    with (OUTPUT / "source_json_coverage.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for relative in json_files:
            verify_file(relative, expected[relative])
            parsed = json.loads((SOURCE / relative).read_text(encoding="utf-8-sig"), object_pairs_hook=Pairs)
            actual = {"json_value": [], "json_key": []}
            for axis, row in walk(parsed):
                if relative not in recovered:
                    row.pop("occurrence_path")
                actual[axis].append(position_signature(axis, row))
            for axis in actual:
                observed = coverage[axis].pop(relative, [])
                matches = sorted(actual[axis]) == sorted(observed)
                duplicate_count = len(observed) - len(set(observed))
                record = {"file": relative, "source_file_sha256": expected[relative], "axis": axis,
                          "source_count": len(actual[axis]), "inventory_count": len(observed),
                          "source_positions_sha256": sha(b"".join(sorted(actual[axis]))),
                          "inventory_positions_sha256": sha(b"".join(sorted(observed))),
                          "duplicate_inventory_positions": duplicate_count,
                          "status": "PASS" if matches and not duplicate_count else "FAIL",
                          "lossless_occurrence_positions": relative in recovered}
                write_row(stream, record)
                coverage_counts[axis] += len(actual[axis])
                if relative in recovered:
                    recovered_positions[relative][axis] = {"locations": len(actual[axis]), "status": record["status"],
                                                          "positions_sha256": record["source_positions_sha256"]}
                if record["status"] != "PASS":
                    coverage_failures.append(record)
    for axis, remaining in coverage.items():
        if remaining:
            coverage_failures.append({"axis": axis, "unmatched_inventory_files": sorted(remaining)})
    with (OUTPUT / "remaining_primary_field_statistics.jsonl").open("x", encoding="utf-8") as stream:
        for field, count in unknown_fields.most_common():
            write_row(stream, {"group": field[0], "field_pattern": field[1], "count": count, "samples": unknown_samples[field]})
    with (OUTPUT / "classification_conflicts.jsonl").open("x", encoding="utf-8") as stream:
        for row in conflicts:
            write_row(stream, row)
    with (OUTPUT / "extraction_errors_preserved.jsonl").open("x", encoding="utf-8") as stream:
        for row in error_rows:
            write_row(stream, row)
    recovery_diagnostics = []
    for error in error_rows:
        positions = recovered_positions.get(error["path"], {})
        extraction_pass = len(positions) == 2 and all(row["status"] == "PASS" for row in positions.values())
        recovery_diagnostics.append({"file": error["path"], "source_file_sha256": error["source_sha256"],
                                     "historical_error": error, "current_extraction_status": "PASS" if extraction_pass else "FAIL",
                                     "unresolved_extraction_failure": not extraction_pass, "recovered_positions": positions,
                                     "duplicate_key_loader_semantics": "UNKNOWN", "runtime_behavior_diagnostic": "NOT_RUN",
                                     "unchanged_file_candidate_policy": "PRESERVE_ORIGINAL_BYTES",
                                     "reason": "원본의 모든 중복 발생 위치 복구 여부와 게임 로더가 선택하는 값의 의미를 구분"})
    (OUTPUT / "extraction_recovery_diagnostics.json").write_text(json.dumps(recovery_diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    changed = [relative for relative, entry in artifacts.items() if digest(BASE / relative) != entry["sha256"]]
    changed.extend("ROOT:" + relative for relative, expected_hash in external_artifacts.items() if digest(ROOT / relative) != expected_hash)
    (OUTPUT / "root_evidence_artifacts.json").write_text(json.dumps(external_artifacts, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT / "evidence_artifacts.json").write_text(json.dumps(artifacts, ensure_ascii=False, indent=2), encoding="utf-8")
    tool_paths = ["tools/soulash2_inventory.py", "tools/soulash2_reference_audit.py",
                  "tools/soulash2_reference_audit_v2.py", "tools/soulash2_reference_audit_v3.py",
                  "tools/soulash2_portrait_audit.py", "tools/soulash2_native_strings.py", "tools/soulash2_effective_inventory.py"]
    if args.revision != "initial":
        tool_paths.append("tools/soulash2_followup_reference_analysis.py")
    if args.revision in {"v3", "v4"}:
        tool_paths.append("tools/soulash2_reference_semantics_v5.py")
    if args.revision == "v4":
        tool_paths.extend(["tools/soulash2_native_field_overlay_v6.py", "tools/soulash2_language_scope_overlay_v7.py"])
    summary = {"game_id": "SOULASH_2", "build_id": BUILD, "check_id": "EFFECTIVE_INVENTORY_MERGE",
               "status": "STALE" if changed else ("FAIL" if conflicts or coverage_failures else "PASS"),
               "started": started, "finished": datetime.now(timezone.utc).isoformat(),
               "scope": "여섯 기존 조사 축과 네 분류 보강 기록의 해시·위치 보존 통합. 전체 조사 완료 판정 아님.",
               "g1_status": g1_status, "g2_status": "FAIL", "translation_status": "NOT_RUN", "translation_gate": gate,
               "axis_rows": axis_counts, "axis_classifications": counts, "role_classifications": roles,
               "media_treatments": media_treatments, "primary_json_groups": primary_groups,
               "overlay_input_rows": overlay_counts, "overlay_dispositions": applied_counts,
               "classification_conflicts": len(conflicts), "source_json_files": len(json_files),
               "source_json_position_counts": coverage_counts, "source_json_coverage_failures": coverage_failures,
               "checked_source_files": len(checked_files), "checked_external_artifacts": external_artifacts, "changed_input_artifacts": changed,
               "translation_work": {"axis_rows": work_counts, "unique_values": len(work_unique),
                                    "axis_characters": work_chars, "axis_words": work_words,
                                    "unique_characters": sum(map(len, work_unique)),
                                    "unique_words": sum(len(re.findall(r"\S+", value)) for value in work_unique),
                                    "groups": work_groups},
               "extraction_errors_preserved": len(error_rows), "historical_extraction_errors": len(error_rows),
               "unresolved_extraction_failures": sum(row["unresolved_extraction_failure"] for row in recovery_diagnostics),
               "lossless_recovered_string_locations": sum(row.get("json_value", {}).get("locations", 0) for row in recovered_positions.values()),
               "duplicate_key_loader_behavior_unknown": len(recovery_diagnostics), "tools": {path: digest(ROOT / path) for path in tool_paths},
               "limitations": ["JSON 속성 키의 기본 UNKNOWN은 값의 내부 참조 판정만으로 자동 해제하지 않음",
                               "PL·기타 JSON 분류는 원행 그대로이며 새 번역 작업은 영어 원본과 영어 이름 TXT만 선정",
                               "미디어 별도 육안 검수 결과는 이번 보강 입력에 포함하지 않아 처리 UNKNOWN을 유지",
                               "맵 본문·전체 네이티브 코드·비ASCII·실행 조합 문자열 조사는 여전히 별도 필요",
                               "추출 오류의 중복 속성 로더 의미를 해결한 것으로 처리하지 않음",
                               "현재 번역 작업 목록은 위치 후보이며 G1 전체 통과 전 대량 번역을 시작하지 않음"],
               "outputs": {path.name: digest(path) for path in OUTPUT.iterdir() if path.is_file() and path.name != "state.json"}}
    (OUTPUT / "effective_inventory_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT / "state.json").write_text(json.dumps({"status": summary["status"], "summary_sha256": digest(OUTPUT / "effective_inventory_summary.json")}), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ["status", "axis_rows", "axis_classifications", "classification_conflicts", "source_json_position_counts", "extraction_errors_preserved"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
