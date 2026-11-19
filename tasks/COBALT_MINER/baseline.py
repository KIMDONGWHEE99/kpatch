"""설치본을 수정하지 않고 원본 사본·지문을 고정합니다."""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path('D:/steam/steamapps/common/Cobalt Miner')
DEST = ROOT / 'source_original/COBALT_MINER/steam_24347666'
WORK = ROOT / 'working_private/COBALT_MINER/investigation_20261101'

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def main():
    WORK.mkdir(parents=True, exist_ok=True)
    records = []
    for src in sorted(SOURCE.rglob('*')):
        if not src.is_file():
            continue
        rel = src.relative_to(SOURCE)
        dst = DEST / rel
        before = digest(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copy2(src, dst)
        assert digest(src) == before == digest(dst), str(rel)
        records.append({'path': rel.as_posix(), 'size': src.stat().st_size, 'sha256': before})
    result = {'game_id': 'COBALT_MINER', 'build_id': 'steam_24347666', 'app_id': 4601880,
              'created_at': datetime.now(timezone.utc).isoformat(), 'files': records,
              'file_count': len(records), 'total_bytes': sum(x['size'] for x in records),
              'copy_verification': 'PASS'}
    target = WORK / 'baseline_manifest.json'
    if target.exists():
        assert json.loads(target.read_text(encoding='utf-8'))['files'] == records
    else:
        target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    shutil.copy2('D:/steam/steamapps/appmanifest_4601880.acf', WORK / 'steam_manifest.acf')
    print(json.dumps({'files': len(records), 'bytes': result['total_bytes'], 'manifest_sha256': digest(target)}))

if __name__ == '__main__':
    main()
