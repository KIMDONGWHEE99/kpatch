"""Soulash 2 원본을 복사하고 전후 내용 지문을 검증한다."""
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"D:\steam\steamapps\common\Soulash 2")
DEST = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
EVIDENCE = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029"

def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def main():
    started = datetime.now(timezone.utc).isoformat()
    if DEST.exists():
        raise SystemExit("기준선 경로가 이미 존재하므로 덮어쓰지 않습니다.")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in SOURCE.rglob("*") if p.is_file())
    total = sum(p.stat().st_size for p in files)
    free = shutil.disk_usage(ROOT).free
    if free < total * 3 + 1024**3:
        raise SystemExit("안전한 작업 여유 공간이 부족합니다.")
    entries = []
    for path in files:
        if path.is_symlink():
            raise RuntimeError(f"심볼릭 링크 확인 필요: {path}")
        rel = path.relative_to(SOURCE)
        before = digest(path)
        target = DEST / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        after = digest(path)
        copied = digest(target)
        if before != after or before != copied:
            raise RuntimeError(f"원본 변경 또는 복사 불일치: {rel}")
        entries.append({"path": rel.as_posix(), "size": target.stat().st_size, "sha256": copied})
    report = {"game_id": "SOULASH_2", "baseline_id": DEST.name, "started": started,
              "finished": datetime.now(timezone.utc).isoformat(), "source": str(SOURCE),
              "destination": str(DEST), "file_count": len(entries), "total_bytes": total,
              "files": entries}
    output = EVIDENCE / "baseline_manifest.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"files": len(entries), "bytes": total, "free": free,
                      "manifest_sha256": digest(output), "baseline": str(DEST)}))

if __name__ == "__main__":
    main()
