"""검토한 번역 묶음을 위치별로 합치고 실행 불가한 부분 자산 사본을 만든다."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

from soulash2_validate_text import validate_pair

ROOT = Path(__file__).resolve().parents[1]
BUILD = "0.10.4.0.1_20261029"
SOURCE = ROOT / "source_original/SOULASH_2" / BUILD
INVENTORY = ROOT / "extracted_private/SOULASH_2" / BUILD / "effective_inventory/v4/translation_work_v2.jsonl"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line, object_pairs_hook=pairs_hook)


def pairs_hook(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("중복 속성 키가 있는 파일은 이 빌드 경로에서 처리하지 않습니다: " + key)
        result[key] = value
    return result


def source_object(path):
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=pairs_hook)


def contained(base, relative):
    """드라이브 표기·상위 이동·별칭 경로를 읽기 전에 거부한다."""
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("잘못된 상대 경로")
    path = PurePosixPath(relative)
    if path.is_absolute() or any(part in (".", "..") for part in relative.split("/")) or str(path) != relative:
        raise ValueError("정규화되지 않은 상대 경로: " + relative)
    resolved = (base / relative).resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise ValueError("허용 경로 이탈: " + relative)
    return resolved


def index_inventory(path):
    expected = {}
    for row in read_rows(path):
        identity = row.get("location_id")
        if not isinstance(identity, str) or not identity or identity in expected:
            raise ValueError("목록의 누락/중복 위치 ID")
        expected[identity] = row
    return expected


def checked_index(cursor, part):
    if isinstance(cursor, list):
        if not part.isascii() or not part.isdigit() or str(int(part)) != part or int(part) >= len(cursor):
            raise ValueError("잘못된 배열 위치")
        return int(part)
    if not isinstance(cursor, dict) or part not in cursor:
        raise ValueError("존재하지 않는 객체 위치")
    return part


def set_pointer(obj, pointer, source, target):
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("잘못된 JSON 위치")
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]
    if "/" + "/".join(part.replace("~", "~0").replace("/", "~1") for part in parts) != pointer:
        raise ValueError("정규화되지 않은 JSON 위치")
    if not parts:
        raise ValueError("루트 전체 교체는 지원하지 않습니다")
    cursor = obj
    for part in parts[:-1]:
        cursor = cursor[checked_index(cursor, part)]
    key = checked_index(cursor, parts[-1])
    if type(cursor[key]) is not str or cursor[key] != source:
        raise ValueError("원본 위치/값 불일치: " + pointer)
    cursor[key] = target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, action="append", required=True)
    parser.add_argument("--hold-batch", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "build_candidate/SOULASH_2").resolve()):
        parser.error("후보는 build_candidate/SOULASH_2 안의 새 폴더에 생성합니다")
    output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    input_hashes = {INVENTORY.resolve(): sha(INVENTORY), Path(__file__).resolve(): sha(Path(__file__)),
                    Path(validate_pair.__code__.co_filename).resolve(): sha(Path(validate_pair.__code__.co_filename))}
    expected = index_inventory(INVENTORY)
    explicit_holds, hold_batches = {}, []
    for path in args.hold_batch:
        path = path.resolve()
        if not path.is_relative_to((ROOT / "working_private/SOULASH_2/translations").resolve()):
            raise ValueError("허용 보류 목록 경로 밖")
        if any(item["path"] == path.relative_to(ROOT).as_posix() for item in hold_batches):
            raise ValueError("중복 보류 묶음")
        input_hashes[path] = sha(path)
        hold_batches.append({"path": path.relative_to(ROOT).as_posix(), "sha256": input_hashes[path]})
        for row in read_rows(path):
            identity = row.get("location_id")
            if not isinstance(identity, str) or not identity or identity in explicit_holds:
                raise ValueError("보류 위치 ID 누락 또는 중복")
            if not isinstance(row.get("reason"), str) or not row["reason"].strip():
                raise ValueError("보류 사유 누락")
            evidence = contained(ROOT, row["evidence_path"])
            if not evidence.is_relative_to((ROOT / "working_private/SOULASH_2").resolve()):
                raise ValueError("보류 근거 경로 이탈")
            input_hashes[evidence] = sha(evidence)
            if input_hashes[evidence] != row["evidence_sha256"]:
                raise ValueError("보류 근거 지문 변경")
            explicit_holds[identity] = row
    grouped, accepted, holds, failures, seen = defaultdict(list), [], [], [], set()
    batches, batch_paths, source_values = [], set(), {}
    for path in args.batch:
        path = path.resolve()
        if not path.is_relative_to((ROOT / "working_private/SOULASH_2/translations").resolve()):
            raise ValueError("허용 번역 원본 경로 밖")
        if path in batch_paths:
            raise ValueError("같은 번역 묶음을 중복 지정했습니다")
        batch_paths.add(path)
        input_hashes[path] = sha(path)
        batches.append({"path": path.relative_to(ROOT).as_posix(), "sha256": input_hashes[path]})
        for row in read_rows(path):
            identity = row.get("location_id")
            if identity in seen:
                failures.append({"location_id": identity, "reason": "중복 번역"})
                continue
            seen.add(identity)
            original = expected.get(identity)
            if original is None or any(row.get(k) != original.get(k) for k in ("file", "field_path", "source", "source_file_sha256", "source_value_sha256")):
                failures.append({"location_id": identity, "reason": "현재 목록과 원본 식별 정보 불일치"})
                continue
            relative, pointer = row["file"], row["field_path"]
            source_file = contained(SOURCE, relative)
            if not relative.endswith(".json") or not isinstance(pointer, str) or not pointer.startswith("/") or identity != relative + "#" + pointer:
                failures.append({"location_id": identity, "reason": "JSON 위치 식별 계약 위반"})
                continue
            if not isinstance(row.get("target"), str) or not isinstance(row["source"], str):
                failures.append({"location_id": identity, "reason": "원문 또는 번역이 문자열이 아님"})
                continue
            if hashlib.sha256(row["source"].encode("utf-8")).hexdigest() != row["source_value_sha256"]:
                failures.append({"location_id": identity, "reason": "원문 값 지문 불일치"})
                continue
            if source_file not in source_values:
                input_hashes[source_file] = sha(source_file)
                source_values[source_file] = source_object(source_file)
            if input_hashes[source_file] != row["source_file_sha256"]:
                failures.append({"location_id": identity, "reason": "원본 파일 지문 변경"})
                continue
            set_pointer(source_values[source_file], pointer, row["source"], row["source"])
            if identity in explicit_holds:
                decision = explicit_holds[identity]
                if any(decision.get(k) != row.get(k) for k in ("file", "field_path", "source", "source_file_sha256", "source_value_sha256", "target")):
                    failures.append({"location_id": identity, "reason": "보류 결정과 현재 번역 정보 불일치"})
                    continue
                holds.append({**row, "hold_reason": decision["reason"], "hold_evidence_path": decision["evidence_path"],
                              "hold_evidence_sha256": decision["evidence_sha256"], "translation_status": "NOT_RUN"})
                continue
            # 효과 성공/실패의 none은 사용 코드 판정 전 후보에 넣지 않는다.
            if row["field_path"].startswith("/ability/") and row["field_path"].endswith(("/success", "/fail")) and row["source"] in ("none", "none."):
                holds.append({**row, "hold_reason": "능력 메시지 생략 비교값 여부 조사 중", "translation_status": "NOT_RUN"})
                continue
            if row.get("target") == row["source"]:
                holds.append({**row, "hold_reason": "원문 유지의 위치별 판정 필요", "translation_status": "NOT_RUN"})
                continue
            pair = validate_pair(row["source"], row.get("target"))
            if not pair["passed"]:
                failures.append({"location_id": identity, "reason": "번역 제어 정보 검사 실패", "detail": pair})
                continue
            normalized = {**original, "target": row["target"], "translation_status": "TRANSLATED_PENDING_REVIEW",
                          "translation_gate": "G1_JSON_TTF_LIMITED_PASS", "translation_batch": path.resolve().relative_to(ROOT).as_posix()}
            accepted.append(normalized)
            grouped[row["file"]].append(normalized)
    for identity in set(explicit_holds) - seen:
        failures.append({"location_id": identity, "reason": "보류 결정에 대응하는 번역 묶음이 없음"})
    if failures:
        (output / "stage_failure.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
        raise ValueError("실패한 번역이 있으므로 후보 생성을 중단합니다")
    files = []
    for relative, rows in sorted(grouped.items()):
        source_path = contained(SOURCE, relative)
        destination = contained(output / "payload", relative)
        source_hash = sha(source_path)
        input_hashes[source_path] = source_hash
        if any(row["source_file_sha256"] != source_hash for row in rows):
            raise ValueError("원본 파일 지문 변경: " + relative)
        value = source_object(source_path)
        for row in rows:
            set_pointer(value, row["field_path"], row["source"], row["target"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        if sha(source_path) != source_hash:
            raise ValueError("처리 도중 원본 변경: " + relative)
        files.append({"file": relative, "source_sha256": source_hash, "candidate_sha256": sha(destination), "locations": len(rows)})
    for name, rows in [("canonical.jsonl", accepted), ("holds.jsonl", holds)]:
        with (output / name).open("x", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    changed = sum(row["source"] != row["target"] for row in accepted)
    changed_inputs = [str(path) for path, digest in input_hashes.items() if sha(path) != digest]
    if changed_inputs:
        raise ValueError("처리 도중 입력 변경: " + repr(changed_inputs))
    report = {"game_id": "SOULASH_2", "build_id": BUILD, "check_id": "TRANSLATION_STAGE",
              "started": started, "finished": datetime.now(timezone.utc).isoformat(), "command": sys.argv,
              "tool_sha256": input_hashes[Path(__file__).resolve()],
              "validator_sha256": input_hashes[Path(validate_pair.__code__.co_filename).resolve()],
              "inventory_path": INVENTORY.resolve().relative_to(ROOT).as_posix(),
              "inventory_sha256": input_hashes[INVENTORY.resolve()], "batches": batches, "hold_batches": hold_batches,
              "source_files": [{"file": path.relative_to(SOURCE).as_posix(), "sha256": input_hashes[path]}
                               for path in sorted(source_values)],
              "status": "PASS", "scope": "SUBSET_ASSETS_ONLY", "release_ready": False,
              "g3_status": "NOT_RUN", "g4_status": "NOT_RUN", "g5_status": "NOT_RUN",
              "submitted_rows": len(seen), "accepted_rows": len(accepted), "changed_rows": changed,
              "held_rows": len(holds), "inventory_rows": len(expected), "missing_rows": len(expected)-len(accepted),
              "canonical_sha256": sha(output / "canonical.jsonl"), "holds_sha256": sha(output / "holds.jsonl"), "files": files,
              "limitations": ["실행 파일·글꼴 없는 부분 자산이며 실행/설치용 완성 후보가 아님", "생성 후 별도 위치별 재추출 검사가 필요함", "번역 문맥 교정과 실제 화면 검수는 별도 수행"]}
    with (output / "stage_report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in ("status", "accepted_rows", "held_rows", "missing_rows", "scope")}))


if __name__ == "__main__":
    main()
