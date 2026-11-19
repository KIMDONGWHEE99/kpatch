"""화면 접근에만 쓰는 개발 안내·픽셀 검수 사본을 만든다. 게임 실행은 하지 않는다."""
import json
import shutil
import struct
from pathlib import Path

from dat_container import DatFile, sha

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'working_private/THE_HORDE_OF_GORAK'
CANDIDATE = ROOT / 'build_candidate/THE_HORDE_OF_GORAK/ko_candidate_02/THOG.dat'
FIXTURE = WORK / 'qa_fixture_02'
OUTPUT = WORK / 'qa_fixture_03'
SEMANTIC = ROOT / 'extracted_private/THE_HORDE_OF_GORAK/steam_26336311/nebula_03/package.json'
FRAME10 = 'top/037:3333/008:333d'


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def verify(before, after, changes, append=None):
    """작성 코드의 성공 카운트 대신 전 객체·청크를 허용 구간과 대조한다."""
    reread = DatFile(after)
    assert reread.integrity_summary()['status'] == 'PASS'
    expected = {}
    for change in changes:
        target = change['target']
        expected.setdefault(target, bytearray(before.get_target(target)[1]))
        struct.pack_into(change['format'], expected[target], change['offset'], change['expected'])
    if append:
        target, offset, data = append
        expected.setdefault(target, bytearray(before.get_target(target)[1]))
        expected[target][offset:offset] = data
    for target, data in expected.items():
        assert reread.get_target(target)[1] == data, target
    for index, obj in enumerate(before.objects):
        if f'object:{index}' not in expected:
            assert obj.raw == reread.objects[index].raw
    changed = []
    for location, chunk in before.by_location.items():
        if chunk.children:
            continue
        if chunk.decoded != reread.by_location[location].decoded:
            assert location in expected or chunk.chunk_id in (0x2242, 0x2256, 0x2257), location
            changed.append(location)
    assert before.header == reread.header
    return changed


def main():
    if (OUTPUT / 'pixel_scene19').exists():
        raise ValueError('새 출력 폴더만 허용')
    source = (FIXTURE / 'THOG.qa-only.dat').read_bytes()
    candidate = CANDIDATE.read_bytes()
    assert sha(source) == 'dfb4fb958c6342c32d27fa57330be28b8c12f576dbf409f1f0a2d7b96f0ecf2a'
    assert sha(candidate) == 'ead9003686811357da03b1f0e6c36f2fb05a3d6cd9aa4a060bc5b629fb6c9b6c'
    dat = DatFile(source)
    change = {'target': FRAME10, 'offset': 95326, 'format': '<H', 'source': 0, 'expected': 1,
              'field': 'frame10.event489.action0.parameter0.Value',
              'reason': 'Tab을 누르지 않았을 때도 제목 대신 기존 전체 설명 단락1을 표시. 키 조건과 기능 행동은 유지.'}
    dat.patch(FRAME10, 95326, struct.pack('<H', 0), struct.pack('<H', 1))
    result = dat.serialize()
    changed = verify(DatFile(source), result, [change])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT / 'THOG.qa-only.dat').exists():
        # 픽셀 파트 도중 중단한 경우 이미 만든 개발 사본은 재검증만 하고 보존한다.
        assert (OUTPUT / 'THOG.qa-only.dat').read_bytes() == result
    else:
        (OUTPUT / 'THOG.qa-only.dat').write_bytes(result)
        shutil.copytree(FIXTURE / 'profiles', OUTPUT / 'profiles')
    profiles = []
    for path in sorted((FIXTURE / 'profiles').rglob('*')):
        if path.is_file():
            relative = path.relative_to(FIXTURE)
            assert path.read_bytes() == (OUTPUT / relative).read_bytes()
            profiles.append({'path': relative.as_posix(), 'sha256': sha(path.read_bytes())})
    dev_report = {'qa_only': True, 'status': 'PASS', 'runtime_status': 'NOT_RUN',
         'source_fixture': str(FIXTURE), 'source_fixture_sha256': sha(source),
         'candidate_sha256': sha(candidate), 'qa_dat_sha256': sha(result), 'changes': [change],
         'changed_decoded_chunks': changed, 'unchanged_profiles': profiles,
         'tool_sha256': sha(Path(__file__).read_bytes())}
    if not (OUTPUT / 'fixture_report.json').exists():
        save(OUTPUT / 'fixture_report.json', dev_report)

    # 종료 표식은 충돌 감지에도 쓰인다. 본편 좌표를 바꾸지 않고 이벤트 없는 예비 장면에 표시 사본만 추가한다.
    package = json.loads(SEMANTIC.read_text(encoding='utf-8'))
    dat = DatFile(candidate)
    frame_chunks = [c for c in dat.chunks if c.chunk_id == 0x3333]
    changes, appended, records = [], bytearray(), []
    destination = next(c for c in frame_chunks[19].children if c.chunk_id == 0x3338)
    count = struct.unpack_from('<I', destination.decoded)[0]
    assert count == 10 and len(destination.decoded) == 8 + count * 20
    assert destination.decoded[-4:].hex() == 'e5af70b7'
    occupied = {x['Handle'] for x in package['Frames'][19]['FrameInstances']['Instances']}
    for index, (frame, handle, image, x, y) in enumerate([(10, 818, 215, 320, 300),
                                                       (10, 489, 980, 640, 300),
                                                       (10, 799, 1512, 960, 300),
                                                       (9, 222, 1820, 543, 500)]):
        instances = package['Frames'][frame]['FrameInstances']['Instances']
        matches = [i for i, row in enumerate(instances) if row['ObjectInfo'] == handle]
        assert len(matches) == 1
        position = matches[0]
        chunk = next(c for c in frame_chunks[frame].children if c.chunk_id == 0x3338)
        record_offset = 4 + position * 20
        record = bytearray(chunk.decoded[record_offset:record_offset+20])
        old = struct.unpack('<HHiihhHH', record)
        assert old[1] == handle and old[2:4] == (instances[position]['PositionX'], instances[position]['PositionY'])
        new_handle = 100 + index
        assert new_handle not in occupied
        struct.pack_into('<H', record, 0, new_handle)
        struct.pack_into('<ii', record, 4, x, y)
        struct.pack_into('<H', record, 16, 1)
        appended.extend(record)
        records.append({'image': image, 'object': handle, 'source_frame': frame,
                        'source_chunk': chunk.location, 'source_offset': record_offset,
                        'source_record_sha256': sha(chunk.decoded[record_offset:record_offset+20]),
                        'source_position': list(old[2:4]), 'destination_frame': 19,
                        'destination_instance': new_handle, 'destination_position': [x, y], 'layer': 1,
                        'destination_record_hex': record.hex()})
        if handle in (489, 799):
            flag = {'target': f'object:{handle}', 'offset': 42, 'format': '<H', 'source': 0, 'expected': 8,
                    'field': 'NewObjectFlags.VisibleAtStart', 'reason': '숨긴 충돌 표식의 픽셀을 검수 장면에서 표시'}
            changes.append(flag)
            dat.patch(flag['target'], 42, struct.pack('<H', 0), struct.pack('<H', 8))
    changes.append({'target': destination.location, 'offset': 0, 'format': '<I', 'source': count,
                    'expected': count + 4, 'field': 'FrameInstances.Count', 'reason': '원래 객체4개를 별도 검수 장면에 추가'})
    destination.replacement = struct.pack('<I', count + 4) + destination.decoded[4:-4] + appended + destination.decoded[-4:]
    pixels = dat.serialize()
    changed = verify(DatFile(candidate), pixels, changes, (destination.location, 4 + count * 20, appended))
    folder = OUTPUT / 'pixel_scene19'
    folder.mkdir()
    (folder / 'THOG.qa-only.dat').write_bytes(pixels)
    save(folder / 'fixture_report.json', {'qa_only': True, 'status': 'PASS', 'runtime_status': 'NOT_RUN',
         'candidate_sha256': sha(candidate), 'qa_dat_sha256': sha(pixels), 'entry_frame': 19,
         'changes': changes, 'instances_added': records, 'changed_decoded_chunks': changed,
         'reason': '장면19 원본 이벤트는 시작 시 소리 중지 한 개. 본편 종료 충돌 이벤트250/253에 영향을 주지 않는 화면 검수 사본.',
         'semantic_package_sha256': sha(SEMANTIC.read_bytes()), 'tool_sha256': sha(Path(__file__).read_bytes())})
    assert (FIXTURE / 'THOG.qa-only.dat').read_bytes() == source and CANDIDATE.read_bytes() == candidate
    print(json.dumps({'dev': sha(result), 'pixels': sha(pixels), 'output': str(OUTPUT)}))


if __name__ == '__main__':
    main()
