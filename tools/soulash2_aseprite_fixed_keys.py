"""Aseprite 고정 속성 키를 공식 내보내기 코드와 중복 보존 원문 구조에 대조한다."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029"
SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
PARTS = "data/mods/core_2/portraits/portrait_parts.json"


class Pairs(list):
    """같은 이름의 프레임도 원문 등장 순서 그대로 보존한다."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def get_one(obj, key):
    if not isinstance(obj, Pairs):
        raise ValueError("객체가 아닌 부모")
    values = [value for name, value in obj if name == key]
    if len(values) != 1:
        raise ValueError("고정 필드 중복·누락: " + key)
    return values[0]


def keys(obj):
    if not isinstance(obj, Pairs):
        raise ValueError("필드 객체가 아님")
    result = [key for key, _ in obj]
    if len(set(result)) != len(result):
        raise ValueError("고정 필드가 중복됨")
    return result


def fields(obj, names, value_type):
    if set(keys(obj)) != set(names):
        raise ValueError("고정 필드 집합 불일치")
    if any(type(value) is not value_type for _, value in obj):
        raise ValueError("고정 필드 값 형식 불일치")


def frame_schema(frame):
    if set(keys(frame)) != {"frame", "rotated", "trimmed", "spriteSourceSize", "sourceSize", "duration"}:
        raise ValueError("프레임 부모 구조 불일치")
    fields(get_one(frame, "frame"), ("x", "y", "w", "h"), int)
    fields(get_one(frame, "spriteSourceSize"), ("x", "y", "w", "h"), int)
    fields(get_one(frame, "sourceSize"), ("w", "h"), int)
    if type(get_one(frame, "rotated")) is not bool or type(get_one(frame, "trimmed")) is not bool or type(get_one(frame, "duration")) is not int:
        raise ValueError("프레임 제어값 형식 불일치")


def layer_schema(layer):
    names = keys(layer)
    if not set(names).issubset({"name", "group", "opacity", "blendMode", "color", "data"}) or "name" not in names:
        raise ValueError("레이어 부모 구조 불일치")
    for key in ("name", "group", "blendMode", "color", "data"):
        if key in names and not isinstance(get_one(layer, key), str):
            raise ValueError("레이어 문자열 형식 불일치")
    if "opacity" in names and (type(get_one(layer, "opacity")) is not int or not 0 <= get_one(layer, "opacity") <= 255):
        raise ValueError("불투명도 형식 불일치")
    if ("opacity" in names) != ("blendMode" in names):
        raise ValueError("이미지 레이어 고정 속성 쌍 불일치")


def collect(obj, path="", steps=()):
    if isinstance(obj, Pairs):
        count = Counter()
        for ordinal, (key, value) in enumerate(obj):
            count[key] += 1
            current = [*steps, {"key": key, "occurrence": count[key], "pair_ordinal": ordinal}]
            identity = {"parent_path": path, "key": key, "occurrence_path": current}
            yield sha(canonical(identity)), identity, obj, value
            yield from collect(value, path + "/" + key.replace("~", "~0").replace("/", "~1"), current)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from collect(value, path + "/" + str(index), [*steps, {"index": index}])


def run(output):
    output = output.resolve()
    if not output.is_relative_to(ROOT / "working_private/SOULASH_2"):
        raise ValueError("판정 출력 경계 오류")
    output.mkdir(parents=True, exist_ok=False)
    inputs = {}

    def blob(path):
        path = path.resolve()
        if path not in inputs:
            inputs[path] = path.read_bytes()
        return inputs[path]

    def record(path):
        return {"artifact": path.resolve().relative_to(ROOT).as_posix(), "sha256": sha(blob(path))}

    manifest_path = BASE / "reference_portraits/official_sources/manifest.json"
    official = json.loads(blob(manifest_path))
    exporter = next(row for row in official if row["local_file"] == "doc_exporter.cpp")
    exporter_path = manifest_path.parent / exporter["local_file"]
    exporter_bytes = blob(exporter_path)
    if sha(exporter_bytes) != exporter["sha256"]:
        raise ValueError("공식 코드 지문 불일치")
    code = exporter_bytes.decode("utf-8").splitlines()
    frame_lines = "\n".join(code[1475:1504])
    layer_lines = "\n".join(code[1621:1640])
    for token in ("frames", "frame", "x", "y", "w", "h", "rotated", "trimmed", "spriteSourceSize", "sourceSize", "duration"):
        if '\\"' + token + '\\"' not in frame_lines:
            raise ValueError("공식 프레임 키 근거 없음: " + token)
    for token in ("layers", "name", "group", "opacity", "blendMode"):
        if '\\"' + token + '\\"' not in layer_lines:
            raise ValueError("공식 레이어 키 근거 없음: " + token)

    source_path = SOURCE / PARTS
    source_data = blob(source_path)
    source_sha = sha(source_data)
    baseline = json.loads(blob(BASE / "baseline_manifest.json"))
    if next(row["sha256"] for row in baseline["files"] if row["path"] == PARTS) != source_sha:
        raise ValueError("게임 원본 지문 불일치")
    obj = json.loads(source_data.decode("utf-8-sig"), object_pairs_hook=Pairs)
    frames = get_one(obj, "frames")
    layers = get_one(get_one(obj, "meta"), "layers")
    if not isinstance(frames, Pairs) or type(layers) is not list:
        raise ValueError("공식 프레임·레이어 상위 구조 불일치")
    for _, frame in frames:
        frame_schema(frame)
    for layer in layers:
        layer_schema(layer)
    actual = {identity: (parts, parent, value) for identity, parts, parent, value in collect(obj)}

    ledger_path = BASE / "reference_triage/property_key_review_ledger_v2.jsonl"
    ledger_sha = sha(blob(ledger_path))
    selected = {}
    for raw in blob(ledger_path).splitlines():
        row = json.loads(raw)
        if row.get("review_category") == "OFFICIAL_FORMAT_FIXED_FIELD_CANDIDATE":
            index = row["original_inventory"]["row_number"]
            if index in selected:
                raise ValueError("후보 중복 위치")
            selected[index] = row
    original_path = BASE / "json_property_keys.jsonl"
    original_sha = sha(blob(original_path))
    originals = {}
    for number, raw in enumerate(blob(original_path).splitlines(keepends=True), 1):
        if number in selected:
            originals[number] = (json.loads(raw), sha(raw))
    if set(originals) != set(selected):
        raise ValueError("원시 키 목록에 후보 누락")

    proof = {"status": "PASS", "scope": "ASEPRITE_FIXED_PROPERTY_KEYS_ONLY", "classification": "INTERNAL", "source": record(source_path), "official_manifest": record(manifest_path),
             "official_code": {**record(exporter_path), "url": exporter["github_url"], "commit": exporter["commit"]},
             "frame_rule": {"line_start": 1476, "line_end": 1504, "required_parent": "frames/<sample> 및 frame·spriteSourceSize·sourceSize 사각형 객체", "frame_instances": len(frames), "values_checked": "정수 좌표·크기·시간 및 bool 플래그"},
             "layer_rule": {"line_start": 1622, "line_end": 1640, "required_parent": "meta/layers 배열의 레이어 객체", "layer_instances": len(layers), "values_checked": "name·group·blendMode 문자열 및 opacity 정수"},
             "limitation": "고정 속성명만 판정. 동적 프레임 식별자와 name·group·data 등의 값에는 이 판정을 적용하지 않음."}
    proof_path = output / "format_evidence.json"
    proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
    proof_hash = sha(proof_path.read_bytes())
    output_path = output / "classification_key_overlay.jsonl"
    counts = Counter()
    seen = set()
    with output_path.open("x", encoding="utf-8", newline="\n") as stream:
        for number, candidate in selected.items():
            row, row_sha = originals[number]
            if candidate["file"] != PARTS or row["file"] != PARTS or candidate["source_file_sha256"] != source_sha or row["source_file_sha256"] != source_sha:
                raise ValueError("후보 원본 파일 경계 불일치")
            if candidate["original_inventory"]["sha256"] != original_sha:
                raise ValueError("후보 원시 목록 지문 불일치")
            location_data = {key: row[key] for key in ("parent_path", "key", "occurrence_path") if key in row}
            if any(candidate.get(key) != value for key, value in location_data.items()):
                raise ValueError("후보와 원시 키 위치 불일치")
            identity = sha(canonical(location_data))
            if identity in seen or identity not in actual:
                raise ValueError("실제 키 위치 중복·누락")
            seen.add(identity)
            real_identity, parent, value = actual[identity]
            if real_identity != location_data or candidate.get("source_value_sha256") != sha(row["key"].encode("utf-8")):
                raise ValueError("중복 등장 위치 또는 키 지문 불일치")
            steps = row["occurrence_path"]
            names = [step.get("key") for step in steps]
            key = row["key"]
            if len(steps) == 3 and names[0] == "frames" and key in {"frame", "rotated", "trimmed", "spriteSourceSize", "sourceSize", "duration"}:
                frame_schema(parent)
                rule = "aseprite_frame_fixed_property"
            elif len(steps) == 4 and names[0] == "frames" and names[2] in {"frame", "spriteSourceSize", "sourceSize"} and key in ({"w", "h"} if names[2] == "sourceSize" else {"x", "y", "w", "h"}):
                fields(parent, ("w", "h") if names[2] == "sourceSize" else ("x", "y", "w", "h"), int)
                rule = "aseprite_rectangle_fixed_property"
            elif len(steps) == 4 and names[:2] == ["meta", "layers"] and "index" in steps[2] and key in {"name", "group", "opacity", "blendMode"}:
                layer_schema(parent)
                rule = "aseprite_layer_fixed_property"
            else:
                raise ValueError("고정 속성으로 입증하지 못한 부모 경로")
            counts[rule] += 1
            location = PARTS + "#key/" + identity
            result = {**row, "axis": "json_key", "location_id": location, "record_id": "json_key:" + location, "source": key, "source_value_sha256": sha(key.encode("utf-8")), "previous_classification": "UNKNOWN", "classification": "INTERNAL",
                      "rule_id": rule, "reason": "Aseprite 공식 내보내기 코드가 쓰는 고정 속성명이며 실제 원문의 같은 부모 구조·값 형식·등장 순서와 일치합니다. 속성의 문자열 값은 별도 축에서 판정합니다.",
                      "evidence_kind": "official_format_and_exact_parent_structure", "evidence_ref": {"artifact": proof_path.relative_to(ROOT).as_posix(), "sha256": proof_hash, "rule": rule},
                      "inventory_origin": {"artifact": original_path.relative_to(ROOT).as_posix(), "artifact_sha256": original_sha, "row_number": number, "row_sha256": row_sha}, "runtime_observed": False}
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
    reopened = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    if len(reopened) != len(selected) or len({row["location_id"] for row in reopened}) != len(selected) or any(row["classification"] != "INTERNAL" for row in reopened):
        raise ValueError("판정 결과 재열기 불일치")
    inputs[Path(__file__).resolve()] = Path(__file__).read_bytes()
    for path, data in inputs.items():
        if path.read_bytes() != data:
            raise ValueError("검사 도중 입력 변경")
    report = {"status": "PASS", "scope": "ASEPRITE_FIXED_PROPERTY_KEYS_ONLY", "g2_status": "NOT_RUN", "runtime_status": "NOT_RUN", "selected_rows": len(selected), "classified_internal": len(reopened), "unresolved_selected": 0, "rules": dict(counts), "frame_instances": len(frames), "frame_unique_names": len({name for name, _ in frames}), "layers": len(layers), "source_reopen": "PASS", "output_reopen": "PASS", "overlay": {"path": output_path.relative_to(ROOT).as_posix(), "sha256": sha(output_path.read_bytes())}, "inputs": [{"path": path.relative_to(ROOT).as_posix(), "sha256": sha(data)} for path, data in sorted(inputs.items())]}
    (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps({key: result[key] for key in ("status", "selected_rows", "classified_internal", "unresolved_selected", "rules")}))


if __name__ == "__main__":
    main()
