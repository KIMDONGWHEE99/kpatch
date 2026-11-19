"""설치본을 읽기만 하여 독립 원본 사본과 내용 지문을 만든다."""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GAME = "THE_HORDE_OF_GORAK"
SOURCE = Path("D:/steam/steamapps/common/The Horde of Gorak")
DEST = ROOT / "source_original" / GAME / "steam_26336311"
WORK = ROOT / "working_private" / GAME / "investigation_20261031"

def digest(path):
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    WORK.mkdir(parents=True, exist_ok=True)
    records = []
    for src in sorted(SOURCE.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(SOURCE)
        dst = DEST / rel
        before = digest(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copy2(src, dst)
        assert digest(src) == before == digest(dst), str(rel)
        records.append({"path": rel.as_posix(), "size": src.stat().st_size, "sha256": before})
    result = {"game_id": GAME, "build_id": "steam_26336311", "app_id": 4911050,
              "created_at": datetime.now(timezone.utc).isoformat(), "files": records,
              "file_count": len(records), "total_bytes": sum(x["size"] for x in records),
              "copy_verification": "PASS"}
    target = WORK / "baseline_manifest.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    shutil.copy2("D:/steam/steamapps/appmanifest_4911050.acf", WORK / "steam_manifest.acf")
    print(json.dumps({"files": len(records), "bytes": result["total_bytes"], "manifest_sha256": digest(target), "target": str(target)}))

if __name__ == "__main__":
    main()
