"""주변 대사 QA 사본의 플레이어 시작 위치 X만 -400으로 바꿉니다."""
import importlib.util
import json
import struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('fixture',Path(__file__).with_name('qa_fixture.py'))
fixture=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
source=ROOT/'working_private/COBALT_MINER/qa_fixtures/ko02r1_ambient_cycle_01/COBALT MINER.qa-only.dat'
output=ROOT/'working_private/COBALT_MINER/qa_fixtures/ko02r1_ambient_cycle_02'
if output.exists():raise ValueError('기존 산출물 덮어쓰기 금지')
assert fixture.sha(source.read_bytes())=='c2ad4fd4c6bf628768e1414a15a9b0a8566f23966257b23a0dd4e184206917dd'
dat=fixture.DatFile.load(source)
game=fixture.chunk_for(dat,7)
before=game.decoded
events=fixture.event_operations(before)
assert len(events)==1516
action=events[1484]['Actions'][1]
value=fixture.op_bytes(before,action)
assert struct.unpack_from('<hhh',value,2)==(2,1,152)
assert len(value)==38 and struct.unpack_from('<H',value,14)[0]==537
assert struct.unpack_from('<hh',value,18)==(0,0)
offset=action['offset']+18
after=bytearray(before)
struct.pack_into('<h',after,offset,-400)
game.replacement=bytes(after)
output.mkdir(parents=True)
destination=output/'COBALT MINER.qa-only.dat'
destination.write_bytes(dat.serialize())
reopened=fixture.DatFile.load(destination)
new_raw=fixture.chunk_for(reopened,7).decoded
assert len(new_raw)==len(before)
assert new_raw[:offset]==before[:offset] and new_raw[offset+2:]==before[offset+2:]
assert struct.unpack_from('<h',new_raw,offset)[0]==-400
changed=[k for k,v in dat.by_location.items() if not v.children and v.decoded!=reopened.by_location[k].decoded]
assert changed==[game.location,dat.one(0x2242).location]
report=dict(status='PASS',runtime_status='NOT_RUN',independent_verification='NOT_RUN',qa_only=True,
            source_path=str(source),source_sha256=fixture.sha(source.read_bytes()),output_path=str(destination),output_sha256=fixture.sha(destination.read_bytes()),
            candidate_dat_sha256='44ec13b0867b1de0ab0108acb338ccb302915d42f9e677084c6cb97402635258',
            changed_field=dict(frame=7,event=1484,action=1,object=152,parent_object=537,field='ParameterPosition.X',decoded_offset=offset,before=0,after=-400),
            preserved='원래1484이벤트와추가setup/30개순환·말풍선538·본문539·표시레이어·글꼴·문구·저장키 모두동일. 플레이어위치X 2바이트와컨테이너검사값만변경',
            timing=dict(warmup_ms=5000,cycle_ms=3000,paragraphs=30,end_game_timer_ms=95000),
            reason='원래높은layer4의플레이어거리/방향표시를삭제하지않고,검수용플레이어를말풍선왼쪽으로옮겨서시각영역을분리',
            limits=['실제표시재검수필요','정식후보수정없음'])
(output/'position_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(report['output_sha256'])
