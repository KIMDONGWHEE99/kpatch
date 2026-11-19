"""JSON·TXT 통합 검사기의 누락·뒤바뀜·삭제·오염 거부를 작은 격리 자료로 시험한다."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

from soulash2_complete_stage import build
from soulash2_complete_stage_verify import verify

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_rows(path, value):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in value), encoding="utf-8")


def main():
    folder = ROOT / "working_private/SOULASH_2/complete_stage_selftest" / str(time.time_ns())
    source = folder / "source"
    source.mkdir(parents=True)
    write_json(source / "data.json", {"objects": [{"id": 1, "name": "One"}, {"id": 2, "name": "Two"}], "format": "::name", "ability": {"1": {"success": "none"}}, "empty": []})
    (source / "names.txt").write_bytes(b"\xef\xbb\xbfAlara\r\nBorin\nCora")
    inventory = []
    for file, field, value, target in [("data.json", "/objects/0/name", "One", "하나"), ("data.json", "/objects/1/name", "Two", "둘"), ("data.json", "/format", "::name", "::name"), ("data.json", "/ability/1/success", "none", "none"), ("names.txt", 1, "Alara", "알라라"), ("names.txt", 2, "Borin", "보린")]:
        row = {"file": file, "source": value, "source_file_sha256": sha((source / file).read_bytes()), "source_value_sha256": sha(value.encode()), "classification": "VISIBLE_TRANSLATE"}
        row.update({"field_path": field, "location_id": file + "#" + field} if isinstance(field, str) else {"line": field, "location_id": file + "#line/" + str(field)})
        inventory.append(row)
    targets = ["하나", "둘", "::name", "none", "알라라", "보린"]
    batch = [{**row, "target": target} for row, target in zip(inventory, targets)]
    write_rows(folder / "inventory.jsonl", inventory)
    write_rows(folder / "batch.jsonl", batch)
    evidence = folder / "evidence.json"
    write_json(evidence, {"reason": "가상 자료의 명시적인 유지 판정"})
    decisions = [{**batch[i], "classification": "VISIBLE_KEEP", "reason": "가상 유지 근거", "evidence_path": evidence.relative_to(ROOT).as_posix(), "evidence_sha256": sha(evidence.read_bytes())} for i in (2, 3)]
    write_rows(folder / "resolution.jsonl", decisions)
    kwargs = {"inventory": folder / "inventory.jsonl", "batches": [folder / "batch.jsonl"], "resolutions": [folder / "resolution.jsonl"], "source": source}
    baseline = folder / "correct"
    report = build(baseline, **kwargs)
    cases = []

    def expect(name, action, valid=False):
        try:
            result = action()
            passed = (result["status"] == "PASS") == valid
            reason = result["status"]
        except (ValueError, KeyError, OSError, TypeError) as error:
            passed, reason = not valid, str(error)
        cases.append({"case": name, "status": "PASS" if passed else "FAIL", "observed": reason})

    expect("정상 JSON·혼합 줄바꿈 TXT·근거 유지", lambda: verify(baseline), True)

    def mutation(name, callback):
        target = folder / name
        shutil.copytree(baseline, target)
        callback(target)
        return verify(target)

    def json_change(target, callback):
        path = target / "payload/data.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        callback(value)
        write_json(path, value)

    expect("JSON 번역 위치 교환", lambda: mutation("swap", lambda p: json_change(p, lambda v: v["objects"].reverse())))
    expect("JSON 객체 삭제", lambda: mutation("delete", lambda p: json_change(p, lambda v: v["objects"].pop())))
    expect("JSON 빈 번역", lambda: mutation("empty", lambda p: json_change(p, lambda v: v["objects"][0].update(name=""))))
    expect("JSON 비번역 ID 변경", lambda: mutation("id_change", lambda p: json_change(p, lambda v: v["objects"][0].update(id=99))))
    expect("JSON 빈 배열 삭제", lambda: mutation("delete_empty", lambda p: json_change(p, lambda v: v.pop("empty"))))
    expect("JSON 순서 변경", lambda: mutation("order", lambda p: write_json(p / "payload/data.json", dict(reversed(list(json.loads((p / "payload/data.json").read_text(encoding="utf-8")).items()))))))
    expect("TXT 위치 교환", lambda: mutation("txt_swap", lambda p: (p / "payload/names.txt").write_bytes("보린\r\n알라라\nCora".encode("utf-8-sig"))))
    expect("TXT 줄바꿈 변경", lambda: mutation("txt_eol", lambda p: (p / "payload/names.txt").write_bytes("알라라\n보린\nCora".encode("utf-8-sig"))))
    expect("TXT 줄 삭제", lambda: mutation("txt_delete", lambda p: (p / "payload/names.txt").write_bytes("알라라\r\n보린\n".encode("utf-8-sig"))))
    expect("TXT BOM 손실", lambda: mutation("txt_bom", lambda p: (p / "payload/names.txt").write_bytes("알라라\r\n보린\nCora".encode("utf-8"))))
    expect("추가 후보 파일", lambda: mutation("extra", lambda p: (p / "payload/extra.bin").write_bytes(b"x")))
    expect("후보 파일 삭제", lambda: mutation("missing_file", lambda p: (p / "payload/names.txt").unlink()))
    expect("거짓 성공 개수", lambda: mutation("fake_count", lambda p: write_json(p / "stage_report.json", {**json.loads((p / "stage_report.json").read_text(encoding="utf-8")), "accepted_rows": 999})))
    unresolved = folder / "unresolved"
    build(unresolved, **{**kwargs, "resolutions": []})
    expect("해결 근거 없는 KEEP·none", lambda: verify(unresolved))
    write_rows(folder / "partial.jsonl", batch[:-1])
    missing = folder / "missing"
    build(missing, **{**kwargs, "batches": [folder / "partial.jsonl"]})
    expect("로스터 누락 하나", lambda: verify(missing))
    (evidence).write_bytes(b"changed")
    expect("판정 근거 변경", lambda: verify(baseline))
    write_json(evidence, {"reason": "가상 자료의 명시적인 유지 판정"})
    write_rows(folder / "unknown.jsonl", [{**decisions[0], "classification": "UNKNOWN"}])
    expect("미분류 해결 판정", lambda: build(folder / "unknown", **{**kwargs, "resolutions": [folder / "unknown.jsonl"]}))
    write_rows(folder / "duplicate.jsonl", batch + [batch[0]])
    expect("중복 입력 위치", lambda: build(folder / "duplicate", **{**kwargs, "batches": [folder / "duplicate.jsonl"]}))
    write_rows(folder / "empty.jsonl", [{**r, "target": ""} if i == 0 else r for i, r in enumerate(batch)])
    expect("빈 입력 번역", lambda: build(folder / "empty_input", **{**kwargs, "batches": [folder / "empty.jsonl"]}))
    write_rows(folder / "wrong_source.jsonl", [{**r, "source_value_sha256": "0" * 64} if i == 0 else r for i, r in enumerate(batch)])
    expect("다른 원문 입력", lambda: build(folder / "wrong_source", **{**kwargs, "batches": [folder / "wrong_source.jsonl"]}))
    write_rows(folder / "batch.jsonl", [{**r, "target": "변조"} if i == 0 else r for i, r in enumerate(batch)])
    expect("번역 입력 변경", lambda: verify(baseline))
    write_rows(folder / "batch.jsonl", batch)
    expect("자료 복원 후 정상", lambda: verify(baseline), True)
    result = {"status": "PASS" if all(row["status"] == "PASS" for row in cases) else "FAIL", "synthetic_fixture": True, "cases": cases}
    write_json(folder / "report.json", result)
    print(json.dumps({"status": result["status"], "cases": len(cases), "report": (folder / "report.json").relative_to(ROOT).as_posix()}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
