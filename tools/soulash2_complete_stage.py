"""근거가 확정된 JSON·TXT 번역을 합치며 미해결 위치를 전체 통과로 처리하지 않는다."""
import argparse
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

from soulash2_validate_text import validate_pair

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
INVENTORY = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029/effective_inventory/v4/translation_work_v2.jsonl"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("중복 JSON 속성: " + key)
        result[key] = value
    return result


def contained(base, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("잘못된 상대 경로")
    path = PurePosixPath(relative)
    if path.is_absolute() or str(path) != relative or any(p in (".", "..") for p in relative.split("/")):
        raise ValueError("정규 상대 경로가 아님")
    target = (base / relative).resolve()
    if not target.is_relative_to(base.resolve()):
        raise ValueError("경로 경계 이탈")
    return target


def pointer_access(obj, pointer):
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("JSON 위치 오류")
    parts = [p.replace("~1", "/").replace("~0", "~") for p in pointer[1:].split("/")]
    if "/" + "/".join(p.replace("~", "~0").replace("/", "~1") for p in parts) != pointer:
        raise ValueError("JSON 위치가 정규 형식이 아님")
    cursor = obj
    for index, part in enumerate(parts):
        if isinstance(cursor, list):
            if not part.isascii() or not part.isdigit() or str(int(part)) != part or int(part) >= len(cursor):
                raise ValueError("배열 위치 오류")
            key = int(part)
        elif isinstance(cursor, dict) and part in cursor:
            key = part
        else:
            raise ValueError("없는 JSON 위치")
        if index == len(parts) - 1:
            return cursor, key
        cursor = cursor[key]


def line_parts(data):
    text = data.decode("utf-8-sig")
    result = []
    for line in text.splitlines(keepends=True):
        if line.endswith("\r\n"):
            result.append((line[:-2], "\r\n"))
        elif line.endswith(("\r", "\n")):
            result.append((line[:-1], line[-1:]))
        else:
            result.append((line, ""))
    return result


def build(output, inventory=INVENTORY, batches=(), overrides=(), resolutions=(), holds=(), source=SOURCE):
    output, source, inventory = output.resolve(), source.resolve(), inventory.resolve()
    if not output.is_relative_to(ROOT / "build_candidate/SOULASH_2") and not output.is_relative_to(ROOT / "working_private/SOULASH_2/complete_stage_selftest"):
        raise ValueError("후보 출력 경계 오류")
    synthetic = source != SOURCE.resolve()
    if synthetic and not source.is_relative_to(ROOT / "working_private/SOULASH_2/complete_stage_selftest"):
        raise ValueError("시험 원본 경계 오류")
    output.mkdir(parents=True, exist_ok=False)
    snapshots, entries, parsed = {}, {}, {}

    def blob(path):
        path = path.resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError("입력 경로 경계 오류")
        if path not in snapshots:
            snapshots[path] = path.read_bytes()
        return snapshots[path]

    def record(path):
        path = path.resolve()
        return {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(blob(path))}

    def rows(path):
        return [json.loads(line, object_pairs_hook=unique) for line in blob(path).decode("utf-8-sig").splitlines() if line.strip()]

    tool_record = record(Path(__file__))
    validator_record = record(Path(validate_pair.__code__.co_filename))
    inventory_record = record(inventory)
    for row in rows(inventory):
        loc = row.get("location_id")
        if not isinstance(loc, str) or not loc or loc in entries:
            raise ValueError("목록 위치 누락·중복")
        for evidence in row.get("roster_evidence", []):
            if record(contained(ROOT, evidence["path"]))["sha256"] != evidence["sha256"]:
                raise ValueError("추가 로스터 분류 근거 지문 변경")
        entries[loc] = row

    def identity_check(row, partial=False):
        loc = row.get("location_id")
        if loc not in entries:
            raise ValueError("목록에 없는 위치: " + str(loc))
        expected = entries[loc]
        fields = ("file", "field_path", "line", "source", "source_file_sha256", "source_value_sha256")
        for key in fields:
            if (not partial or key in row) and row.get(key) != expected.get(key):
                raise ValueError("원문 식별 불일치: " + loc + " / " + key)
        return expected

    selected, origins, histories = {}, {}, defaultdict(list)
    input_groups = {}
    for kind, paths in (("batches", batches), ("overrides", overrides)):
        input_groups[kind] = []
        for path in paths:
            path = path.resolve()
            rec = record(path)
            if rec in input_groups[kind]:
                raise ValueError("중복 입력 파일")
            input_groups[kind].append(rec)
            local_seen = set()
            for row in rows(path):
                loc = row.get("location_id")
                identity_check(row)
                if loc in local_seen or (kind == "batches" and loc in selected):
                    raise ValueError("번역 위치 중복: " + str(loc))
                local_seen.add(loc)
                if "previous_target" in row and loc in selected and selected[loc].get("target") != row["previous_target"]:
                    raise ValueError("교정 전 번역 불일치: " + loc)
                if "previous_target_sha256" in row and digest(str(row.get("previous_target", "")).encode("utf-8")) != row["previous_target_sha256"]:
                    raise ValueError("교정 전 번역 지문 불일치")
                selected[loc] = row
                origins[loc] = rec
                histories[loc].append(rec)

    def evidence_check(row):
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            raise ValueError("판정 사유 누락")
        evidence = contained(ROOT, row["evidence_path"])
        if record(evidence)["sha256"] != row["evidence_sha256"]:
            raise ValueError("판정 근거 지문 불일치")

    held_ids, decisions = set(), {}
    for kind, paths in (("holds", holds), ("resolutions", resolutions)):
        input_groups[kind] = []
        for path in paths:
            rec = record(path)
            if rec in input_groups[kind]:
                raise ValueError("중복 판정 파일")
            input_groups[kind].append(rec)
            for row in rows(path):
                loc = row.get("location_id")
                original = identity_check(row, partial=True)
                for key in ("source_file_sha256", "source_value_sha256"):
                    if row.get(key) != original[key]:
                        raise ValueError("판정 원문 지문 누락 또는 불일치")
                evidence_check(row)
                if kind == "holds":
                    if loc in held_ids:
                        raise ValueError("보류 판정 중복")
                    held_ids.add(loc)
                else:
                    if loc in decisions:
                        raise ValueError("해결 판정 중복")
                    if row.get("classification") not in ("VISIBLE_TRANSLATE", "VISIBLE_KEEP", "INTERNAL"):
                        raise ValueError("허용되지 않은 해결 분류")
                    decisions[loc] = row
                    origins[loc] = rec

    # 제출하지 않은 위치를 포함해 목록 전체의 실제 원문을 다시 연다.
    for loc, row in entries.items():
        relative = row["file"]
        path = contained(source, relative)
        data = blob(path)
        if digest(data) != row["source_file_sha256"] or digest(row["source"].encode("utf-8")) != row["source_value_sha256"]:
            raise ValueError("원문 지문 불일치: " + loc)
        if relative not in parsed:
            parsed[relative] = json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique) if relative.endswith(".json") else line_parts(data)
        if relative.endswith(".json"):
            if loc != relative + "#" + row["field_path"]:
                raise ValueError("JSON 식별 경계 불일치")
            parent, key = pointer_access(parsed[relative], row["field_path"])
            actual = parent[key]
        elif relative.endswith(".txt"):
            line = row.get("line")
            if type(line) is not int or not 1 <= line <= len(parsed[relative]) or loc != relative + "#line/" + str(line):
                raise ValueError("TXT 식별 경계 불일치")
            actual = parsed[relative][line - 1][0]
        else:
            raise ValueError("지원하지 않는 원문 형식")
        if type(actual) is not str or actual != row["source"]:
            raise ValueError("원문 위치 값 불일치: " + loc)

    accepted, unresolved, missing, grouped = [], [], [], defaultdict(list)
    for loc, original in entries.items():
        row = decisions.get(loc, selected.get(loc))
        if row is None:
            missing.append(loc)
            continue
        target = row.get("target")
        if not isinstance(target, str) or not target:
            raise ValueError("빈 번역 또는 문자열 아님: " + loc)
        classification = row.get("classification") if loc in decisions else "VISIBLE_TRANSLATE"
        if loc not in decisions and (loc in held_ids or target == original["source"] or (original.get("field_path", "").startswith("/ability/") and original.get("field_path", "").endswith(("/success", "/fail")) and original["source"] in ("none", "none."))):
            unresolved.append({**original, "target": target, "hold_reason": "위치별 근거가 있는 해결 판정 필요"})
            continue
        if classification in ("VISIBLE_KEEP", "INTERNAL"):
            if target != original["source"]:
                raise ValueError("유지 판정이 원문을 변경함: " + loc)
        else:
            if target == original["source"]:
                raise ValueError("번역 판정에 원문 잔존: " + loc)
            pair = validate_pair(original["source"], target)
            if not pair["passed"]:
                raise ValueError("문자열 구조 검증 실패: " + loc + " " + json.dumps(pair, ensure_ascii=False))
        normalized = {**original, "target": target, "classification": classification, "translation_origin": origins[loc], "override_history": histories[loc]}
        if loc in decisions:
            normalized["resolution"] = decisions[loc]
        accepted.append(normalized)
        grouped[original["file"]].append(normalized)

    files = []
    for relative, group in sorted(grouped.items()):
        original_data = blob(contained(source, relative))
        value = deepcopy(parsed[relative])
        changed = any(row["target"] != row["source"] for row in group)
        if not changed:
            data = original_data
        elif relative.endswith(".json"):
            for row in group:
                parent, key = pointer_access(value, row["field_path"])
                parent[key] = row["target"]
            data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        else:
            for row in group:
                value[row["line"] - 1] = (row["target"], value[row["line"] - 1][1])
            data = (b"\xef\xbb\xbf" if original_data.startswith(b"\xef\xbb\xbf") else b"") + "".join(text + eol for text, eol in value).encode("utf-8")
        destination = contained(output / "payload", relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        files.append({"file": relative, "source_sha256": digest(original_data), "candidate_sha256": digest(data), "size": len(data), "locations": len(group)})

    for name, value in (("canonical.jsonl", accepted), ("holds.jsonl", unresolved)):
        (output / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in value), encoding="utf-8", newline="\n")
    (output / "missing.json").write_text(json.dumps(missing, ensure_ascii=False, indent=2), encoding="utf-8")
    for path, data in snapshots.items():
        if path.read_bytes() != data:
            raise ValueError("처리 중 입력 변경: " + str(path))
    report = {"schema_version": 1, "game_id": "SOULASH_2", "steam_build": "25967323", "scope": "DECLARED_ROSTER_JSON_TXT_ONLY", "synthetic_fixture": synthetic,
              "status": "PASS" if not missing and not unresolved else "FAIL", "generation_status": "PASS", "roster_g4_status": "NOT_RUN", "g2_status": "NOT_RUN", "g5_status": "NOT_RUN", "release_ready": False,
              "generated_at": datetime.now(timezone.utc).isoformat(), "source_root": source.relative_to(ROOT).as_posix(), "inventory": inventory_record,
              "tool": tool_record, "validator": validator_record, **input_groups,
              "inventory_rows": len(entries), "submitted_rows": len(set(selected) | set(decisions)), "accepted_rows": len(accepted), "changed_rows": sum(row["target"] != row["source"] for row in accepted),
              "held_rows": len(unresolved), "missing_rows": len(missing), "unresolved_total": len(missing) + len(unresolved), "files": files,
              "canonical_sha256": digest((output / "canonical.jsonl").read_bytes()), "holds_sha256": digest((output / "holds.jsonl").read_bytes()), "missing_sha256": digest((output / "missing.json").read_bytes()),
              "inputs": [record(path) for path in sorted(snapshots)]}
    (output / "stage_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, action="append", default=[])
    parser.add_argument("--override", type=Path, action="append", default=[])
    parser.add_argument("--resolution", type=Path, action="append", default=[])
    parser.add_argument("--hold-batch", type=Path, action="append", default=[])
    parser.add_argument("--inventory", type=Path, default=INVENTORY)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.output, args.inventory, args.batch, args.override, args.resolution, args.hold_batch)
    print(json.dumps({k: result[k] for k in ("status", "accepted_rows", "held_rows", "missing_rows", "scope")}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
