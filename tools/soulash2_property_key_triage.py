"""속성 키를 문서/코드의 고정 필드와 동적 명칭·속성 사전으로 나누되 일괄 제외하지 않는다."""
from collections import Counter, defaultdict
import argparse
import hashlib
import html
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029"
SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
OUTPUT = BASE / "reference_triage"
CORE = "data/mods/core_2/"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", choices=["initial", "v2"], default="initial")
    args = parser.parse_args()
    suffix = "_v2" if args.revision == "v2" else ""
    destination = OUTPUT / ("property_key_review_ledger" + suffix + ".jsonl")
    if destination.exists():
        raise ValueError("기존 키 검토 목록을 덮어쓰지 않습니다.")
    doc = (SOURCE / "data/docs/index.html").read_text(encoding="utf-8")
    doc_sha = digest(SOURCE / "data/docs/index.html")
    official_manifest_path = BASE / "reference_portraits/official_sources/manifest.json"
    official_manifest = json.loads(official_manifest_path.read_text(encoding="utf-8"))
    exporter = next(row for row in official_manifest if row["local_file"] == "doc_exporter.cpp")
    exporter_path = official_manifest_path.parent / exporter["local_file"]
    assert digest(exporter_path) == exporter["sha256"]
    format_proof = {"artifact": exporter_path.relative_to(ROOT).as_posix(), "artifact_sha256": exporter["sha256"],
                    "github_url": exporter["github_url"], "commit": exporter["commit"],
                    "evidence_kind": "official_json_export_field_schema"}
    schema = defaultdict(list)

    def walk(value, group, path, proof):
        if isinstance(value, dict):
            for key, child in value.items():
                schema[(group, path, key)].append(proof)
                walk(child, group, path + "/" + key, proof)
        elif isinstance(value, list):
            for child in value:
                walk(child, group, path + "/*", proof)

    for match in re.finditer(r"<code>(.*?)</code>", doc, re.S):
        try:
            obj = json.loads(html.unescape(match.group(1)))
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        group, prefix = None, ""
        if "algorithm" in obj and "scenarios" in obj:
            group, prefix = "locations.json", "/special/*"
        elif "races" in obj:
            group = "character.json"
        elif "animation_tick" in obj:
            group, prefix = "weather.json", "/*"
        elif "landmass" in obj and "biomes" in obj:
            group = "worldgen.json"
        if group:
            proof = {"file": "data/docs/index.html", "source_file_sha256": doc_sha,
                     "line_start": doc[:match.start()].count("\n") + 1, "line_end": doc[:match.end()].count("\n") + 1,
                     "evidence_kind": "parsed_documentation_schema_example"}
            walk(obj, group, prefix, proof)
    code_rules = [
        ("messages.json", r"/main/\*", {"align", "color", "format"}, "align", 290, 341),
        ("entities", r"", {"equipment"}, "equipment_load", 452, 489),
        ("entities", r"/equipment/[^/]+/\*", {"id"}, "equipment_load", 523, 572),
        ("entities", r"/equipment", {"disabled_slots", "custom_slots"}, "chained_parse", 899, 921),
        ("entities", r"", {"chained"}, "chained_read", 86, 106),
        ("entities", r"/chained", {"map"}, "chained_read", 106, 108),
        ("locations.json", r"/special/\*", {"scenarios"}, "spawn_on", 482, 488),
        ("locations.json", r"/special/\*/scenarios/\*", {"spawns"}, "spawn_on", 490, 500),
        ("locations.json", r"/special/\*/scenarios/\*/spawns/\*", {"entities", "spawn_on", "placement", "chance", "amount"}, "spawn_on", 482, 984),
    ]
    code_proofs = {}
    for name in {row[3] for row in code_rules}:
        path = ROOT / "working_private/SOULASH_2/rea/responses" / ("pseudo_field_" + name + ".json")
        record = json.loads(path.read_text(encoding="utf-8"))["result"]["structuredContent"]
        code_proofs[name] = {"artifact": path.relative_to(ROOT).as_posix(), "artifact_sha256": digest(path),
                             "evidence_id": record["evidence_id"], "subject_sha256": record["subject"]["digest"]["sha256"],
                             "procedure_requested": record["parameters"]["procedure"], "evidence_kind": "native_fixed_property_lookup"}
    input_path = BASE / "json_property_keys.jsonl"
    input_sha = digest(input_path)
    counts, by_role, patterns = Counter(), defaultdict(Counter), Counter()
    examples = defaultdict(list)
    with destination.open("x", encoding="utf-8") as out:
        for number, line in enumerate(input_path.open(encoding="utf-8"), 1):
            row = json.loads(line)
            relative = row["file"]
            local = relative[len(CORE):] if relative.startswith(CORE) else relative
            if local.startswith("translations/pl/"):
                local = local[len("translations/pl/"):]
            group = local.split("/")[0]
            parent = re.sub(r"/[0-9]+(?=/|$)", "/*", row["parent_path"])
            key = row["key"]
            category, evidence = "UNRESOLVED_SCHEMA_KEY", []
            reason = "구조 반복이나 단어 모양만으로 코드 키 또는 표시 명칭을 확정하지 않음"
            dynamic = ((group == "portraits" and parent in {"/frames", "/colors", "/restrictions"}) or
                       (group == "world_tiles.json" and parent == "") or
                       (group == "worldgen.json" and (parent == "/seaports" or re.fullmatch(r"/biomes/[^/]+", parent))) or
                       (group == "entities" and re.fullmatch(r"/producer/follow_up", parent)) or
                       (group == "buildings" and parent == "/occupation_per_race") or
                       (group == "character.json" and re.fullmatch(r"/races/\*/subraces", parent)))
            attribute = ((group == "entities" and re.fullmatch(r"/(statistics|resistance|resistances|equipment)", parent)
                          and not (args.revision == "v2" and parent == "/equipment" and key in {"disabled_slots", "custom_slots"})) or
                         (group == "character.json" and re.fullmatch(r"/races/\*/(statistics|ages)", parent)) or
                         (group == "abilities" and parent == "/effects") or
                         (group == "messages.json" and parent in {"/directions", "/action_plan_description"}))
            if dynamic:
                category = "DYNAMIC_DICTIONARY_IDENTITY_OR_LABEL"
                reason = "멤버 키 자체가 부품·팔레트·종족·생물군계·행동 등 데이터 이름/참조를 담는 사전. 표시 경로 별도 확인 필요"
                evidence = [{"kind": "exact_dictionary_context", "group": group, "parent_path": row["parent_path"]}]
            elif attribute:
                category = "ENUM_ATTRIBUTE_OR_SLOT_DICTIONARY"
                reason = "능력치·효과·방향·장비칸 등의 사전 키. 별도 표시명 표를 쓰는지 원키를 표시하는지 소비 코드 확인 필요"
                evidence = [{"kind": "exact_attribute_dictionary_context", "group": group, "parent_path": row["parent_path"]}]
            else:
                for rgroup, pattern, keys, name, start, end in code_rules:
                    if relative.startswith(CORE) and group == rgroup and re.fullmatch(pattern, parent) and key in keys:
                        category = "CODE_PARSER_FIXED_FIELD"
                        reason = "같은 자료 구조의 고정 속성 조회에 사용됨을 원본 실행 파일의 소비 코드에서 확인. 값의 표시 여부와 구분"
                        evidence = [{**code_proofs[name], "normalized_result_line_start": start, "normalized_result_line_end": end}]
                        if args.revision == "v2" and row.get("role") == "auxiliary_translation":
                            category = "AUXILIARY_LOADER_SCHEMA_CANDIDATE"
                            reason = "영어 구조의 고정 조회와 대응하는 PL 필드. PL 오버레이가 같은 로더로 합쳐지는지 확인 전 확정하지 않음"
                        break
                if category == "UNRESOLVED_SCHEMA_KEY" and (group, parent, key) in schema and relative.startswith(CORE):
                    category = "DOCUMENTED_FIXED_FIELD_CANDIDATE"
                    reason = "동봉 JSON 예제의 같은 구조에서 쓰이는 고정 필드 후보. 실제 코드 사용 확인 전 일괄 INTERNAL 처리하지 않음"
                    evidence = schema[(group, parent, key)]
            if args.revision == "v2" and relative == CORE + "portraits/portrait_parts.json":
                fixed_frame = ((re.fullmatch(r"/frames/[^/]+", parent) and key in {"frame", "rotated", "trimmed", "spriteSourceSize", "sourceSize", "duration"}) or
                               (re.fullmatch(r"/frames/[^/]+/(frame|spriteSourceSize)", parent) and key in {"x", "y", "w", "h"}) or
                               (re.fullmatch(r"/frames/[^/]+/sourceSize", parent) and key in {"w", "h"}))
                fixed_layer = parent == "/meta/layers/*" and key in {"name", "group", "opacity", "blendMode"}
                if fixed_frame or fixed_layer:
                    category = "OFFICIAL_FORMAT_FIXED_FIELD_CANDIDATE"
                    reason = "Aseprite 공식 내보내기 코드의 고정 JSON 필드명. 프레임 식별자·레이어 이름 값과 구분하며 게임 표시 소비는 별도 확인"
                    evidence = [{**format_proof, "line_start": 1476 if fixed_frame else 1581,
                                 "line_end": 1504 if fixed_frame else 1640}]
            output = {"file": relative, "parent_path": row["parent_path"], "key": key, "source_file_sha256": row["source_file_sha256"],
                      "source_value_sha256": hashlib.sha256(key.encode("utf-8")).hexdigest(), "role": row.get("role"),
                      "classification": "UNKNOWN", "review_category": category, "reason": reason, "evidence": evidence,
                      "original_inventory": {"artifact": "json_property_keys.jsonl", "sha256": input_sha, "row_number": number},
                      "runtime_observed": False, "applied_to_effective_inventory": False}
            if "occurrence_path" in row:
                output["occurrence_path"] = row["occurrence_path"]
            out.write(json.dumps(output, ensure_ascii=False) + "\n")
            counts[category] += 1
            by_role[row.get("role", "unspecified")][category] += 1
            pattern_key = (category, group, parent, key if category in {"CODE_PARSER_FIXED_FIELD", "DOCUMENTED_FIXED_FIELD_CANDIDATE"} else "<member>")
            patterns[pattern_key] += 1
            if len(examples[category]) < 3:
                examples[category].append({"file": relative, "parent_path": row["parent_path"], "key": key})
    report = {"status": "PASS", "input_rows": sum(counts.values()), "input_sha256": input_sha, "counts": counts,
              "role_counts": by_role, "examples": examples, "tool_sha256": digest(Path(__file__)),
              "classification_changed": 0, "scope": "모든 키의 조사 우선순위 분리. 표시 가능 사전 키를 고정 구조 키와 분리", "code_proofs": code_proofs,
              "top_patterns": [{"category": key[0], "group": key[1], "parent_pattern": key[2], "key": key[3], "count": count} for key, count in patterns.most_common(30)],
              "output_sha256": digest(destination), "limitations": ["속성 키가 반복된다는 사실만으로 INTERNAL 판정하지 않음", "문서 예제와 코드에서 확인한 고정 키 범위를 전체 스키마로 확대하지 않음",
                                                                     "원값/키 인벤토리 및 번역 후보를 변경하지 않음", "임의 명칭 사전의 표시 노출은 코드와 편집기에서 추가 확인 필요"]}
    report["review_revision"] = args.revision
    report["review_notes"] = ["숫자 경로 정규화는 배열 인덱스와 숫자 사전키를 합칠 수 있어 실제 승격 시 부모 컨테이너 타입 대조 필요",
                              "고정 조회는 키 변경 금지의 근거이며 generic 편집기/디버그 UI의 원키 표시 부재를 증명하지 않음",
                              "문서 JSON 예제의 같은 키 출현은 고정 스키마의 후보이며 모든 사전 멤버의 고정성을 증명하지 않음"]
    (OUTPUT / ("property_key_review_summary" + suffix + ".json")).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ["status", "input_rows", "counts", "role_counts", "classification_changed"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
