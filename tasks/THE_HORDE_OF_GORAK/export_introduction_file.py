"""확인된 업로드 목록의 파일만 작은 조각으로 전달합니다."""
import base64
import hashlib
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
work = root / 'working_private/THE_HORDE_OF_GORAK/introduction_20261102'
manifest = json.loads((work / 'upload_manifest.json').read_text(encoding='utf-8'))
if len(sys.argv) == 1:
    print(json.dumps(manifest, ensure_ascii=True))
else:
    entry = manifest['files'][int(sys.argv[1])]
    raw = (work / 'repository' / entry['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry['sha256']
    encoded = base64.b64encode(raw).decode('ascii')
    start = int(sys.argv[2])
    length = int(sys.argv[3])
    print(encoded[start:start + length])
