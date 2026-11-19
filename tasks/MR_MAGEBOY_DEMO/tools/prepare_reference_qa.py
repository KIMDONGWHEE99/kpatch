"""원본의 예비 화면 오류를 대조할 격리 실행 사본을 만듭니다."""
import argparse
import hashlib
import shutil
from pathlib import Path

from pck_tools import ROOT, GAME, BASELINE, EXTRACTED, WORK, read_pack
from build_candidate import TOOLS, PCK, read, write, sha, prepare_qa


def prepare(reference_id):
    candidate = ROOT / 'build_candidate' / GAME / reference_id
    stage = WORK / reference_id
    assert not candidate.exists() and not stage.exists(), '고정된 원본 검수 사본을 덮어쓰지 않습니다.'
    stage.mkdir(parents=True)
    shutil.copytree(BASELINE, candidate)
    for original in BASELINE.iterdir():
        if original.is_file():
            assert sha(original) == sha(candidate / original.name), '원본 검수 기준선 복제 실패'
    driver = (TOOLS / 'qa_driver.gd').read_bytes()
    # 원본 InputEventHelper에는 패치에서 추가한 표시 함수가 없으므로 미사용 입력 덤프만 원문으로 호환합니다.
    assert driver.count(b'InputEventHelper.localize_display_text(raw)') == 2
    reference_driver = driver.replace(b'InputEventHelper.localize_display_text(raw)', b'raw')
    driver_path = stage / 'reference_driver.gd'
    driver_path.write_bytes(reference_driver)
    input_lock = {'reference': True, 'source_pck_sha256': sha(BASELINE / PCK),
                  'original_files': {p.name: sha(p) for p in BASELINE.iterdir() if p.is_file()},
                  'parent_driver_sha256': hashlib.sha256(driver).hexdigest(),
                  'reference_driver_sha256': sha(driver_path),
                  'reference_driver_compatibility': '미사용 입력 덤프의 최종 표시2식만 원문으로 반환; maincredits/prototype 동작은 동일'}
    write(stage / 'input_lock.json', input_lock)
    write(stage / 'build_manifest.json', {'game_id': GAME, 'candidate': reference_id, 'source_reference': True,
          'source_pck_sha256': sha(BASELINE / PCK), 'candidate_pck_sha256': sha(candidate / PCK),
          'input_lock_sha256': sha(stage / 'input_lock.json'), 'modified_inputs': [], 'pck_changes': {},
          'script_count': 0, 'resource_count': 0, 'files': [{'path': p.name, 'size': p.stat().st_size, 'sha256': sha(p)} for p in candidate.iterdir() if p.is_file()],
          'status': 'PASS', 'graphics_status': 'NOT_RUN', 'scope': '원본과 동일한 대조 기준선; 한국어 패치 후보가 아님'})
    originals = {entry['name']: entry['data'] for entry in read_pack(candidate / PCK)[3]}
    remaps = {entry['source']: entry['target'] for entry in read(WORK / 'remap_targets.json')}
    prepare_qa(candidate, stage, EXTRACTED / 'recovered', remaps, originals, driver_path)
    manifest = read(stage / 'qa_manifest.json')
    write(stage / 'reference_report.json', {'reference': reference_id, 'status': 'PASS',
          'source_pck_sha256': sha(BASELINE / PCK), 'candidate_pck_sha256': sha(candidate / PCK),
          'qa_pck_sha256': manifest['qa_pck_sha256'], 'original_entries': len(originals),
          'qa_changes': manifest['qa_changes'], 'reference_driver_sha256': sha(driver_path),
          'graphics_status': 'NOT_RUN', 'scope': '설정6필드·Steam 초기화 차단·observer/config만 다른 원본 대조 검수'})
    print(manifest['qa_pck_sha256'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('reference_id')
    prepare(parser.parse_args().reference_id)
