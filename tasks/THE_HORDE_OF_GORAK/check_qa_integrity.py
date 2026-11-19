"""검수 실행 전후의 사용자 파일과 설치본 내용을 독립 비교한다."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GAME = 'THE_HORDE_OF_GORAK'
INSTALLED = Path('D:/steam/steamapps/common/The Horde of Gorak')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    qa = ROOT / 'working_private' / GAME / sys.argv[1]
    before = json.loads((qa / 'evidence/prelaunch.json').read_text(encoding='utf-8'))
    manifest = json.loads((ROOT / 'working_private' / GAME / 'investigation_20261031/baseline_manifest.json').read_text(encoding='utf-8'))
    failures = []
    for row in manifest['files']:
        path = INSTALLED / row['path']
        if not path.is_file() or sha(path) != row['sha256']:
            failures.append({'kind':'installed_changed', 'path':row['path']})
    expected = {r['path']:r for r in before['user_files_before']}
    found = {}
    for root in map(Path, before['monitored_roots']):
        if root.name == 'userdata':
            files = [p for account in root.iterdir() if account.is_dir() for p in (account / '4911050').rglob('*') if p.is_file()]
        elif root.is_dir():
            files = [p for p in root.rglob('*') if p.is_file()]
        else:
            files = [root] if root.is_file() else []
        for path in files:
            found[str(path)] = {'path':str(path),'size':path.stat().st_size,'sha256':sha(path)}
    for path in sorted(expected.keys() | found.keys()):
        if expected.get(path) != found.get(path):
            failures.append({'kind':'user_file_changed', 'path':path})
    baseline_acf = ROOT / 'working_private' / GAME / 'investigation_20261031/steam_manifest.acf'
    current_acf = Path('D:/steam/steamapps/appmanifest_4911050.acf')
    result = {'status':'PASS' if not failures else 'FAIL', 'installed_files':len(manifest['files']),
              'user_files':len(expected), 'monitored_roots':before['monitored_roots'],
              'steam_manifest_unchanged':sha(baseline_acf)==sha(current_acf), 'failures':failures,
              'limitation':'명시한 파일 영역 비교이며 운영체제 전체 또는 Steam 내부 설정 전체 비교가 아닙니다.'}
    (qa / 'evidence/post_integrity.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    return bool(failures)

if __name__ == '__main__':
    raise SystemExit(main())
