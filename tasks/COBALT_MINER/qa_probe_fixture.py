"""기존 게임 상자에서 대화/세계 정보를 표시하거나 작업대 앞으로 이동하는 검수 사본입니다."""
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

def build(input_path, output, panel, paragraph=0, cycle_ms=0, warmup_ms=5000):
    output = output.resolve()
    if not output.is_relative_to(fixture.PRIVATE) or output.exists():
        raise ValueError('새 비공개 검수 경로만 허용')
    if cycle_ms and not 1000 <= cycle_ms <= 60000:
        raise ValueError('문단 자동순환 간격은1~60초')
    output.mkdir(parents=True)
    entry = fixture.build(input_path, output / 'entry', 'newgame')
    dat = fixture.DatFile.load(entry)
    game = fixture.chunk_for(dat, 7)
    raw = game.decoded
    events = fixture.event_operations(raw)
    package = json.loads((ROOT / 'extracted_private/COBALT_MINER/steam_24347666/nebula_01/package.json').read_text(encoding='utf-8-sig'))
    def action(event, index):
        return fixture.op_bytes(raw, events[event]['Actions'][index])
    def find_action(handle, typ, num):
        for event in events:
            for op in event['Actions']:
                if (op['handle'], op['type'], op['num']) == (handle, typ, num):
                    return fixture.op_bytes(raw, op)
        raise ValueError('원래 동작 템플릿 없음')
    always = fixture.op_bytes(raw, events[838]['Conditions'][0])
    if struct.unpack_from('<hh', always, 2) != (-1, -1):
        raise ValueError('Always 조건 템플릿 불일치')
    logo_raw = fixture.chunk_for(dat, 0).decoded
    start = fixture.op_bytes(logo_raw, fixture.event_operations(logo_raw)[0]['Conditions'][0])
    if struct.unpack_from('<hh', start, 2) != (-3, -1):
        raise ValueError('StartOfFrame 조건 템플릿 불일치')
    template = events[300]
    appended, changes, schedule = [], [], []
    motor_flag_off = bytearray(find_action(152, 2, 36))
    struct.pack_into('<H', motor_flag_off, 6, 161)
    if panel == 'upgrades':
        # 모든 원래 장면 초기화가 끝난 뒤 실제 업그레이드 탐지 객체에 상대 이동합니다.
        position = bytearray(action(101, 0))
        if len(position) != 38 or struct.unpack_from('<HH', position, 12) != (16, 161):
            raise ValueError('플레이어 상대 이동 템플릿 불일치')
        struct.pack_into('<H', position, 14, 261)
        actions = [bytes(motor_flag_off), bytes(position)]
        appended.append(fixture.make_event(raw, template, [start], actions))
        changes.append(dict(panel=panel, reason='기존 flag0 off 동작의 대상만 Active15로 바꾸고 Active4 상대 위치 동작의 부모 객체만 실제 Detector updates261로 변경. 원래 event835 표시 조건을 사용', target_object=261))
    else:
        handle = {'dialog': 204, 'information': 534, 'ambient': 539}[panel]
        paragraphs = package['FrameItems']['Items'][str(handle)]['Properties']['ObjectParagraphs']['Paragraphs']
        if not 0 <= paragraph < len(paragraphs):
            raise ValueError('문단 번호 범위 초과')
        if panel == 'dialog':
            setup = [action(286, 0), action(286, 1), action(297, 1), action(1474, 87)]
        elif panel == 'information':
            setup = [find_action(534, 3, 27), action(1474, 92)]
        else:
            # 대사 탐지 객체에 플레이어를 옮겨 원래 배경 위치(탐지 객체 기준)를 사용합니다.
            position = bytearray(action(101, 0))
            struct.pack_into('<H', position, 14, 537)
            appended.append(fixture.make_event(raw, template, [start], [bytes(motor_flag_off), bytes(position)]))
            setup = [find_action(538, 2, 27), find_action(539, 3, 27), action(241, 0), action(1474, 104)]
        paragraph_action = bytearray(action(300, 0))
        if len(paragraph_action) != 20 or struct.unpack_from('<hhh', paragraph_action, 2) != (3, 84, 204) or struct.unpack_from('<H', paragraph_action, 12)[0] != 31:
            raise ValueError('문단 선택 템플릿 불일치')
        struct.pack_into('<H', paragraph_action, 6, handle)
        def select(index):
            value = bytearray(paragraph_action)
            struct.pack_into('<i', value, 14, index)
            return bytes(value)
        appended.append(fixture.make_event(raw, template, [always], setup + [select(paragraph)]))
        if cycle_ms:
            logo = fixture.chunk_for(dat, 0).decoded
            timer_event = fixture.event_operations(logo)[1]
            timer = bytearray(fixture.op_bytes(logo, timer_event['Conditions'][0])[:22])
            if struct.unpack_from('<hh', timer, 2) != (-4, -8):
                raise ValueError('원래 Timer 조건 템플릿 불일치')
            struct.pack_into('<h', timer, 0, 22)
            timer[7] = 1
            def timer_condition(number, milliseconds):
                value = bytearray(timer)
                struct.pack_into('<h', value, 4, number)
                struct.pack_into('<i', value, 12, milliseconds)
                return bytes(value)
            for index in range(len(paragraphs)):
                begin = warmup_ms + index * cycle_ms
                end = begin + cycle_ms
                appended.append(fixture.make_event(raw, template, [timer_condition(-1, begin), timer_condition(-2, end)], [select(index)]))
                schedule.append(dict(paragraph=index, begin_game_timer_ms=begin, end_game_timer_ms=end,
                                     capture_target_game_timer_ms=begin + cycle_ms // 2,
                                     inventory_location=f'object:{handle}/paragraph:{index}'))
        changes.append(dict(panel=panel, object_handle=handle, paragraph=paragraph, cycle_count=len(schedule),
                            reason='기존 보이기/상대 배치/문단 선택 동작을 마지막 이벤트에 복제. 실제 상자·글꼴·폭·배경을 사용하며 앞선 진행 조건과 구분한 표시 검수',
                            timer_reference='Nebula.Core Condition.cs Timer -1 greater/-2 less; 원래 ParameterTimer14바이트와 원래 표시 동작 재사용'))
    game.replacement = fixture.rewrite_events(raw, {}, appended)
    output_bytes = dat.serialize()
    after = fixture.DatFile(output_bytes)
    actual_raw = fixture.chunk_for(after, 7).decoded
    actual_events = fixture.event_operations(actual_raw)
    if len(actual_events) != len(events) + len(appended):
        raise ValueError('검수 이벤트 추가 수 불일치')
    for index, event in enumerate(actual_events):
        actual = actual_raw[event['offset']:event['offset'] + event['size']]
        expected = raw[events[index]['offset']:events[index]['offset'] + events[index]['size']] if index < len(events) else appended[index - len(events)]
        if actual != expected:
            raise ValueError('원래 이벤트 변조 또는 검수 동작 불일치')
    permitted = {game.location, dat.one(0x2242).location}
    for location, before in dat.by_location.items():
        if before.children:
            continue
        if before.decoded != after.by_location[location].decoded and location not in permitted:
            raise ValueError('검수 변경 경계 밖 자산 변경')
    if dat.header != after.header or after.integrity_summary()['status'] != 'PASS':
        raise ValueError('검수 헤더·검사값 불일치')
    path = output / 'COBALT MINER.qa-only.dat'
    path.write_bytes(output_bytes)
    report = dict(status='PASS', qa_only=True, runtime_status='NOT_RUN', panel=panel,
                  input_path=str(input_path), input_sha256=fixture.sha(input_path.read_bytes()),
                  entry_sha256=fixture.sha(entry.read_bytes()), output_path=str(path), output_sha256=fixture.sha(output_bytes),
                  tool_sha256=fixture.sha(Path(__file__).read_bytes()), original_event_count=len(events), appended_events=len(appended),
                  changes=changes, schedule=schedule, cycle_ms=cycle_ms, warmup_ms=warmup_ms,
                  appended_event_records=[dict(index=len(events)+index, sha256=fixture.sha(value), raw_hex=value.hex()) for index, value in enumerate(appended)],
                  limits=['게임 실행/캡처는 하지 않음. 후보15파일과 저장격리 guard는 실행자가 연결해야 함',
                          '자동 표시 검수는 원래 퀘스트 분기 통과를 의미하지 않음',
                          '107문단 순환은 게임 타이머 기준. 프로세스 시작 시각이 아니라 본편 프레임 진입과 실제 화면 문구로 캡처 번호를 확인',
                          '창 크기/전체화면·원래 텍스트·글꼴·그림·저장 키는 그대로이며 변경은 검수용 이벤트 추가와 별도entry 로고/메뉴 진입뿐'])
    (output / 'probe_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'runtime_status', 'panel', 'output_path', 'output_sha256', 'appended_events')}, ensure_ascii=False))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--panel', choices=['dialog', 'information', 'ambient', 'upgrades'], required=True)
    parser.add_argument('--paragraph', type=int, default=0)
    parser.add_argument('--cycle-ms', type=int, default=0)
    parser.add_argument('--warmup-ms', type=int, default=5000)
    args = parser.parse_args()
    build(args.input, args.output, args.panel, args.paragraph, args.cycle_ms, args.warmup_ms)
