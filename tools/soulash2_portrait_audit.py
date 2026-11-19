"""Aseprite 공식 출처와 게임 원본을 대조해 초상화 미확정 값만 별도 판정한다."""
import argparse
import hashlib
import json
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = "0.10.4.0.1_20261029"
SOURCE = ROOT / "source_original/SOULASH_2" / BUILD
EVIDENCE = ROOT / "extracted_private/SOULASH_2" / BUILD
OUTPUT = EVIDENCE / "reference_portraits"
CORE = "data/mods/core_2/"
PARTS = CORE + "portraits/portrait_parts.json"
RESTRICTIONS = CORE + "portraits/restrictions.json"
CHARACTER = CORE + "character.json"
DOC = "data/docs/index.html"
SOURCE_FILES = [("aseprite/aseprite", "src/app/doc_exporter.cpp", "doc_exporter.cpp"),
                ("aseprite/aseprite", "src/doc/blend_mode.cpp", "blend_mode.cpp"),
                ("aseprite/api", "api/layer.md", "layer.md")]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Soulash2-Portrait-Format-Audit"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def fetch_sources():
    folder = OUTPUT / "official_sources"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder / "manifest.json"
    if manifest.exists():
        raise SystemExit("이미 고정한 공식 출처를 덮어쓰지 않습니다.")
    records = []
    for repository, source_path, name in SOURCE_FILES:
        metadata_url = f"https://api.github.com/repos/{repository}/commits?path={source_path}&per_page=1"
        commit = json.loads(get(metadata_url))[0]["sha"]
        url = f"https://raw.githubusercontent.com/{repository}/{commit}/{source_path}"
        raw = get(url)
        path = folder / name
        with path.open("xb") as stream:
            stream.write(raw)
        records.append({"repository": repository, "commit": commit, "source_path": source_path, "url": url,
                        "github_url": f"https://github.com/{repository}/blob/{commit}/{source_path}",
                        "local_file": name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"sources": records}, ensure_ascii=True))


def read_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


class Pairs(list):
    """JSON 객체의 중복 속성을 지우지 않는다."""


def get_unique(obj, name):
    values = [value for key, value in obj if key == name]
    if len(values) != 1:
        raise ValueError("유일한 JSON 속성이 아님: " + name)
    return values[0]


def resolve_occurrence(obj, steps):
    for step in steps:
        if "index" in step:
            if isinstance(obj, Pairs):
                raise ValueError("배열 위치가 객체를 가리킴")
            obj = obj[step["index"]]
        else:
            ordinal = step["pair_ordinal"]
            if not isinstance(obj, Pairs) or obj[ordinal][0] != step["key"]:
                raise ValueError("JSON 속성 위치 불일치")
            count = sum(key == step["key"] for key, _ in obj[:ordinal + 1])
            if count != step["occurrence"]:
                raise ValueError("JSON 속성 등장 횟수 불일치")
            obj = obj[ordinal][1]
    return obj


def resolve_pointer(obj, pointer):
    for part in pointer.lstrip("/").split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        obj = obj[int(key)] if isinstance(obj, list) else obj[key]
    return obj


def audit():
    started = datetime.now(timezone.utc).isoformat()
    manifest_path = OUTPUT / "official_sources/manifest.json"
    official = json.loads(manifest_path.read_text(encoding="utf-8"))
    official_by_name, source_lines = {}, {}
    for item in official:
        path = manifest_path.parent / item["local_file"]
        if digest(path) != item["sha256"]:
            raise ValueError("공식 출처 지문 불일치: " + path.name)
        official_by_name[path.name] = item
        source_lines[path.name] = path.read_text(encoding="utf-8").splitlines()
    baseline_path = EVIDENCE / "baseline_manifest.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    expected = {row["path"]: row["sha256"] for row in baseline["files"]}
    checked = {}

    def verified(relative):
        path = SOURCE / relative
        if relative not in checked:
            checked[relative] = digest(path)
            if checked[relative] != expected[relative]:
                raise ValueError("원본 지문 불일치: " + relative)
        return path

    parts_pairs = json.loads(verified(PARTS).read_text(encoding="utf-8"), object_pairs_hook=Pairs)
    parts = json.loads(verified(PARTS).read_text(encoding="utf-8"))
    restrictions = json.loads(verified(RESTRICTIONS).read_text(encoding="utf-8"))
    character = json.loads(verified(CHARACTER).read_text(encoding="utf-8"))
    doc = verified(DOC).read_text(encoding="utf-8").splitlines()
    raw_input = EVIDENCE / "reference_v2/classification_reference_unresolved_v2.jsonl"
    rows = [row for row in read_jsonl(raw_input) if row["file"].startswith(CORE + "portraits/")]
    selected = {row["location_id"] for row in rows}
    original_rows = {row["location_id"]: row for row in read_jsonl(EVIDENCE / "json_strings.jsonl") if row["location_id"] in selected}
    if len(original_rows) != len(rows):
        raise ValueError("원시 위치 목록의 누락 또는 중복")
    doc_evidence = json.loads((EVIDENCE / "reference_v2/documentation_evidence_v2.json").read_text(encoding="utf-8"))
    for item in doc_evidence.values():
        if item["file"] == DOC and item["file_sha256"] != expected[DOC]:
            raise ValueError("동봉 문서 증거의 지문 불일치")

    def official_evidence(name, anchor, before=0, after=0):
        lines = source_lines[name]
        matches = [i for i, line in enumerate(lines) if anchor in line]
        if len(matches) != 1:
            raise ValueError("공식 코드 근거를 유일하게 찾지 못함: " + anchor)
        index = matches[0]
        item = official_by_name[name]
        return {"kind": "official_source", "url": item["github_url"], "commit": item["commit"],
                "source_sha256": item["sha256"], "line_start": max(1, index + 1 - before),
                "line_end": min(len(lines), index + 1 + after), "anchor": anchor}

    def local_evidence(relative, pointer, value=None):
        item = {"kind": "local_structure", "file": relative, "source_sha256": expected[relative], "field_path": pointer}
        if value is not None:
            item["value"] = value
        return item

    def documented(key):
        item = doc_evidence[key]
        return {"kind": "shipped_documentation", "file": item["file"], "source_sha256": item["file_sha256"],
                "line_start": item["line_start"], "line_end": item["line_end"]}

    exporter_blend = official_evidence("doc_exporter.cpp", "<< blend_mode_to_string(layerImg->blendMode())", 2, 3)
    exporter_color = official_evidence("doc_exporter.cpp", "doc::color_t color = data.color();", 2, 10)
    exporter_layers = official_evidence("doc_exporter.cpp", "// meta.layers", 0, 56)
    api_color = official_evidence("layer.md", "## Layer.color", 0, 8)
    api_data = official_evidence("layer.md", "## Layer.data", 0, 8)
    normal = official_evidence("blend_mode.cpp", '"normal"', 1, 1)
    metadata_export = official_evidence("doc_exporter.cpp", '// "meta" property', 0, 16)
    layer_groups = defaultdict(list)
    for index, layer in enumerate(parts["meta"]["layers"]):
        if "group" in layer:
            layer_groups[layer["group"]].append(index)
    age_definitions = defaultdict(list)
    for index, race in enumerate(character["races"]):
        for age, threshold in race.get("ages", {}).items():
            age_definitions[age].append((index, threshold))
    definitions = {}
    for row in read_jsonl(EVIDENCE / "classification_reference_definitions.jsonl"):
        if row["namespace"] in {"entities", "races"}:
            definitions[(row["namespace"], row["canonical_id"])] = row["definitions"]
    counts, rules, unresolved = Counter(), Counter(), []
    out_file = OUTPUT / "classification_portrait_overlay.jsonl"
    if out_file.exists():
        raise ValueError("기존 초상화 판정을 덮어쓰지 않습니다.")
    with out_file.open("x", encoding="utf-8") as stream:
        for row in rows:
            original = original_rows[row["location_id"]]
            actual = resolve_occurrence(parts_pairs, original["occurrence_path"]) if "occurrence_path" in original else resolve_pointer(restrictions, row["field_path"])
            if actual != row["source"] or row["source_file_sha256"] != expected[row["file"]] or hashlib.sha256(actual.encode("utf-8")).hexdigest() != row["source_value_sha256"]:
                raise ValueError("위치별 원본 값 또는 지문 불일치: " + row["location_id"])
            result = {key: row[key] for key in ("location_id", "file", "field_path", "field_pattern", "source", "source_file_sha256", "source_value_sha256")}
            if "occurrence_path" in original:
                result["occurrence_path"] = original["occurrence_path"]
            result.update({"previous_classification": "UNKNOWN", "classification": "UNKNOWN", "runtime_observed": False,
                           "evidence_kind": "static_structure_and_official_format", "evidence": [], "rule": "unresolved"})
            field, value = row["field_pattern"], row["source"]
            if field == "/meta/layers/*/blendMode" and value == "normal":
                result.update(classification="INTERNAL", rule="aseprite_blend_mode", reason="Aseprite 레이어 합성 enum 값. 표시 문장이 아닌 normal 합성 모드 코드.", evidence=[exporter_blend, normal])
            elif field == "/meta/layers/*/color" and re.fullmatch(r"#[0-9a-fA-F]{8}", value):
                result.update(classification="INTERNAL", rule="aseprite_layer_userdata_color", reason="Aseprite 타임라인 레이어의 사용자 지정 표시색을 RGBA 16진수로 직렬화한 메타데이터. 게임 팔레트 참조로 단정하지 않음.", evidence=[exporter_color, exporter_layers, api_color])
            elif field == "/meta/layers/*/name" and layer_groups.get(value):
                references = [local_evidence(PARTS, f"/meta/layers/{index}/group", value) for index in layer_groups[value]]
                result.update(classification="INTERNAL", rule="aseprite_parent_group_identity", reason="같은 내보내기 목록의 group 필드가 실제로 참조하는 부모 레이어 식별자.", evidence=[exporter_layers, documented("portrait_groups"), *references])
            elif field == "/meta/layers/*/name" and value in restrictions["restrictions"]:
                result.update(classification="INTERNAL", rule="portrait_restriction_part_identity", reason="게임 초상화 제한 표의 실제 키와 연결되는 부분 식별자. 중복 레이어 이름 문제는 이 판정으로 해소하지 않음.", evidence=[documented("generated_restrictions"), documented("layer_names"), local_evidence(RESTRICTIONS, "/restrictions/" + value.replace("~", "~0").replace("/", "~1"))])
            elif field in {"/meta/app", "/meta/version", "/meta/image", "/meta/format", "/meta/scale"}:
                valid = {"/meta/app": value == "https://www.aseprite.org/", "/meta/version": bool(re.fullmatch(r"[0-9.]+-x64", value)),
                         "/meta/image": value.endswith(".png"), "/meta/format": value == "RGBA8888", "/meta/scale": value == "1"}[field]
                if valid:
                    result.update(classification="INTERNAL", rule="aseprite_export_provenance", reason="Aseprite 내보내기 프로그램·버전·출력 이미지 파일명·픽셀 형식·배율 메타데이터.", evidence=[metadata_export, documented("export_paths")])
            elif "/ages/" in field and value in age_definitions:
                references = [local_evidence(CHARACTER, f"/races/{index}/ages/{value}", threshold) for index, threshold in age_definitions[value]]
                result.update(classification="INTERNAL", rule="portrait_age_threshold_key", reason="동봉 문서의 초상화 ages 조건 구조이며 character.races.ages의 실제 연령 단계 키와 연결됨.", evidence=[documented("portrait_age_keys"), *references])
            elif field == "/meta/layers/*/data":
                result.update(rule="aseprite_freeform_userdata_unknown", reason="Aseprite 사용자 지정 자유 텍스트. 게임 화면 표시·소비 코드 미확인으로 UNKNOWN 유지.", evidence=[api_data, exporter_color])
            elif "/entities/" in field or field.endswith("/apply_on_race_transform"):
                namespace = "entities" if "/entities/" in field else "races"
                key = value[len("core_2_"):] if value.startswith("core_2_") else value
                targets = definitions.get((namespace, key), [])
                for target in targets:
                    verified(target["file"])
                result.update(rule="portrait_undocumented_condition", reason="정의 ID의 일치는 조사 힌트이지만 해당 제한 필드의 소비 규칙 근거가 없어 UNKNOWN 유지.",
                              definition_hints=targets, evidence=[documented("portrait_restrictions")])
            if not result.get("reason"):
                result["reason"] = "허용한 공식 구조·참조 근거에 일치하지 않아 UNKNOWN 유지."
            counts[result["classification"]] += 1
            rules[result["rule"]] += 1
            if result["classification"] == "UNKNOWN":
                unresolved.append(result)
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
    unresolved_path = OUTPUT / "classification_portrait_unresolved.jsonl"
    with unresolved_path.open("x", encoding="utf-8") as stream:
        for row in unresolved:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    report = {"game_id": "SOULASH_2", "build_id": BUILD, "check_id": "G2_PORTRAIT_FORMAT_OVERLAY", "status": "PASS",
              "scope": "초상화 UNKNOWN의 공식 내보내기 형식·파일 위치·명시적 참조 판정", "g2_status": "NOT_RUN", "started": started,
              "finished": datetime.now(timezone.utc).isoformat(), "tool_sha256": digest(__file__), "command": sys.argv,
              "baseline_manifest_sha256": digest(baseline_path), "input_sha256": digest(raw_input), "official_source_manifest_sha256": digest(manifest_path),
              "rows": len(rows), "counts": dict(counts), "rules": dict(rules), "checked_source_files": checked,
              "outputs": {out_file.name: digest(out_file), unresolved_path.name: digest(unresolved_path)},
              "limitations": ["Aseprite 내보내기 형식의 증거이며 Soulash 2 실행 관찰 아님", "레이어 color는 Aseprite 타임라인 사용자 색. 게임의 팔레트로 사용된다는 뜻 아님", "자유 텍스트 data와 문서화되지 않은 entities/apply_on_race_transform 조건은 UNKNOWN 유지", "원본의 중복 frames 키·중복 레이어 식별자 로딩 문제는 이 판정으로 해결하지 않음", "기존 인벤토리·번역·후보는 수정하지 않음"]}
    (OUTPUT / "portrait_audit_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(rows), "counts": dict(counts), "rules": dict(rules), "summary": str(OUTPUT / "portrait_audit_summary.json")}, ensure_ascii=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-sources", action="store_true")
    args = parser.parse_args()
    if args.fetch_sources:
        fetch_sources()
    else:
        audit()


if __name__ == "__main__":
    main()
