"""마지막 100달러 거래를 원래 버튼으로 시험하는 A/B 검수 사본을 만듭니다."""
import importlib.util
import json
import struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PRIVATE=ROOT/'working_private/COBALT_MINER'
SOURCE=ROOT/'build_candidate/COBALT_MINER/ko_candidate_02r1/COBALT MINER.dat'
spec=importlib.util.spec_from_file_location('fixture',Path(__file__).with_name('qa_fixture.py'))
fixture=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def build(branch, source=SOURCE, output=None):
    output=output or PRIVATE/f'qa_fixtures/ko02r1_terminal_{branch.lower()}_01'
    if output.exists():raise ValueError('기존 검수 파일 덮어쓰기 금지')
    entry=fixture.build(source,output/'entry','menu')
    dat=fixture.DatFile.load(entry)
    game=fixture.chunk_for(dat,7);raw=game.decoded;events=fixture.event_operations(raw)
    menu=fixture.chunk_for(dat,2);menu_raw=menu.decoded;menu_events=fixture.event_operations(menu_raw)
    def action(event,index):return fixture.op_bytes(raw,events[event]['Actions'][index])
    logo=fixture.chunk_for(dat,0).decoded
    start=fixture.op_bytes(logo,fixture.event_operations(logo)[0]['Conditions'][0])
    is_new=bytearray(fixture.op_bytes(raw,events[1463]['Conditions'][1]))
    assert len(is_new)==16 and struct.unpack_from('<hh',is_new,2)==(-1,-28) and struct.unpack_from('<ii',is_new,8)==(2,1)
    struct.pack_into('<i',is_new,12,0)
    setter=action(117,0)
    assert len(setter)==30 and struct.unpack_from('<hhh',setter,2)==(7,80,192) and struct.unpack_from('<i',setter,22)[0]==0
    def counter(handle,value):
        data=bytearray(setter);struct.pack_into('<H',data,6,handle);struct.pack_into('<i',data,22,value);return bytes(data)
    coords=(8094,9129) if branch=='A' else (19600,1853)
    def position(event,index,handle):
        data=bytearray(action(event,index))
        assert len(data)==38 and struct.unpack_from('<hhh',data,2)==(2,1,handle) and struct.unpack_from('<H',data,14)[0]==65535
        struct.pack_into('<hh',data,18,*coords)
        return bytes(data)
    off=bytearray(next(fixture.op_bytes(raw,a) for e in events for a in e['Actions'] if (a['type'],a['num'],a['handle'])==(2,36,152)))
    struct.pack_into('<H',off,6,161)
    actions=[counter(296,100),counter(624 if branch=='A' else 744,99900 if branch=='A' else 49900),bytes(off),
             position(304,1,152),position(486,2,164),position(486,1,163),action(1438,1),action(1438,2)]
    appended=[]
    if branch=='B':
        # 원래 해금 때 사용하는 위치 동작만 복제하며 퀘스트 값은 바꾸지 않습니다.
        detector=action(1371,0)
        assert struct.unpack_from('<hhh',detector,2)==(2,1,711) and struct.unpack_from('<hh',detector,18)==coords
        appended.append(fixture.make_event(raw,events[304],[start],[detector]))
    appended.append(fixture.make_event(raw,events[304],[start,bytes(is_new)],actions))
    game.replacement=fixture.rewrite_events(raw,{},appended)
    new_menu=bytearray(menu_raw)
    jumps=[a for a in menu_events[7]['Actions'] if (a['type'],a['num'])==(-3,2)]
    assert len(jumps)==1
    jump_offset=jumps[0]['offset']+12
    struct.pack_into('<I',new_menu,jump_offset,fixture.frame_handle(dat,7))
    menu.replacement=bytes(new_menu)
    result=dat.serialize();destination=output/'COBALT MINER.qa-only.dat';destination.write_bytes(result)
    check=fixture.DatFile(result);new_raw=fixture.chunk_for(check,7).decoded;new_events=fixture.event_operations(new_raw)
    assert len(new_events)==1484+len(appended)
    for i,event in enumerate(events):
        n=new_events[i]
        assert raw[event['offset']:event['offset']+event['size']]==new_raw[n['offset']:n['offset']+n['size']]
    permitted={game.location,menu.location,dat.one(0x2242).location}
    changed=[]
    for loc,old in dat.by_location.items():
        if not old.children and old.decoded!=check.by_location[loc].decoded:
            assert loc in permitted;changed.append(loc)
    assert check.integrity_summary()['status']=='PASS' and check.header==dat.header
    report=dict(status='PASS',runtime_status='NOT_RUN',independent_verification='NOT_RUN',qa_only=True,branch=branch,
                source_sha256=fixture.sha(source.read_bytes()),entry_sha256=fixture.sha(entry.read_bytes()),
                output_path=str(destination),output_sha256=fixture.sha(result),
                original_events_preserved=1484,appended_events=len(appended),changed_leaves_from_entry=changed,
                menu_change='새 게임 버튼의 원래 조건/초기화는 그대로, 목적 장면만 도입5에서 본편7로 변경. 계속하기 버튼은 완전 보존',
                seed_condition='StartOfFrame AND Global C=0. 계속하기의 Global C=1에서는 초기값을 다시 주지 않음',
                seed_values=dict(money=100,loan=99900 if branch=='A' else 0,loan2=49900 if branch=='B' else 0,player_position=coords,motorcycle_flag0=False),
                seed_value_scope='변경은 money와 선택 분기의 loan 또는 loan2만. 다른 상환 누계는 새 게임의 원래0을 유지',
                detector_position_change=dict(object=711,x=19600,y=1853,source_event=1371,source_action=0) if branch=='B' else None,
                original_payment=dict(button=629 if branch=='A' else 742,event=1257 if branch=='A' else 1384,cash_subtract=100,loan_add=100),
                original_branch=dict(event=1470 if branch=='A' else 1471,threshold=100000 if branch=='A' else 50000,target_frame=14 if branch=='A' else 11),
                save_contract=dict(filename='saveprofile.ini',group='',encoding='ASCII 호환',newlines='CRLF',keys=['money','loan','loan2'],
                                   loader_event=1463,loader_actions={'money':9,'loan':6,'loan2':92},save_event=217,save_actions={'money':15,'loan':78,'loan2':79}),
                procedure=['기존처럼 격리된 profile/temp/Steam 차단과 후보15파일 검증을 적용',
                           '실제 메뉴에서 새 게임 선택. cash100/해당 누계 확인 후 원래 게임 저장 버튼 클릭',
                           '원래 ESC로 메뉴에 복귀 후 실제 계속하기 클릭. 원래 로더로 동일 값/위치가 복원되는지 확인',
                           '원래 $100 버튼 클릭으로 cash0 및 누계 문턱 도달, 원래 분기와 엔딩/로고/메뉴 복귀 확인',
                           'QA 전후 실제 사용자17파일 무결성과 격리 저장 변경 범위를 기록'],
                limits=['마지막 상태를 준비한 대표 분기 시험이며 전체 퀘스트 완주가 아님','후보/원본/사용자 저장 파일은 수정하지 않음','장면의 창/폰트/본문/버튼/분기/저장 이벤트는 원형 보존'])
    (output/'terminal_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(branch,report['output_sha256'])


if __name__=='__main__':
    for branch in ['A','B']:build(branch)
