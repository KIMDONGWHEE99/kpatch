"""생성기를 가져오지 않고 원문·입력 번역에서 기대값을 다시 계산하는 독립 G4 검사."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

from soulash2_validate_text import validate_pair

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("중복 속성")
        result[key] = value
    return result


def safe(base, rel):
    if not isinstance(rel, str) or not rel or ":" in rel or "\\" in rel:
        raise ValueError("파일 경로 오류")
    if PurePosixPath(rel).is_absolute() or str(PurePosixPath(rel)) != rel or any(p in (".", "..") for p in rel.split("/")):
        raise ValueError("경로 정규 형식 오류")
    path = (base / rel).resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError("허용 경로 이탈")
    return path


def walk(value, pointer=""):
    if isinstance(value, dict):
        yield pointer, ("object", tuple(value))
        for key, child in value.items():
            yield from walk(child, pointer + "/" + key.replace("~", "~0").replace("/", "~1"))
    elif isinstance(value, list):
        yield pointer, ("array", len(value))
        for index, child in enumerate(value):
            yield from walk(child, pointer + "/" + str(index))
    else:
        yield pointer, (type(value).__name__, value)


def split_text(data):
    lines = data.decode("utf-8-sig").splitlines(keepends=True)
    output = []
    for line in lines:
        suffix = "\r\n" if line.endswith("\r\n") else line[-1:] if line.endswith(("\r", "\n")) else ""
        output.append((line[:-len(suffix)] if suffix else line, suffix))
    return output


def verify(candidate):
    candidate = candidate.resolve()
    if not candidate.is_relative_to(ROOT / "build_candidate/SOULASH_2") and not candidate.is_relative_to(ROOT / "working_private/SOULASH_2/complete_stage_selftest"):
        raise ValueError("후보 경계 오류")
    snapshots, failures = {}, []

    def blob(path):
        path = path.resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError("입력 경계 오류")
        if path not in snapshots:
            snapshots[path] = path.read_bytes()
        return snapshots[path]

    def document(path):
        return json.loads(blob(path).decode("utf-8-sig"), object_pairs_hook=unique)

    def rows(path):
        return [json.loads(line, object_pairs_hook=unique) for line in blob(path).decode("utf-8-sig").splitlines() if line.strip()]

    def checked(record):
        path = safe(ROOT, record["path"])
        if sha(blob(path)) != record["sha256"]:
            raise ValueError("입력 지문 변경: " + record["path"])
        return path

    report = document(candidate / "stage_report.json")
    if report.get("schema_version") != 1 or report.get("game_id") != "SOULASH_2" or report.get("steam_build") != "25967323":
        raise ValueError("생성 보고서 식별 오류")
    source = safe(ROOT, report["source_root"])
    synthetic = source != SOURCE.resolve()
    if synthetic and not source.is_relative_to(ROOT / "working_private/SOULASH_2/complete_stage_selftest"):
        raise ValueError("원본 경계 오류")
    if report.get("synthetic_fixture") != synthetic:
        raise ValueError("시험 여부 식별 오류")
    for key in ("tool", "validator"):
        checked(report[key])
    declared_paths = set()
    for rec in report["inputs"]:
        path = checked(rec)
        if path in declared_paths:
            raise ValueError("입력 지문 목록 중복")
        declared_paths.add(path)
    entries = {}
    for row in rows(checked(report["inventory"])):
        loc = row.get("location_id")
        if not isinstance(loc, str) or not loc or loc in entries:
            raise ValueError("조사 목록 중복·누락 위치")
        for evidence in row.get("roster_evidence", []):
            checked(evidence)
        entries[loc] = row

    def same_source(row, partial=False):
        loc = row.get("location_id")
        if loc not in entries:
            raise ValueError("조사 목록 밖의 입력")
        original = entries[loc]
        for key in ("file", "field_path", "line", "source", "source_file_sha256", "source_value_sha256"):
            if (not partial or key in row) and row.get(key) != original.get(key):
                raise ValueError("입력 원문 위치 불일치: " + str(loc))
        return original

    selected = {}
    for kind in ("batches", "overrides"):
        seen_paths = set()
        for rec in report[kind]:
            path = checked(rec)
            if path in seen_paths:
                raise ValueError("번역 파일 중복")
            seen_paths.add(path)
            local_seen = set()
            for row in rows(path):
                same_source(row)
                loc = row["location_id"]
                if loc in local_seen or (kind == "batches" and loc in selected):
                    raise ValueError("번역 위치 중복")
                local_seen.add(loc)
                if "previous_target" in row and loc in selected and row["previous_target"] != selected[loc].get("target"):
                    raise ValueError("교정 전 번역 불일치")
                if "previous_target_sha256" in row and sha(str(row.get("previous_target", "")).encode("utf-8")) != row["previous_target_sha256"]:
                    raise ValueError("교정 전 번역 지문 오류")
                selected[loc] = row
    held, decisions = set(), {}
    for kind in ("holds", "resolutions"):
        seen_paths = set()
        for rec in report[kind]:
            path = checked(rec)
            if path in seen_paths:
                raise ValueError("판정 파일 중복")
            seen_paths.add(path)
            for row in rows(path):
                original = same_source(row, partial=True)
                if any(row.get(k) != original.get(k) for k in ("source_file_sha256", "source_value_sha256")):
                    raise ValueError("판정 원문 지문 오류")
                if not isinstance(row.get("reason"), str) or not row["reason"].strip():
                    raise ValueError("판정 사유 없음")
                checked({"path": row["evidence_path"], "sha256": row["evidence_sha256"]})
                loc = row["location_id"]
                if kind == "holds":
                    if loc in held:
                        raise ValueError("보류 중복")
                    held.add(loc)
                else:
                    if loc in decisions or row.get("classification") not in ("VISIBLE_TRANSLATE", "VISIBLE_KEEP", "INTERNAL"):
                        raise ValueError("해결 중복·분류 오류")
                    decisions[loc] = row

    sources, original_trees = {}, {}
    for loc, row in entries.items():
        relative = row["file"]
        data = blob(safe(source, relative))
        sources[relative] = data
        if sha(data) != row["source_file_sha256"] or sha(row["source"].encode("utf-8")) != row["source_value_sha256"]:
            raise ValueError("실제 원문 지문 불일치")
        if relative not in original_trees:
            original_trees[relative] = dict(walk(json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique))) if relative.endswith(".json") else split_text(data)
        original = original_trees[relative]
        if relative.endswith(".json"):
            field = row.get("field_path")
            if loc != relative + "#" + str(field) or original.get(field) != ("str", row["source"]):
                raise ValueError("실제 JSON 위치 값 불일치")
        elif relative.endswith(".txt"):
            line = row.get("line")
            if type(line) is not int or not 1 <= line <= len(original) or loc != relative + "#line/" + str(line) or original[line - 1][0] != row["source"]:
                raise ValueError("실제 TXT 위치 값 불일치")
        else:
            raise ValueError("미지원 원문 형식")

    expected, missing, unresolved, grouped = {}, [], [], defaultdict(dict)
    for loc, row in entries.items():
        decision = decisions.get(loc)
        chosen = decision if decision is not None else selected.get(loc)
        if chosen is None:
            missing.append(loc)
            continue
        target = chosen.get("target")
        if not isinstance(target, str) or not target:
            raise ValueError("빈 기대 번역")
        field = row.get("field_path", "")
        if decision is None and (loc in held or target == row["source"] or (field.startswith("/ability/") and field.endswith(("/success", "/fail")) and row["source"] in ("none", "none."))):
            unresolved.append(loc)
            continue
        classification = decision["classification"] if decision is not None else "VISIBLE_TRANSLATE"
        if classification in ("INTERNAL", "VISIBLE_KEEP"):
            if target != row["source"]:
                raise ValueError("유지 판정 원문 변경")
        elif target == row["source"] or not validate_pair(row["source"], target)["passed"]:
            raise ValueError("기대 번역 구조 또는 원문 잔존 오류")
        expected[loc] = {**row, "target": target, "classification": classification}
        grouped[row["file"]][field if row["file"].endswith(".json") else row["line"]] = target

    canonical = rows(candidate / "canonical.jsonl")
    if [row.get("location_id") for row in canonical] != list(expected):
        failures.append({"reason": "통합 목록 위치·순서·개수 불일치"})
    for row in canonical:
        loc = row.get("location_id")
        original = expected.get(loc)
        if original is None or any(row.get(k) != original.get(k) for k in ("file", "field_path", "line", "source", "source_file_sha256", "source_value_sha256", "target", "classification")):
            failures.append({"reason": "통합 목록 기대값 불일치", "location_id": loc})
    actual_holds = rows(candidate / "holds.jsonl")
    if [row.get("location_id") for row in actual_holds] != unresolved:
        failures.append({"reason": "보류 목록 불일치"})
    if document(candidate / "missing.json") != missing:
        failures.append({"reason": "누락 목록 불일치"})
    counts = {"inventory_rows": len(entries), "submitted_rows": len(set(selected) | set(decisions)), "accepted_rows": len(expected), "held_rows": len(unresolved), "missing_rows": len(missing), "unresolved_total": len(missing) + len(unresolved), "changed_rows": sum(row["target"] != row["source"] for row in expected.values())}
    for key, value in counts.items():
        if report.get(key) != value:
            failures.append({"reason": "생성 보고서 개수 불일치", "field": key})
    for name, field in (("canonical.jsonl", "canonical_sha256"), ("holds.jsonl", "holds_sha256"), ("missing.json", "missing_sha256")):
        if sha(blob(candidate / name)) != report.get(field):
            failures.append({"reason": "생성 산출물 지문 불일치", "file": name})
    payload = candidate / "payload"
    actual_files = {path.relative_to(payload).as_posix() for path in payload.rglob("*") if path.is_file()} if payload.exists() else set()
    if actual_files != set(grouped):
        failures.append({"reason": "후보 파일 누락·추가", "missing": sorted(set(grouped) - actual_files), "extra": sorted(actual_files - set(grouped))})
    report_files = {row["file"]: row for row in report["files"]}
    if len(report_files) != len(report["files"]) or set(report_files) != set(grouped):
        failures.append({"reason": "생성 파일 목록 불일치"})
    checked_files = []
    for relative in sorted(actual_files & set(grouped)):
        data = blob(safe(payload, relative))
        old = original_trees[relative]
        required = grouped[relative]
        differences = []
        if relative.endswith(".json"):
            new = dict(walk(json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique)))
            for field in set(old) | set(new):
                target = ("str", required[field]) if field in required else old.get(field)
                if field not in old or field not in new or new[field] != target:
                    differences.append(field)
        else:
            new = split_text(data)
            if len(new) != len(old):
                differences.append("line_count")
            if data.startswith(b"\xef\xbb\xbf") != sources[relative].startswith(b"\xef\xbb\xbf"):
                differences.append("BOM")
            for i in range(max(len(old), len(new))):
                target = (required.get(i + 1, old[i][0]), old[i][1]) if i < len(old) else None
                if i >= len(new) or new[i] != target:
                    differences.append("line/" + str(i + 1))
        metadata = report_files.get(relative, {})
        if metadata.get("candidate_sha256") != sha(data) or metadata.get("source_sha256") != sha(sources[relative]) or metadata.get("size") != len(data) or metadata.get("locations") != len(required):
            differences.append("file_manifest")
        if differences:
            failures.append({"reason": "원문 전체 구조·기대 번역 경계 불일치", "file": relative, "locations": differences[:100], "difference_count": len(differences)})
        checked_files.append({"file": relative, "sha256": sha(data), "status": "FAIL" if differences else "PASS"})
    complete = not missing and not unresolved
    if report.get("status") != ("PASS" if complete else "FAIL") or report.get("release_ready") is not False or report.get("scope") != "DECLARED_ROSTER_JSON_TXT_ONLY":
        failures.append({"reason": "통과 범위 또는 배포 선언 오류"})
    # 원문·근거·번역·검사 도구를 포함한 모든 재독립 입력을 고정한다.
    blob(Path(__file__))
    for path, data in list(snapshots.items()):
        if path.read_bytes() != data:
            failures.append({"reason": "검사 중 입력 변경", "file": path.relative_to(ROOT).as_posix()})
    if not complete:
        failures.append({"reason": "로스터에 미해결 위치가 남음", "missing": len(missing), "held": len(unresolved)})
    result = {"schema_version": 1, "game_id": "SOULASH_2", "steam_build": "25967323", "status": "PASS" if not failures else "FAIL", "roster_g4_status": "PASS" if not failures else "FAIL", "scope": "DECLARED_ROSTER_JSON_TXT_ONLY", "synthetic_fixture": synthetic, "g2_status": "NOT_RUN", "g5_status": "NOT_RUN", "release_ready": False,
              **counts, "failures": failures, "files": checked_files, "stage_report_sha256": sha(blob(candidate / "stage_report.json")), "inputs": [{"path": path.relative_to(ROOT).as_posix(), "sha256": sha(data)} for path, data in sorted(snapshots.items())]}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.candidate)
    except (ValueError, KeyError, OSError, TypeError) as error:
        result = {"status": "FAIL", "roster_g4_status": "FAIL", "scope": "DECLARED_ROSTER_JSON_TXT_ONLY", "release_ready": False, "failures": [{"reason": str(error)}]}
    (args.candidate / "independent_validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "roster_g4_status", "scope")}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
