"""최종 ZIP을 지정한 설치본에 적용하고 복구 원본과 저장 보존을 기록합니다."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / 'working_private/MR_MAGEBOY_DEMO'
GAME = Path('D:/steam/steamapps/common/MR MAGEBOY DEMO')
OUT = WORK / 'installation_1.0.0_c06'
OUT.mkdir(parents=True, exist_ok=True)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def snapshot():
    roots = [Path(os.environ['APPDATA']) / 'Godot/app_userdata/MR MAGEBOY DEMO',
             Path(os.environ['APPDATA']) / 'MR MAGEBOY DEMO']
    roots += list(Path('D:/steam/userdata').glob('*/5310040'))
    roots += list(Path('D:/steam/userdata').glob('*/4483400'))
    return [{'root': str(root), 'exists': root.exists(), 'files':
             [{'path': path.relative_to(root).as_posix(), 'size': path.stat().st_size,
               'sha256': digest(path)} for path in sorted(root.rglob('*')) if path.is_file()]
             if root.exists() else []} for root in roots]


package = json.loads((WORK / 'package_1.0.0_r3/package.json').read_text(encoding='utf-8'))
assert package['G6'] == package['G7'] == package['independent_G4'] == 'PASS'
tested_zip = Path(package['archive'])
assert digest(tested_zip) == package['zip_sha256']
canonical_zip = ROOT / 'release_output/MR_MAGEBOY_DEMO_KOREAN_PATCH_1.0.0.zip'
assert not canonical_zip.exists() or digest(canonical_zip) == package['zip_sha256']
shutil.copy2(tested_zip, canonical_zip)
assert digest(canonical_zip) == package['zip_sha256']
extracted = OUT / 'from_final_zip'
extracted.mkdir(exist_ok=True)
with zipfile.ZipFile(canonical_zip) as archive:
    assert sorted(archive.namelist()) == sorted(package['allowed_files'])
    archive.extractall(extracted)
assert digest(extracted / 'manifest.json') == package['manifest_sha256']
manifest = json.loads((extracted / 'manifest.json').read_text(encoding='utf-8'))
for row in manifest['payload']:
    path = extracted / row['path']
    assert path.stat().st_size == row['size'] and digest(path) == row['sha256']

# 추가 플레이 검수는 사용자 요청에 따라 중단하며 설치 무결성만 확인합니다.
before = [{'path': row['path'], 'size': (GAME / row['path']).stat().st_size,
           'sha256': digest(GAME / row['path'])} for row in manifest['baseline']]
for expected, actual in zip(manifest['baseline'], before):
    assert actual['sha256'] == expected['sha256'], '지원 원본과 설치본이 다릅니다.'
save_before = snapshot()
write('game_before.json', before)
write('user_save_before.json', save_before)
command = ['powershell.exe', '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
           '-File', str(extracted / 'Patch.ps1'), '-Mode', 'Install', '-GameDirectory', str(GAME)]
result = subprocess.run(command, capture_output=True)
(OUT / 'install_stdout.txt').write_bytes(result.stdout)
(OUT / 'install_stderr.txt').write_bytes(result.stderr)
assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')
after = [{'path': row['path'], 'size': (GAME / row['path']).stat().st_size,
          'sha256': digest(GAME / row['path'])} for row in manifest['baseline']]
expected_hashes = {row['path']: row['sha256'] for row in manifest['baseline']}
expected_hashes.update({row['path']: row['patched_sha256'] for row in manifest['changes']})
assert all(row['sha256'] == expected_hashes[row['path']] for row in after)
save_after = snapshot()
write('game_after.json', after)
write('user_save_after.json', save_after)
assert save_before == save_after, '사용자 저장 또는 설정이 달라졌습니다.'
key = hashlib.sha256(str(GAME).lower().encode('utf-8')).hexdigest()[:16].upper()
backup = Path(os.environ['LOCALAPPDATA']) / 'MRMageboyKoreanPatch/working_private' / key / 'build_25734075'
receipt = json.loads((backup / 'receipt.json').read_text(encoding='utf-8-sig'))
transaction = json.loads((backup / 'transaction.json').read_text(encoding='utf-8-sig'))
assert receipt['status'] == 'COMPLETE' and receipt['mode'] == 'Install'
assert receipt['manifest_sha256'] == package['manifest_sha256']
backup_files = []
for index, row in enumerate(manifest['changes']):
    path = backup / f'cache/{index}/original'
    assert digest(path) == row['original_sha256']
    backup_files.append({'path': row['path'], 'sha256': digest(path)})
report = {'status': 'PASS', 'completed_utc': datetime.now(timezone.utc).isoformat(),
          'user_request': '검수 그만하고 마무리하세요', 'additional_runtime_qa': 'NOT_RUN',
          'game_directory': str(GAME), 'candidate': manifest['candidate'],
          'steam_build': manifest['steam_build'], 'canonical_zip': str(canonical_zip),
          'zip_sha256': digest(canonical_zip), 'manifest_sha256': package['manifest_sha256'],
          'installer_sha256': digest(extracted / 'Patch.ps1'), 'installer_exit_code': result.returncode,
          'game_files': after, 'backup_directory': str(backup), 'original_backup_files': backup_files,
          'transaction_phase': transaction['phase'], 'user_save_integrity': 'PASS',
          'user_save_roots': len(save_before), 'user_save_file_count': sum(len(row['files']) for row in save_before),
          'external_upload': 'NOT_RUN', 'all_gates_passed': False}
write('installation_report.json', report)
print(json.dumps({'status': report['status'], 'game_directory': str(GAME),
                  'installed_files': len(manifest['changes']), 'verified_files': len(after),
                  'user_save_integrity': 'PASS', 'backup_directory': str(backup)}, ensure_ascii=False))
