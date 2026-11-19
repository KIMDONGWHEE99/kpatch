"""동봉 문서와 초상화 키 연결로 Soulash 2 미확정 목록을 추가 보강한다.

v1 판정·번역 후보를 변경하지 않고 v2 결과만 별도 작성한다.
"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

import soulash2_reference_audit as prior


ROOT = Path(__file__).resolve().parents[1]
CORE = prior.CORE
PARTS = CORE + "portraits/portrait_parts.json"
RESTRICTIONS = CORE + "portraits/restrictions.json"
CHARACTER = CORE + "character.json"
DOC = prior.DOC
ANCHORS = {
    "dialogue_name": ("<strong>name</strong> - name of the dialogue", 0, 2),
    "animation_name": ("<strong>Name</strong> - name of your animation, will be displayed", 0, 0),
    "portrait_groups": ("<p>The first step is creating an ASEprite file", 0, 3),
    "layer_names": ("<p>You can add layers to each of the mentioned groups", 0, 2),
    "export_settings": ("<p>Once you have your modified character parts", 0, 9),
    "export_paths": ("<p>After clicking Export", 0, 5),
    "generated_restrictions": ("<p>After uploading these files, launch the game", 0, 4),
    "portrait_restrictions": ("folder, the next thing to do is to assign your new item", -1, 4),
    "portrait_race_ids": ("<p>Each race and gender has its own", 0, 2),
    "portrait_subraces": ("<p>Rasimi race has also its subraces", 0, 14),
    "portrait_colors": ("<p>Items that require color will also need", 0, 12),
    "portrait_rgb": ("<p>At the very beginning of the file there are colors", 0, 1),
    "portrait_age_keys": ("<p>And Human hair:</p>", 0, 18),
    "map_stairs": ("<strong>stairs_down/stairs_up</strong> defines Entity ids", 0, 0),
    "map_entrance": ("<strong>building_on_entrance</strong> defines a Building Map id", 0, 1),
    "map_mode": ("<strong>mode</strong> - you can choose one of the modes", 0, 2),
    "map_placement": ("<strong>placement</strong> choose placment of the maps", 0, 3),
    "passive_tags": ("<strong>restrict_tags</strong> - the passive effect applies", 0, 0),
    "passive_effects": ("<strong>effects</strong> - a list of bonuses provided", 0, 2),
    "animation_inner": ("<strong>Inner Animation</strong> - your animation may be a container", 0, 2),
    "actions_tilesheet": ("Image is index from <em>\"actions\"</em> tilesheet", 0, 0),
    "world_tilesheet": ("tileset, you can define it in <em>assets.json</em>", 0, 0),
}


class PairObject(list):
    """중복 frames 키를 지우지 않기 위한 JSON 속성 목록."""


def pair_get(obj, key):
    matches = [value for name, value in obj if name == key]
    if len(matches) != 1:
        raise ValueError("속성이 없거나 중복됨: " + key)
    return matches[0]


def strict_convert(value):
    if isinstance(value, PairObject):
        result = {}
        for key, child in value:
            if key in result:
                raise ValueError("하위 자료의 중복 속성: " + key)
            result[key] = strict_convert(child)
        return result
    if isinstance(value, list):
        return [strict_convert(child) for child in value]
    return value


def pointer(parts):
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def path_parts(path):
    return [part.replace("~1", "/").replace("~0", "~") for part in path.lstrip("/").split("/")]


def review_pattern(row):
    pattern = row["field_pattern"]
    if row["file"] == RESTRICTIONS:
        pattern = re.sub(r"^/restrictions/[^/]+/", "/restrictions/<part>/", pattern)
        pattern = re.sub(r"^/colors/[^/]+/", "/colors/<palette>/", pattern)
    return pattern


def validate_palette(value):
    return isinstance(value, list) and bool(value) and all(isinstance(item, list) and len(item) in {3, 4} and all(isinstance(number, int) and not isinstance(number, bool) and 0 <= number <= 255 for number in item) for item in value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-id", default=prior.BUILD)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = ROOT / "source_original/SOULASH_2" / args.build_id
    evidence = ROOT / "extracted_private/SOULASH_2" / args.build_id
    output = (args.output or evidence / "reference_v2").resolve()
    if not output.is_relative_to(ROOT / "extracted_private") or output.exists():
        raise SystemExit("기존 결과와 분리된 extracted_private 아래 새 출력 경로가 필요합니다.")
    output.mkdir(parents=True)
    manifest_path = evidence / "baseline_manifest.json"
    input_path = evidence / "classification_reference_unresolved.jsonl"
    definitions_path = evidence / "classification_reference_definitions.jsonl"
    manifest = prior.json_load(manifest_path)
    expected = {item["path"]: item for item in manifest["files"]}
    source_checked, cache = set(), {}
    started = datetime.now(timezone.utc).isoformat()

    def verified(relative):
        target = source / relative
        if relative not in source_checked:
            if relative not in expected or prior.digest(target) != expected[relative]["sha256"]:
                raise ValueError("고정 기준선과 내용 지문 불일치: " + relative)
            source_checked.add(relative)
        return target

    def load(relative):
        if relative not in cache:
            cache[relative] = prior.json_load(verified(relative))
        return cache[relative]

    def target_evidence(relative, field, value, kind="value"):
        verified(relative)
        return {"file": relative, "file_sha256": expected[relative]["sha256"], "field_path": field, "target_kind": kind, "value": value}

    doc_lines = verified(DOC).read_text(encoding="utf-8-sig").splitlines()
    docs = {}
    for key, (phrase, before, after) in ANCHORS.items():
        matches = [index for index, line in enumerate(doc_lines) if phrase in line]
        if len(matches) != 1:
            raise ValueError("문서 구절 위치가 고유하지 않음: " + key)
        index = matches[0]
        docs[key] = {"file": DOC, "file_sha256": expected[DOC]["sha256"], "line_start": index + before + 1, "line_end": index + after + 1, "text": "\n".join(doc_lines[index + before:index + after + 1])}
    definitions = defaultdict(dict)
    for line in definitions_path.open(encoding="utf-8"):
        row = json.loads(line)
        definitions[row["namespace"]][row["canonical_id"]] = row["definitions"]
    for path in sorted((source / CORE / "animations").glob("*.json")):
        relative = path.relative_to(source).as_posix()
        obj = load(relative)
        key = prior.canonical_id(obj["id"])
        definitions["animations"].setdefault(key, []).append({"file": relative, "file_sha256": expected[relative]["sha256"], "field_path": "/id", "id": obj["id"], "canonical_id": key, "namespace": "animations"})

    def resolve(namespace, value):
        found = definitions[namespace].get(prior.canonical_id(value), [])
        if len(found) != 1:
            return None
        found = found[0]
        verified(found["file"])
        return found

    pair_tree = json.loads(verified(PARTS).read_text(encoding="utf-8-sig"), object_pairs_hook=PairObject)
    meta = strict_convert(pair_get(pair_tree, "meta"))
    frame_pairs = pair_get(pair_tree, "frames")
    layers = meta["layers"]
    layer_names = defaultdict(list)
    frame_names = defaultdict(list)
    for index, layer in enumerate(layers):
        layer_names[layer["name"]].append(index)
    for ordinal, (key, value) in enumerate(frame_pairs):
        match = re.fullmatch(r".*\(([^()]*)\)\.aseprite", key)
        if match:
            frame_names[match.group(1)].append({"key": key, "pair_ordinal": ordinal})
    restrictions = load(RESTRICTIONS)
    character = load(CHARACTER)
    race_positions = defaultdict(list)
    for index, race in enumerate(character["races"]):
        race_positions[prior.canonical_id(race["id"])].append(index)
    passive_effect_lines = {}
    passive_start = next(i for i, line in enumerate(doc_lines) if '<th scope="col">effect</th>' in line)
    passive_end = next(i for i in range(passive_start, len(doc_lines)) if "</table>" in doc_lines[i])
    for index in range(passive_start, passive_end + 1):
        matched = re.fullmatch(r"\s*<td>([a-z0-9_]+)</td>\s*", doc_lines[index])
        if matched:
            passive_effect_lines[matched.group(1)] = index
    totals, rule_counts, unknown_groups, pattern_counts = Counter(), Counter(), Counter(), Counter()
    pattern_examples = defaultdict(list)
    before_groups, after_groups = Counter(), Counter()
    seen = set()
    overlay_path = output / "classification_reference_overlay_v2.jsonl"
    unresolved_path = output / "classification_reference_unresolved_v2.jsonl"
    with overlay_path.open("w", encoding="utf-8", newline="\n") as overlay, unresolved_path.open("w", encoding="utf-8", newline="\n") as unresolved:
        for line in input_path.open(encoding="utf-8"):
            row = json.loads(line)
            if row["classification"] != "UNKNOWN" or row["location_id"] in seen:
                raise ValueError("입력 분류/위치 ID 오류")
            seen.add(row["location_id"])
            if row["source_file_sha256"] != expected[row["file"]]["sha256"]:
                raise ValueError("입력 출처 해시 불일치")
            group = row["file"][len(CORE):].split("/")[0]
            pattern = row["field_pattern"]
            parts = path_parts(row["field_path"])
            value = row["source"]
            classification, rule_id, reason, doc_keys, targets = None, None, None, [], []
            totals["input_unknown"] += 1
            before_groups[group] += 1
            if group == "dialogues.json" and pattern == "/*/name":
                classification, rule_id = "VISIBLE_TRANSLATE", "dialogue_editor_label"
                reason, doc_keys = "동봉 문서가 대화 편집기 표시명이라고 직접 명시", ["dialogue_name"]
            elif group == "animations" and pattern == "/name":
                classification, rule_id = "VISIBLE_TRANSLATE", "animation_editor_label"
                reason, doc_keys = "동봉 문서가 능력 편집기의 애니메이션 선택 표시명이라고 직접 명시", ["animation_name"]
            elif row["file"] == PARTS and pattern == "/meta/layers/*/name":
                if len(layer_names.get(value, [])) == 1 and len(frame_names.get(value, [])) == 1 and value in restrictions["restrictions"]:
                    classification, rule_id = "INTERNAL", "portrait_layer_restriction_key"
                    reason = "Aseprite 레이어 이름이 고유 프레임 이름과 게임이 생성하는 restrictions 속성 키에 연결됨"
                    doc_keys = ["layer_names", "export_settings", "export_paths", "generated_restrictions"]
                    targets = [target_evidence(RESTRICTIONS, pointer(["restrictions", value]), value, "property_key"), {**target_evidence(PARTS, pointer(["frames", frame_names[value][0]["key"]]), frame_names[value][0]["key"], "property_key"), "pair_ordinal": frame_names[value][0]["pair_ordinal"]}]
            elif row["file"] == PARTS and pattern == "/meta/layers/*/group":
                matches = layer_names.get(value, [])
                if len(matches) == 1 and "group" not in layers[matches[0]]:
                    classification, rule_id = "INTERNAL", "portrait_layer_group_reference"
                    reason = "레이어의 group 값이 같은 내보내기 파일의 고유 최상위 그룹 이름을 참조"
                    doc_keys = ["portrait_groups", "layer_names", "export_settings"]
                    targets = [target_evidence(PARTS, f"/meta/layers/{matches[0]}/name", value)]
            elif row["file"] == RESTRICTIONS and len(parts) >= 4 and parts[0] == "restrictions":
                variant = restrictions["restrictions"][parts[1]][int(parts[2])]
                if parts[3] == "races" and len(parts) == 5:
                    found = resolve("races", value)
                    if found:
                        classification, rule_id = "INTERNAL", "portrait_race_id"
                        reason, doc_keys, targets = "초상화 적용 종족의 ID가 character.json 종족 정의와 일치", ["portrait_restrictions", "portrait_race_ids"], [found]
                elif parts[3] == "subraces" and len(parts) == 5 and variant.get("races") == ["10"] and len(race_positions["10"]) == 1:
                    position = race_positions["10"][0]
                    if value in character["races"][position].get("subraces", {}):
                        classification, rule_id = "INTERNAL", "portrait_subrace_key"
                        reason, doc_keys = "라시미 종족 제한 아래 하위 종족 키가 실제 종족 정의 키와 일치", ["portrait_subraces"]
                        targets = [target_evidence(CHARACTER, pointer(["races", position, "subraces", value]), value, "property_key")]
                elif parts[3] == "colors" and len(parts) == 4 and validate_palette(restrictions["colors"].get(value)):
                    classification, rule_id = "INTERNAL", "portrait_palette_key"
                    reason, doc_keys = "초상화 colors 값이 같은 파일의 실제 RGB 숫자 팔레트 키를 참조", ["portrait_colors", "portrait_rgb"]
                    targets = [target_evidence(RESTRICTIONS, pointer(["colors", value]), value, "property_key")]
                elif parts[3] == "ages" and len(parts) == 5 and value in {"kid", "adult", "middle_aged"}:
                    classification, rule_id = "INTERNAL", "documented_portrait_age_key"
                    reason, doc_keys = "동봉 문서가 초상화 적용 조건 ages 배열에 넣는 제어값으로 예시", ["portrait_age_keys"]
            elif group == "locations.json" and re.fullmatch(r"/special/\*/algorithm/parameters/stairs_(up|down)", pattern):
                found = resolve("entities", value)
                if found:
                    classification, rule_id = "INTERNAL", "map_stairs_entity"
                    reason, doc_keys, targets = "지하·지상 계단 생성에 사용할 엔티티 ID", ["map_stairs"], [found]
            elif group == "locations.json" and pattern == "/special/*/algorithm/parameters/building_on_entrance":
                found = resolve("maps", value)
                if found:
                    classification, rule_id = "INTERNAL", "map_entrance_id"
                    reason, doc_keys, targets = "입구 생성에 사용할 지도 ID", ["map_entrance"], [found]
            elif group == "locations.json" and re.fullmatch(r"/special/\*/scenarios/\*/building_maps/\*/placement", pattern) and value == "carve":
                classification, rule_id = "INTERNAL", "documented_map_placement"
                reason, doc_keys = "동봉 문서가 기존 타일을 깎는 배치 제어값 carve로 명시", ["map_placement"]
            elif group == "locations.json" and re.fullmatch(r"/special/\*/scenarios/\*/building_maps/\*/mode", pattern) and value == "all":
                classification, rule_id = "INTERNAL", "documented_map_mode"
                reason, doc_keys = "동봉 문서가 모든 지도 선택을 제어하는 all로 명시", ["map_mode"]
            elif group == "passives.json" and pattern == "/*/restrict_tags/*":
                found = resolve("tags", value)
                if found:
                    classification, rule_id = "INTERNAL", "passive_tag_restriction"
                    reason, doc_keys, targets = "지속 효과 적용 조건 태그 참조", ["passive_tags"], [found]
            elif group == "passives.json" and pattern == "/*/effects/*/effect" and value in passive_effect_lines:
                classification, rule_id = "INTERNAL", "documented_passive_effect_key"
                reason, doc_keys = "동봉 문서 effects 표의 기계 처리용 effect 키와 정확히 일치", ["passive_effects"]
                index = passive_effect_lines[value]
                targets = [{"file": DOC, "file_sha256": expected[DOC]["sha256"], "target_kind": "documented_enum_key", "value": value, "line_start": index + 1, "line_end": index + 1, "text": doc_lines[index]}]
            elif group == "animations" and pattern == "/inner_animation":
                found = resolve("animations", value)
                if found:
                    classification, rule_id = "INTERNAL", "inner_animation_id"
                    reason, doc_keys, targets = "애니메이션 컨테이너의 내부 애니메이션 정의 ID", ["animation_inner"], [found]
            elif group == "assets.json" and pattern == "/graphics/tilesheets/*/name" and value in {"actions", "world_tiles_overlay"}:
                classification, rule_id = "INTERNAL", "documented_tilesheet_key"
                reason = "문서에서 게임 기능이 찾아 쓰는 타일시트 등록명으로 지정"
                doc_keys = ["actions_tilesheet" if value == "actions" else "world_tilesheet"]
            if classification:
                prior.emit(overlay, {**row, "classification": classification, "previous_classification": "UNKNOWN", "rule_id": rule_id, "reason": reason, "evidence_kind": "documented_structure_and_links" if targets else "bundled_documentation", "document_evidence": [docs[key] for key in doc_keys], "target_evidence": targets, "runtime_observed": False, "translation_status": "NOT_RUN" if classification == "VISIBLE_TRANSLATE" else None})
                totals[classification] += 1
                rule_counts[rule_id] += 1
            else:
                prior.emit(unresolved, {**row, "review_pattern": review_pattern(row), "v2_reason": "추가 문서·참조 근거 미충족; 기존 UNKNOWN 유지"})
                totals["remaining_unknown"] += 1
                after_groups[group] += 1
                key = (group, review_pattern(row))
                pattern_counts[key] += 1
                if len(pattern_examples[key]) < 3:
                    pattern_examples[key].append({"location_id": row["location_id"], "source": value})
    assert totals["input_unknown"] == totals["INTERNAL"] + totals["VISIBLE_TRANSLATE"] + totals["remaining_unknown"]
    with (output / "remaining_field_statistics_v2.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for (group, pattern), count in pattern_counts.most_common():
            prior.emit(stream, {"group": group, "field_pattern": pattern, "count": count, "examples": pattern_examples[(group, pattern)]})
    (output / "documentation_evidence_v2.json").write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"game_id": "SOULASH_2", "build_id": args.build_id, "check_id": "G2_REFERENCE_OVERLAY_V2", "status": "PASS", "scope": "v1 영어 UNKNOWN 목록의 추가 문서·구조 판정 생성", "g2_status": "NOT_RUN", "started": started, "finished": datetime.now(timezone.utc).isoformat(), "command": sys.argv, "tool_sha256": prior.digest(Path(__file__)), "imported_tool_sha256": prior.digest(Path(prior.__file__)), "python_version": sys.version, "inputs": {"baseline_manifest": prior.digest(manifest_path), "unresolved_v1": prior.digest(input_path), "definitions_v1": prior.digest(definitions_path)}, "counts": totals, "rules": rule_counts, "before_groups": before_groups, "after_groups": after_groups, "verified_source_files": len(source_checked), "portrait_structure": {"layer_rows": len(layers), "unique_layer_names": len(layer_names), "duplicate_layer_names": sum(len(v) > 1 for v in layer_names.values()), "restriction_parts": len(restrictions["restrictions"]), "frame_names": len(frame_names), "ambiguous_frame_names": sum(len(v) > 1 for v in frame_names.values())}, "output_hashes": {p.name: prior.digest(p) for p in output.iterdir() if p.is_file()}, "limitations": ["기존 인벤토리·후보 manifest·원본 파일은 변경하지 않음", "문서화되지 않은 색상 합성 방식, 나이 elder, 미연결 레이어, font/sound 표시명은 UNKNOWN 유지", "속성 키 목록, 지도 이름, 중복 정의·중복 JSON 키의 실행 해석 문제는 이 판정으로 해결하지 않음", "실행을 관찰하지 않았으며 전체 G2·G3 완료 아님"]}
    (output / "classification_reference_summary_v2.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"counts": totals, "rules": rule_counts, "after_groups": after_groups}, ensure_ascii=False))


if __name__ == "__main__":
    main()
