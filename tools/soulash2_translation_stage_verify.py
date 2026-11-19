"""생성기와 별개로 부분 후보 전체 JSON의 구조·위치별 값·변경 경계를 대조한다."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

from soulash2_validate_text import validate_pair

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
INVENTORY = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029/effective_inventory/v4/translation_work_v2.jsonl"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("중복 JSON 속성: " + key)
        result[key] = value
    return result


def safe_file(base, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("잘못된 상대 파일 경로")
    path = PurePosixPath(relative)
    if path.is_absolute() or str(path) != relative or any(p in (".", "..") for p in relative.split("/")):
        raise ValueError("상위 경로 또는 비정규 파일 경로")
    actual = (base / relative).resolve()
    if not actual.is_relative_to(base.resolve()):
        raise ValueError("파일 경로가 허용 범위를 벗어남")
    return actual


def walk(value, path=""):
    # 구조와 빈 컨테이너도 검증하여 값만 같은 삭제·배열 순서 변경을 놓치지 않는다.
    if isinstance(value, dict):
        yield path, ("object", tuple(value))
        for key, child in value.items():
            yield from walk(child, path + "/" + key.replace("~", "~0").replace("/", "~1"))
    elif isinstance(value, list):
        yield path, ("array", len(value))
        for index, child in enumerate(value):
            yield from walk(child, path + "/" + str(index))
    else:
        yield path, (type(value).__name__, value)


def compare(original, candidate, expected):
    left, right = dict(walk(original)), dict(walk(candidate))
    failures = []
    for path in sorted(set(left) | set(right)):
        actual = right.get(path)
        required = ("str", expected[path]) if path in expected else left.get(path)
        if path not in left or path not in right or actual != required:
            failures.append({"path": path, "source": left.get(path), "expected": required, "actual": actual})
    for path in set(expected) - set(left):
        failures.append({"path": path, "reason": "존재하지 않는 번역 위치"})
    return failures


def selftests():
    source = {"items": [{"id": 1, "text": "one"}, {"id": 2, "text": "two"}], "empty": []}
    correct = {"items": [{"id": 1, "text": "하나"}, {"id": 2, "text": "둘"}], "empty": []}
    expected = {"/items/0/text": "하나", "/items/1/text": "둘"}
    cases = [("정상", correct, True),
             ("위치교환", {"items": [{"id": 1, "text": "둘"}, {"id": 2, "text": "하나"}], "empty": []}, False),
             ("빈값", {"items": [{"id": 1, "text": ""}, {"id": 2, "text": "둘"}], "empty": []}, False),
             ("객체삭제", {"items": [{"id": 1, "text": "하나"}], "empty": []}, False),
             ("식별자변경", {"items": [{"id": 3, "text": "하나"}, {"id": 2, "text": "둘"}], "empty": []}, False),
             ("원문잔존", source, False), ("빈배열삭제", {"items": correct["items"]}, False),
             ("예상밖추가", {**correct, "extra": "추가"}, False)]
    return [{"case": name, "passed": (not compare(source, candidate, expected)) == valid} for name, candidate, valid in cases]


def verify(candidate):
    """원 번역 묶음에서 기대 집합을 다시 계산하고 파일 전체를 독립 대조한다."""
    candidate = candidate.resolve()
    if not candidate.is_relative_to((ROOT / "build_candidate/SOULASH_2").resolve()):
        raise ValueError("후보 경로 경계 오류")
    started = datetime.now(timezone.utc).isoformat()
    snapshots, failures, checked = {}, [], []

    def blob(path):
        path = path.resolve()
        if path not in snapshots:
            data = path.read_bytes()
            snapshots[path] = (hashlib.sha256(data).hexdigest(), data)
        return snapshots[path][1]

    def digest(path):
        blob(path)
        return snapshots[path.resolve()][0]

    def document(path):
        return json.loads(blob(path).decode("utf-8-sig"), object_pairs_hook=unique_object)

    def rows_at(path):
        return [json.loads(line, object_pairs_hook=unique_object) for line in blob(path).decode("utf-8").splitlines()]

    def index_rows(rows, label):
        result = {}
        for row in rows:
            key = row.get("location_id")
            if not isinstance(key, str) or not key or key in result:
                raise ValueError(label + "의 중복 또는 누락 위치 ID")
            result[key] = row
        return result

    def expect(condition, reason, **detail):
        if not condition:
            failures.append({"reason": reason, **detail})

    stage_path = safe_file(candidate, "stage_report.json")
    verifier_hash = digest(Path(__file__))
    stage = document(stage_path)
    stage_hash = digest(stage_path)
    rows, holds = [], []
    try:
        expect(stage.get("build_id") == "0.10.4.0.1_20261029", "다른 빌드의 후보")
        expect(stage.get("scope") == "SUBSET_ASSETS_ONLY" and stage.get("release_ready") is False, "부분 후보 범위 표기 오류")
        expect(stage.get("status") == "PASS", "후보 생성 단계가 통과하지 않음")
        expect(all(stage.get(key) == "NOT_RUN" for key in ("g3_status", "g4_status", "g5_status")), "부분 형식 검사를 전체 완료로 확대한 상태")
        generator = ROOT / "tools/soulash2_translation_stage.py"
        expect(digest(generator) == stage.get("tool_sha256"), "생성 도구 지문 변경")
        validator = Path(validate_pair.__code__.co_filename).resolve()
        expect(digest(validator) == stage.get("validator_sha256"), "제어 정보 검사 도구 지문 변경")
        expect(stage.get("inventory_path") == INVENTORY.resolve().relative_to(ROOT).as_posix(), "원본 목록 경로 불일치")
        expect(digest(INVENTORY) == stage.get("inventory_sha256"), "원본 목록 지문 변경")
        inventory = index_rows(rows_at(INVENTORY), "원본 목록")
        canonical_path, holds_path = safe_file(candidate, "canonical.jsonl"), safe_file(candidate, "holds.jsonl")
        expect(digest(canonical_path) == stage.get("canonical_sha256"), "번역 목록 지문 변경")
        expect(digest(holds_path) == stage.get("holds_sha256"), "보류 목록 지문 변경")
        rows, holds = rows_at(canonical_path), rows_at(holds_path)
        accepted = index_rows(rows, "번역 목록")
        held = index_rows(holds, "보류 목록")
        expect(not set(accepted) & set(held), "번역/보류 위치 중복")
        submitted, batch_paths, row_batches = {}, set(), {}
        for batch in stage["batches"]:
            path = safe_file(ROOT, batch["path"])
            if not path.is_relative_to((ROOT / "working_private/SOULASH_2/translations").resolve()) or path in batch_paths:
                raise ValueError("번역 묶음 경로 이탈 또는 중복")
            batch_paths.add(path)
            expect(digest(path) == batch["sha256"], "원 번역 묶음 지문 변경", file=batch["path"])
            for identity, row in index_rows(rows_at(path), "번역 묶음").items():
                if identity in submitted:
                    raise ValueError("서로 다른 번역 묶음의 위치 중복")
                submitted[identity] = row
                row_batches[identity] = path.relative_to(ROOT).as_posix()
        hold_decisions, hold_paths = {}, set()
        for batch in stage.get("hold_batches", []):
            path = safe_file(ROOT, batch["path"])
            if not path.is_relative_to((ROOT / "working_private/SOULASH_2/translations").resolve()) or path in hold_paths:
                raise ValueError("보류 묶음 경로 이탈 또는 중복")
            hold_paths.add(path)
            expect(digest(path) == batch["sha256"], "보류 묶음 지문 변경")
            for identity, decision in index_rows(rows_at(path), "보류 결정").items():
                if identity in hold_decisions:
                    raise ValueError("서로 다른 보류 묶음의 위치 중복")
                if not isinstance(decision.get("reason"), str) or not decision["reason"].strip():
                    raise ValueError("보류 사유 누락")
                evidence = safe_file(ROOT, decision["evidence_path"])
                if not evidence.is_relative_to((ROOT / "working_private/SOULASH_2").resolve()):
                    raise ValueError("보류 근거 경로 이탈")
                expect(digest(evidence) == decision["evidence_sha256"], "보류 근거 지문 변경")
                hold_decisions[identity] = decision
        expect(set(hold_decisions) <= set(submitted), "보류 결정에 대응하는 번역 묶음이 없음")
        expected_accepted, expected_held, source_docs, source_nodes = {}, {}, {}, {}
        fields = ("file", "field_path", "source", "source_file_sha256", "source_value_sha256")
        for identity, row in submitted.items():
            original = inventory.get(identity)
            if original is None or any(row.get(key) != original.get(key) for key in fields):
                raise ValueError("현재 목록과 번역 묶음의 원본 정보 불일치: " + identity)
            relative, pointer = row["file"], row["field_path"]
            source = safe_file(SOURCE, relative)
            if not relative.endswith(".json") or not isinstance(pointer, str) or identity != relative + "#" + pointer:
                raise ValueError("번역 위치 식별 계약 위반")
            if relative not in source_docs:
                source_docs[relative] = document(source)
                source_nodes[relative] = dict(walk(source_docs[relative]))
            expect(digest(source) == row["source_file_sha256"], "원본 파일 지문 변경", file=relative)
            expect(source_nodes[relative].get(pointer) == ("str", row["source"]), "원본 위치/값 불일치", location_id=identity)
            expect(isinstance(row.get("target"), str), "번역이 문자열이 아님", location_id=identity)
            expect(hashlib.sha256(row["source"].encode("utf-8")).hexdigest() == row["source_value_sha256"], "원문 값 지문 불일치", location_id=identity)
            decision = hold_decisions.get(identity)
            if decision is not None:
                expect(all(decision.get(key) == row.get(key) for key in (*fields, "target")),
                       "보류 결정과 현재 번역 정보 불일치", location_id=identity)
            withheld = (identity in hold_decisions or row["source"] == row.get("target") or
                        (pointer.startswith("/ability/") and pointer.endswith(("/success", "/fail")) and row["source"] in ("none", "none.")))
            (expected_held if withheld else expected_accepted)[identity] = row
        expect(set(accepted) == set(expected_accepted), "허용 번역 위치의 누락/추가 또는 보류 오집계")
        expect(set(held) == set(expected_held), "보류 위치의 누락/추가")
        for actuals, intended, is_held in ((accepted, expected_accepted, False), (held, expected_held, True)):
            for identity, actual in actuals.items():
                wanted = intended.get(identity)
                if wanted is None:
                    continue
                expect(all(actual.get(key) == wanted.get(key) for key in (*fields, "target")), "후보 번역 목록이 원 번역 묶음과 다름", location_id=identity)
                expect(actual.get("translation_status") == ("NOT_RUN" if is_held else "TRANSLATED_PENDING_REVIEW"), "번역 검토 상태 표기 오류", location_id=identity)
                if is_held and identity in hold_decisions:
                    decision = hold_decisions[identity]
                    expect(actual.get("hold_reason") == decision["reason"] and
                           actual.get("hold_evidence_path") == decision["evidence_path"] and
                           actual.get("hold_evidence_sha256") == decision["evidence_sha256"],
                           "명시적 보류 사유 또는 근거 불일치", location_id=identity)
                if not is_held:
                    expect(actual.get("translation_batch") == row_batches[identity], "번역 출처 묶음 불일치", location_id=identity)
                    expect(validate_pair(actual["source"], actual["target"])["passed"], "번역 제어 정보 오류", location_id=identity)
        for key, expected_count in (("submitted_rows", len(submitted)), ("accepted_rows", len(accepted)),
                                    ("changed_rows", len(expected_accepted)), ("held_rows", len(held)),
                                    ("inventory_rows", len(inventory)), ("missing_rows", len(inventory) - len(expected_accepted))):
            expect(stage.get(key) == expected_count, "집계 불일치", field=key, expected=expected_count, actual=stage.get(key))
        source_manifest = {}
        for item in stage["source_files"]:
            if item["file"] in source_manifest:
                raise ValueError("원본 파일 목록 중복")
            source_manifest[item["file"]] = item["sha256"]
        expect(set(source_manifest) == set(source_docs), "원본 파일 목록 누락/추가")
        for relative, expected_hash in source_manifest.items():
            expect(digest(safe_file(SOURCE, relative)) == expected_hash, "원본 파일 목록 지문 불일치", file=relative)
        payload = (candidate / "payload").resolve()
        if not payload.is_relative_to(candidate):
            raise ValueError("후보 자산 폴더가 후보 밖으로 연결됨")
        actual_files = set()
        for path in payload.rglob("*"):
            if not path.resolve().is_relative_to(payload):
                raise ValueError("후보 안의 파일/폴더 연결이 경계 이탈")
            if path.is_file():
                actual_files.add(path.relative_to(payload).as_posix())
        file_manifest = {}
        for item in stage["files"]:
            relative = item["file"]
            safe_file(SOURCE, relative)
            safe_file(payload, relative)
            if relative in file_manifest:
                raise ValueError("후보 파일 목록 중복")
            file_manifest[relative] = item
        expected_files = {r["file"] for r in expected_accepted.values()}
        expect(actual_files == set(file_manifest) == expected_files, "후보 파일 추가/누락 또는 번역 파일 목록 불일치")
        for relative, item in file_manifest.items():
            source, modified = safe_file(SOURCE, relative), safe_file(payload, relative)
            expect(digest(source) == item["source_sha256"] and digest(modified) == item["candidate_sha256"], "원본 또는 후보 지문 불일치", file=relative)
            originals, actual = document(source), document(modified)
            targets = {}
            for row in rows:
                if row["file"] != relative:
                    continue
                if row["field_path"] in targets:
                    raise ValueError("한 파일 안의 번역 위치 중복")
                targets[row["field_path"]] = row["target"]
            expect(item["locations"] == len(targets), "파일별 번역 개수 불일치", file=relative)
            findings = compare(originals, actual, targets)
            failures.extend({"file": relative, **finding} for finding in findings)
            checked.append({"file": relative, "locations": len(targets), "all_nodes": len(dict(walk(actual))), "failures": len(findings)})
        for path, (before, _) in snapshots.items():
            expect(sha(path) == before, "검사 도중 입력/후보 변경", file=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name)
    except (ValueError, KeyError, TypeError, OSError, UnicodeError) as error:
        failures.append({"reason": "검사 입력 또는 구조 오류", "detail": str(error)})
    tests = selftests()
    report = {"game_id": "SOULASH_2", "build_id": stage["build_id"], "check_id": "SUBSET_INDEPENDENT_READBACK",
              "started": started, "finished": datetime.now(timezone.utc).isoformat(), "tool_sha256": verifier_hash,
              "command": sys.argv, "stage_report_sha256": stage_hash,
              "input_hashes": [{"path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name, "sha256": value[0]} for path, value in snapshots.items()],
              "status": "FAIL" if failures or not all(test["passed"] for test in tests) else "PASS",
              "scope": "SUBSET_ASSETS_ONLY", "release_ready": False, "locations": len(rows), "held_rows": len(holds), "files": checked,
              "selftests": tests, "failures": failures, "g3_semantic_review": "NOT_RUN", "g4_full": "NOT_RUN", "g5": "NOT_RUN"}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    report_path = candidate / "independent_validation.json"
    if report_path.exists():
        raise ValueError("검사 이력 덮어쓰기 금지")
    report = verify(candidate)
    with report_path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"status": report["status"], "locations": report["locations"], "failures": len(report["failures"]), "selftests": len(report["selftests"])}))
    return 1 if report["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
