"""게임별 경로와 기록을 한곳에서 관리합니다."""
from pathlib import Path
import json, hashlib, subprocess, os
from pck_tools import ROOT, GAME, BASELINE, EXTRACTED, WORK

RECOVERED = EXTRACTED / 'recovered'
PCK = 'HowEmpiresWork.pck'
GDRE = ROOT / 'tools/gdre_2.6.4/bin/gdre_tools.exe'

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))

def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def run_gdre(args, folder, label):
    folder.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for key in ('APPDATA', 'LOCALAPPDATA'):
        dest = WORK / 'tool_profile' / key
        dest.mkdir(parents=True, exist_ok=True)
        env[key] = str(dest)
    command = [str(GDRE), '--headless'] + [str(a) for a in args]
    proc = subprocess.run(command, capture_output=True, env=env, timeout=240)
    (folder / (label + '.stdout.log')).write_bytes(proc.stdout)
    (folder / (label + '.stderr.log')).write_bytes(proc.stderr)
    write_json(folder / (label + '.run.json'), {'command':command, 'exit_code':proc.returncode})
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-2000:].decode('utf-8', errors='replace'))
    return proc
