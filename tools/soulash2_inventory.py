"""Soulash 2 기준선의 위치별 문구와 미디어를 보수적으로 조사한다.

실행을 관찰하지 않은 분류는 구조 근거로 표시한다. 폴란드어 자료는 ID가
정합한 대응 값의 차이만 힌트로 남기며 자동 분류 근거로 사용하지 않는다.
"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUILD = "0.10.4.0.1_20261029"
CORE = "data/mods/core_2/"
MEDIA_EXTENSIONS = {".png", ".gif", ".jpg", ".jpeg", ".webp", ".mp4", ".webm", ".ogg", ".wav", ".mp3"}
DISPLAY_RULES = {
    "abilities": [r"/(name|description)"],
    "buildings": [r"/name"],
    "entities": [r"/(name|description)", r"/openable/description", r"/fighter/attackNames/\*", r"/resource/affix", r"/persona/occupation"],
    "events": [r"/(name|flavor)", r"/interactions/\*/label", r"/.*(announcement|history_event|death_text)", r"/history_events/(begin|end|success|failure)"],
    "milestones": [r"/(name|description)"],
    "ability_amplifiers.json": [r"/\*/(name|description)"],
    "ability_stackers.json": [r"/\*/(name|description)"],
    "building_groups.json": [r"/.*name"],
    "building_names.json": [r"/building_names/\*/(formats|prefixes|suffixes|core_names)/\*"],
    "character.json": [r"/(production_actions|control_actions)/\*/(name|description|success_message|failure_message)", r"/races/\*/(name|description|orphan_surname)", r"/races/\*/subraces/[^/]+/name", r"/custom_eq_slots/\*/name"],
    "conversations.json": [r"/(conversations|family_conversations)/\*/(text|answer_positive|answer_negative)"],
    "dialogues.json": [r"/\*/(ally_dialogue|monologue|ally_monologue|player_dialogue)/\*/\*"],
    "goals.json": [r"/paths/\*/(name|objective)", r"/paths/\*/goals/\*/(short|long)"],
    "locations.json": [r"/(settlements|special)/\*/(name|full_name)", r"/special/\*/algorithm/parameters/rumors?/\*"],
    "messages.json": [r"/main/\*/format", r"/statistics/\*/(name|description)", r"/[^/]+/\*/(name|description|label|format|text)", r"/ability/\*/(effect|success|fail)", r"/(action_plan_description|directions)/[^/]+", r"/relative_terms/\*/genders/\*/name", r"/(hit_location|ability_target|ability_requirement|aoe_shape|year_part|day_part|item_type|weapon_type|tag|rarity|ai_behaviors|temperatures|precipitations|crimes|skill_levels)/\*"],
    "passives.json": [r"/\*/(name|description)"],
    "region_names.json": [r"/[^/]+/(prefixes|suffixes)/\*"],
    "skills.json": [r"/\*/(name|description)"],
    "tutorial.json": [r"/[^/]+/(title|description)", r"/[^/]+/(keys_keyboard|gamepad_keys)/\*/text"],
    "weather.json": [r"/\*/(name|trigger_message)"],
}


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def pointer(path):
    return "".join("/" + str(item).replace("~", "~0").replace("/", "~1") for item in path)


def pattern_pointer(path):
    return pointer(["*" if isinstance(item, int) else item for item in path])


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("중복 JSON 키: " + key)
        result[key] = value
    return result


def load_json(raw):
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=strict_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("비표준 숫자: " + value)))


class PairObject(list):
    """중복 키를 지우지 않고 속성 순서를 그대로 보존한다."""


def lossless_rows(value, path=(), occurrences=(), ancestry=()):
    if isinstance(value, PairObject):
        ids = [item for key, item in value if key == "id" and isinstance(item, (str, int))]
        if len(ids) == 1:
            ancestry += ({"path": pointer(path), "id": ids[0]},)
        seen = Counter()
        for ordinal, (key, child) in enumerate(value):
            seen[key] += 1
            step = {"key": key, "occurrence": seen[key], "pair_ordinal": ordinal}
            yield from lossless_rows(child, path + (key,), occurrences + (step,), ancestry)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from lossless_rows(child, path + (index,), occurrences + ({"index": index},), ancestry)
    elif isinstance(value, str):
        yield path, value, occurrences, ancestry


def duplicate_paths(value, path=()):
    if isinstance(value, PairObject):
        counter = Counter(key for key, _ in value)
        for key, count in counter.items():
            if count > 1:
                yield {"parent_path": pointer(path), "key": key, "count": count}
        for key, child in value:
            yield from duplicate_paths(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from duplicate_paths(child, path + (index,))


def lossless_property_rows(value, path=(), occurrences=()):
    if isinstance(value, PairObject):
        seen = Counter()
        for ordinal, (key, child) in enumerate(value):
            seen[key] += 1
            step = {"key": key, "occurrence": seen[key], "pair_ordinal": ordinal}
            yield path, key, occurrences + (step,)
            yield from lossless_property_rows(child, path + (key,), occurrences + (step,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from lossless_property_rows(child, path + (index,), occurrences + ({"index": index},))


def create_batches(output):
    """문맥 그룹마다 번역 전 후보를 분할한다. 번역 결과를 만들지는 않는다."""
    destination = output / "translation_batch_candidates"
    if destination.exists():
        raise ValueError("분할 자료 폴더가 이미 존재합니다. 새 출력 경로를 사용하세요.")
    destination.mkdir()
    grouped = defaultdict(list)
    for filename in ["translation_work.jsonl", "text_lines.jsonl"]:
        with (output / filename).open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if row["classification"] != "VISIBLE_TRANSLATE":
                    continue
                group = source_context(row["file"])[1].split("/")[0]
                if filename == "text_lines.jsonl":
                    group = "npc_name_text"
                grouped[group].append(row)
    batches = []
    for group, rows in sorted(grouped.items()):
        chunks, chunk, chars = [], [], 0
        for row in rows:
            if chunk and (len(chunk) >= 200 or chars + len(row["source"]) > 14000):
                chunks.append(chunk)
                chunk, chars = [], 0
            chunk.append(row)
            chars += len(row["source"])
        if chunk:
            chunks.append(chunk)
        for index, chunk in enumerate(chunks, 1):
            name = re.sub(r"[^a-zA-Z0-9_-]", "_", group) + f"_{index:03d}.jsonl"
            target = destination / name
            with target.open("w", encoding="utf-8", newline="\n") as stream:
                for row in chunk:
                    write_jsonl(stream, row)
            batches.append({"file": name, "group": group, "locations": len(chunk), "source_characters": sum(len(row["source"]) for row in chunk), "sha256": digest(target), "translation_status": "NOT_RUN", "gate": "G1 통과 후 번역 시작"})
    (destination / "manifest.json").write_text(json.dumps(batches, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"batches": len(batches), "locations": sum(row["locations"] for row in batches), "manifest_sha256": digest(destination / "manifest.json")}


def string_rows(value, path=(), ancestry=()):
    if isinstance(value, dict):
        if "id" in value and isinstance(value["id"], (str, int)):
            ancestry = ancestry + ({"path": pointer(path), "id": value["id"]},)
        for key, child in value.items():
            yield from string_rows(child, path + (key,), ancestry)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from string_rows(child, path + (index,), ancestry)
    elif isinstance(value, str):
        yield path, value, ancestry


def property_rows(value, path=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield path, key
            yield from property_rows(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from property_rows(child, path + (index,))


def identity(value):
    if isinstance(value, dict) and isinstance(value.get("id"), (str, int)):
        return type(value["id"]).__name__, value["id"]
    return None


def match_pl(source, translated, path):
    """배열은 고유 ID로만 정합한다. 순서만 같은 배열을 같은 대상으로 보지 않는다."""
    left, right, right_path = source, translated, []
    id_matches = 0
    for step in path:
        if isinstance(step, str):
            if not isinstance(left, dict) or not isinstance(right, dict) or step not in right:
                return None, None, "missing_field", id_matches
            left, right = left[step], right[step]
            right_path.append(step)
        else:
            if not isinstance(left, list) or not isinstance(right, list):
                return None, None, "container_mismatch", id_matches
            selected = left[step]
            selected_id = identity(selected)
            if selected_id is None:
                return None, None, "array_without_stable_id", id_matches
            left_matches = [i for i, item in enumerate(left) if identity(item) == selected_id]
            right_matches = [i for i, item in enumerate(right) if identity(item) == selected_id]
            if len(left_matches) != 1 or len(right_matches) != 1:
                return None, None, "missing_or_duplicate_id", id_matches
            other_index = right_matches[0]
            left, right = selected, right[other_index]
            right_path.append(other_index)
            id_matches += 1
    if not isinstance(right, str):
        return None, None, "value_type_mismatch", id_matches
    return right, pointer(right_path), "id_matched" if id_matches else "dictionary_path", id_matches


def source_context(relative):
    if not relative.startswith(CORE):
        return "other", relative, None
    local = relative[len(CORE):]
    if local.startswith("translations/"):
        pieces = local.split("/", 2)
        return "auxiliary_translation", pieces[2] if len(pieces) == 3 else local, pieces[1]
    return "primary_english", local, "en"


def classify(local, path, value, role):
    normalized = pattern_pointer(path)
    group = local.split("/")[0]
    if role == "other":
        return "UNKNOWN", "기본 게임 외 JSON 자료: 사용 위치 확인 필요", None
    for rule in DISPLAY_RULES.get(group, []):
        if re.fullmatch(rule, normalized):
            if not value:
                return "VISIBLE_KEEP", "표시 문구 필드의 원래 빈 값: 빈 값 보존", f"{group}:{rule}"
            return "VISIBLE_TRANSLATE", "영어 원본의 표시 설명·대화·서식 데이터 구조", f"{group}:{rule}"
    if group == "npc" and any(part in {"prefixes", "suffixes", "beginning"} for part in path):
        return "VISIBLE_TRANSLATE" if value else "VISIBLE_KEEP", "인물·정착지·전쟁 이름의 조합 조각: character.json 이름 자료 참조", "npc:name_parts"
    if path and path[-1] == "id":
        return "INTERNAL", "객체의 ID 필드: 참조 식별값 보존", "identity_field"
    if group == "entities" and len(path) == 2 and path[0] == "components":
        return "INTERNAL", "객체 동작을 지정하는 components 배열의 구성요소 키", "entities:components"
    if group == "conversations.json" and ((len(path) == 4 and path[2] in {"options", "entities"}) or (len(path) == 3 and path[2] in {"type", "event"})):
        return "INTERNAL", "대화 연결·대상·처리 종류를 지정하는 참조 필드", "conversations:references"
    if group == "tutorial.json" and len(path) == 4 and path[1] in {"keys_keyboard", "gamepad_keys"} and path[-1] == "id":
        return "INTERNAL", "설명에서 치환하는 입력 안내 자리표시자 키", "tutorial:placeholder_id"
    if group == "character.json" and len(path) == 4 and path[0] == "races" and path[2] == "names":
        return "INTERNAL", "인물·정착지 이름 사전 파일의 상대 경로", "character:name_resource"
    if group == "assets.json" and (value.endswith((".png", ".ogg", ".ttf")) or normalized.endswith("/path")):
        return "INTERNAL", "assets.json 자산 파일 참조", "assets:resource_path"
    return "UNKNOWN", "표시 여부 또는 참조 용도를 확정할 근거가 아직 없음", None


def write_jsonl(stream, row):
    stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-id", default=DEFAULT_BUILD)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write-batches", action="store_true")
    args = parser.parse_args()
    source = (args.source or ROOT / "source_original/SOULASH_2" / args.build_id).resolve()
    output = (args.output or ROOT / "extracted_private/SOULASH_2" / args.build_id).resolve()
    if not source.is_relative_to(ROOT / "source_original"):
        raise SystemExit("읽기는 고정된 source_original 기준선에서만 허용합니다.")
    if not output.is_relative_to(ROOT / "extracted_private"):
        raise SystemExit("출력은 extracted_private 아래여야 합니다.")
    manifest_path = ROOT / "extracted_private/SOULASH_2" / args.build_id / "baseline_manifest.json"
    if not manifest_path.is_file():
        raise SystemExit("기준선 복사 완료 목록이 아직 없습니다. 완료 후 실행하세요.")
    manifest = load_json(manifest_path.read_bytes())
    expected = {item["path"]: item for item in manifest["files"]}
    actual = {p.relative_to(source).as_posix(): p for p in source.rglob("*") if p.is_file()}
    if set(actual) != set(expected):
        raise SystemExit("기준선 파일 목록이 고정 목록과 다릅니다.")
    for name, path in actual.items():
        if path.stat().st_size != expected[name]["size"] or digest(path) != expected[name]["sha256"]:
            raise SystemExit("기준선 내용 지문 불일치: " + name)
    output.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    errors, documents, file_rows, recovered = [], {}, [], {}
    counts, primary_counts, groups, fields = Counter(), Counter(), defaultdict(Counter), defaultdict(Counter)
    unique_visible, group_visible, hint_counts = set(), defaultdict(set), Counter()
    volume, group_volume = Counter(), defaultdict(Counter)
    for relative in sorted(actual):
        if not relative.lower().endswith(".json"):
            continue
        path = actual[relative]
        try:
            documents[relative] = load_json(path.read_bytes())
            file_rows.append({"path": relative, "sha256": expected[relative]["sha256"], "size": expected[relative]["size"], "parse": "PASS"})
        except Exception as exc:
            error = {"path": relative, "source_sha256": expected[relative]["sha256"], "stage": "json_parse", "error": str(exc), "status": "UNKNOWN"}
            try:
                alternate = json.loads(path.read_bytes().decode("utf-8-sig"), object_pairs_hook=PairObject)
                recovered[relative] = alternate
                error["alternate_extraction"] = "PASS_LOSSLESS_PROPERTY_PAIRS"
                error["duplicates"] = list(duplicate_paths(alternate))
                error["remaining_unknown"] = "게임 JSON 로더의 중복 키 처리 및 실제 사용 여부"
            except Exception as alternate_error:
                error["alternate_extraction"] = "FAIL"
                error["alternate_error"] = str(alternate_error)
            errors.append(error)
            file_rows.append({"path": relative, "sha256": expected[relative]["sha256"], "size": expected[relative]["size"], "parse": "FAIL", "alternate_parse": error["alternate_extraction"]})
    with (output / "json_strings.jsonl").open("w", encoding="utf-8", newline="\n") as strings, (output / "json_property_keys.jsonl").open("w", encoding="utf-8", newline="\n") as keys, (output / "translation_work.jsonl").open("w", encoding="utf-8", newline="\n") as work:
        for relative, document in documents.items():
            role, local, language = source_context(relative)
            group = local.split("/")[0]
            translated = documents.get(CORE + "translations/pl/" + local) if role == "primary_english" else None
            for path, value, ancestry in string_rows(document):
                state, reason, rule = classify(local, path, value, role)
                row = {"location_id": relative + "#" + pointer(path), "file": relative, "field_path": pointer(path), "field_pattern": pattern_pointer(path), "id_ancestry": ancestry, "source_file_sha256": expected[relative]["sha256"], "source_value_sha256": sha256_bytes(value.encode("utf-8")), "source": value, "role": role, "language": language, "classification": state, "evidence_kind": "static_structure" if state != "UNKNOWN" else "unknown", "reason": reason, "rule": rule, "runtime_observed": False}
                if translated is not None:
                    other, other_path, method, id_count = match_pl(document, translated, path)
                    hint_counts[method] += 1
                    if other is not None and other != value:
                        row["pl_hint"] = {"file": CORE + "translations/pl/" + local, "file_sha256": expected[CORE + "translations/pl/" + local]["sha256"], "path": other_path, "value": other, "matching": method, "id_matches": id_count, "classification_authority": False}
                counts[state] += 1
                if role == "primary_english":
                    primary_counts[state] += 1
                    groups[group][state] += 1
                    fields[(group, row["field_pattern"])][state] += 1
                    if state == "VISIBLE_TRANSLATE":
                        unique_visible.add(value)
                        group_visible[group].add(value)
                        size = {"characters": len(value), "words": len(re.findall(r"\b[\w]+(?:['’-][\w]+)*\b", value))}
                        volume.update(size)
                        group_volume[group].update(size)
                        write_jsonl(work, row)
                write_jsonl(strings, row)
            for path, key in property_rows(document):
                write_jsonl(keys, {"file": relative, "parent_path": pointer(path), "key": key, "source_file_sha256": expected[relative]["sha256"], "role": role, "classification": "UNKNOWN", "reason": "JSON 속성 키의 표시 사용 여부는 값 목록과 별도 추적 필요"})
        for relative, document in recovered.items():
            role, local, language = source_context(relative)
            group = local.split("/")[0]
            for path, value, occurrences, ancestry in lossless_rows(document):
                occurrence_hash = sha256_bytes(json.dumps(occurrences, ensure_ascii=False).encode("utf-8"))
                row = {"location_id": relative + "#occurrence/" + occurrence_hash, "file": relative, "field_path": pointer(path), "field_pattern": pattern_pointer(path), "occurrence_path": occurrences, "id_ancestry": ancestry, "source_file_sha256": expected[relative]["sha256"], "source_value_sha256": sha256_bytes(value.encode("utf-8")), "source": value, "role": role, "language": language, "classification": "UNKNOWN", "evidence_kind": "unknown", "reason": "중복 키를 포함한 원본을 속성 순서와 등장 횟수로 무손실 추출: 실제 로더 해석 미확인", "runtime_observed": False, "extraction_method": "lossless_property_pairs"}
                counts["UNKNOWN"] += 1
                if role == "primary_english":
                    primary_counts["UNKNOWN"] += 1
                    groups[group]["UNKNOWN"] += 1
                    fields[(group, row["field_pattern"])]["UNKNOWN"] += 1
                write_jsonl(strings, row)
            for path, key, occurrences in lossless_property_rows(document):
                write_jsonl(keys, {"file": relative, "parent_path": pointer(path), "key": key, "occurrence_path": occurrences, "source_file_sha256": expected[relative]["sha256"], "role": role, "classification": "UNKNOWN", "reason": "중복 속성을 보존한 키 목록: 로더 해석 및 표시 여부 확인 필요"})
    media, maps, text_counts = [], [], Counter()
    with (output / "text_lines.jsonl").open("w", encoding="utf-8", newline="\n") as text_stream:
        for relative, path in sorted(actual.items()):
            extension = path.suffix.lower()
            if extension in MEDIA_EXTENSIONS:
                media.append({"location_id": relative, "file": relative, "sha256": expected[relative]["sha256"], "size": expected[relative]["size"], "classification": "MEDIA", "treatment": "UNKNOWN", "media_type": "audio" if extension in {".ogg", ".wav", ".mp3"} else "video" if extension in {".mp4", ".webm"} else "image", "reason": "픽셀 또는 음성 내용의 육안·청취 검토 전"})
            if extension == ".smap":
                try:
                    raw = path.read_bytes()
                    parts = raw.decode("utf-8-sig").split("|", 11)
                    if len(parts) < 12:
                        raise ValueError("예상한 11개 이상 헤더 구분자가 없습니다.")
                    maps.append({"location_id": relative + "#header/1", "file": relative, "sha256": expected[relative]["sha256"], "map_id": parts[0], "source": parts[1], "source_value_sha256": sha256_bytes(parts[1].encode("utf-8")), "classification": "UNKNOWN", "reason": "smap 헤더의 지도 이름: 편집기·게임 표시 참조 확인 전", "remaining_payload_audit": "NOT_RUN"})
                except Exception as exc:
                    errors.append({"path": relative, "source_sha256": expected[relative]["sha256"], "stage": "smap_header", "error": str(exc), "status": "UNKNOWN"})
            if extension == ".txt":
                try:
                    content = path.read_bytes().decode("utf-8-sig")
                    is_names = relative.startswith(CORE + "npc/names/")
                    for number, line in enumerate(content.splitlines(), 1):
                        write_jsonl(text_stream, {"location_id": relative + "#line/" + str(number), "file": relative, "line": number, "source_file_sha256": expected[relative]["sha256"], "source_value_sha256": sha256_bytes(line.encode("utf-8")), "source": line, "classification": "VISIBLE_TRANSLATE" if is_names and line else "UNKNOWN", "reason": "character.json이 참조하는 인명 사전" if is_names else "문서·로그·부가 텍스트: 게임 표시 여부 별도 확인", "runtime_observed": False})
                        text_counts["name_lines" if is_names else "other_lines"] += 1
                        if is_names and line:
                            text_counts["name_characters"] += len(line)
                            text_counts["name_words"] += len(re.findall(r"\b[\w]+(?:['’-][\w]+)*\b", line))
                except Exception as exc:
                    errors.append({"path": relative, "source_sha256": expected[relative]["sha256"], "stage": "text_decode", "error": str(exc), "status": "UNKNOWN"})
    for name, rows in [("json_files.jsonl", file_rows), ("media_inventory.jsonl", media), ("map_names.jsonl", maps), ("extraction_errors.jsonl", errors)]:
        with (output / name).open("w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                write_jsonl(stream, row)
    with (output / "field_statistics.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for (group, field), states in sorted(fields.items()):
            write_jsonl(stream, {"group": group, "field_pattern": field, "counts": states})
    summary = {"game_id": "SOULASH_2", "build_id": args.build_id, "check_id": "G2_INITIAL_STRUCTURED_INVENTORY", "status": "FAIL" if errors else "NOT_RUN", "status_reason": "추출 오류 또는 미분류·코드·전체 미디어 조사 미완료로 G2 통과 아님", "started": started, "finished": datetime.now(timezone.utc).isoformat(), "command": sys.argv, "tool_sha256": digest(Path(__file__)), "python_version": sys.version, "baseline_manifest_sha256": digest(manifest_path), "file_count": len(actual), "json_files": len(file_rows), "json_parse_failures": sum(item["stage"] == "json_parse" for item in errors), "extraction_errors": len(errors), "all_json_value_counts": counts, "primary_english_value_counts": primary_counts, "primary_visible_unique_values": len(unique_visible), "primary_groups": dict(groups), "translation_split_units": [{"group": group, "locations": states.get("VISIBLE_TRANSLATE", 0), "unique_values": len(group_visible[group])} for group, states in sorted(groups.items()) if states.get("VISIBLE_TRANSLATE", 0)], "pl_alignment_counts": hint_counts, "media_files": len(media), "map_names": len(maps), "text_lines": text_counts, "limitations": ["구조상 표시 문구와 런타임 관찰을 구분. 모든 runtime_observed=false", "배열 항목은 고유 ID가 있는 경우만 폴란드어와 비교. 같은 인덱스로 강제 정합하지 않음", "모든 JSON 속성 키를 별도 보존하며 미확인 값은 UNKNOWN", "실행 파일의 코드 문자열·smap 본문·미디어 픽셀 및 음성·사용 글꼴 연결은 이 도구의 완료 범위 아님", "일부 구조 분류는 표시 후보이며 실제 호출 경로로 보강 필요. G2 전체 완료를 의미하지 않음"]}
    summary["primary_visible_volume"] = volume
    summary["primary_visible_unique_characters"] = sum(map(len, unique_visible))
    summary["primary_visible_unique_words"] = sum(len(re.findall(r"\b[\w]+(?:['’-][\w]+)*\b", value)) for value in unique_visible)
    summary["primary_group_volume"] = dict(group_volume)
    summary["lossless_recovered_json_files"] = len(recovered)
    if args.write_batches:
        summary["translation_batches"] = create_batches(output)
    (output / "inventory_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ["json_files", "json_parse_failures", "extraction_errors", "primary_english_value_counts", "primary_visible_unique_values", "media_files", "map_names", "text_lines"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
