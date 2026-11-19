"""종료 결함의 원인을 분리하는 검수 전용 DAT를 만듭니다. 배포용이 아닙니다."""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tasks/THE_HORDE_OF_GORAK'))
from dat_container import DatFile, sha

WORK = ROOT / 'working_private/COBALT_MINER'
ORIGINAL = WORK / 'qa_fixtures/original_terminal_a_control_01/COBALT MINER.qa-only.dat'
CANDIDATE = WORK / 'qa_fixtures/ko03_terminal_a_01/COBALT MINER.qa-only.dat'


def build(mode):
    original = DatFile.load(ORIGINAL)
    source = DatFile.load(CANDIDATE)
    result = DatFile.load(CANDIDATE)
    allowed = set()
    if mode == 'no_objects':
        for key in (0x2256, 0x2257):
            result.one(key).replacement = original.one(key).decoded
            allowed.add(result.one(key).location)
    elif mode == 'no_media':
        for key in (0x6666, 0x5555):
            result.one(key).replacement = original.one(key).decoded
            allowed.add(result.one(key).location)
    elif mode == 'no_fonts':
        for key in (0x2259, 0x2258, 0x6667, 0x5556):
            result.one(key).replacement = original.one(key).decoded
            allowed.add(result.one(key).location)
        meta = json.loads((WORK / 'candidate_builds/ko_candidate_03/build_report.json').read_text(encoding='utf-8'))
        for row in meta['fonts']['buttons']:
            handle = row['object']
            before = original.objects[handle].decoded
            current = bytearray(result.objects[handle].decoded)
            offset = struct.unpack_from('<H', before, 12)[0] + 20 + 36
            assert struct.unpack_from('<H', current, 12)[0] + 20 + 36 == offset
            current[offset:offset + 92] = before[offset:offset + 92]
            result.objects[handle].replacement = bytes(current)
        allowed.update(result.one(key).location for key in (0x2256, 0x2257))
    else:
        raise ValueError(mode)
    data = result.serialize()
    check = DatFile(data)
    assert check.integrity_summary()['status'] == 'PASS'
    allowed.add(result.one(0x2242).location)
    changes = []
    for loc, block in source.by_location.items():
        after = check.by_location[loc]
        if not block.children and block.decoded != after.decoded:
            assert loc in allowed, loc
            changes.append(dict(location=loc, before=sha(block.decoded), after=sha(after.decoded)))
    for index, (left, right) in enumerate(zip(source.chunks, check.chunks)):
        if left.chunk_id == 0x3333:
            assert left.decoded == right.decoded, index
    assert check.header == source.header
    output = WORK / f'qa_fixtures/ko03_terminal_a_{mode}_01'
    output.mkdir()
    target = output / 'COBALT MINER.qa-only.dat'
    target.write_bytes(data)
    report = dict(status='PASS', runtime_status='NOT_RUN', qa_only=True,
                  purpose='종료 결함 원인 분리. 한글 표시 판정이나 배포에 사용하지 않음',
                  mode=mode, original_sha256=sha(original.original), source_sha256=sha(source.original),
                  output_sha256=sha(data), changes=changes,
                  event_chunks_and_header_unchanged=True)
    (output / 'isolation_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(mode, report['output_sha256'])


if __name__ == '__main__':
    build(sys.argv[1])
