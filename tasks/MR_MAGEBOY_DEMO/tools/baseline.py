"""원본 보존과 빌드 기준선 기록."""
from pathlib import Path
import hashlib
import json
import shutil
import struct
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
GAME = 'MR_MAGEBOY_DEMO'
BUILD = '25734075'
SOURCE = Path(r'D:\steam\steamapps\common\MR MAGEBOY DEMO')
BASELINE = ROOT / 'source_original' / GAME / ('steam_' + BUILD)
WORK = ROOT / 'working_private' / GAME

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

BASELINE.mkdir(parents=True, exist_ok=True)
WORK.mkdir(parents=True, exist_ok=True)
files = []
for path in sorted(SOURCE.rglob('*')):
    if not path.is_file():
        continue
    relative = path.relative_to(SOURCE)
    destination = BASELINE / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = sha(path)
    if destination.exists():
        assert sha(destination) == digest, relative
    else:
        shutil.copy2(path, destination)
    assert sha(destination) == digest
    files.append({'path': relative.as_posix(), 'size': path.stat().st_size, 'sha256': digest})
shutil.copy2(SOURCE.parents[1] / 'appmanifest_5310040.acf', WORK / 'steam_manifest.acf')
header = (BASELINE / 'MR MAGEBOY DEMO.pck').open('rb').read(40)
record = {'game_id': GAME, 'build_id': BUILD, 'appid': '5310040',
          'time': datetime.now(timezone.utc).isoformat(), 'source': str(SOURCE),
          'pck_version': struct.unpack_from('<I', header, 4)[0],
          'engine_version': '.'.join(map(str, struct.unpack_from('<III', header, 8))),
          'python': sys.version, 'files': files}
output = WORK / 'baseline.json'
output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(record, ensure_ascii=False, indent=2))
