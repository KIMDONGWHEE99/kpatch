"""말단 분기 사본을 빌더와 독립된 Nebula 재추출/원래 이벤트로 검사합니다."""
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'working_private/COBALT_MINER'
EXT = ROOT / 'extracted_private/COBALT_MINER'
spec = importlib.util.spec_from_file_location('dat_container', ROOT/'tasks/THE_HORDE_OF_GORAK/dat_container.py')
container = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = container
spec.loader.exec_module(container)

def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def literal(operation, value):
    result = copy.deepcopy(operation)
    result['Parameters'][-1]['Data']['Expressions'][0]['Expression']['Value'] = value
    return result

def main():
    source_path = ROOT/'build_candidate/COBALT_MINER/ko_candidate_02r1/COBALT MINER.dat'
    source = container.DatFile.load(source_path)
    ref_path = EXT/'qa_dialog_cycle_03/package.json'
    ref = load(ref_path)
    original_path = EXT/'steam_24347666/nebula_01/package.json'
    original = load(original_path)
    events = ref['Frames'][7]['FrameEvents']['Events'][:1484]
    start = original['Frames'][0]['FrameEvents']['Events'][0]['Conditions'][0]
    is_new = literal(events[1463]['Conditions'][1], 0)
    assert (is_new['ObjectType'],is_new['Num']) == (-1,-8)
    assert is_new['Parameters'][0]['Data']['Value'] == 2
    off = next(a for e in events for a in e['Actions'] if (a['ObjectType'],a['Num'],a['ObjectInfo'])==(2,36,152))
    off = copy.deepcopy(off); off['ObjectInfo'] = 161
    index_path = BASE/'qa_fixture_index_ko02r1_v4.json'
    index = load(index_path)
    index['previous_index_path'] = str(index_path)
    index['previous_index_sha256'] = sha(index_path)
    for branch, loan, amount, coords in [('a',624,99900,(8094,9129)),('b',744,49900,(19600,1853))]:
        folder = BASE/f'qa_fixtures/ko02r1_terminal_{branch}_01'
        path = folder/'COBALT MINER.qa-only.dat'
        check = container.DatFile.load(path)
        assert check.header == source.header
        assert check.by_location.keys() == source.by_location.keys()
        changed = [k for k,v in source.by_location.items() if not v.children and v.decoded != check.by_location[k].decoded]
        assert changed == ['top/029:3333/008:333d','top/031:3333/008:333d','top/036:3333/008:333d','top/046:2242'], changed
        assert check.integrity_summary()['status'] == 'PASS'
        extracted = EXT/f'qa_terminal_{branch}_01'
        actual = load(extracted/'package.json')
        assert load(extracted/'summary.json')['errors'] == 0
        assert actual['FrameItems'] == ref['FrameItems']
        ae = actual['Frames'][7]['FrameEvents']['Events']
        assert ae[:1484] == events
        assert len(ae) == 1485 + (branch=='b')
        setup = copy.deepcopy(events[304])
        setup['Conditions'] = [start,is_new]
        values = []
        for handle,value in [(296,100),(loan,amount)]:
            setter = literal(events[117]['Actions'][0],value)
            setter['ObjectInfo'] = handle
            values.append(setter)
        values.append(off)
        for e,a in [(304,1),(486,2),(486,1)]:
            move = copy.deepcopy(events[e]['Actions'][a])
            move['Parameters'][0]['Data']['X'],move['Parameters'][0]['Data']['Y'] = coords
            values.append(move)
        values.extend([events[1438]['Actions'][1],events[1438]['Actions'][2]])
        setup['Actions'] = values
        assert ae[-1] == setup
        if branch == 'b':
            detector = copy.deepcopy(events[304])
            detector['Conditions'] = [start]
            detector['Actions'] = [events[1371]['Actions'][0]]
            assert ae[1484] == detector
        menu_expected = copy.deepcopy(original['Frames'][2]['FrameEvents']['Events'][7])
        jumps = [a for a in menu_expected['Actions'] if (a['ObjectType'],a['Num']) == (-3,2)]
        assert len(jumps) == 1
        jumps[0]['Parameters'][0]['Data']['Value'] = 0
        menu = actual['Frames'][2]['FrameEvents']['Events']
        assert menu[7] == menu_expected
        assert menu[8] == original['Frames'][2]['FrameEvents']['Events'][8]
        for i,event in enumerate(menu):
            if i != 7: assert event == ref['Frames'][2]['FrameEvents']['Events'][i]
        for f in range(17):
            if f not in (0,2,7): assert actual['Frames'][f] == ref['Frames'][f]
        report = dict(status='PASS',runtime_status='NOT_RUN',qa_only=True,branch=branch.upper(),
                      source_sha256=sha(source_path),candidate_sha256=sha(path),
                      package_sha256=sha(extracted/'package.json'),semantic_reference_sha256=sha(ref_path),
                      original_package_sha256=sha(original_path),nebula_reader_sha256=sha(ROOT/'tasks/THE_HORDE_OF_GORAK/tools/NebulaExtract/bin/Release/net8.0-windows/NebulaExtract.dll'),
                      method='빌더를 가져오지 않고 전체 DAT leaf와 별도 Nebula 해석 결과의 객체/이벤트를 대조',
                      original_game_events_preserved=1484,objects_preserved=895,changed_leaves=changed,
                      explicit_original_events_preserved=[217,218,1257,1384,1463,1470,1471],
                      entry='로고 자동 진입과 새 게임 목적지만 변경. 정상 버튼 조건/초기화/계속하기 보존',
                      additional_events='A: 새 게임일 때만 잔액/누계/이동/중심 설정. B: 같은 조건과 원래 detector 이동 별도1개',
                      newgame_gate=dict(global_value_index=2,comparison='equal',value=0),
                      seed=dict(money=100,loan_object=loan,loan_value=amount,player_position=coords,motorcycle_flag0=False),
                      continue_behavior='Global C=1이면 QA 값 초기화 안 함. 원래 로더1463을 사용',
                      save_contract=dict(filename='saveprofile.ini',keys=['money','loan','loan2'],save_event=217,escape_save_event=218,load_event=1463),
                      limits=['실제 메뉴 조작/저장/불러오기/$100 거래/엔딩 이동은 아직 NOT_RUN','전체 퀘스트 완주를 대신하지 않는 마지막 거래 대표 시험'])
        report_path = folder/'independent_terminal_verification.json'
        assert not report_path.exists()
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        index['fixtures'].append(dict(id=folder.name,path=str(path),sha256=sha(path),panel='terminal_'+branch,
                                      report=str(folder/'terminal_report.json'),boundary_report=str(report_path),boundary_status='PASS',runtime_status='NOT_RUN'))
        print(branch,sha(path),sha(report_path))
    output = BASE/'qa_fixture_index_ko02r1_v5.json'
    assert not output.exists()
    output.write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf-8')
    print('index',sha(output))

if __name__ == '__main__':
    main()
