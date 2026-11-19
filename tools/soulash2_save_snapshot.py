"""기존 저장 영역을 읽고 검증 전후의 내용을 비교한다."""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "working_private/SOULASH_2/save_snapshots"

def sha(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()

def targets():
    paths = []
    for variable in ("APPDATA", "LOCALAPPDATA"):
        root = Path(os.environ[variable])
        for name in ("Soulash 2", "Soulash2"):
            paths.append(root / "WizardsOfTheCode" / name)
    # 문서와 이전 공개 기록의 두 제품명 표기를 모두 감시한다.
    for parent in ("Documents", "Saved Games"):
        for name in ("Soulash 2", "Soulash2"):
            paths.append(Path(os.environ["USERPROFILE"]) / parent / name)
    steam = Path(r"D:\steam\userdata")
    if steam.exists():
        for account in steam.iterdir():
            if account.is_dir() and account.name.isdigit():
                paths.append(account / "2399160")
    return paths

def snapshot(label):
    if not label.replace("_", "").replace("-", "").isalnum():
        raise ValueError("영문·숫자·밑줄·하이픈 이름만 사용합니다.")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    entries = []
    for path in targets():
        record = {"path": str(path), "exists": path.exists(), "files": []}
        if path.exists():
            for file in sorted(path.rglob("*")):
                if file.is_symlink():
                    raise RuntimeError("저장 폴더의 링크를 개별 확인해야 합니다.")
                if file.is_file():
                    stat = file.stat()
                    record["files"].append({"path": file.relative_to(path).as_posix(),
                        "size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": sha(file)})
        entries.append(record)
    report = {"label": label, "created": datetime.now(timezone.utc).isoformat(),
              "script_sha256": sha(Path(__file__)), "targets": entries}
    path = OUTPUT / (label + ".json")
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"snapshot": str(path), "targets": len(entries),
                      "files": sum(len(x["files"]) for x in entries)}))

def compare(left, right):
    first = json.loads((OUTPUT/(left+".json")).read_text(encoding="utf-8"))
    second = json.loads((OUTPUT/(right+".json")).read_text(encoding="utf-8"))
    # 내용뿐 아니라 경로 생성과 수정 시각도 확인한다.
    equal = first["targets"] == second["targets"]
    report = {"check_id": "G5_USER_SAVE_COMPARE", "status": "PASS" if equal else "FAIL",
              "left_sha256": sha(OUTPUT/(left+".json")), "right_sha256": sha(OUTPUT/(right+".json"))}
    with (OUTPUT/f"compare_{left}_{right}.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report))
    if not equal:
        raise SystemExit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("snapshot", "compare"))
    parser.add_argument("labels", nargs="+")
    args = parser.parse_args()
    if args.command == "snapshot" and len(args.labels) == 1:
        snapshot(args.labels[0])
    elif args.command == "compare" and len(args.labels) == 2:
        compare(*args.labels)
    else:
        parser.error("snapshot에는 이름 1개, compare에는 이름 2개가 필요합니다.")
