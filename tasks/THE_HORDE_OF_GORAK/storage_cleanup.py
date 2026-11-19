"""사용자가 요청한 게임 작업 사본만 제거하고 보존 파일의 지문을 대조한다."""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GAME = 'THE_HORDE_OF_GORAK'
ZONES = [ROOT / z / GAME for z in ('source_original', 'extracted_private', 'working_private', 'build_candidate')]
OUT = ROOT / 'working_private' / GAME / 'storage_cleanup_20261031'
INSTALL = Path(r'D:\steam\steamapps\common\The Horde of Gorak')
BACKUP = Path(r'C:\Users\PC\AppData\Local\TheHordeOfGorakKoreanPatch\working_private\35633642EDCA0C0A\build_26336311')
PRIVATE = ROOT / 'working_private' / GAME


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def checked(path):
    # 삭제 대상의 실제 절대 경로와 모든 상위 경로의 연결 여부를 확인한다.
    assert path.is_absolute() and path.resolve() == path, str(path)
    assert any(path.is_relative_to(z) for z in ZONES), str(path)
    assert not path.is_relative_to(OUT), str(path)
    for current in (path, *path.parents):
        if current == ROOT.parent:
            break
        assert not (current.lstat().st_file_attributes & 0x400), str(current)
    assert path.is_file(), str(path)


def reason(path):
    rel = path.relative_to(ROOT)
    zone, game, *parts = rel.parts
    assert game == GAME
    if zone == 'source_original':
        return '원본 게임 작업 사본'
    if zone == 'extracted_private':
        # 검수용 모아보기 이미지와 목록은 보존한다.
        if len(parts) > 2 and parts[1].startswith('nebula_'):
            tail = parts[2:]
            if tail[0] in ('images', 'fonts', 'frames', 'extension_blobs', 'sounds', 'music') or tail == ['package.json']:
                return '게임에서 추출한 원시 자산'
        return None
    if zone == 'build_candidate':
        if 'game' in parts or path.name == 'THOG.dat':
            return '배포 후보 게임 사본'
        return None
    if not parts or parts[0] in ('storage_cleanup_20261031', 'research', 'installer_synthetic_01'):
        return None
    if parts[0] == 'personal_release_01':
        if len(parts) > 1 and parts[1] == 'install_trial':
            return '최종 ZIP 설치 시험 게임 사본'
        if 'installer_state' in parts and 'cache' in parts and path.name in ('original', 'patched'):
            return '설치 시험 전용 복원 캐시'
    if parts[0].startswith('qa_') and len(parts) > 1 and parts[1] == 'game':
        return '실행 검수 게임 사본'
    if path.name == 'smoke_candidate.dat' or (path.name.startswith('THOG') and path.suffix == '.dat'):
        return '재조립 및 검수용 게임 자료 사본'
    if parts[0].startswith('native_candidate_') and path.suffix.lower() in ('.exe', '.dll', '.mfx', '.mvx'):
        return '실행 모듈 후보 사본'
    if parts[0] == 'package_1.0.0_r1' and path.suffix == '.rebuilt':
        return '차이 패치 복원 시험 중복 파일'
    for index, part in enumerate(parts):
        if part in ('nebula', 'nebula_candidate', 'nebula_dev', 'nebula_pixels'):
            tail = parts[index + 1:]
            if tail and (tail[0] in ('images', 'fonts', 'frames', 'extension_blobs', 'sounds', 'music') or tail == ['package.json']):
                return '독립 재추출의 원시 게임 자산'
    return None


def rows(paths):
    return [{'path': str(p), 'bytes': p.stat().st_size, 'sha256': digest(p)} for p in sorted(set(paths))]


def protected_paths():
    roots = [*ZONES, ROOT / 'tasks' / GAME, ROOT / 'validation' / GAME,
             ROOT / 'release_output' / f'{GAME}_KOREAN_PATCH_1.0.0_r1', INSTALL, BACKUP]
    files = [f for base in roots for f in base.rglob('*') if f.is_file() and not f.is_relative_to(OUT)]
    files.append(ROOT / 'release_output' / f'{GAME}_KOREAN_PATCH_1.0.0_r1.zip')
    return files


def verify_installed():
    record = json.loads((PRIVATE / 'personal_release_01/installation_result.json').read_text(encoding='utf-8'))
    assert len(record['files']) == 32
    for row in record['files']:
        assert digest(INSTALL / row['path']) == row['sha256'], row['path']
    # 복구 캐시의 원본 지문은 설치 시 검증된 기록을 보존하고 전후 전체 대조한다.
    assert BACKUP.is_dir() and (BACKUP / 'receipt.json').is_file()
    assert digest(ROOT / 'release_output' / f'{GAME}_KOREAN_PATCH_1.0.0_r1.zip') == record['zip_sha256']
    return {'installed_files': 32, 'zip_matches_release': True, 'backup_files': sum(p.is_file() for p in BACKUP.rglob('*'))}


def plan():
    assert not (OUT / 'plan.json').exists(), '기존 계획을 덮어쓰지 않습니다.'
    OUT.mkdir(parents=True, exist_ok=True)
    installed = verify_installed()
    targets = []
    for zone in ZONES:
        for path in zone.rglob('*'):
            if path.is_file() and (why := reason(path)):
                checked(path)
                targets.append({'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest(path), 'reason': why})
    assert targets
    target_names = {r['path'] for r in targets}
    kept = rows(p for p in protected_paths() if str(p) not in target_names)
    write('preserved_before.json', kept)
    groups = {}
    for row in targets:
        group = groups.setdefault(row['reason'], {'files': 0, 'bytes': 0})
        group['files'] += 1
        group['bytes'] += row['bytes']
    result = {'created_utc': datetime.now(timezone.utc).isoformat(), 'scope': '이번 The Horde of Gorak 작업의 원본·후보·QA 복사 및 추출 게임 자산',
              'files': len(targets), 'bytes': sum(r['bytes'] for r in targets), 'groups': groups,
              'preserved_files': len(kept), 'installation_before': installed, 'targets': targets}
    write('plan.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'targets'}, ensure_ascii=False))
    print('preserved_large_files', json.dumps([{'path': r['path'], 'bytes': r['bytes']} for r in kept if r['bytes'] > 10_000_000 and str(ROOT) in r['path']], ensure_ascii=False))


def apply():
    plan_data = json.loads((OUT / 'plan.json').read_text(encoding='utf-8'))
    assert not (OUT / 'result.json').exists()
    # 삭제 전에 계획의 모든 경로와 파일 내용을 다시 대조한다.
    for row in plan_data['targets']:
        p = Path(row['path'])
        checked(p)
        assert p.stat().st_size == row['bytes'] and digest(p) == row['sha256'], str(p)
    before = shutil.disk_usage(ROOT).free
    deleted = []
    with (OUT / 'deleted_paths.jsonl').open('w', encoding='utf-8') as log:
        for row in plan_data['targets']:
            Path(row['path']).unlink()
            deleted.append(row['path'])
            log.write(json.dumps(row, ensure_ascii=False) + '\n')
            log.flush()
    # 경계가 확인된 게임 작업 영역 내부의 빈 폴더만 지운다.
    for zone in ZONES:
        for directory in sorted((p for p in zone.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            assert directory.resolve() == directory and directory.is_relative_to(zone)
            assert not (directory.lstat().st_file_attributes & 0x400)
            if not any(directory.iterdir()):
                directory.rmdir()
    after = shutil.disk_usage(ROOT).free
    preserved = json.loads((OUT / 'preserved_before.json').read_text(encoding='utf-8'))
    failures = []
    for row in preserved:
        p = Path(row['path'])
        if not p.is_file() or p.stat().st_size != row['bytes'] or digest(p) != row['sha256']:
            failures.append(row['path'])
    remaining = [p for p in deleted if Path(p).exists()]
    result = {'status': 'PASS' if not failures and not remaining else 'FAIL', 'deleted_files': len(deleted),
              'deleted_bytes': plan_data['bytes'], 'free_bytes_before': before, 'free_bytes_after': after,
              'observed_free_increase': after - before, 'preserved_verified_files': len(preserved),
              'preservation_failures': failures, 'remaining_targets': remaining, 'installation_after': verify_installed(),
              'completed_utc': datetime.now(timezone.utc).isoformat(),
              'limitations': '여유 공간의 전후 차이에는 동시에 동작하는 다른 프로그램의 영향이 포함될 수 있습니다.'}
    write('result.json', result)
    print(json.dumps(result, ensure_ascii=False))
    assert result['status'] == 'PASS'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['plan', 'apply'])
    args = parser.parse_args()
    plan() if args.mode == 'plan' else apply()
