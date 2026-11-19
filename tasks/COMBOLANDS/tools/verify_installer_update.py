"""최종 ZIP 설치기를 별도 한글 경로의 원본 사본에 적용하고 복원합니다."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / 'working_private/COMBOLANDS/run_20260906/package_1.0.1'
package = WORK / 'from_final_zip'
game = WORK / '다른 설치 위치 [한글 공백]/Combolands'
manifest = json.loads((package / 'manifest.json').read_text(encoding='utf8'))
assert game.resolve().is_relative_to((ROOT / 'working_private').resolve())
if not game.exists():
    shutil.copytree(ROOT / 'source_original/COMBOLANDS/steam_20260906/game', game)
environment = {key.upper(): value for key, value in os.environ.items()}
environment['LOCALAPPDATA'] = str(WORK / 'isolated_appdata')
powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
# 작업 도구의 PowerShell 7 전용 환경을 Windows 기본 PowerShell에 넘기지 않습니다.
environment['PSMODULEPATH'] = str(powershell.parent / 'Modules')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(expected):
    actual = {p.relative_to(game).as_posix(): sha(p) for p in game.rglob('*') if p.is_file()}
    assert actual == expected, [key for key in actual.keys() | expected.keys() if actual.get(key) != expected.get(key)]
    return len(actual)


original = {item['path']: item['sha256'] for item in manifest['baseline']}
patched = original | {item['path']: item['patched_sha256'] for item in manifest['changes']}
check(original)
results = []
for mode, expected in [('Install', patched), ('Uninstall', original)]:
    process = subprocess.run([
        str(powershell), '-NoLogo', '-NoProfile', '-NonInteractive', '-STA',
        '-ExecutionPolicy', 'Bypass', '-File', str(package / 'Patch.ps1'),
        '-Mode', mode, '-GameDirectory', str(game),
    ], env=environment, capture_output=True)
    (WORK / (mode.lower() + '_stdout.log')).write_bytes(process.stdout)
    (WORK / (mode.lower() + '_stderr.log')).write_bytes(process.stderr)
    assert process.returncode == 0, (mode, process.stderr.decode('utf8', errors='replace'))
    results.append(dict(mode=mode, status='PASS', exit_code=process.returncode, files_checked=check(expected)))
report = dict(
    status='PASS', version=manifest['version'], candidate=manifest['candidate'],
    zip_sha256=sha(ROOT / 'release_output/COMBOLANDS_KOREAN_PATCH_1.0.1.zip'),
    manifest_sha256=sha(package / 'manifest.json'),
    installer_sha256=sha(package / 'Patch.ps1'), tool_sha256=sha(Path(__file__)),
    test_directory=str(game), user_installation_modified=False, user_game_executed=False,
    results=results,
)
(WORK / 'install_remove_validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print(json.dumps(dict(status='PASS', results=results, zip_sha256=report['zip_sha256']), ensure_ascii=False))
