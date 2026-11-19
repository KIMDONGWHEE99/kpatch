"""통합 뒤 남은 값 중 동봉 문서의 실제 예제와 고유 정의가 연결되는 후보만 기록한다."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029"
SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
OUTPUT = BASE / "reference_followup_v4"
CORE = "data/mods/core_2/"
DOC = "data/docs/index.html"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_row(stream, value):
    stream.write(json.dumps(value, ensure_ascii=False) + "\n")


def pointer(parts):
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def resolve(value, path):
    for key in path.lstrip("/").split("/"):
        key = key.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def main():
    OUTPUT.mkdir(exist_ok=False)
    expected = {row["path"]: row["sha256"] for row in json.loads((BASE / "baseline_manifest.json").read_text(encoding="utf-8"))["files"]}
    checked, parsed = {}, {}

    def verify(relative):
        if relative not in checked:
            checked[relative] = digest(SOURCE / relative)
        if checked[relative] != expected[relative]:
            raise ValueError("원본 지문 불일치: " + relative)
        return SOURCE / relative

    def load(relative):
        if relative not in parsed:
            parsed[relative] = json.loads(verify(relative).read_text(encoding="utf-8-sig"))
        return parsed[relative]

    doc_text = verify(DOC).read_text(encoding="utf-8")
    doc_lines = doc_text.splitlines()

    def doc_anchor(anchor, after=0):
        positions = [index for index, line in enumerate(doc_lines) if anchor in line]
        if len(positions) != 1:
            raise ValueError("문서 근거가 유일하지 않음: " + anchor)
        start = positions[0]
        return {"file": DOC, "source_file_sha256": expected[DOC], "line_start": start + 1,
                "line_end": start + 1 + after, "source": "\n".join(doc_lines[start:start + 1 + after])}

    fragments = []
    for match in re.finditer(r"<code>(.*?)</code>", doc_text, re.S):
        try:
            obj = json.loads(html.unescape(match.group(1)))
        except json.JSONDecodeError:
            continue
        fragments.append({"object": obj, "line_start": doc_text[:match.start()].count("\n") + 1,
                          "line_end": doc_text[:match.end()].count("\n") + 1})
    location_sample = next(row for row in fragments if isinstance(row["object"], dict) and "algorithm" in row["object"] and "scenarios" in row["object"])
    weather_sample = next(row for row in fragments if isinstance(row["object"], dict) and "animation_tick" in row["object"])
    world_sample = next(row for row in fragments if isinstance(row["object"], dict) and "landmass" in row["object"] and "biomes" in row["object"])

    def sample_evidence(sample, path):
        return {"file": DOC, "source_file_sha256": expected[DOC], "line_start": sample["line_start"],
                "line_end": sample["line_end"], "parsed_example_field_path": path, "value": resolve(sample["object"], path)}

    mode_examples = []
    for si, scenario in enumerate(location_sample["object"]["scenarios"]):
        for mi, item in enumerate(scenario["building_maps"]):
            if item["mode"] == "one_of":
                mode_examples.append(sample_evidence(location_sample, f"/scenarios/{si}/building_maps/{mi}/mode"))
    if not mode_examples:
        raise ValueError("동봉 문서의 one_of 예제를 찾지 못함")
    definitions = defaultdict(dict)
    for line in (BASE / "classification_reference_definitions.jsonl").open(encoding="utf-8"):
        row = json.loads(line)
        definitions[row["namespace"]][row["canonical_id"]] = row["definitions"]
    for path in sorted((SOURCE / CORE / "animations").glob("*.json")):
        relative = path.relative_to(SOURCE).as_posix()
        obj = load(relative)
        definitions["animations"].setdefault(str(obj["id"]), []).append({"file": relative, "file_sha256": expected[relative], "field_path": "/id", "id": obj["id"]})
    world = load(CORE + "worldgen.json")
    tiles = load(CORE + "world_tiles.json")
    biomes = defaultdict(list)
    for category, values in world_sample["object"]["biomes"].items():
        for key, value in values.items():
            if key in world["biomes"].get(category, {}) and key in tiles:
                biomes[key].append(sample_evidence(world_sample, f"/biomes/{category}/{key}"))
                biomes[key].append({"file": CORE + "worldgen.json", "source_file_sha256": expected[CORE + "worldgen.json"],
                                    "field_path": f"/biomes/{category}/{key}", "value": world["biomes"][category][key]})
    for sample in (location_sample, weather_sample):
        for index, key in enumerate(sample["object"]["biomes"]):
            if key in tiles:
                biomes[key].append(sample_evidence(sample, f"/biomes/{index}"))
    for key in biomes:
        biomes[key].append({"file": CORE + "world_tiles.json", "source_file_sha256": expected[CORE + "world_tiles.json"],
                            "field_path": "/" + key, "evidence_kind": "existing_world_tile_definition_key"})
    anchors = {
        "mode": doc_anchor("<strong>mode</strong> - you can choose", 2),
        "locations_biomes": doc_anchor("<strong>biomes</strong> - what biomes your location"),
        "weather_biomes": doc_anchor("<strong>biomes</strong> - where this weather"),
        "on_impact": doc_anchor("<strong>Play On Impact</strong>"),
        "inner_animation": doc_anchor("<strong>Inner Animation</strong>", 2),
        "race_tags": doc_anchor("<strong>tags</strong> - you can find examples", 1),
        "weather_animation": doc_anchor("<strong>animation</strong> - choose an animation for you weather", 2),
        "weather_ability": doc_anchor("<strong>ability</strong> - coose ability"),
    }
    input_path = BASE / "effective_inventory/unresolved_json_primary.jsonl"
    counts, unresolved_counts = Counter(), Counter()
    candidates, unresolved = [], []
    for line in input_path.open(encoding="utf-8"):
        effective = json.loads(line)
        row = effective["original_record"]
        relative, field, value = row["file"], row["field_pattern"], row["source"]
        rule, namespace, evidence = None, None, []
        if relative == CORE + "locations.json" and field == "/special/*/scenarios/*/building_maps/*/mode" and value == "one_of":
            rule, evidence = "documented_json_example_one_of", [anchors["mode"], *mode_examples]
        elif relative == CORE + "locations.json" and field == "/special/*/biomes/*":
            rule, evidence = "documented_location_biome", [anchors["locations_biomes"]]
        elif relative == CORE + "weather.json" and field == "/*/biomes/*":
            rule, evidence = "documented_weather_biome", [anchors["weather_biomes"]]
        elif relative.startswith(CORE + "animations/") and field == "/particles/*/on_impact":
            rule, namespace, evidence = "animation_impact_id", "animations", [anchors["on_impact"]]
        elif relative.startswith(CORE + "animations/") and field == "/animation":
            rule, namespace, evidence = "animation_inner_id", "animations", [anchors["inner_animation"]]
        elif relative == CORE + "character.json" and field == "/races/*/tags/*":
            rule, namespace, evidence = "documented_race_tag", "tags", [anchors["race_tags"]]
        elif relative == CORE + "weather.json" and field == "/*/animation":
            rule, namespace, evidence = "documented_weather_animation", "animations", [anchors["weather_animation"]]
        elif relative == CORE + "weather.json" and field == "/*/ability/*":
            rule, namespace, evidence = "documented_weather_ability", "abilities", [anchors["weather_ability"]]
        if rule is None:
            continue
        if resolve(load(relative), row["field_path"]) != value or expected[relative] != row["source_file_sha256"]:
            raise ValueError("원본 값 위치 불일치: " + row["location_id"])
        result = {"location_id": row["location_id"], "file": relative, "field_path": row["field_path"], "field_pattern": field,
                  "source": value, "source_file_sha256": row["source_file_sha256"], "source_value_sha256": row["source_value_sha256"],
                  "previous_classification": "UNKNOWN", "classification": "UNKNOWN", "rule_id": rule,
                  "evidence_kind": "shipped_documented_structure_and_exact_definition", "document_evidence": evidence,
                  "runtime_observed": False, "integration_status": "PENDING_NOT_APPLIED_TO_EFFECTIVE_INVENTORY"}
        if namespace:
            matches = definitions[namespace].get(value, [])
            for target in matches:
                target_path = target["file"]
                if resolve(load(target_path), target["field_path"]) != target["id"]:
                    raise ValueError("정의 ID 위치 불일치")
            if len(matches) == 1:
                result.update(classification="INTERNAL", target_definition=matches[0], reason="문서가 정한 선택·참조 필드와 유일한 정의 ID를 함께 확인")
            else:
                result.update(reason="참조 정의 누락 또는 중복으로 UNKNOWN 유지", definition_hints=matches)
        elif "biome" in rule:
            if value in biomes:
                result.update(classification="INTERNAL", target_evidence=biomes[value], reason="동봉 예제의 생물군계 설정 키와 같은 필터 값이며 실제 world_tiles 정의가 존재")
            else:
                result.update(reason="동봉 예제와 정확히 연결되지 않는 생물군계 값은 이름 유사성으로 치환하지 않고 UNKNOWN 유지")
        else:
            result.update(classification="INTERNAL", reason="같은 동봉 문서의 실제 JSON 예제에서 one_of가 명시된 지도 선택 설정. 설명의 one_off 철자와의 차이도 근거에 보존")
        if result["classification"] == "INTERNAL":
            counts[rule] += 1
            candidates.append(result)
        else:
            unresolved_counts[rule] += 1
            unresolved.append(result)
    for name, rows in [("classification_followup_overlay_v4.jsonl", candidates), ("classification_followup_unresolved_v4.jsonl", unresolved)]:
        with (OUTPUT / name).open("x", encoding="utf-8") as stream:
            for row in rows:
                write_row(stream, row)
    report = {"status": "PASS", "scope": "기존 통합 목록을 바꾸지 않은 동봉 문서·정확한 참조의 추가 분석",
              "created": datetime.now(timezone.utc).isoformat(), "input_sha256": digest(input_path),
              "tool_sha256": digest(Path(__file__)), "proposed_internal": len(candidates), "unknown_retained": len(unresolved),
              "rule_counts": counts, "unresolved_rule_counts": unresolved_counts, "checked_source_files": len(checked),
              "effective_inventory_modified": False, "translation_started": False,
              "limitations": ["실제 실행·로더 관찰 아님", "spawn_on·빈 chained map·장비 이름·internal_name은 이번 규칙에 포함하지 않음",
                              "boreal와 boreal_forest처럼 서로 다른 표기는 동일 개념으로 간주하지 않음", "문서화된 값 이외 marker는 UNKNOWN 유지"],
              "output_sha256": {path.name: digest(path) for path in OUTPUT.iterdir()}}
    (OUTPUT / "followup_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
