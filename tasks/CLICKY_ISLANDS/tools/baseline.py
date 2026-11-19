"""원본 지문 확인과 독립 사본 확보(G0).

HOW_EMPIRES_WORK의 baseline.py를 복사해 게임 이름·빌드·경로를 바꿨습니다.
실제 게임 폴더는 읽기만 하고, 사본은 source_original 아래에만 만듭니다.
"""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import struct

ROOT = Path(__file__).resolve().parents[3]
GAME = 'CLICKY_ISLANDS'
BUILD = 'steam_26701014'
APP_ID = 4178790
SOURCE = Path('D:/steam/steamapps/common/Clicky Islands')
BASE = ROOT / 'source_original' / GAME / BUILD
WORK = ROOT / 'working_private' / GAME


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    BASE.mkdir(parents=True, exist_ok=True)
    rows = []
    for src in sorted(SOURCE.rglob('*')):
        if not src.is_file():
            continue
        name = src.relative_to(SOURCE).as_posix()
        digest = sha(src)
        dest = BASE / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(src, dest)
        # 복사 뒤에 사본과 설치본을 다시 읽어 세 값이 같은지 확인합니다.
        assert sha(dest) == digest == sha(src), name
        rows.append({'path': name, 'size': src.stat().st_size, 'sha256': digest})
    extra = sorted(p.relative_to(BASE).as_posix() for p in BASE.rglob('*') if p.is_file())
    assert extra == [r['path'] for r in rows], '사본에 설치본에 없는 파일이 있습니다.'
    data = {'game_id': GAME, 'build_id': BUILD, 'app_id': APP_ID, 'source': str(SOURCE),
            'created': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'files': rows,
            'file_count': len(rows), 'total_bytes': sum(r['size'] for r in rows)}
    target = WORK / 'baseline.json'
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    header = (BASE / 'Clicky Islands.pck').open('rb').read(40)
    magic, version, major, minor, patch, flags, base, directory = struct.unpack('<4s5I2Q', header)
    print('Baseline', len(rows), data['total_bytes'], 'manifest_sha256', sha(target))
    print('PCK', magic, 'v', version, 'engine', major, minor, patch, 'flags', flags, 'base', base, 'dir', directory)
    for r in rows:
        print(r['sha256'], r['size'], r['path'])


if __name__ == '__main__':
    main()
