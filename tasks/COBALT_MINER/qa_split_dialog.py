"""검증된 대화 순환 사본의 추가 검수 이벤트만 네 개의 짧은 구간으로 나눕니다."""
from __future__ import annotations

import importlib.util
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / 'working_private/COBALT_MINER'
SOURCE = PRIVATE / 'qa_fixtures/ko02r1_dialog_cycle_03/COBALT MINER.qa-only.dat'
SOURCE_SHA256 = 'b7cdefc216e143f6eaff8988bf9481a8e803c52a266e04040ffa6c118dfa665d'
RANGES = [(0, 29), (30, 59), (60, 89), (90, 106)]
spec = importlib.util.spec_from_file_location('fixture', Path(__file__).with_name('qa_fixture.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def main():
    source = fixture.DatFile.load(SOURCE)
    if fixture.sha(SOURCE.read_bytes()) != SOURCE_SHA256:
        raise ValueError('독립 검증된 cycle03 지문 불일치')
    raw = fixture.chunk_for(source, 7).decoded
    events = fixture.event_operations(raw)
    if len(events) != 1592:
        raise ValueError('원래 1484개 + setup1개 + 순환107개 경계 불일치')
    pieces = [raw[e['offset']:e['offset'] + e['size']] for e in events]
    start, end, reserve, length_field = fixture.event_region(raw)
    reports = []
    for first, last in RANGES:
        output = PRIVATE / f'qa_fixtures/ko02r1_dialog_split_{first:03d}_{last:03d}_01'
        if output.exists():
            raise ValueError(f'기존 검수 산출물 덮어쓰기 금지: {output}')
        output.mkdir(parents=True)
        setup = bytearray(pieces[1484])
        selector = events[1484]['Actions'][-1]
        if (selector['type'], selector['num'], selector['handle']) != (3, 84, 204):
            raise ValueError('검수 setup 문단 선택 불일치')
        setup_value_offset = selector['offset'] - events[1484]['offset'] + 14
        struct.pack_into('<i', setup, setup_value_offset, first)
        body = pieces[:1484] + [bytes(setup)]
        schedule = []
        for slot, paragraph in enumerate(range(first, last + 1)):
            event = events[1485 + paragraph]
            data = bytearray(pieces[1485 + paragraph])
            begin = 5000 + slot * 2000
            for condition, milliseconds in zip(event['Conditions'], [begin, begin + 2000]):
                if condition['type'] != -4 or condition['num'] not in [-1, -2]:
                    raise ValueError('검수 Timer 조건 불일치')
                struct.pack_into('<i', data, condition['offset'] - event['offset'] + 12, milliseconds)
            body.append(bytes(data))
            schedule.append(dict(paragraph=paragraph, location=f'object:204/paragraph:{paragraph}',
                                 begin_game_timer_ms=begin, end_game_timer_ms=begin + 2000))
        header = bytearray(raw[:start])
        body_bytes = b''.join(body)
        struct.pack_into('<I', header, reserve, len(body_bytes))
        struct.pack_into('<I', header, length_field, len(body_bytes))
        rebuilt = bytes(header) + body_bytes + raw[end:]
        dat = fixture.DatFile.load(SOURCE)
        game = fixture.chunk_for(dat, 7)
        game.replacement = rebuilt
        result = dat.serialize()
        destination = output / 'COBALT MINER.qa-only.dat'
        destination.write_bytes(result)
        report = dict(status='NOT_RUN', boundary_validation='NOT_RUN', runtime_status='NOT_RUN', qa_only=True,
                      source=str(SOURCE), source_sha256=SOURCE_SHA256,
                      output_path=str(destination), output_sha256=fixture.sha(result),
                      candidate_dat_sha256='44ec13b0867b1de0ab0108acb338ccb302915d42f9e677084c6cb97402635258',
                      first_paragraph=first, last_paragraph=last, cycle_ms=2000, warmup_ms=5000,
                      original_events=1484, setup_events=1, cycle_events=len(schedule), schedule=schedule,
                      capture_duration_ms=70000 if last-first == 29 else 45000,
                      allowed_changes=['frame7의 추가 검수 setup 마지막 문단번호 4바이트',
                                       '추가 검수 순환 이벤트에서 구간 밖 이벤트 제거, 남긴 두 Timer의 밀리초 필드만 재배치',
                                       '이벤트 영역 두 길이 필드 및 DAT 직렬화 검사값'],
                      limits=['문단 ID·순서·텍스트·글꼴·그림·원래1484이벤트·entry초기화는 보존',
                              '게임 타이머와 실제 경과 시간은 같다고 가정하지 않음. 실제 캡처 내용으로 누락 검사',
                              '검수용 파일이며 배포본에 넣지 않음'])
        (output / 'split_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        reports.append(report)
    print(json.dumps([dict(path=r['output_path'], sha256=r['output_sha256'], paragraphs=[r['first_paragraph'], r['last_paragraph']]) for r in reports]))


if __name__ == '__main__':
    main()
