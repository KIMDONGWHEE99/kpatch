"""동봉 편집기 설명과 정의 연결로 Soulash 2 엔티티·위치·건물 필드를 보강한다."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

import soulash2_reference_audit as common


ROOT = Path(__file__).resolve().parents[1]
CORE = common.CORE
MESSAGES = CORE + "messages.json"
CHARACTER = CORE + "character.json"
DOC = common.DOC
DOC_PHRASES = {
    "entity_ids": ("Soulash 2 uses two identifiers for its entities", 0, 3),
    "building_occupation": ("<strong>occupation</strong> - index of entity", 0, 1),
    "building_race": ("<strong>race</strong> - which race can build this building", 0, 0),
    "building_name": ("<strong>name</strong> - name of your building", 0, 1),
    "skill_id": ("<strong>skill_id</strong> - this an unique id of a skill", 0, 0),
    "carvable_tiles": ("<strong>carvables</strong> - defines which tiles", 0, 1),
    "damage_keys": ("Damage types are defined in <strong>messages.json</strong>", 0, 1),
    "statistic_keys": ("Statistics are defined in <strong>messages.json</strong>", 0, 1),
    "production_actions": ("Woodcutting, Mining, Sheering, Treshing are described", -1, 1),
    "production_targets": ("Any action can be performed on any environment tile", 0, 2),
    "location_spawns": ("<strong>spawns</strong> - defines entities", 0, 1),
}


def rule(key, group, pattern, namespace, evidence, component=None, target_component=None):
    return {"id": key, "group": group, "pattern": pattern, "namespace": namespace,
            "evidence": evidence, "component": component, "target_component": target_component}


RULES = [
    rule("chained_entity_cell", "entities", r"/chained/map/\*/\*", "entities", ["tooltip:Chained", "doc:entity_ids"], "chained"),
    rule("health_corpse_entity", "entities", r"/corpse", "entities", ["tooltip:Health", "doc:entity_ids"], "health"),
    rule("humanoid_race_id", "entities", r"/humanoid/race", "races", ["tooltip:Humanoid", "doc:building_race"], "humanoid"),
    rule("ai_tag_relations", "entities", r"/artificial_intelligence/(allies|enemies)/\*", "tags", ["tooltip:AI", "tooltip:Tags"], "artificial_intelligence"),
    rule("entity_skill_id", "entities", r"/skills/skills/\*", "skills", ["tooltip:Skills", "doc:skill_id"], "skills"),
    rule("random_spawn_terrain", "entities", r"/random_resource/spawn_at/\*", "entities", ["tooltip:Random Resource", "doc:entity_ids"], "random_resource"),
    rule("ai_production_actions", "entities", r"/artificial_intelligence/allow_production/\*", "production_actions", ["tooltip:AI", "doc:production_actions", "doc:production_targets"], "artificial_intelligence"),
    rule("ai_producer_entity", "entities", r"/artificial_intelligence/allow_producer_entities/\*", "entities", ["tooltip:AI", "tooltip:Producer", "doc:production_targets"], "artificial_intelligence", "producer"),
    rule("usable_recipe_entity", "entities", r"/usable/recipe", "entities", ["tooltip:Usable", "tooltip:Craftable", "doc:entity_ids"], "usable", "craftable"),
    rule("usable_skill_id", "entities", r"/usable/skill_p", "skills", ["tooltip:Usable", "doc:skill_id"], "usable"),
    rule("weapon_animation_id", "entities", r"/weapon/attack_animation", "animations", ["tooltip:Weapon"], "weapon"),
    rule("damage_animation_id", "entities", r"/damage_applier/dmg_animation", "animations", ["tooltip:Damage applier"], "damage_applier"),
    rule("on_destruction_recipe", "entities", r"/on_destruction/recipes/\*", "entities", ["tooltip:On destruction", "tooltip:Craftable", "doc:entity_ids"], "on_destruction", "craftable"),
    rule("producer_follow_up_entity", "entities", r"/producer/follow_up/[^/]+", "entities", ["tooltip:Producer", "doc:production_actions", "doc:production_targets"], "producer"),
    rule("equipment_custom_slot_id", "entities", r"/equipment/custom_slots/\*", "custom_eq_slots", ["tooltip:Equipment"], "equipment"),
    rule("weapon_damage_key", "entities", r"/weapon/damage/\*/dmg_type", "damage_keys", ["tooltip:Weapon", "doc:damage_keys"], "weapon"),
    rule("applied_damage_key", "entities", r"/damage_applier/dmg_type", "damage_keys", ["tooltip:Damage applier", "doc:damage_keys"], "damage_applier"),
    rule("race_specific_occupation", "buildings", r"/occupation_per_race/[^/]+", "entities", ["doc:building_occupation", "doc:building_race", "doc:entity_ids"]),
    rule("building_required_entity", "buildings", r"/required_entities/\*/entities/\*", "entities", ["main:673", "doc:entity_ids", "doc:building_name"]),
    rule("building_skill_id", "buildings", r"/enables/\*", "skills", ["doc:building_name", "doc:skill_id"]),
    rule("building_group_id", "buildings", r"/group", "building_groups", ["doc:building_name"]),
    rule("location_carvable_entity", "locations.json", r"/special/\*/algorithm/parameters/carvables/\*", "entities", ["doc:carvable_tiles", "doc:entity_ids"]),
]


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def resolve_path(value, path):
    if not path:
        return value
    for step in path.lstrip("/").split("/"):
        step = step.replace("~1", "/").replace("~0", "~")
        value = value[int(step)] if isinstance(value, list) else value[step]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-id", default=common.BUILD)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = ROOT / "source_original/SOULASH_2" / args.build_id
    evidence = ROOT / "extracted_private/SOULASH_2" / args.build_id
    output = (args.output or evidence / "reference_v3").resolve()
    if not output.is_relative_to(ROOT / "extracted_private") or output.exists():
        raise SystemExit("extracted_private 아래에 새로운 결과 경로가 필요합니다.")
    input_path = evidence / "reference_v2/classification_reference_unresolved_v2.jsonl"
    manifest_path = evidence / "baseline_manifest.json"
    definitions_path = evidence / "classification_reference_definitions.jsonl"
    manifest = common.json_load(manifest_path)
    expected = {row["path"]: row for row in manifest["files"]}
    checked, cache = set(), {}
    started = datetime.now(timezone.utc).isoformat()

    def verified(relative):
        path = source / relative
        if relative not in checked:
            if relative not in expected or common.digest(path) != expected[relative]["sha256"]:
                raise ValueError("원본 해시 불일치: " + relative)
            checked.add(relative)
        return path

    def load(relative):
        if relative not in cache:
            cache[relative] = common.json_load(verified(relative))
        return cache[relative]

    definitions = defaultdict(dict)
    for line in definitions_path.open(encoding="utf-8"):
        row = json.loads(line)
        definitions[row["namespace"]][row["canonical_id"]] = row["definitions"]
    for path in sorted((source / CORE / "animations").glob("*.json")):
        relative = path.relative_to(source).as_posix()
        obj = load(relative)
        key = common.canonical_id(obj["id"])
        definitions["animations"].setdefault(key, []).append({"file": relative, "file_sha256": expected[relative]["sha256"], "field_path": "/id", "id": obj["id"], "canonical_id": key})
    for namespace, relative, array_path in [("building_groups", CORE + "building_groups.json", ""), ("custom_eq_slots", CHARACTER, "/custom_eq_slots")]:
        doc = load(relative)
        rows = resolve_path(doc, array_path) if array_path else doc
        for index, obj in enumerate(rows):
            key = common.canonical_id(obj["id"])
            definitions[namespace].setdefault(key, []).append({"file": relative, "file_sha256": expected[relative]["sha256"], "field_path": f"{array_path}/{index}/id", "id": obj["id"], "canonical_id": key})
    messages = load(MESSAGES)
    for namespace, array_key in [("damage_keys", "damage_type"), ("statistic_keys", "statistics")]:
        for index, obj in enumerate(messages[array_key]):
            key = obj["name"].lower()
            definitions[namespace].setdefault(key, []).append({"file": MESSAGES, "file_sha256": expected[MESSAGES]["sha256"], "field_path": f"/{array_key}/{index}/name", "source_name": obj["name"], "canonical_id": key, "transform": "lowercase_as_documented"})
    doc_lines = verified(DOC).read_text(encoding="utf-8-sig").splitlines()
    supporting = {}
    for key, (phrase, before, after) in DOC_PHRASES.items():
        matches = [i for i, line in enumerate(doc_lines) if phrase in line]
        if not matches:
            raise ValueError("문서 구절 없음: " + key)
        index = matches[0]
        supporting["doc:" + key] = {"file": DOC, "file_sha256": expected[DOC]["sha256"], "line_start": index + before + 1, "line_end": index + after + 1, "source": "\n".join(doc_lines[index + before:index + after + 1])}
    for index, tooltip in enumerate(messages["component_type"]):
        name = tooltip["name"]
        key = "tooltip:" + name
        if key in supporting:
            raise ValueError("구성요소 설명명 중복: " + name)
        supporting[key] = {"file": MESSAGES, "file_sha256": expected[MESSAGES]["sha256"], "field_path": f"/component_type/{index}/description", "component_name": name, "source": tooltip["description"], "source_value_sha256": sha_bytes(tooltip["description"].encode("utf-8"))}
    for index, message in enumerate(messages["main"]):
        if message["id"] == 673:
            supporting["main:673"] = {"file": MESSAGES, "file_sha256": expected[MESSAGES]["sha256"], "field_path": f"/main/{index}/format", "message_id": 673, "source": message["format"], "source_value_sha256": sha_bytes(message["format"].encode("utf-8"))}
    for item in RULES:
        for key in item["evidence"]:
            if key not in supporting:
                raise ValueError("규칙 근거 없음: " + key)
    output.mkdir(parents=True)
    counts, rule_counts, failures, remaining_groups = Counter(), Counter(), Counter(), Counter()
    fields, samples = Counter(), defaultdict(list)
    source_group_counts, display_review_counts = Counter(), Counter()
    seen = set()
    files_written = ["classification_reference_overlay_v3.jsonl", "classification_reference_unresolved_v3.jsonl", "display_field_review_v3.jsonl"]
    with (output / files_written[0]).open("w", encoding="utf-8", newline="\n") as overlay, (output / files_written[1]).open("w", encoding="utf-8", newline="\n") as unresolved, (output / files_written[2]).open("w", encoding="utf-8", newline="\n") as display_review:
        for line in input_path.open(encoding="utf-8"):
            row = json.loads(line)
            if row["classification"] != "UNKNOWN" or row["location_id"] in seen:
                raise ValueError("입력 위치·분류 오류")
            seen.add(row["location_id"])
            group = row["file"][len(CORE):].split("/")[0]
            source_group_counts[group] += 1
            counts["input_unknown"] += 1
            selected = next((item for item in RULES if item["group"] == group and re.fullmatch(item["pattern"], row["field_pattern"])), None)
            failure = "no_supported_rule"
            resolved, extra = None, []
            if selected:
                doc = load(row["file"])
                if row["source_file_sha256"] != expected[row["file"]]["sha256"] or resolve_path(doc, row["field_path"]) != row["source"]:
                    raise ValueError("입력 값과 원본 위치 불일치")
                matches = definitions[selected["namespace"]].get(common.canonical_id(row["source"]), [])
                if selected["component"] and selected["component"] not in doc.get("components", []):
                    failure = "source_component_missing"
                elif len(matches) != 1:
                    failure = "definition_missing" if not matches else "definition_ambiguous"
                else:
                    resolved = matches[0]
                    verified(resolved["file"])
                    failure = None
                    if selected["target_component"] and selected["target_component"] not in load(resolved["file"]).get("components", []):
                        resolved, failure = None, "target_component_missing"
                    if resolved and selected["id"] in {"race_specific_occupation", "producer_follow_up_entity"}:
                        key = row["field_path"].split("/")[-1]
                        namespace = "races" if selected["id"] == "race_specific_occupation" else "production_actions"
                        parents = definitions[namespace].get(key, [])
                        if len(parents) != 1:
                            resolved, failure = None, "selector_key_not_unique_definition"
                        else:
                            verified(parents[0]["file"])
                            extra.append(parents[0])
                    if resolved and selected["id"] == "building_required_entity":
                        index = int(row["field_path"].split("/")[2])
                        requirement = doc["required_entities"][index]
                        if not isinstance(requirement.get("count"), (int, float)) or isinstance(requirement["count"], bool) or requirement["count"] < 0:
                            resolved, failure = None, "requirement_count_shape_unknown"
                        else:
                            extra.append({"file": row["file"], "file_sha256": expected[row["file"]]["sha256"], "field_path": f"/required_entities/{index}/count", "value": requirement["count"], "evidence_kind": "numeric_requirement_count"})
            if resolved:
                common.emit(overlay, {**row, "previous_classification": "UNKNOWN", "classification": "INTERNAL", "rule_id": selected["id"], "reason": "문서화된 구성요소/필드 구조와 고유 정의 참조를 함께 확인", "supporting_evidence_ids": selected["evidence"], "target_definition": resolved, "additional_reference_evidence": extra, "source_component": selected["component"], "target_component": selected["target_component"], "evidence_kind": "shipped_description_and_exact_definition", "runtime_observed": False})
                counts["INTERNAL"] += 1
                rule_counts[selected["id"]] += 1
            else:
                common.emit(unresolved, {**row, "v3_reason": failure, "attempted_v3_rule": selected["id"] if selected else None})
                counts["remaining_unknown"] += 1
                failures[failure] += 1
                remaining_groups[group] += 1
                pattern = row.get("review_pattern", row["field_pattern"])
                key = (group, pattern)
                fields[key] += 1
                if len(samples[key]) < 3:
                    samples[key].append({"location_id": row["location_id"], "source": row["source"]})
                if group in {"entities", "locations.json", "buildings"} and row["field_path"].split("/")[-1] in {"name", "description"}:
                    context = resolve_path(load(row["file"]), row["field_path"].rsplit("/", 1)[0])
                    related = definitions["entities"].get(common.canonical_id(context.get("id")), []) if isinstance(context, dict) and row["field_path"].startswith("/equipment/") else []
                    matched_names = []
                    for item in related:
                        target = load(item["file"])
                        matched_names.append({"file": item["file"], "file_sha256": item["file_sha256"], "field_path": "/name", "source": target.get("name"), "same_name": target.get("name") == row["source"]})
                    common.emit(display_review, {**row, "classification": "UNKNOWN", "context_properties": sorted(context) if isinstance(context, dict) else [], "related_entity_name_values": matched_names, "reason": "표시 가능 이름·설명: 생성용 복제 이름인지 편집기 표시 필드인지 실제 소비 경로 추가 확인 필요", "supporting_evidence_ids": ["tooltip:Equipment"] if row["field_path"].startswith("/equipment/") else [], "runtime_observed": False})
                    display_review_counts[(group + ":" + row["field_pattern"])] += 1
    assert counts["input_unknown"] == counts["INTERNAL"] + counts["remaining_unknown"]
    # 원래 인벤토리의 표시성 필드도 다시 집계하여 중첩 필드가 목록에서 빠지지 않았는지 남긴다.
    display_coverage = defaultdict(Counter)
    with (evidence / "json_strings.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["role"] != "primary_english":
                continue
            group = row["file"][len(CORE):].split("/")[0]
            if group in {"entities", "locations.json", "buildings"} and row["field_path"].split("/")[-1] in {"name", "description"}:
                display_coverage[(group, row["field_pattern"])][row["classification"]] += 1
    with (output / "name_description_coverage_v3.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for (group, pattern), states in sorted(display_coverage.items()):
            common.emit(stream, {"group": group, "field_pattern": pattern, "original_classification_counts": states})
    with (output / "remaining_field_statistics_v3.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for (group, pattern), count in fields.most_common():
            common.emit(stream, {"group": group, "field_pattern": pattern, "count": count, "examples": samples[(group, pattern)]})
    (output / "supporting_evidence_v3.json").write_text(json.dumps(supporting, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "classification_rules_v3.json").write_text(json.dumps(RULES, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"game_id": "SOULASH_2", "build_id": args.build_id, "check_id": "G2_REFERENCE_OVERLAY_V3", "status": "PASS", "scope": "동봉 구성요소 설명·필드 구조·고유 정의 연결에 따른 추가 판정", "g2_status": "NOT_RUN", "started": started, "finished": datetime.now(timezone.utc).isoformat(), "command": sys.argv, "tool_sha256": common.digest(Path(__file__)), "imported_tool_sha256": common.digest(Path(common.__file__)), "inputs": {"baseline_manifest": common.digest(manifest_path), "unresolved_v2": common.digest(input_path), "definitions_v1": common.digest(definitions_path)}, "counts": counts, "rules": rule_counts, "failure_counts": failures, "source_groups": source_group_counts, "remaining_groups": remaining_groups, "display_review_counts": display_review_counts, "checked_source_files": len(checked), "top_remaining_fields": [{"group": key[0], "field": key[1], "count": count, "examples": samples[key]} for key, count in fields.most_common(10)], "output_hashes": {path.name: common.digest(path) for path in output.iterdir() if path.is_file()}, "limitations": ["원본·기존 overlay·번역 후보 manifest는 변경하지 않음", "미등록 marker, 빈 ID, -1, 중복 정의를 존재하지 않는 기능 또는 내부값으로 간주하지 않음", "참조형 내부값과 표시되는 이름을 분리하며 nested equipment name은 UNKNOWN 유지", "수치형 필드는 번역 문자열 조사 범위 밖이며 본 도구는 문자열 값만 판정", "map 본문 전체 파싱·native enum 사용 경로·전수 런타임·G2 전체 완료를 뜻하지 않음"]}
    (output / "classification_reference_summary_v3.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"counts": counts, "rules": rule_counts, "remaining_groups": remaining_groups, "display_review_total": sum(display_review_counts.values())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
