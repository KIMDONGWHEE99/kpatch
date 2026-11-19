"""지정 설치본의 교정 파일만 백업·적용·복원하는 개인용 도구입니다."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
GAME = Path(r'D:\steam\steamapps\common\Alaska Gold Fever')
DATA = 'Alaska Gold Fever_Data/'
AA = DATA + 'StreamingAssets/aa/'
ALLOWED = {
    DATA + 'resources.assets', DATA + 'sharedassets2.assets', DATA + 'sharedassets3.assets',
    AA + 'catalog.bin', AA + 'catalog.hash',
    AA + 'StandaloneWindows64/localization-string-tables-korean(ko)_assets_all.bundle',
    AA + 'StandaloneWindows64/localization-string-tables-korean_assets_all.bundle',
}
STATE = ROOT / 'working_private/ALASKA_GOLD_FEVER/installation'
BACKUP = ROOT / 'source_original/ALASKA_GOLD_FEVER/installation_backup'
CANDIDATES = ROOT / 'build_candidate/ALASKA_GOLD_FEVER'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.new')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    os.replace(temp, path)


def process_check():
    # 게임 실행 중에는 덮어쓰지 않습니다.
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-Command',
         "@(Get-Process -Name 'Alaska Gold Fever' -ErrorAction SilentlyContinue).Count"],
        capture_output=True, text=True, check=True)
    if result.stdout.strip() != '0':
        raise RuntimeError('게임을 종료한 뒤 다시 실행해 주세요.')


def target(relative):
    if relative not in ALLOWED:
        raise ValueError('허용되지 않은 파일입니다: '+relative)
    result = (GAME / relative).resolve(strict=True)
    result.relative_to(GAME.resolve(strict=True))
    return result


def write_game(source, destination, expected):
    # 임시 게임 자산은 만들지 않으며, 기록 직후 내용 지문을 확인합니다.
    with source.open('rb') as src, destination.open('wb') as dst:
        shutil.copyfileobj(src, dst, length=8*1024*1024)
        dst.flush()
        os.fsync(dst.fileno())
    if digest(destination) != expected:
        raise RuntimeError('파일 기록 후 확인에 실패했습니다: '+str(destination))


def restore(journal, journal_path):
    if Path(journal['game_path']).resolve() != GAME.resolve():
        raise ValueError('복원 대상 경로가 다릅니다.')
    for r in journal['game_identity']:
        if digest(GAME / r['path']) != r['sha256']:
            raise ValueError('게임이 업데이트되거나 실행 파일이 바뀌어 복원을 멈췄습니다.')
    backup_dir = Path(journal['backup_path']).resolve(strict=True)
    backup_dir.relative_to(BACKUP.resolve(strict=True))
    records = journal['files']
    if {r['path'] for r in records} != ALLOWED or len(records) != len(ALLOWED):
        raise ValueError('복원 파일 목록이 다릅니다.')
    interrupted = journal['status'] in ('INSTALLING', 'ROLLING_BACK', 'FAILED_RECOVERY_REQUIRED', 'RESTORING')
    for r in records:
        if digest(backup_dir / r['path']) != r['source_sha256']:
            raise ValueError('백업 파일이 바뀌었습니다: '+r['path'])
        actual = digest(target(r['path']))
        if actual not in {r['source_sha256'], r['candidate_sha256']}:
            if not (interrupted and r.get('write_started')):
                raise ValueError('게임 업데이트 또는 다른 수정이 발견되어 복원을 멈췄습니다: '+r['path'])
    journal['status'] = 'RESTORING'
    save(journal_path, journal)
    for r in records:
        write_game(backup_dir / r['path'], target(r['path']), r['source_sha256'])
        r['restored'] = True
        save(journal_path, journal)
    journal['status'] = 'RESTORED'
    journal['restored_utc'] = datetime.now(timezone.utc).isoformat()
    save(journal_path, journal)


def install(candidate):
    candidate = candidate.resolve(strict=True)
    candidate.relative_to(CANDIDATES.resolve(strict=True))
    manifest_path = candidate / 'build_manifest.json'
    manifest = load(manifest_path)
    if manifest['build_id'] != '25782395' or manifest['build_status'] != 'PASS':
        raise ValueError('후보 생성 상태가 정상적이지 않습니다.')
    report = load(candidate / 'verification.json')
    if report.get('status') != 'PASS' or report.get('candidate_manifest_sha256') != digest(manifest_path):
        raise ValueError('후보 파일 기본 확인을 먼저 완료해야 합니다.')
    records = manifest['files']
    if {r['path'] for r in records} != ALLOWED or len(records) != len(ALLOWED):
        raise ValueError('변경 파일은 번역·글꼴·목록의 7개로 제한됩니다.')
    # 모든 입력을 확인한 다음에만 백업과 설치를 시작합니다.
    for r in records:
        if digest(candidate / 'overlay' / r['path']) != r['candidate_sha256']:
            raise ValueError('후보 파일이 바뀌었습니다: '+r['path'])
        if digest(target(r['path'])) != r['source_sha256']:
            raise ValueError('지원하는 원본과 다릅니다. 덮어쓰지 않습니다: '+r['path'])
    baseline = load(ROOT / manifest['baseline_manifest']['path'])
    identity = []
    for r in baseline['files']:
        if r['path'] in ('Alaska Gold Fever.exe', 'GameAssembly.dll', DATA+'globalgamemanagers'):
            if digest(GAME / r['path']) != r['sha256']:
                raise ValueError('게임 실행 파일의 버전 또는 내용이 다릅니다.')
            identity.append({'path':r['path'], 'sha256':r['sha256']})
    if len(identity) != 3:
        raise ValueError('원본의 실행 파일 정보가 부족합니다.')
    journal_path = STATE / 'current.json'
    if journal_path.exists() and load(journal_path)['status'] not in ('RESTORED', 'ROLLED_BACK'):
        raise ValueError('기존 설치 기록이 있습니다. 먼저 상태를 확인하거나 복원하세요.')
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = BACKUP / stamp
    backup_dir.mkdir(parents=True, exist_ok=False)
    for r in records:
        backup_file = backup_dir / r['path']
        backup_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target(r['path']), backup_file)
        if digest(backup_file) != r['source_sha256']:
            raise ValueError('백업 확인에 실패했습니다.')
    journal = {
        'status':'INSTALLING', 'game_path':str(GAME), 'build_id':'25782395',
        'candidate_path':str(candidate), 'candidate_manifest_sha256':digest(manifest_path),
        'verification_sha256':digest(candidate / 'verification.json'),
        'game_identity':identity,
        'backup_path':str(backup_dir), 'started_utc':datetime.now(timezone.utc).isoformat(),
        'files':records,
    }
    save(journal_path, journal)
    try:
        for r in records:
            r['write_started'] = True
            save(journal_path, journal)
            write_game(candidate / 'overlay' / r['path'], target(r['path']), r['candidate_sha256'])
            r['installed'] = True
            save(journal_path, journal)
    except BaseException as exc:
        journal['error'] = str(exc)
        journal['status'] = 'ROLLING_BACK'
        save(journal_path, journal)
        try:
            restore(journal, journal_path)
            journal['status'] = 'ROLLED_BACK'
            save(journal_path, journal)
        except BaseException as recovery_error:
            journal['status'] = 'FAILED_RECOVERY_REQUIRED'
            journal['recovery_error'] = str(recovery_error)
            save(journal_path, journal)
        raise
    journal['status'] = 'INSTALLED'
    journal['finished_utc'] = datetime.now(timezone.utc).isoformat()
    save(journal_path, journal)
    save(backup_dir / 'installation.json', journal)
    return journal


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='개인용 한국어 교정 적용 및 원본 복원')
    parser.add_argument('action', choices=['install', 'restore'])
    parser.add_argument('--candidate', type=Path)
    args = parser.parse_args()
    process_check()
    if args.action == 'install':
        if args.candidate is None: parser.error('--candidate가 필요합니다.')
        journal = install(args.candidate)
    else:
        journal_path = STATE / 'current.json'
        journal = load(journal_path)
        restore(journal, journal_path)
    print(json.dumps({'status':journal['status'], 'files':len(journal['files']),
                      'game':journal['game_path'], 'backup':journal['backup_path']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
