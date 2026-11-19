"""이미 조립된 c06 검수 사본과 작성 source를 독립 왕복하여 고정합니다."""
import difflib
import hashlib
from pathlib import Path

from pck_tools import WORK, EXTRACTED, read_pack
from build_candidate import TOOLS, PCK, comparable, read, write, sha, run_tool


def check_source(source, stage, label):
    compiled = stage / label / 'compiled'
    recovered = stage / label / 'recovered'
    compiled.mkdir(parents=True, exist_ok=True)
    recovered.mkdir(parents=True, exist_ok=True)
    run_tool(['--compile=' + source.as_posix(), '--bytecode=4.5.0', '--output=' + compiled.as_posix()], stage, label + '_compile')
    bytecode = compiled / (source.stem + '.gdc')
    assert bytecode.exists()
    run_tool(['--decompile=' + bytecode.as_posix(), '--bytecode=4.5.0', '--output=' + recovered.as_posix()], stage, label + '_recover')
    restored = recovered / source.name
    assert comparable(source.read_text(encoding='utf-8')) == comparable(restored.read_text(encoding='utf-8'))
    return {'compiled_sha256': sha(bytecode), 'recovered_sha256': sha(restored), 'lexical_roundtrip': 'PASS'}


def freeze():
    stage = WORK / 'qa_driver_c06_review'
    assert not stage.exists(), '고정된 검수 명세를 덮어쓰지 않습니다.'
    stage.mkdir()
    authored = TOOLS / 'qa_driver.gd'
    before_hash = sha(authored)
    assert before_hash == 'ed896507394d97c91aed133d2415331104aab4065caeedcee85c111be6140deb'
    source = stage / 'qa_driver.gd'
    source.write_bytes(authored.read_bytes())
    assert sha(source) == before_hash == sha(authored)
    candidate_stage = WORK / 'ko_1.0.0_c06'
    qa_pack = candidate_stage / 'qa_game' / PCK
    packed = {entry['name']: entry['data'] for entry in read_pack(qa_pack)[3]}
    assert packed['korean_qa_driver.gd'] == source.read_bytes()
    roundtrip = check_source(source, stage, 'c06')
    previous_review = read(WORK / 'qa_driver_c05_review/qa_driver_revision_c05.json')
    previous_packed = {entry['name']: entry['data'] for entry in read_pack(WORK / 'ko_1.0.0_c05/qa_game' / PCK)[3]}['korean_qa_driver.gd']
    assert hashlib.sha256(previous_packed).hexdigest() == previous_review['driver_sha256']
    (stage / 'c05_to_c06.diff').write_text(''.join(difflib.unified_diff(previous_packed.decode('utf-8').splitlines(True), source.read_text(encoding='utf-8').splitlines(True), fromfile='c05_packed_driver', tofile='c06_frozen_source')), encoding='utf-8')
    changes = dict(previous_review['changes'])
    changes.update({
        'prototype': 'JSON 숫자를 int로 명시 변환한 뒤 기존 예비 레벨 1/2/3 허용 목록으로 진입. 게임 조건은 변경하지 않음',
        'main_exit': '유일한 원본 MainMenu의 _on_exit_button_pressed를 호출하고 원래 확인 상태를 읽어 기록',
        'main_exit_confirm': '같은 원본 MainMenu의 _on_exit_confirmation_confirmed 호출. 종료 후 캡처를 성공으로 꾸미지 않음',
        'skill_layout': '실제 표시 중인 설명 PanelContainer의 global_rect, viewport_rect, z_index를 읽어 기록하는 기능만 추가'
    })
    review = {'status': 'PASS', 'candidate': 'ko_1.0.0_c06', 'driver_sha256': sha(source),
              'driver_source_path': str(source), 'previous_review_sha256': sha(WORK / 'qa_driver_c05_review/qa_driver_revision_c05.json'),
              'previous_driver_sha256': previous_review['driver_sha256'], **roundtrip, 'changes': changes,
              'previous_packed_driver_sha256': hashlib.sha256(previous_packed).hexdigest(), 'source_diff_sha256': sha(stage / 'c05_to_c06.diff'),
              'original_evidence': previous_review['original_evidence'] + ['addons/maaacks_game_template/base/nodes/menus/main_menu/main_menu.gd', 'game/scenes/menus/main_menu/main_menu_with_animations.gd'],
              'qa_pck_sha256': sha(qa_pack), 'packed_source_identical': True,
              'scope': '검수 전용 observer의 승인된 진입·상태 주입·읽기 기록만 고정. c06 제품 자산과 입력, 이전 후보 증거는 변경하지 않음',
              'graphics_status': 'NOT_RUN'}
    for entry in review['original_evidence']:
        assert (EXTRACTED / 'recovered' / entry.split(':')[0]).exists(), entry
    write(stage / 'qa_driver_revision_c06.json', review)
    reference_stage = WORK / 'original_reference_c06'
    reference_source = reference_stage / 'reference_driver.gd'
    expected = source.read_bytes().replace(b'InputEventHelper.localize_display_text(raw)', b'raw')
    assert source.read_bytes().count(b'InputEventHelper.localize_display_text(raw)') == 2
    assert reference_source.read_bytes() == expected
    reference_lock = read(reference_stage / 'input_lock.json')
    assert reference_lock['parent_driver_sha256'] == sha(source)
    assert reference_lock['reference_driver_sha256'] == sha(reference_source)
    reference_pack = reference_stage / 'qa_game' / PCK
    reference_actual = {entry['name']: entry['data'] for entry in read_pack(reference_pack)[3]}
    assert reference_actual['korean_qa_driver.gd'] == expected
    reference_roundtrip = check_source(reference_source, stage, 'reference')
    write(reference_stage / 'reference_driver_review.json', {
        'status': 'PASS', 'candidate': 'original_reference_c06', 'driver_sha256': sha(reference_source),
        'driver_source_path': str(reference_source), 'parent_driver_sha256': sha(source),
        'parent_review_path': str(stage / 'qa_driver_revision_c06.json'), 'parent_review_sha256': sha(stage / 'qa_driver_revision_c06.json'),
        **reference_roundtrip, 'qa_pck_sha256': sha(reference_pack), 'packed_source_identical': True,
        'changes': {'input_compatibility': '원본에 없는 localize_display_text를 호출하는 미사용 입력 덤프의 최종 표시 식 2개만 원문 반환으로 대체'},
        'scope': '원본 대조를 위한 호환식 2개 외 모든 검수 명령은 고정된 c06 observer와 동일. 메인 제작진 및 예비 레벨 1/3 비교 가능',
        'graphics_status': 'NOT_RUN'
    })
    print({'driver_sha256': sha(source), 'reference_driver_sha256': sha(reference_source), 'status': 'PASS'})


if __name__ == '__main__':
    freeze()
