"""검증된 이전 후보에 창 제목 번역 세 필드만 추가합니다."""
import json
from pathlib import Path
import native_inventory as inv


def main():
    previous = inv.ROOT / 'working_private/COBALT_MINER/native_candidate_03'
    candidate = inv.ROOT / 'working_private/COBALT_MINER/native_candidate_04'
    assert not candidate.exists()
    worklist = inv.OUT / 'native_visible_worklist_v5.json'
    rows = json.loads(worklist.read_text(encoding='utf-8'))[-3:]
    assert {x['source'] for x in rows} == {'Untitled', ' - 24 bit', ' - 32 bit'}
    files = ['COBALT MINER.exe', 'Modules/cctrans.dll', 'Modules/mmfs2.dll', 'Modules/steam_api.dll', 'Modules/Steamworks.mfx']
    generated = {name: (previous / name).read_bytes() for name in files}
    data = bytearray(generated['COBALT MINER.exe'])
    patches = []
    for row in rows:
        assert row['file'] == 'COBALT MINER.exe' and row['encoding'] == 'utf-16le'
        offset, size = row['file_offset'], row['bytes']
        before = bytes(data[offset:offset + size + 2])
        assert before[:-2].decode('utf-16le') == row['source'] and before[-2:] == bytes(2)
        assert inv.sha(before[:-2]) == row['source_bytes_sha256']
        encoded = row['translation'].encode('utf-16le') + bytes(2)
        assert len(encoded) <= len(before)
        after = encoded.ljust(len(before), b'\0')
        data[offset:offset + len(before)] = after
        patches.append({'file': row['file'], 'offset': offset, 'size': len(before), 'source': row['source'],
                        'translation': row['translation'], 'before': before.hex(), 'after': after.hex()})
    generated['COBALT MINER.exe'] = bytes(data)
    candidate.mkdir(parents=True)
    for name, raw in generated.items():
        path = candidate / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    audit = {'candidate': str(candidate.relative_to(inv.ROOT)), 'source_build': 'steam_24347666',
             'parent_candidate': str(previous.relative_to(inv.ROOT)), 'expected_fields': 192,
             'worklist_sha256': inv.sha(worklist.read_bytes()), 'tool_sha256': inv.sha(Path(__file__).read_bytes()),
             'patches': patches, 'files': [{'file': name, 'parent_sha256': inv.sha((previous / name).read_bytes()), 'candidate_sha256': inv.sha(raw)} for name, raw in generated.items()],
             'distribution_allowlist': files, 'graphics_qa': 'NOT_RUN'}
    (candidate / 'native_title_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'candidate': str(candidate), 'new_fields': len(patches), 'exe_sha256': inv.sha(data)}))


if __name__ == '__main__':
    main()
