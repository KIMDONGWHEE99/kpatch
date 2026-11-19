"""배포 데이터와 분리한 검수 전용 DAT·저장 상태를 생성한다. 게임은 실행하지 않는다."""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

from dat_container import DatFile

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / 'working_private/THE_HORDE_OF_GORAK'
ORIGINAL = ROOT / 'source_original/THE_HORDE_OF_GORAK/steam_26336311/THOG.dat'
SEMANTIC = ROOT / 'extracted_private/THE_HORDE_OF_GORAK/steam_26336311/nebula_03'
RAW = PRIVATE / 'investigation_20261031/classification/raw_frames.json'
FRAME10 = 'top/037:3333/008:333d'
SOURCE_SHA = '60825bc8e3969274f5235088f86c38a8fd187b6265b8082de6b9625d1437e950'
BUILDING_KEYS = ('lumberjack', 'ogreshouse', 'goldmine', 'barracks', 'workshop',
                 'laboratory', 'shamantower', 'beastscave', 'trollshut',
                 'ridersranch', 'blacksmith', 'market')
POSITION_EVENTS = (705, 721, 732, 744, 750, 760, 772, 784, 794, 800, 810, 820, 830)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def ini_values(data):
    """인코딩과 비대상 줄을 보존하도록 ASCII 키의 숫자 부분만 찾는다."""
    result = {}
    for match in re.finditer(rb'(?m)^([A-Za-z][A-Za-z0-9_]*)=(-?\d+)(?=\r?$)', data):
        key = match.group(1).decode('ascii')
        if key in result:
            raise ValueError(f'중복 저장 키: {key}')
        result[key] = {'value': int(match.group(2)), 'offset': match.start(2),
                       'end': match.end(2), 'source': match.group(2).decode('ascii')}
    if data.count(b'[]\r\n') != 1 or data.count(b'[') != 1:
        raise ValueError('확인한 단일 빈 INI 그룹과 다름')
    return result


def patch_ini(data, changes, evidence):
    values = ini_values(data)
    edits = []
    for key, value in changes.items():
        if key not in values or not evidence.get(key):
            raise ValueError(f'키 또는 실제 읽기 근거 없음: {key}')
        old = values[key]
        if old['value'] == value:
            continue
        edits.append({'target': f'ini:[]/{key}', 'offset': old['offset'],
                      'source': old['source'], 'expected': str(value),
                      'source_bytes': old['end'] - old['offset'],
                      'consumers': evidence[key]})
    result = data
    for edit in sorted(edits, key=lambda x: x['offset'], reverse=True):
        start = edit['offset']
        end = start + edit['source_bytes']
        assert result[start:end] == edit['source'].encode('ascii')
        result = result[:start] + edit['expected'].encode('ascii') + result[end:]
    after = ini_values(result)
    assert set(after) == set(values)
    for key in after:
        assert after[key]['value'] == changes.get(key, values[key]['value'])
    # 역방향 복원으로 숫자 이외의 원본 줄·위치·비ASCII 문자 보존을 검증한다.
    restored = result
    for key in sorted(changes, key=lambda k: after[k]['offset'], reverse=True):
        item = after[key]
        restored = restored[:item['offset']] + values[key]['source'].encode('ascii') + restored[item['end']:]
    assert restored == data
    for edit in edits:
        edit['output_offset'] = after[edit['target'].split('/')[-1]]['offset']
    return result, edits


def semantic_evidence(original, candidate):
    frames = read_json(RAW)
    readers = {}
    rows10 = read_json(SEMANTIC / 'frames/10.json')
    for frame_index in range(20):
        raw_frame = frames[frame_index]
        source_chunk = original.by_location[raw_frame['chunk']].decoded
        candidate_chunk = candidate.by_location[raw_frame['chunk']].decoded
        raw_events = {event['index']: event for event in raw_frame['events']}
        for row in read_json(SEMANTIC / f'frames/{frame_index:02}.json'):
            keys = re.findall(r'Expression ID 82\("Ini"\)"([^"\r\n]+)"\)', row['display'])
            if not keys:
                continue
            # Nebula는 압축된 복합 행동을 여러 줄로 펼치므로 표시 index와 원시 index가 다를 수 있다.
            matches = [operation for operation in raw_events[row['ev']][row['kind']]
                       if operation['type'] == row['ObjectType']
                       and operation['num'] == row['Num']
                       and operation['handle'] == row['ObjectInfo']
                       and all(key in [text['value'] for parameter in operation['parameters']
                                       for text in parameter['strings']] for key in keys)]
            if len(matches) != 1:
                raise ValueError(f'INI 소비 위치가 유일하지 않음: {frame_index}/{row["ev"]}/{row["index"]}')
            operation = matches[0]
            start, length = operation['offset'], operation['size']
            # 번역 후보에서도 해당 읽기 식이 바뀌지 않았음을 확인한다.
            assert candidate_chunk[start:start+length] == source_chunk[start:start+length]
            for key in keys:
                readers.setdefault(key, []).append({
                    'frame': frame_index, 'event': row['ev'], 'kind': row['kind'],
                    'semantic_operation': row['index'], 'raw_operation': operation['index'],
                    'object': row['ObjectInfo'],
                    'target': raw_frame['chunk'], 'offset': start, 'bytes': length,
                    'source_bytes_sha256': sha(source_chunk[start:start+length]),
                    'display': row['display']})
    chosen = set(POSITION_EVENTS) | set(range(477, 500)) | set(range(505, 513))
    chosen |= set(range(1236, 1246)) | {6, 7, 239, 240, 241, 243, 244, 245, 246, 250, 253}
    events = []
    raw10 = {event['index']: event for event in frames[10]['events']}
    for number in sorted(chosen):
        event = raw10[number]
        events.append({'frame': 10, 'event': number, 'target': FRAME10,
                       'offset': event['offset'], 'bytes': event['size'],
                       'source_bytes_sha256': sha(original.by_location[FRAME10].decoded[event['offset']:event['offset']+event['size']]),
                       'operations': [row for row in rows10 if row['ev'] == number]})
    return readers, events


def make_presets():
    resources = dict(stone=100000, wood=100000, gold=100000, crystals=10000, freeorcs=100)
    buildings = resources | {key: 1 for key in BUILDING_KEYS}
    buildings |= dict(orchut=1, orchall=1, magicstone=1, currentcastle=1,
                      towerhp=500000, win=0, tutorial=5)
    presets = {'resources': resources}
    # 각 연구 쌍 중 하나만 완료한다. 8개 전부 활성화하는 불가능한 조합은 만들지 않는다.
    for stage in range(5):
        lab = {f'lab{i}': int(i % 2 == 1 and i <= stage * 2) for i in range(1, 9)}
        presets[f'buildings_research_stage{stage}'] = buildings | lab | dict(labeach=stage, labresearch=0, labprogress=0)
    lab = {f'lab{i}': int(i % 2 == 0) for i in range(1, 9)}
    presets['buildings_research_right_complete'] = buildings | lab | dict(labeach=4, labresearch=0, labprogress=0)
    # 기존 게임의 승리 조건·구출 연출을 그대로 통과하도록 HP만 1로 둔다.
    presets['victory_castle1'] = resources | dict(currentcastle=1, towerhp=1, win=0, tutorial=5)
    presets['ending_castle6'] = resources | dict(currentcastle=6, towerhp=1, win=0, tutorial=5)
    return presets


def build(candidate_path, save_path, output):
    candidate_path, save_path, output = candidate_path.resolve(), save_path.resolve(), output.resolve()
    if not candidate_path.is_relative_to(ROOT / 'build_candidate/THE_HORDE_OF_GORAK'):
        raise ValueError('입력은 이 게임의 빌드 후보 DAT만 허용')
    if not save_path.is_relative_to(PRIVATE) or not output.is_relative_to(PRIVATE):
        raise ValueError('저장 입력과 출력은 지정된 비공개 작업 폴더 안에 있어야 함')
    if output.exists() or not output.name.startswith('qa_fixture_'):
        raise ValueError('새 qa_fixture_ 폴더만 생성 가능')
    source_data = ORIGINAL.read_bytes()
    candidate_data, save_data = candidate_path.read_bytes(), save_path.read_bytes()
    assert sha(source_data) == SOURCE_SHA
    original, dat = DatFile(source_data), DatFile(candidate_data)
    assert dat.integrity_summary()['status'] == 'PASS'
    readers, events = semantic_evidence(original, dat)
    data_changes = [
        {'target': FRAME10, 'offset': 94702, 'source': 7, 'expected': 6,
         'format': '<h', 'field': 'frame10.event477.action0.Num',
         'reason': '시작 시 개발 그룹50 비활성 대신 활성; 기존 단축키 동작 유지'},
        {'target': 'object:510', 'offset': 42, 'source': 4, 'expected': 12,
         'format': '<H', 'field': 'NewObjectFlags.VisibleAtStart',
         'reason': '개발 단축키 안내를 처음부터 표시'},
    ]
    for change in data_changes:
        dat.patch(change['target'], change['offset'], struct.pack(change['format'], change['source']),
                  struct.pack(change['format'], change['expected']))
    result = dat.serialize()
    reread = DatFile(result)
    assert reread.integrity_summary()['status'] == 'PASS'
    before = DatFile(candidate_data)
    allowed = {}
    for change in data_changes:
        allowed.setdefault(change['target'], []).append(change)
    for target, changes in allowed.items():
        expected = bytearray(before.get_target(target)[1])
        for change in changes:
            struct.pack_into(change['format'], expected, change['offset'], change['expected'])
        assert reread.get_target(target)[1] == expected
    for index, obj in enumerate(before.objects):
        if index != 510:
            assert obj.raw == reread.objects[index].raw
    changed_chunks = []
    for location, chunk in before.by_location.items():
        if chunk.children:
            continue
        if chunk.decoded != reread.by_location[location].decoded:
            assert location == FRAME10 or chunk.chunk_id in (0x2256, 0x2257, 0x2242)
            changed_chunks.append(location)
    assert before.header == reread.header
    output.mkdir(parents=True)
    (output / 'THOG.qa-only.dat').write_bytes(result)
    save_json(output / 'event_evidence.json', events)
    profiles = []
    for name, changes in make_presets().items():
        data, edits = patch_ini(save_data, changes, readers)
        path = output / 'profiles' / name / 'saveprofile.ini'
        path.parent.mkdir(parents=True)
        path.write_bytes(data)
        profiles.append({'name': name, 'path': path.relative_to(output).as_posix(),
                         'sha256': sha(data), 'expected_values': changes, 'changes': edits,
                         'status': 'PASS', 'runtime_status': 'NOT_RUN'})
    # 원본·후보·입력 저장 파일에 쓰지 않았다는 종료 시 재확인.
    assert candidate_path.read_bytes() == candidate_data and save_path.read_bytes() == save_data
    report = {'status': 'PASS', 'runtime_status': 'NOT_RUN', 'qa_only': True,
              'original_dat_sha256': sha(source_data),
              'candidate_path': str(candidate_path), 'candidate_sha256': sha(candidate_data),
              'qa_dat_sha256': sha(result), 'source_save_path': str(save_path),
              'source_save_sha256': sha(save_data), 'tool_sha256': sha(Path(__file__).read_bytes()),
              'semantic_package_sha256': sha((SEMANTIC / 'package.json').read_bytes()),
              'raw_frames_sha256': sha(RAW.read_bytes()), 'data_changes': data_changes,
              'changed_decoded_chunks': changed_chunks,
              'profiles': profiles, 'warnings': [
                  '배포본에 절대 포함하지 않는 검수 전용 파일',
                  '별도 격리 프로필에 복사한 뒤 이어하기로 진입; 새 게임은 저장 값을 초기화함',
                  '기존 정상 저장/불러오기 증거와 fixture 검수 증거를 구분할 것',
                  '생성기는 게임 실행·설치본·실행 중 검수 폴더를 수정하지 않음']}
    save_json(output / 'fixture_report.json', report)
    print(json.dumps({'output': str(output), 'qa_dat_sha256': sha(result), 'profiles': len(profiles)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--save', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.candidate, args.save, args.output)
