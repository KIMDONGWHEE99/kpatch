"""별도 Nebula 재추출과 전체 DAT 경계 비교로 네 대화 검수 사본을 검사합니다."""
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'working_private/COBALT_MINER'
EXTRACTED = ROOT / 'extracted_private/COBALT_MINER'
spec = importlib.util.spec_from_file_location('dat_container', ROOT / 'tasks/THE_HORDE_OF_GORAK/dat_container.py')
container = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = container
spec.loader.exec_module(container)


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source_path = BASE / 'qa_fixtures/ko02r1_dialog_cycle_03/COBALT MINER.qa-only.dat'
    assert sha(source_path) == 'b7cdefc216e143f6eaff8988bf9481a8e803c52a266e04040ffa6c118dfa665d'
    source = container.DatFile.load(source_path)
    package = load(EXTRACTED / 'qa_dialog_cycle_03/package.json')
    original = package['Frames'][7]['FrameEvents']['Events']
    assert len(original) == 1592
    old_index_path = BASE / 'qa_fixture_index_ko02r1_v2.json'
    index = load(old_index_path)
    index['previous_index_sha256'] = sha(old_index_path)
    index['previous_index_path'] = str(old_index_path)
    cycle = BASE / 'qa_fixtures/ko02r1_dialog_cycle_03'
    index['fixtures'].append(dict(id=cycle.name, path=str(source_path), sha256=sha(source_path), panel='dialog',
                                  report=str(cycle/'probe_report.json'), boundary_report=str(cycle/'independent_cycle_verification.json'), runtime_status='NOT_RUN'))
    for first, last in [(0, 29), (30, 59), (60, 89), (90, 106)]:
        folder = BASE / f'qa_fixtures/ko02r1_dialog_split_{first:03d}_{last:03d}_01'
        candidate_path = folder / 'COBALT MINER.qa-only.dat'
        candidate = container.DatFile.load(candidate_path)
        assert candidate.header == source.header
        assert set(candidate.by_location) == set(source.by_location)
        changed = []
        for location, before in source.by_location.items():
            after = candidate.by_location[location]
            if not before.children and before.decoded != after.decoded:
                changed.append(location)
        assert changed == ['top/036:3333/008:333d', 'top/046:2242'], changed
        assert candidate.integrity_summary()['status'] == 'PASS'
        extracted = EXTRACTED / f'qa_dialog_split_{first:03d}_{last:03d}_01'
        actual = load(extracted / 'package.json')
        assert load(extracted/'summary.json')['errors'] == 0
        assert actual['FrameItems'] == package['FrameItems']
        events = actual['Frames'][7]['FrameEvents']['Events']
        assert len(events) == 1485 + last - first + 1
        assert events[:1484] == original[:1484]
        setup = copy.deepcopy(original[1484])
        setup['Actions'][-1]['Parameters'][0]['Data']['Value'] = first
        assert events[1484] == setup
        verified = []
        for offset, paragraph in enumerate(range(first, last + 1)):
            expected = copy.deepcopy(original[1485 + paragraph])
            begin = 5000 + offset * 2000
            expected['Conditions'][0]['Parameters'][0]['Data']['Timer'] = begin
            expected['Conditions'][1]['Parameters'][0]['Data']['Timer'] = begin + 2000
            assert events[1485 + offset] == expected
            verified.append(dict(paragraph=paragraph, begin_game_timer_ms=begin, end_game_timer_ms=begin + 2000))
        report = dict(status='PASS', runtime_status='NOT_RUN', source_sha256=sha(source_path),
                      candidate_sha256=sha(candidate_path), package_sha256=sha(extracted/'package.json'),
                      nebula_reader_sha256=sha(ROOT/'tasks/THE_HORDE_OF_GORAK/tools/NebulaExtract/bin/Release/net8.0-windows/NebulaExtract.dll'),
                      method='빌더를 가져오지 않는 별도 검사. Nebula 실제 재추출의 전체1484기존이벤트 및 전체895객체 비교. 새 setup1개와 각 문단의 두 Timer/선택 동작 전체 필드 대조',
                      changed_dat_leaves=changed, original_events_preserved=1484, objects_preserved=895,
                      asset_boundary='다른 장면, 저장키, 문단, 글꼴, 이미지, 메뉴, 헤더 등 모든 비대상 leaf decoded bytes 동일',
                      verified_paragraphs=verified, allowed_changes='추가 검수 이벤트의 구간 선택 및 타이머 재배치와 컨테이너 길이/검사값뿐',
                      limits=['실제 화면·입력·저장 동작은 이 검사에서 실행하지 않음', '실제 화면 내용으로 문단 대응을 확인해야 함'])
        report_path = folder/'independent_boundary_verification.json'
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        index['fixtures'].append(dict(id=folder.name, path=str(candidate_path), sha256=sha(candidate_path), panel='dialog',
                                      report=str(folder/'split_report.json'), boundary_report=str(report_path), boundary_status='PASS',
                                      paragraph_range=[first,last], capture_duration_ms=70000 if last-first==29 else 45000, runtime_status='NOT_RUN'))
        print(folder.name,sha(candidate_path),'PASS')
    path = BASE/'qa_fixture_index_ko02r1_v3.json'
    if path.exists():
        raise ValueError('인덱스 덮어쓰기 금지')
    path.write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf-8')
    print('index',sha(path))


if __name__ == '__main__':
    main()
