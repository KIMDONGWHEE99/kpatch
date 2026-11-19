"""광고판/발전소 앞의 실제 월드 화면에 진입하는 검수 전용 사본을 만듭니다."""
from __future__ import annotations
import argparse
import importlib.util
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('cobalt_fixture', Path(__file__).with_name('qa_fixture.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)

def build(input_path, output, target):
    output = output.resolve()
    if output.exists() or not output.is_relative_to(fixture.PRIVATE):
        raise ValueError('새 비공개 검수 출력만 허용')
    package_path = ROOT / 'extracted_private/COBALT_MINER/steam_24347666/nebula_01/package.json'
    package = json.loads(package_path.read_text(encoding='utf-8-sig'))
    manifest_path = ROOT / 'working_private/COBALT_MINER/media_ko_02/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    handle = {'billboard':827,'power_station':506}[target]
    instances = [row for row in package['Frames'][7]['FrameInstances']['Instances'] if row['ObjectInfo'] == handle]
    anchor = instances[0]
    x, y = anchor['PositionX'], anchor['PositionY'] + 200
    expected = (18830,3300) if target == 'billboard' else (15424,6568)
    if (x,y) != expected:
        raise ValueError('확인한 원래 시설 배치와 다름')
    output.mkdir(parents=True)
    entry = fixture.build(input_path, output / 'entry', 'newgame')
    dat = fixture.DatFile.load(entry)
    chunk = fixture.chunk_for(dat,7)
    raw = chunk.decoded
    events = fixture.event_operations(raw)
    def action(event,index):
        return fixture.op_bytes(raw,events[event]['Actions'][index])
    def move(event,index,expected_handle):
        value = bytearray(action(event,index))
        if len(value)!=38 or struct.unpack_from('<hhh',value,2)!=(2,1,expected_handle) or struct.unpack_from('<H',value,14)[0]!=0xFFFF:
            raise ValueError('원래 절대 이동 동작 템플릿 불일치')
        struct.pack_into('<hh',value,18,x,y)
        return bytes(value)
    # 원래 플래그0 끄기 동작은 대상만 오토바이로 지정합니다.
    motor = bytearray(next(fixture.op_bytes(raw,a) for e in events for a in e['Actions'] if (a['type'],a['num'],a['handle'])==(2,36,152)))
    struct.pack_into('<H',motor,6,161)
    actions = [bytes(motor)]
    if target == 'power_station':
        # 자원 차감/저장 없이 원래 건설 완료 값과 원래 animation1 동작만 사용합니다.
        setter, animation = action(1219,3), action(1220,1)
        if struct.unpack_from('<hhh',setter,2)!=(2,31,506) or struct.unpack_from('<hhh',animation,2)!=(2,17,506):
            raise ValueError('원래 발전소 완료 동작 불일치')
        actions.extend([setter,animation])
    actions.extend([move(304,1,152),move(486,2,164),move(486,1,163),action(1438,1),action(1438,2)])
    logo = fixture.chunk_for(dat,0).decoded
    start = fixture.op_bytes(logo,fixture.event_operations(logo)[0]['Conditions'][0])
    appended = fixture.make_event(raw,events[304],[start],actions)
    chunk.replacement = fixture.rewrite_events(raw,{},[appended])
    result = dat.serialize()
    check = fixture.DatFile(result)
    new = fixture.chunk_for(check,7).decoded
    new_events = fixture.event_operations(new)
    if len(new_events)!=len(events)+1:
        raise ValueError('검수 이벤트 개수 오류')
    for i,event in enumerate(new_events):
        expected_bytes = raw[events[i]['offset']:events[i]['offset']+events[i]['size']] if i<len(events) else appended
        if new[event['offset']:event['offset']+event['size']]!=expected_bytes:
            raise ValueError('기존 이벤트 또는 추가 동작 변경')
    for key,before in dat.by_location.items():
        if before.children:continue
        if before.decoded!=check.by_location[key].decoded and key not in {chunk.location,dat.one(0x2242).location}:
            raise ValueError('월드 검수 동작 이외 자산 변경')
    if dat.header!=check.header or check.integrity_summary()['status']!='PASS':
        raise ValueError('헤더/무결성 실패')
    path = output/'COBALT MINER.qa-only.dat'
    path.write_bytes(result)
    report = dict(status='PASS',qa_only=True,runtime_status='NOT_RUN',target=target,object_handle=handle,
                  original_anchor=dict(x=anchor['PositionX'],y=anchor['PositionY'],layer=anchor['Layer']),
                  player_and_camera=dict(x=x,y=y),state_changes=['Active15 flag0 off','Active4/cam1/cam2 위치','원래 중심 스크롤 동작']+(['Power Generetor A=1, animation1']if target=='power_station'else[]),
                  input_path=str(input_path),input_sha256=fixture.sha(input_path.read_bytes()),output_path=str(path),output_sha256=fixture.sha(result),
                  tool_sha256=fixture.sha(Path(__file__).read_bytes()),package_sha256=fixture.sha(package_path.read_bytes()),media_manifest_sha256=fixture.sha(manifest_path.read_bytes()),
                  image_handles=[1123]if target=='power_station'else[x['handle']for x in manifest['files']if x['handle']!=1123],
                  appended_event=len(events),appended_raw_hex=appended.hex(),original_event_bytes_unchanged=True,
                  limits=['새 게임 기본 값과 원래 시간/색상/애니메이션/이미지를 유지. 배포본 변경 아님','광고판은 첫 배치 인스턴스의 원래 좌표를 선택해 복수 객체 상대 선택의 모호성을 제거','일반 진행/건설 비용/실제 저장 검수와 구분. 저장 계약·사용자 저장에는 이 작업자가 접근하지 않음'])
    (output/'world_media_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'fixture_tool.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({k:report[k]for k in('status','target','output_path','output_sha256','player_and_camera')},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--target',required=True,choices=['billboard','power_station'])
    args=parser.parse_args()
    build(args.input,args.output,args.target)
