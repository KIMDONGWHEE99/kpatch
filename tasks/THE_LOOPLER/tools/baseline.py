"""설치본을 읽어 원본 사본과 내용 지문을 고정합니다."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[3]
INSTALL = Path(r'D:\steam\steamapps\common\The Loopler')
SOURCE = ROOT / 'source_original/THE_LOOPLER/steam_25262314/game'
EXTRACT = ROOT / 'extracted_private/THE_LOOPLER/steam_25262314'

def sha(path):
    return hashlib.file_digest(path.open('rb'), 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(path.read_bytes()).hexdigest()

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

if __name__ == '__main__':
    records = []
    for path in sorted(INSTALL.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(INSTALL)
        digest = sha(path)
        dest = SOURCE / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(path, dest)
        assert sha(dest) == digest, str(rel)
        records.append({'path': rel.as_posix(), 'size': path.stat().st_size, 'sha256': digest})
    write_json(EXTRACT / 'baseline.json', {'game_id': 'THE_LOOPLER', 'steam_app_id': 4150860, 'build_id': '25262314', 'files': records})
    shutil.copy2(Path(r'D:\steam\steamapps\appmanifest_4150860.acf'), EXTRACT / 'appmanifest_4150860.acf')
    print(json.dumps({'files': len(records), 'bytes': sum(r['size'] for r in records), 'manifest_sha256': sha(EXTRACT / 'baseline.json')}))
