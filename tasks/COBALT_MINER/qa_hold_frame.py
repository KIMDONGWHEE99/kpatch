"""장면을 넘기는 원래 타이머의 시간 값만 늘리는 검수 전용 사본입니다."""
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

def build(input_path, output, frame_index, hold_ms=120000):
    output = output.resolve()
    if output.exists() or not output.is_relative_to(fixture.PRIVATE) or not 10000 <= hold_ms <= 3600000:
        raise ValueError('새 비공개 경로 및10초~1시간의 제한된 검수 시간만 허용')
    original = fixture.DatFile.load(input_path)
    source = fixture.chunk_for(original, frame_index).decoded
    records = []
    for event in fixture.event_operations(source):
        if not any(a['type'] == -3 and a['num'] in (0, 1, 2) for a in event['Actions']):
            continue
        for condition in event['Conditions']:
            if (condition['type'], condition['num']) != (-4, -8):
                continue
            parameter = condition['parameters'][0]
            if parameter['code'] != 2 or parameter['size'] != 14:
                raise ValueError('원래 Timer 매개변수 구조와 다름')
            offset = parameter['offset'] + 4
            before = struct.unpack_from('<i', source, offset)[0]
            if before >= hold_ms:
                raise ValueError('검수 시간은 원래 시간보다 길어야 함')
            records.append(dict(frame=frame_index,event=event['index'],condition=condition['index'],offset=offset,before_ms=before,after_ms=hold_ms))
    if not records:
        raise ValueError('직접적인 시간 조건으로 장면을 넘기는 이벤트가 없음. 객체 값이나 입력 조건은 임의로 바꾸지 않음')
    output.mkdir(parents=True)
    entry = fixture.build(input_path, output / 'entry', 'frame', entry_frame=frame_index)
    dat = fixture.DatFile.load(entry)
    chunk = fixture.chunk_for(dat, frame_index)
    if chunk.decoded != source:
        raise ValueError('진입 사본이 대상 장면을 바꿈')
    edited = bytearray(chunk.decoded)
    for row in records:
        struct.pack_into('<i', edited, row['offset'], hold_ms)
    chunk.replacement = bytes(edited)
    raw = dat.serialize()
    reopened = fixture.DatFile(raw)
    allowed = set()
    for row in records:
        allowed.update(range(row['offset'], row['offset'] + 4))
    actual = fixture.chunk_for(reopened, frame_index).decoded
    if len(source) != len(actual) or any(a != b and i not in allowed for i, (a, b) in enumerate(zip(source, actual))):
        raise ValueError('장면 이동 타이머 숫자 외 변경')
    for key, before in dat.by_location.items():
        if before.children:
            continue
        if before.decoded != reopened.by_location[key].decoded and key not in {chunk.location, dat.one(0x2242).location}:
            raise ValueError('허용하지 않은 자산 변경')
    if dat.header != reopened.header or reopened.integrity_summary()['status'] != 'PASS':
        raise ValueError('창 설정 또는 DAT 검사값 불일치')
    path = output / 'COBALT MINER.qa-only.dat'
    path.write_bytes(raw)
    report = dict(status='PASS',qa_only=True,runtime_status='NOT_RUN',input_path=str(input_path),input_sha256=fixture.sha(input_path.read_bytes()),
                  entry_sha256=fixture.sha(entry.read_bytes()),output_path=str(path),output_sha256=fixture.sha(raw),tool_sha256=fixture.sha(Path(__file__).read_bytes()),
                  frame=frame_index,changes=records,scope='원래 장면 이동 조건의 시간 숫자4바이트만 변경. 동작/그림/본문/진행 조건 종류와 자동 이동 자체 보존',
                  limits=['진입을 위한 로고/메뉴 변경은 별도entry fixture_report에 기록','본문의 자체 애니메이션·다른 시간 동작은 원래대로 진행','배포본에 포함하지 않음'])
    (output / 'hold_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (output / 'hold_tool.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({k: report[k] for k in ('status','frame','output_path','output_sha256','changes')},ensure_ascii=False))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--frame',required=True,type=int,choices=range(17))
    parser.add_argument('--hold-ms',type=int,default=120000)
    args=parser.parse_args()
    build(args.input,args.output,args.frame,args.hold_ms)
