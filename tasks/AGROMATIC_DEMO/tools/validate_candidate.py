"""실제 PCK를 다시 추출·복원하여 위치별 기대 번역을 독립 검증합니다."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

from pck_tools import read_pack
from validator import ROOT, WORK, save, sha, validate_text, synthetic_tests


GDRE = ROOT / "tools/gdre_2.6.4/bin/gdre_tools.exe"
RESOURCE_CONVERTER = Path(__file__).with_name("validate_resources.gd")
FIELD = re.compile(r'^([\w/]+)\s*=\s*("(?:\\.|[^"\\])*")', re.M | re.S)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_relative(name: str) -> str:
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("잘못된 논리 경로")
    parsed = PurePosixPath(name)
    if parsed.is_absolute() or any(part in ("", ".", "..") for part in name.split("/")) or ":" in name:
        raise ValueError("논리 경로는 안전한 상대 경로여야 합니다: " + name)
    return name


def script_literals(text: str) -> list[dict]:
    """주석을 제외한 GDScript 문자열을 등장 순서대로 읽습니다."""
    output, i = [], 0
    while i < len(text):
        char = text[i]
        if char == "#":
            end = text.find("\n", i)
            i = len(text) if end < 0 else end + 1
            continue
        if char not in ("'", '"'):
            i += 1
            continue
        start = i
        quote = char * 3 if text.startswith(char * 3, i) else char
        i += len(quote)
        inner = i
        while i < len(text):
            if text[i] == "\\":
                i += 2
                continue
            if text.startswith(quote, i):
                break
            i += 1
        if i >= len(text):
            raise ValueError("끝나지 않은 스크립트 문자열: " + str(start))
        raw = text[inner:i]
        end = i + len(quote)
        try:
            value = json.loads(text[start:end]) if quote == '"' else decode_godot(raw)
        except (ValueError, json.JSONDecodeError):
            value = decode_godot(raw)
        output.append({"start": start, "end": end, "text": value, "literal": text[start:end]})
        i = end
    return output


def decode_godot(raw: str) -> str:
    # 원본 감사의 토큰 판독 규칙과 같은 기본 이스케이프를 읽습니다.
    return raw.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r").replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")


def script_code_tokens(text: str) -> list:
    """공백·주석만 제외하며 문자열의 값과 모든 동작 코드를 대조합니다."""
    literals = {token["start"]: token for token in script_literals(text)}
    result, position = [], 0
    while position < len(text):
        if position in literals:
            token = literals[position]
            result.append(["string", token["text"]])
            position = token["end"]
        elif text[position] == "#":
            end = text.find("\n", position)
            position = len(text) if end < 0 else end + 1
        elif text[position].isspace():
            position += 1
        else:
            result.append(text[position])
            position += 1
    return result


def compare_script_sources(manifest_path: Path, candidate: dict, pack: dict) -> dict:
    """독립 재복원본 전체를 빌드에서 승인한 소스 해시·코드와 대조합니다."""
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(expected, dict) or not expected:
        raise ValueError("스크립트 소스 해시 명세가 비었습니다.")
    errors, results = [], []
    for name, expected_sha in expected.items():
        name = safe_relative(name)
        source = manifest_path.parent / "script_build/sources" / name
        pack_path = resolve_pack_path(pack, name)
        if sha(source) != expected_sha:
            errors.append({"path": name, "kind": "approved_source_hash"})
        restored = Path(candidate[pack_path]["restored"])
        before = script_code_tokens(source.read_text(encoding="utf-8-sig"))
        after = script_code_tokens(restored.read_text(encoding="utf-8-sig"))
        equal = before == after
        if not equal:
            errors.append({"path": name, "kind": "full_script_structure", "expected_tokens": len(before), "actual_tokens": len(after)})
        results.append({"path": name, "approved_source_sha256": expected_sha, "restored_sha256": sha(restored),
                        "status": "PASS" if equal else "FAIL"})
    return {"status": "FAIL" if errors else "PASS", "scripts": len(expected), "errors": errors,
            "manifest_sha256": sha(manifest_path), "results": results}


def resource_fields(text: str) -> dict[str, list[str]]:
    values = defaultdict(list)
    for match in FIELD.finditer(text):
        values[match[1]].append(json.loads(match[2], strict=False))
    return dict(values)


def json_strings(value) -> int:
    if isinstance(value, dict):
        return sum(json_strings(child) for child in value.values())
    if isinstance(value, list):
        return sum(json_strings(child) for child in value)
    return int(isinstance(value, str))


def resolve_pack_path(pack: dict, path: str) -> str:
    path = safe_relative(path.removeprefix("recovered/"))
    entries = pack["entries"]
    if path in entries:
        return path
    if path.endswith(".gd") and path[:-3] + ".gdc" in entries:
        return path[:-3] + ".gdc"
    remap = entries.get(path + ".remap")
    if remap:
        match = re.search(r'\bpath\s*=\s*"res://([^"]+)"', remap["data"].decode("utf-8"))
        if match and match[1] in entries:
            return safe_relative(match[1])
    raise KeyError("PCK에 자산이 없습니다: " + path)


def run_gdre(arguments: list[str], stage: Path, label: str) -> None:
    runtime = stage / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["APPDATA"] = str(runtime / "roaming")
    environment["LOCALAPPDATA"] = str(runtime / "local")
    command = [str(GDRE), "--headless", *arguments]
    result = subprocess.run(command, env=environment, cwd=ROOT, capture_output=True, timeout=600)
    (runtime / (label + ".stdout.log")).write_bytes(result.stdout)
    (runtime / (label + ".stderr.log")).write_bytes(result.stderr)
    save(runtime / (label + ".command.json"), {"command": command, "exit_code": result.returncode, "tool_sha256": sha(GDRE)})
    if result.returncode:
        raise ValueError("GDRE 복원 실패: " + label)


def restore_assets(pack: dict, paths: set[str], stage: Path) -> dict[str, dict]:
    """실제 컨테이너에서 가져온 바이트만 새 폴더에 쓰고 다시 복원합니다."""
    observations, scripts, resources = {}, defaultdict(list), []
    for path in sorted(paths):
        data = pack["entries"][path]["data"]
        raw = stage / "raw" / path
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(data)
        suffix = Path(path).suffix
        observed = {"sha256": digest(data), "raw": str(raw), "kind": "binary"}
        if suffix == ".gdc":
            output = stage / "restored" / Path(path).with_suffix(".gd")
            output.parent.mkdir(parents=True, exist_ok=True)
            scripts[str(Path(path).parent)].append((path, raw, output))
            observed.update(kind="script", restored=str(output))
        elif suffix in {".scn", ".res"}:
            output = stage / "restored" / Path(path).with_suffix(".tscn" if suffix == ".scn" else ".tres")
            output.parent.mkdir(parents=True, exist_ok=True)
            resources.append({"source": str(raw), "output": str(output)})
            observed.update(kind="resource", restored=str(output))
        elif suffix in {".gd", ".tscn", ".tres"}:
            observed.update(kind="script" if suffix == ".gd" else "resource", restored=str(raw))
        elif suffix == ".json":
            observed.update(kind="json", value=json.loads(data.decode("utf-8-sig")))
        observations[path] = observed
    for index, group in enumerate(scripts.values()):
        run_gdre(["--decompile=" + str(raw) for _, raw, _ in group] +
                 ["--bytecode=4.6.2", "--output=" + str(group[0][2].parent)], stage, "decompile_" + str(index))
    if resources:
        config = stage / "resources_config.json"
        save(config, {"entries": resources, "report": str(stage / "resources_report.json")})
        run_gdre(["--path", str(stage / "runtime"), "--script", str(RESOURCE_CONVERTER), "--", str(config)], stage, "resources_to_text")
        report = json.loads((stage / "resources_report.json").read_text(encoding="utf-8"))
        if len(report) != len(resources) or any(row.get("error") != 0 for row in report):
            raise ValueError("장면·자원 복원 결과 불일치")
    for path, observed in observations.items():
        if observed["kind"] in {"script", "resource"}:
            data = Path(observed["restored"]).read_bytes()
            text = data.decode("utf-8-sig")
            observed["restored_sha256"] = digest(data)
            observed["value"] = script_literals(text) if observed["kind"] == "script" else resource_fields(text)
        if observed["kind"] == "script":
            observed["string_count"] = len(observed["value"])
        elif observed["kind"] == "resource":
            observed["string_count"] = sum(map(len, observed["value"].values()))
        elif observed["kind"] == "json":
            observed["string_count"] = json_strings(observed["value"])
    return observations


def select_value(observed: dict, row: dict):
    selector, kind = row["selector"], row["kind"]
    if observed["kind"] != kind:
        raise ValueError("자산 종류 불일치")
    if row.get("expected_count", 1) != 1:
        raise ValueError("단일 위치 selector의 expected_count는 1이어야 합니다.")
    if kind == "json":
        value = observed["value"]
        for part in selector["pointer"]:
            if isinstance(value, list):
                if not isinstance(part, int) or isinstance(part, bool) or part < 0:
                    raise ValueError("JSON 배열 위치는 0 이상의 정수여야 합니다.")
            elif not isinstance(value, dict) or not isinstance(part, str):
                raise ValueError("JSON 객체 위치는 문자열 키여야 합니다.")
            value = value[part]
        return value
    ordinal = selector["ordinal"]
    if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0:
        raise ValueError("문자열 순번이 잘못되었습니다.")
    if kind == "script":
        return observed["value"][ordinal]["text"]
    if kind == "resource":
        field_values = observed["value"].get(selector["field"], [])
        if "field_count" in selector and len(field_values) != selector["field_count"]:
            raise ValueError("자원 필드 문자열 개수 불일치")
        return field_values[ordinal]
    raise ValueError("미지원 위치 종류")


def compare_locations(rows: list[dict], original: dict, candidate: dict,
                      path_map: dict[str, tuple[str, str]], asset_expectations: list[dict] | None = None) -> dict:
    errors, results, seen_ids, seen_selectors = [], [], set(), set()
    for row in rows:
        location_id = row.get("location_id")
        try:
            if not location_id or location_id in seen_ids:
                raise ValueError("위치 ID 누락·중복")
            seen_ids.add(location_id)
            signature = (row["path"], row["kind"], json.dumps(row["selector"], sort_keys=True, ensure_ascii=False))
            if signature in seen_selectors:
                raise ValueError("동일 위치 selector 중복")
            seen_selectors.add(signature)
            source_path, target_path = path_map[row["path"]]
            source_observed, target_observed = original.get(source_path), candidate[target_path]
            if source_observed is not None and row.get("source_asset_sha256") not in (source_observed["sha256"],source_observed.get("restored_sha256")):
                raise ValueError("원본 자산 SHA-256 불일치")
            if source_observed is None and (row.get('source') is not None or row.get('source_asset_sha256') is not None):
                raise ValueError('추가 자산에 원본 값·해시가 지정됨')
            source_row = dict(row)
            source_row["selector"] = row.get("source_selector", row["selector"])
            # field_count는 후보의 기대 개수이므로 원본은 원본 필드 개수로 별도 검사합니다.
            if "field_count" in source_row["selector"]:
                source_row["selector"] = {k: v for k, v in source_row["selector"].items() if k != "field_count"}
            before = select_value(source_observed, source_row) if source_observed is not None else None
            actual = select_value(target_observed, row)
            if before != row["source"]:
                errors.append({"location_id": location_id, "kind": "source_value", "expected": row["source"], "actual": before})
            if actual != row["target"]:
                errors.append({"location_id": location_id, "kind": "target_value", "expected": row["target"], "actual": actual})
            if isinstance(row["source"], str) and isinstance(row["target"], str):
                for error in validate_text(row.get("effective_source", row["source"]), row["target"]):
                    errors.append({"location_id": location_id, "kind": "translation_format", "details": error})
            results.append({"location_id": location_id, "source_path": source_path, "candidate_path": target_path,
                            "source": before, "actual": actual, "expected": row["target"],
                            "status": "PASS" if before == row["source"] and actual == row["target"] else "FAIL"})
        except (KeyError, IndexError, TypeError, ValueError) as error:
            errors.append({"location_id": location_id, "kind": "location_missing_or_invalid", "reason": str(error)})
    expectations = {entry["path"]: entry for entry in asset_expectations or []}
    asset_results = []
    for path, (source_path, target_path) in path_map.items():
        before, after = original.get(source_path), candidate[target_path]
        if before is None:
            before={'string_count':0,'sha256':None}
        expectation = expectations.get(path, {})
        expected_before = expectation.get("source_string_count", before["string_count"])
        expected_after = expectation.get("candidate_string_count", before["string_count"])
        if before["string_count"] != expected_before or after["string_count"] != expected_after:
            errors.append({"path": path, "kind": "asset_string_count", "original": before["string_count"],
                           "candidate": after["string_count"], "expected_original": expected_before, "expected_candidate": expected_after})
        if "source_asset_sha256" in expectation and expectation["source_asset_sha256"] not in (before["sha256"],before.get('restored_sha256')):
            errors.append({"path": path, "kind": "asset_source_hash"})
        for field, count in expectation.get("fields", {}).items():
            if after["kind"] != "resource" or len(after["value"].get(field, [])) != count:
                errors.append({"path": path, "kind": "resource_field_count", "field": field, "expected": count})
        asset_results.append({"path": path, "source_path": source_path, "candidate_path": target_path,
                              "source_sha256": before["sha256"], "candidate_sha256": after["sha256"],
                              "source_string_count": before["string_count"], "candidate_string_count": after["string_count"]})
    return {"status": "FAIL" if errors else "PASS", "errors": errors, "locations": results, "assets": asset_results,
            "expected_locations": len(rows), "observed_locations": len(results)}


def location_synthetic_tests() -> dict:
    source = {"a.json": {"kind": "json", "sha256": "source", "string_count": 2, "value": {"left": "A", "right": "B"}}}
    good = {"a.json": {"kind": "json", "sha256": "candidate", "string_count": 2, "value": {"left": "가", "right": "나"}}}
    rows = [{"path": "a.json", "kind": "json", "location_id": field, "source_asset_sha256": "source",
             "source": original, "target": target, "expected_count": 1, "selector": {"pointer": [field]}}
            for field, original, target in (("left", "A", "가"), ("right", "B", "나"))]
    mapping = {"a.json": ("a.json", "a.json")}
    cases = []
    for name, value in {"correct": good, "location_swap": {"a.json": {**good["a.json"], "value": {"left": "나", "right": "가"}}},
                        "empty": {"a.json": {**good["a.json"], "value": {"left": "", "right": "나"}}},
                        "deletion": {"a.json": {**good["a.json"], "value": {"left": "가"}, "string_count": 1}},
                        "count_difference": {"a.json": {**good["a.json"], "value": {"left": "가", "right": "나", "extra": "가"}, "string_count": 3}}}.items():
        observed = compare_locations(rows, source, value, mapping)["status"]
        cases.append({"case": name, "expected": "PASS" if name == "correct" else "FAIL", "observed": observed})
    tag_cases = synthetic_tests()
    cases.extend(tag_cases["cases"])
    return {"status": "PASS" if all(row["expected"] == row["observed"] for row in cases) else "FAIL", "cases": cases}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--assets", type=Path)
    parser.add_argument("--script-sources", type=Path, help="승인된 전체 스크립트 소스 해시 명세도 대조합니다.")
    parser.add_argument("--stage", type=Path, default=WORK / "candidate_validation")
    parser.add_argument("--retry", action="store_true", help="이전 실패 기록을 보존하고 새 하위 폴더에서 다시 복원합니다.")
    parser.add_argument("--synthetic-only", action="store_true")
    args = parser.parse_args()
    tests = location_synthetic_tests()
    if args.synthetic_only:
        print(json.dumps(tests, ensure_ascii=False, indent=2))
        return 0 if tests["status"] == "PASS" else 1
    if not all((args.original, args.candidate, args.manifest)):
        parser.error("--original, --candidate, --manifest가 필요합니다.")
    args.original, args.candidate, args.manifest = (p.resolve() for p in (args.original, args.candidate, args.manifest))
    args.assets = args.assets.resolve() if args.assets else None
    args.script_sources = args.script_sources.resolve() if args.script_sources else None
    args.stage = args.stage.resolve()
    relative = args.stage.resolve().relative_to(ROOT.resolve())
    if not relative.parts or relative.parts[0] not in {"working_private", "extracted_private", "build_candidate"}:
        raise ValueError("복원 폴더는 작업 공간의 비공개 영역이어야 합니다.")
    report_stage = args.stage
    if args.stage.exists():
        previous = args.stage / "report.json"
        if not args.retry or not previous.exists() or json.loads(previous.read_text(encoding="utf-8")).get("status") != "FAIL":
            raise ValueError("이전 실패 기록이 있을 때만 --retry로 새 복원 폴더를 만들 수 있습니다.")
        attempt = 2
        while (report_stage / f"attempt_{attempt:02d}").exists():
            attempt += 1
        save(report_stage / f"failed_report_{attempt - 1:02d}.json", json.loads(previous.read_text(encoding="utf-8")))
        args.stage = report_stage / f"attempt_{attempt:02d}"
    args.stage.mkdir(parents=True)
    report = {"schema": "agromatic.candidate-validation.v1", "status": "FAIL", "synthetic_tests": tests,
              "original_sha256": sha(args.original), "candidate_sha256": sha(args.candidate),
              "manifest_sha256": sha(args.manifest), "validator_sha256": sha(Path(__file__)),
              "assets_manifest_sha256": sha(args.assets) if args.assets else None,
              "script_sources_manifest_sha256": sha(args.script_sources) if args.script_sources else None,
              "restore_stage": str(args.stage),
              "format_validator_sha256": sha(Path(__file__).with_name("validator.py")),
              "resource_converter_sha256": sha(RESOURCE_CONVERTER), "gdre_sha256": sha(GDRE)}
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        rows = manifest if isinstance(manifest, list) else manifest.get("locations", manifest.get("rows"))
        if not isinstance(rows, list) or not rows:
            raise ValueError("기대 위치 배열이 비었습니다.")
        if isinstance(manifest, dict):
            for key in ("original_sha256", "candidate_sha256"):
                if key in manifest and manifest[key] != report[key]:
                    raise ValueError("명세의 컨테이너 해시 불일치: " + key)
        original_pack, candidate_pack = read_pack(args.original), read_pack(args.candidate)
        assets=json.loads(args.assets.read_text(encoding='utf-8')) if args.assets else manifest.get('asset_expectations',[]) if isinstance(manifest,dict) else []
        mapping = {}
        for row in rows+assets:
            logical = safe_relative(row["path"])
            source_hint = row.get("original_path", logical if logical in original_pack["entries"] else row.get("source_path", logical))
            try:
                source_path = resolve_pack_path(original_pack, source_hint)
            except KeyError:
                if row.get('source') is not None or row.get('source_asset_sha256') is not None:
                    raise
                source_path=None
            target_path = resolve_pack_path(candidate_pack, logical)
            pair = (source_path, target_path)
            if logical in mapping and mapping[logical] != pair:
                raise ValueError("같은 자산에 다른 원본 연결이 있습니다: " + logical)
            mapping[logical] = pair
        original = restore_assets(original_pack, {p[0] for p in mapping.values() if p[0] is not None}, args.stage / "original")
        candidate = restore_assets(candidate_pack, {p[1] for p in mapping.values()}, args.stage / "candidate")
        compared = compare_locations(rows, original, candidate, mapping,
                                     assets)
        report.update(compared)
        if args.script_sources:
            full_scripts = compare_script_sources(args.script_sources, candidate, candidate_pack)
            report["full_script_structure"] = full_scripts
            if full_scripts["status"] != "PASS":
                report["errors"].extend(full_scripts["errors"])
                report["status"] = "FAIL"
        if tests["status"] != "PASS":
            report["status"] = "FAIL"
    except Exception as error:
        report["fatal_error"] = str(error)
    save(args.stage / "report.json", report)
    if report_stage != args.stage:
        save(report_stage / "report.json", report)
    print(json.dumps({"status": report["status"], "locations": report.get("observed_locations", 0),
                      "errors": len(report.get("errors", [])), "fatal_error": report.get("fatal_error")}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
