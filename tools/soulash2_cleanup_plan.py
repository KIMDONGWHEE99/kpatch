"""삭제 없이 게임 사본 목록을 고정하고 QA 기록과 보존 파일 지문을 준비한다."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'working_private/SOULASH_2'
OUT = WORK / 'storage_cleanup_20261031'
BASE = ROOT / 'extracted_private/SOULASH_2/0.10.4.0.1_20261029/baseline_manifest.json'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def tree(path):
    """연결 경로를 따라가지 않으며 발견하면 계획을 중단한다."""
    if path.lstat().st_file_attributes & 1024:
        raise ValueError('연결 경로: ' + str(path))
    if path.is_file():
        yield path
        return
    for current, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            item = Path(current) / name
            if item.lstat().st_file_attributes & 1024:
                raise ValueError('연결 경로: ' + str(item))
        for name in files:
            yield Path(current) / name


def main():
    OUT.mkdir(exist_ok=False)
    source = json.loads(BASE.read_text(encoding='utf-8'))
    game_paths = {r['path'] for r in source['files']}
    qa_names = ['g1_probe_01', 'g1_probe_02', 'qa_resume_01', 'qa_resume_02', 'qa_resume_03',
                'qa_finish_01', 'qa_finish_02', 'qa_finish_03', 'qa_finish_04']
    targets = [(ROOT / 'source_original/SOULASH_2/0.10.4.0.1_20261029', '원본 작업 사본'),
               (ROOT / 'build_candidate/SOULASH_2/release_20261031_v1', '최종 게임 실행 사본')]
    targets += [(WORK / name, '격리 QA 게임 사본') for name in qa_names]
    stage_names = ['complete_stage_01', 'complete_stage_02', 'complete_stage_03', 'complete_stage_04',
                   'finish_stage_01', 'resume_stage_01', 'resume_stage_02', 'review_real_20261030_b01']
    targets += [(ROOT / 'build_candidate/SOULASH_2' / name / 'payload', '재생성 가능한 게임 자산') for name in stage_names]
    package = WORK / 'package_1.0.0_20261031'
    targets += [(p, '차이 파일 복원 시험 사본') for p in package.iterdir()
                if p.is_file() and (re.fullmatch(r'\d+\.(forward|reverse)\.rebuilt', p.name) or p.name == 'empty_original')]
    native = WORK / 'native_ui_probe/new'
    targets += [(native / 'candidate_20261030_a' / n, '직접 문구 변경 시험 실행 파일')
                for n in ['forward_restored.bin', 'reverse_restored.bin', 'Soulash 2.exe']]
    targets += [(native / 'candidate_20261031_b/Soulash 2.exe', '배포에 사용한 실행 파일 사본')]
    synthetic = WORK / 'release_preparation/installer_synthetic_r1'
    targets += [(synthetic / name, '설치기 합성 시험 사본') for name in ['source', 'candidate']]
    targets += [(p, '설치기 합성 복원 사본') for p in (synthetic / 'evidence').glob('*.rebuilt')]
    targets += [(synthetic / 'evidence/tests/추가 Steam 라이브러리/steamapps/common/바뀐 설치 폴더 이름', '설치기 합성 설치 사본')]
    targets = [(p.resolve(strict=True), why) for p, why in targets if p.exists()]
    for path, _ in targets:
        assert path.is_relative_to(ROOT)
        assert any(path.is_relative_to(ROOT / part / 'SOULASH_2') for part in ['source_original', 'build_candidate', 'working_private'])
        assert not path.is_relative_to(WORK / 'translations')
    records, files, extra = [], [], []
    for path, why in targets:
        these = list(tree(path))
        size = sum(p.stat().st_size for p in these)
        records.append({'path': str(path), 'relative': path.relative_to(ROOT).as_posix(), 'reason': why,
                        'is_directory': path.is_dir(), 'files': len(these), 'bytes': size})
        for file in these:
            files.append({'path': file.relative_to(ROOT).as_posix(), 'size': file.stat().st_size,
                          'mtime_ns': file.stat().st_mtime_ns})
        if path.name in qa_names:
            extra += [(p, path.name + '/' + p.relative_to(path).as_posix()) for p in these
                      if p.relative_to(path).as_posix() not in game_paths]
    # 실행 사본 안의 로그·설정·검수 저장만 압축 보존한다. 원본 게임 자산은 넣지 않는다.
    archive = OUT / 'qa_records.zip'
    archive_records = []
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for file, name in extra:
            zf.write(file, name)
            archive_records.append({'path': name, 'sha256': digest(file), 'size': file.stat().st_size})
    with zipfile.ZipFile(archive) as zf:
        assert set(zf.namelist()) == {r['path'] for r in archive_records}
        for row in archive_records:
            assert hashlib.sha256(zf.read(row['path'])).hexdigest() == row['sha256']
    protected_roots = [WORK / 'translations', WORK / 'qa_finish_03_evidence', WORK / 'qa_finish_04_evidence',
                       ROOT / 'tasks/SOULASH_2', ROOT / 'release_output/SOULASH_2_KOREAN_PATCH_1.0.0_20261031']
    protected = [ROOT / 'release_output/SOULASH_2_KOREAN_PATCH_1.0.0_20261031.zip', BASE]
    for path in protected_roots:
        protected += list(tree(path))
    protected_records = [{'path': p.relative_to(ROOT).as_posix(), 'size': p.stat().st_size, 'sha256': digest(p)} for p in protected]
    # 실제 설치 게임은 삭제 범위 밖이며 파일 목록·크기·수정 시각만 보존 비교한다.
    installed = Path(source['source'])
    installation_records = [{'path': p.relative_to(installed).as_posix(), 'size': p.stat().st_size,
                             'mtime_ns': p.stat().st_mtime_ns} for p in tree(installed)]
    plan = {'workspace': str(ROOT), 'targets': records, 'delete_files': len(files),
            'delete_bytes': sum(r['bytes'] for r in records), 'disk_free_before': shutil.disk_usage(ROOT).free,
            'qa_archive': {'path': str(archive), 'files': len(extra), 'size': archive.stat().st_size, 'sha256': digest(archive)},
            'installed_game': str(installed), 'installed_files': len(installation_records)}
    for name, data in [('plan.json', plan), ('removed_file_list.json', files), ('qa_record_manifest.json', archive_records),
                       ('protected_before.json', protected_records), ('installed_before.json', installation_records)]:
        (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'targets': len(records), 'files': len(files), 'bytes': plan['delete_bytes'],
                      'qa_records': len(extra), 'plan_sha256': digest(OUT / 'plan.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
