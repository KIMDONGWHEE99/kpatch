"""실제 설치 전후의 게임 파일과 사용자 저장 경계를 독립 확인합니다."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile
from common import ROOT, WORK, EXTRACT, sha, write_json
from prepare_qa import manifest
from qa_session import snapshot


def file_map(rows):
    result = {r["path"]: {"size": r["size"], "sha256": r["sha256"]} for r in rows}
    assert len(result) == len(rows), "파일 목록에 중복 경로가 있습니다."
    return result


def same_path(left, right):
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def package_binding(package_path):
    package = json.loads(package_path.read_text(encoding="utf-8"))
    assert package["game_id"] == "KINGDOM_INC_DEMO" and package["steam_build"] == "25631786"
    assert package["G6"] == package["G7"] == "PASS", "최종 ZIP 검사가 완료되지 않았습니다."
    assert sha(Path(package["archive"])) == package["zip_sha256"]
    # 최종 ZIP의 목록을 직접 읽어, 변경 가능한 외부 보고서와도 대조합니다.
    with zipfile.ZipFile(package["archive"]) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)) and set(names) == set(package["allowed_files"])
        raw = archive.read("manifest.json")
    assert hashlib.sha256(raw).hexdigest() == package["manifest_sha256"]
    packed = json.loads(raw.decode("utf-8-sig"))
    for key in ("game_id", "steam_build", "candidate", "version", "changes"):
        assert packed[key] == package[key], "ZIP과 패키지 보고서가 다릅니다: " + key
    baseline_path = EXTRACT / "baseline.json"
    assert sha(baseline_path) == package["baseline_manifest_sha256"]
    expected = file_map(json.loads(baseline_path.read_text(encoding="utf-8"))["files"])
    assert expected == file_map(packed["baseline"])
    candidate = file_map(package["candidate_files"])
    changes = {r["path"]: r for r in packed["changes"]}
    assert len(changes) == len(packed["changes"])
    assert {p for p in set(expected) | set(candidate) if expected.get(p) != candidate.get(p)} == set(changes)
    for path, change in changes.items():
        assert expected.get(path, {}).get("sha256") == change["original_sha256"]
        assert candidate[path]["sha256"] == change["patched_sha256"]
    return package, expected, candidate


def verify_receipt(game, package, before, local_app_data):
    # 설치기의 ToLowerInvariant + SHA256 앞 16자 경로 규칙과 동일합니다.
    root_key = hashlib.sha256(str(game).lower().encode("utf-8")).hexdigest()[:16].upper()
    storage = Path(local_app_data) / "KingdomIncKoreanPatch/working_private" / root_key / "build_25631786"
    receipt_path = storage / "receipt.json"
    transaction_path = storage / "transaction.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    transaction = json.loads(transaction_path.read_text(encoding="utf-8-sig"))
    assert receipt["status"] == "COMPLETE" and receipt["mode"] == "Install"
    assert receipt["version"] == package["version"] and receipt["candidate"] == package["candidate"]
    assert receipt["files"] == len(package["changes"])
    assert receipt["manifest_sha256"] == package["manifest_sha256"]
    assert same_path(receipt["game_directory"], game) and same_path(receipt["backup_directory"], storage)
    assert transaction["phase"] == "COMPLETE" and transaction["mode"] == "Install"
    assert same_path(transaction["game_directory"], game)
    assert transaction["manifest_sha256"] == package["manifest_sha256"]
    assert transaction["entries"] == [
        {"path": r["path"], "before": before.get(r["path"], {}).get("sha256")}
        for r in package["changes"]
    ], "거래 기록이 실제 설치 전 원본과 다릅니다."
    backups = []
    for i, change in enumerate(package["changes"]):
        path = storage / "cache" / str(i) / "original"
        original_hash = change["original_sha256"] or hashlib.sha256(b"").hexdigest()
        assert sha(path) == original_hash, str(path)
        patched_path = path.with_name("patched")
        assert sha(patched_path) == change["patched_sha256"], str(patched_path)
        backups.append({"path": str(path), "sha256": original_hash,
                        "patched_path": str(patched_path), "patched_sha256": sha(patched_path)})
    return {"backups": backups, "receipt": str(receipt_path), "receipt_sha256": sha(receipt_path),
            "receipt_value": receipt, "transaction_sha256": sha(transaction_path)}


def verify(stage, package_path):
    package_path = Path(package_path).resolve()
    package, expected, pinned_candidate = package_binding(package_path)
    game = Path(r"D:\steam\steamapps\common\Kingdom Inc. Demo")
    output = WORK / ("actual_install_" + package_path.parent.name)
    output.mkdir(exist_ok=True)
    actual = manifest(game)
    changes = {r["path"]: r for r in package["changes"]}
    if stage == "before":
        assert actual == expected, "실제 설치본이 고정한 원본과 다릅니다."
        snapshot(output, "user-before")
        write_json(output / "game-before.json", actual)
        write_json(output / "before.json", {"status": "PASS", "files": len(actual),
                   "game": str(game), "package_sha256": sha(package_path),
                   "zip_sha256": package["zip_sha256"]})
    else:
        before_record = json.loads((output / "before.json").read_text(encoding="utf-8"))
        assert before_record["status"] == "PASS" and same_path(before_record["game"], game)
        assert before_record["package_sha256"] == sha(package_path)
        assert before_record["zip_sha256"] == package["zip_sha256"]
        candidate = ROOT / "build_candidate/KINGDOM_INC_DEMO" / package["candidate"] / "game"
        candidate_manifest = manifest(candidate)
        assert actual == candidate_manifest == pinned_candidate, "실제 설치본·최종 후보·ZIP 생성 기록이 다릅니다."
        before = json.loads((output / "game-before.json").read_text(encoding="utf-8"))
        assert before == expected, "설치 전 파일 기록이 고정한 원본과 다릅니다."
        changed = {p for p in set(actual) | set(before) if actual.get(p) != before.get(p)}
        assert changed == set(changes)
        state = snapshot(output, "user-after")
        user_before = json.loads((output / "user-before.json").read_text(encoding="utf-8"))["state"]
        assert state == user_before, "사용자 저장·설정·Steam 상태가 변경됐습니다."
        installation = verify_receipt(game, package, before, os.environ["LOCALAPPDATA"])
        write_json(output / "game-after.json", actual)
        write_json(output / "after.json", {"status": "PASS", "game": str(game),
                   "files": len(actual), "changed_files": sorted(changed),
                   "added_files": sorted(set(actual) - set(before)),
                   "user_unchanged": True, **installation,
                   "package_sha256": sha(package_path), "verifier_sha256": sha(Path(__file__)),
                   "zip_sha256": package["zip_sha256"],
                   "candidate": package["candidate"]})
    print(json.dumps({"stage": stage, "status": "PASS", "files": len(actual),
                      "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["before", "after"])
    parser.add_argument("--package-report", required=True)
    args = parser.parse_args()
    verify(args.stage, args.package_report)
