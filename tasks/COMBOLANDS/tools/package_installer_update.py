"""검증된 차이 파일을 유지하고 폴더 선택 기능을 담은 새 배포본을 만듭니다."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / 'working_private/COMBOLANDS/run_20260906'
old_release = ROOT / 'release_output/COMBOLANDS_KOREAN_PATCH_1.0.0'
release = ROOT / 'release_output/COMBOLANDS_KOREAN_PATCH_1.0.1'
scratch = WORK / 'package_1.0.1'
template = ROOT / 'tasks/COMBOLANDS/release_template'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


assert not release.exists() and not scratch.exists()
previous = json.loads((WORK / 'package_1.0.0/final_package_validation.json').read_text(encoding='utf8'))
assert sha(old_release / 'manifest.json') == previous['manifest_sha256']
assert sha(old_release.with_name(old_release.name + '.zip')) == previous['zip_sha256']
manifest = json.loads((old_release / 'manifest.json').read_text(encoding='utf8'))
for item in manifest['payload']:
    assert sha(old_release / item['path']) == item['sha256']
shutil.copytree(old_release, release)
scratch.mkdir()
for name in ('Patch.ps1', 'ChooseGame.ps1', 'README.txt'):
    (release / name).write_text((template / name).read_text(encoding='utf-8-sig'), encoding='utf-8-sig')
for name, mode in [('Install.cmd', 'Install'), ('Remove.cmd', 'Uninstall')]:
    (release / name).write_text(
        '@echo off\ncd /d "%~dp0"\npowershell.exe -NoLogo -NoProfile -STA '
        '-ExecutionPolicy Bypass -File "%~dp0Patch.ps1" -Mode ' + mode + ' %*\n'
        'set "PATCH_EXIT=%ERRORLEVEL%"\npause\nexit /b %PATCH_EXIT%\n',
        encoding='ascii', newline='\r\n')

changed_payload = {'Patch.ps1', 'ChooseGame.ps1', 'Install.cmd', 'Remove.cmd', 'README.txt'}
for item in manifest['payload']:
    if item['path'] not in changed_payload:
        assert sha(release / item['path']) == item['sha256']
manifest['version'] = '1.0.1'
manifest['payload'] = [
    dict(path=p.relative_to(release).as_posix(), sha256=sha(p), size=p.stat().st_size)
    for p in sorted(release.rglob('*')) if p.is_file() and p.name != 'manifest.json'
]
save(release / 'manifest.json', manifest)
allowed = {'Patch.ps1', 'ChooseGame.ps1', 'Install.cmd', 'Remove.cmd', 'README.txt',
           'manifest.json', 'tools/xdelta3.exe', 'licenses/NotoSansKR-OFL.txt',
           'licenses/xdelta3-APACHE-2.0.txt'}
for item in manifest['changes']:
    allowed.add(item['forward'])
    if item['reverse']:
        allowed.add(item['reverse'])
assert {p.relative_to(release).as_posix() for p in release.rglob('*') if p.is_file()} == allowed
archive = release.with_name(release.name + '.zip')
assert not archive.exists()
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for relative in sorted(allowed):
        z.write(release / relative, relative)
extracted = scratch / 'from_final_zip'
with zipfile.ZipFile(archive) as z:
    assert len(z.namelist()) == len(allowed) and set(z.namelist()) == allowed
    assert z.testzip() is None
    z.extractall(extracted)
for relative in allowed:
    assert sha(extracted / relative) == sha(release / relative)
save(scratch / 'package_validation.json', dict(
    status='PASS', version='1.0.1', candidate=manifest['candidate'],
    zip_sha256=sha(archive), zip_bytes=archive.stat().st_size,
    manifest_sha256=sha(release / 'manifest.json'), files=len(allowed),
    delta_payload_unchanged=True, game_changes_unchanged=True,
    previous_package_evidence_sha256=sha(WORK / 'package_1.0.0/final_package_validation.json'),
    packaging_tool_sha256=sha(__file__), extracted=str(extracted)))
print(json.dumps(dict(zip=str(archive), bytes=archive.stat().st_size, sha256=sha(archive)), ensure_ascii=False))
