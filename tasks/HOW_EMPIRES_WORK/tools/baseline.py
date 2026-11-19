"""원본 지문 확인, 독립 사본 확보, Godot 자산 복원 시작."""
from pathlib import Path
import hashlib, json, shutil, struct, subprocess, os, datetime

ROOT = Path(__file__).resolve().parents[3]
GAME = 'HOW_EMPIRES_WORK'
SOURCE = Path('D:/steam/steamapps/common/How Empires Work')
BASE = ROOT / 'source_original' / GAME / 'steam_26482667'
WORK = ROOT / 'working_private' / GAME
EXTRACTED = ROOT / 'extracted_private' / GAME / 'steam_26482667'

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
        assert sha(dest) == digest == sha(src), name
        rows.append({'path': name, 'size': src.stat().st_size, 'sha256': digest})
    data = {'game_id': GAME, 'build_id': 'steam_26482667', 'app_id': 4663730,
            'created': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'files': rows}
    (WORK / 'baseline.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    header = (BASE / 'HowEmpiresWork.pck').open('rb').read(40)
    print('Baseline', len(rows), sum(x['size'] for x in rows), 'PCK header', struct.unpack('<6I2Q', header), flush=True)
    env = os.environ.copy()
    for key in ['APPDATA', 'LOCALAPPDATA']:
        path = WORK / 'tool_profile' / key
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    cmd = [str(ROOT / 'tools/gdre_2.6.4/bin/gdre_tools.exe'), '--headless',
           '--recover=' + str(BASE / 'HowEmpiresWork.pck'), '--output=' + str(EXTRACTED / 'recovered')]
    with (WORK / 'recover.stdout.log').open('wb') as out, (WORK / 'recover.stderr.log').open('wb') as err:
        result = subprocess.run(cmd, env=env, stdout=out, stderr=err)
    (WORK / 'recover_run.json').write_text(json.dumps({'command': cmd, 'returncode': result.returncode}), encoding='utf-8')
    print('Recovery exit', result.returncode)

if __name__ == '__main__':
    main()
