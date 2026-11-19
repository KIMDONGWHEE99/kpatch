"""발전소 검수 사본에서 캐릭터 시작 X만 왼쪽 150으로 옮깁니다."""
import importlib.util
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('fixture',Path(__file__).with_name('qa_fixture.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
source = ROOT/'working_private/COBALT_MINER/qa_fixtures/ko02r1_world_power_station_01/COBALT MINER.qa-only.dat'
output = ROOT/'working_private/COBALT_MINER/qa_fixtures/ko02r1_world_power_station_02'
assert not output.exists()
assert fixture.sha(source.read_bytes()) == 'f8fbe82a0c53650a9791f61e62f2c3bb477fc738fe78f83d518c10b4a92ad51d'
dat = fixture.DatFile.load(source)
game = fixture.chunk_for(dat,7)
raw = game.decoded
events = fixture.event_operations(raw)
assert len(events) == 1485
action = events[1484]['Actions'][3]
value = fixture.op_bytes(raw,action)
assert len(value) == 38 and struct.unpack_from('<hhh',value,2) == (2,1,152)
assert struct.unpack_from('<H',value,14)[0] == 65535
assert struct.unpack_from('<hh',value,18) == (15424,6568)
offset = action['offset']+18
changed = bytearray(raw)
struct.pack_into('<h',changed,offset,15274)
game.replacement = bytes(changed)
output.mkdir(parents=True)
destination = output/'COBALT MINER.qa-only.dat'
destination.write_bytes(dat.serialize())
check = fixture.DatFile.load(destination)
after = fixture.chunk_for(check,7).decoded
assert len(raw) == len(after)
assert raw[:offset] == after[:offset] and raw[offset+2:] == after[offset+2:]
assert struct.unpack_from('<h',after,offset)[0] == 15274
assert [k for k,v in dat.by_location.items() if not v.children and v.decoded != check.by_location[k].decoded] == [game.location,dat.one(0x2242).location]
assert check.header == dat.header and check.integrity_summary()['status'] == 'PASS'
report = dict(status='PASS',runtime_status='NOT_RUN',independent_verification='NOT_RUN',qa_only=True,
              source_path=str(source),source_sha256=fixture.sha(source.read_bytes()),output_path=str(destination),output_sha256=fixture.sha(destination.read_bytes()),
              changed_field=dict(frame=7,event=1484,action=3,object=152,field='ParameterPosition.X',decoded_offset=offset,before=15424,after=15274),
              preserved='발전소 본체/완성 값/animation1/표지/본문/레이어/카메라/원래1484이벤트와 나머지 검수 동작 보존. 플레이어 X 2바이트와 컨테이너 검사값만 변경',
              purpose='표지 첫 글자를 가리는 캐릭터를 검수 사본에서만 왼쪽으로 이동',limits=['실제 표지 전체 판독은 실행 담당자가 수행','원본과 배포 후보 변경 없음'])
(output/'position_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(report['output_sha256'])
