"""설치본을 읽기 전용으로 복사하고 기준선의 파일 지문을 검증합니다."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
from datetime import datetime, timezone


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def long_path(path):
    value = os.path.abspath(path)
    return Path(value if value.startswith("\\\\?\\") else "\\\\?\\" + value)


def display_path(path):
    return str(path).removeprefix("\\\\?\\")


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def inventory(root):
    entries = []
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix().casefold()):
        if path.is_symlink():
            raise RuntimeError(f"연결 파일은 수동 검토가 필요합니다: {path}")
        if path.is_file():
            stat = path.stat()
            entries.append({"path": path.relative_to(root).as_posix(), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
    return entries


def priority(entry):
    name = entry["path"].lower()
    base = Path(name).name
    return 0 if ("streamingassets/" in name and entry["size"] <= 10 * 1024 * 1024) or base in {
        "globalgamemanagers", "resources.assets", "gameassembly.dll", "global-metadata.dat", "boot.config"
    } else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    started = timestamp()
    # 읽기 전용 원본에는 디렉터리 핸들을 여는 resolve 대신 절대 경로를 씁니다.
    source = long_path(args.source)
    appmanifest = Path(os.path.abspath(args.manifest))
    workspace = Path(os.path.abspath(args.workspace))
    manifest_bytes = appmanifest.read_bytes()
    build_match = re.search(rb'"buildid"\s+"(\d+)"', manifest_bytes)
    if not build_match:
        raise RuntimeError("Steam 빌드 번호를 찾지 못했습니다.")
    build_id = build_match.group(1).decode("ascii")
    target = long_path(workspace / "source_original" / "ALASKA_GOLD_FEVER" / build_id / "game")
    evidence = workspace / "extracted_private" / "ALASKA_GOLD_FEVER" / build_id
    if target.exists() and not args.resume:
        raise RuntimeError(f"기존 기준선을 덮어쓸 수 없습니다: {target}")
    if args.resume:
        old_report = evidence / "baseline_manifest.json"
        if not old_report.exists() or json.loads(old_report.read_text(encoding="utf-8"))["status"] != "FAIL":
            raise RuntimeError("실패 기록이 있는 중단 기준선만 이어서 작성할 수 있습니다.")
        for name in ("baseline_manifest.json", "baseline_manifest.sha256", "source_inventory_initial.json"):
            previous = evidence / name
            previous.rename(evidence / (previous.stem + "_failed_path_length" + previous.suffix))
    target.mkdir(parents=True, exist_ok=args.resume)
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "appmanifest_original.acf").write_bytes(manifest_bytes)
    initial = inventory(source)
    write_json(evidence / "source_inventory_initial.json", initial)
    total_bytes = sum(entry["size"] for entry in initial)
    if shutil.disk_usage(target).free < total_bytes + 1024 ** 3:
        raise RuntimeError("복사에 필요한 여유 공간이 없습니다.")
    result = {
        "game_id": "ALASKA_GOLD_FEVER", "build_id": build_id,
        "check_id": "G0_BASELINE_FILES", "status": "NOT_RUN",
        "started_at": started, "source": display_path(source), "target": display_path(target),
        "appmanifest_source": str(appmanifest), "appmanifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "command": sys.argv, "python_version": sys.version, "platform": platform.platform(),
        "tool_sha256": digest(Path(os.path.abspath(__file__))), "file_count": len(initial),
        "total_bytes": total_bytes, "failures": [], "files": [],
    }
    ordered = sorted(initial, key=lambda entry: (priority(entry), entry["path"].casefold()))
    early_count = sum(priority(entry) == 0 for entry in ordered)
    try:
        for index, entry in enumerate(ordered, 1):
            origin = source / entry["path"]
            copied = target / entry["path"]
            copied.parent.mkdir(parents=True, exist_ok=True)
            if copied.exists() and args.resume:
                source_hash = digest(origin)
            else:
                copied_hash = hashlib.sha256()
                with origin.open("rb") as reader, copied.open("xb") as writer:
                    while block := reader.read(8 * 1024 * 1024):
                        copied_hash.update(block)
                        writer.write(block)
                shutil.copystat(origin, copied)
                source_hash = copied_hash.hexdigest()
            target_hash = digest(copied)
            stat = origin.stat()
            if stat.st_size != entry["size"] or stat.st_mtime_ns != entry["mtime_ns"] or copied.stat().st_size != entry["size"] or source_hash != target_hash:
                raise RuntimeError(f"복사 중 변경 또는 사본 불일치: {entry['path']}")
            result["files"].append({**entry, "sha256": source_hash, "copy_sha256": target_hash})
            if index == early_count:
                write_json(evidence / "priority_files_ready.json", {"build_id": build_id, "ready_at": timestamp(), "target": display_path(target), "files": result["files"]})
                print(json.dumps({"event": "priority_files_ready", "count": early_count, "path": display_path(target)}, ensure_ascii=False), flush=True)
            if index % 25 == 0 or index == len(ordered):
                print(json.dumps({"event": "copy_progress", "completed": index, "total": len(ordered)}, ensure_ascii=False), flush=True)
        final_inventory = inventory(source)
        if final_inventory != initial:
            raise RuntimeError("복사 전후 설치본 목록 또는 파일 정보가 달라졌습니다.")
        for index, entry in enumerate(result["files"], 1):
            current_hash = digest(source / entry["path"])
            entry["source_post_sha256"] = current_hash
            if current_hash != entry["sha256"]:
                result["failures"].append({"path": entry["path"], "reason": "source_hash_changed"})
            if index % 100 == 0 or index == len(ordered):
                print(json.dumps({"event": "source_recheck_progress", "completed": index, "total": len(ordered)}, ensure_ascii=False), flush=True)
        if appmanifest.read_bytes() != manifest_bytes:
            result["failures"].append({"reason": "appmanifest_changed"})
        target_entries = inventory(target)
        if {(e["path"], e["size"]) for e in target_entries} != {(e["path"], e["size"]) for e in initial}:
            result["failures"].append({"reason": "copy_inventory_mismatch"})
        result["status"] = "PASS" if not result["failures"] else "FAIL"
        result["exit_code"] = 0 if result["status"] == "PASS" else 1
    except Exception as error:
        result["status"] = "FAIL"
        result["exit_code"] = 1
        result["failures"].append({"reason": str(error)})
    result["files"].sort(key=lambda entry: entry["path"].casefold())
    result["finished_at"] = timestamp()
    report = evidence / "baseline_manifest.json"
    write_json(report, result)
    report_hash = digest(report)
    (evidence / "baseline_manifest.sha256").write_text(f"{report_hash}  baseline_manifest.json\n", encoding="ascii")
    print(json.dumps({"event": "finished", "status": result["status"], "file_count": len(result["files"]), "total_bytes": total_bytes, "manifest": str(report), "manifest_sha256": report_hash, "failures": result["failures"]}, ensure_ascii=False), flush=True)
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
