"""완성된 시험 DAT를 다시 읽어 글꼴 연결과 변경 범위를 별도로 확인합니다."""
import io
import json
import struct
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tasks/THE_HORDE_OF_GORAK'))
from dat_container import DatFile, sha, utf16z, u32

BASE = ROOT / 'source_original/COBALT_MINER/steam_24347666/COBALT MINER.dat'
CANDIDATE = ROOT / 'working_private/COBALT_MINER' / (sys.argv[1] if len(sys.argv) > 1 else 'font_smoke_01') / 'COBALT MINER.dat'
assert CANDIDATE.parent.name in {'font_smoke_01', 'font_smoke_02'}
SEMANTIC = ROOT / 'extracted_private/COBALT_MINER/steam_24347666/nebula_01'
FAMILY = 'Cobalt Noto Sans KR'

def permitted_changes(before, after, ranges):
    assert len(before) == len(after)
    allowed = set()
    for start, end in ranges:
        assert 0 <= start <= end <= len(before)
        allowed.update(range(start, end))
    unexpected = [i for i, (x, y) in enumerate(zip(before, after)) if x != y and i not in allowed]
    assert not unexpected, unexpected[:10]

def font_info(raw):
    font = TTFont(io.BytesIO(raw), recalcTimestamp=False)
    cmap = font.getBestCmap()
    result = {'sha256': sha(raw), 'family': font['name'].getDebugName(1), 'style': font['name'].getDebugName(2),
              'weight': font['OS/2'].usWeightClass, 'hangul_syllables': sum(c in cmap for c in range(0xac00, 0xd7a4)),
              'cmap_count': len(cmap), 'embedding_flags': font['OS/2'].fsType}
    font.close()
    return result

def main():
    source = DatFile.load(BASE)
    candidate = DatFile.load(CANDIDATE)
    package = json.loads((SEMANTIC / 'package.json').read_text(encoding='utf-8-sig'))
    expected_button_handles = {int(k) for k, v in package['FrameItems']['Items'].items() if v['Header']['Type'] == 33}
    assert len(source.objects) == len(candidate.objects)
    assert source.header == candidate.header
    assert set(source.by_location) == set(candidate.by_location)
    objects = []
    for before, after in zip(source.objects, candidate.objects):
        ranges = []
        if before.index in expected_button_handles:
            start = struct.unpack_from('<H', before.decoded, 12)[0] + 20
            ranges = [(start + 52, start + 56), (start + 59, start + 60), (start + 64, start + 128)]
            assert utf16z(after.decoded, start + 64)[0] == FAMILY and after.decoded[start + 59] == 129
        if before.index == 60:
            assert utf16z(before.decoded, 348)[0] == 'NEW GAME'
            assert utf16z(after.decoded, 348)[0] == '새 게임'
            ranges.append((348, 366))
        permitted_changes(before.decoded, after.decoded, ranges)
        if ranges:
            objects.append({'object_handle': before.index, 'ranges': ranges,
                            'before_sha256': sha(before.decoded), 'after_sha256': sha(after.decoded)})
    assert [b.handle for b in source.fonts] == [b.handle for b in candidate.fonts]
    logical = []
    for before, after in zip(source.fonts, candidate.fonts):
        permitted_changes(before.decoded, after.decoded, [(28, 32), (35, 36), (40, 104)])
        assert utf16z(after.decoded, 40)[0] == FAMILY and after.decoded[35] == 129
        logical.append({'handle': before.handle, 'old_family': utf16z(before.decoded, 40)[0],
                        'new_family': FAMILY, 'height': struct.unpack_from('<i', after.decoded, 12)[0],
                        'weight': u32(after.decoded, 28)})
    embedded = {b.offset: font_info(b.decoded) for b in DatFile._blocks(candidate.one(0x2259).decoded)}
    source_embedded = [font_info(b.decoded) for b in DatFile._blocks(source.one(0x2259).decoded)]
    assert len(embedded) == len(source_embedded)
    info0, info1 = source.one(0x2258).decoded, candidate.one(0x2258).decoded
    assert len(info0) == len(info1) and len(info1) % 96 == 0
    mappings = []
    for offset in range(0, len(info1), 96):
        old, new = info0[offset:offset + 96], info1[offset:offset + 96]
        permitted_changes(old, new, [(16, 20), (23, 24), (28, 96)])
        font = embedded[u32(new, 92)]
        assert font['family'] == FAMILY and font['weight'] == u32(new, 16)
        assert font['hangul_syllables'] == 11172 and font['embedding_flags'] == 0
        assert utf16z(new, 28)[0] == FAMILY and new[23] == 129
        mappings.append({'index': offset // 96, 'embedded_offset': u32(new, 92), 'embedded_sha256': font['sha256']})
    references = []
    for handle, obj in package['FrameItems']['Items'].items():
        props = obj['Properties']
        paragraphs = props.get('ObjectParagraphs', {}).get('Paragraphs', [])
        for i, paragraph in enumerate(paragraphs):
            references.append({'object_handle': int(handle), 'object_name': obj['Name'], 'field': f'ObjectParagraphs/Paragraphs/{i}/FontHandle', 'font_handle': paragraph['FontHandle']})
        counter = props.get('ObjectCounter', {})
        if counter.get('Font', 0) > 0:
            references.append({'object_handle': int(handle), 'object_name': obj['Name'], 'field': 'ObjectCounter/Font', 'font_handle': counter['Font'], 'display_type': counter['DisplayType']})
    handles = {b.handle for b in candidate.fonts}
    assert all(r['font_handle'] in handles for r in references)
    allowed_chunk_ids = {0x2259, 0x2258, 0x2256, 0x2257, 0x2242, 0x6667, 0x5556}
    event_target = 'top/031:3333/008:333d'
    for location, before in source.by_location.items():
        after = candidate.by_location[location]
        if before.decoded != after.decoded:
            if CANDIDATE.parent.name == 'font_smoke_02' and location == event_target:
                permitted_changes(before.decoded, after.decoded, [(3206, 3224)])
                assert utf16z(before.decoded, 3206)[0] == 'NEW GAME'
                assert utf16z(after.decoded, 3206)[0] == '새 게임'
            elif CANDIDATE.parent.name == 'font_smoke_02' and location == 'top/031:3333':
                # 자식은 이 반복문에서 각각 비교하므로 부모는 청크 구조만 비교한다.
                assert [c.location for c in before.children] == [c.location for c in after.children]
            else:
                assert before.chunk_id in allowed_chunk_ids
        assert before.chunk_id == after.chunk_id and before.flag == after.flag
    assert candidate.integrity_summary()['status'] == 'PASS'
    output = {'source_sha256': sha(source.original), 'candidate_sha256': sha(candidate.original),
              'verifier_sha256': sha(Path(__file__).read_bytes()), 'semantic_sha256': sha((SEMANTIC / 'package.json').read_bytes()),
              'source_embedded': source_embedded, 'candidate_embedded': embedded, 'logical_fonts': logical,
              'mappings': mappings, 'font_references': references, 'buttons': objects,
              'counts': {'objects': len(source.objects), 'paragraph_counter_font_references': len(references),
                         'buttons': len(expected_button_handles), 'logical_fonts': len(logical), 'embedded': len(embedded)},
              'static_status': 'PASS', 'runtime_status': 'NOT_RUN',
              'scope': '원본과 시험 후보의 모든 객체·글꼴 바이트 변경 경계 및 연결. 실제 렌더링은 별도 검사.'}
    target = CANDIDATE.parent / 'independent_font_verification.json'
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(output['counts']))

if __name__ == '__main__':
    main()
