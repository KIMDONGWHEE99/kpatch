"""설치본을 변경하지 않고 독립 사본과 내용 지문을 고정합니다."""
from common import *
import shutil

if __name__ == "__main__":
    records = []
    for path in sorted(INSTALL.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(INSTALL)
        dest = SOURCE / rel
        digest = sha(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(path, dest)
        assert sha(dest) == digest, str(rel)
        records.append({"path": rel.as_posix(), "size": path.stat().st_size, "sha256": digest})
    write_json(EXTRACT / "baseline.json", {
        "game_id": GAME_ID, "steam_app_id": 4702410, "build_id": BUILD, "files": records
    })
    shutil.copy2(Path(r"D:\steam\steamapps\appmanifest_4702410.acf"), EXTRACT / "appmanifest.acf")
    print(json.dumps({"files": len(records), "bytes": sum(r["size"] for r in records),
                      "manifest_sha256": sha(EXTRACT / "baseline.json")}))
