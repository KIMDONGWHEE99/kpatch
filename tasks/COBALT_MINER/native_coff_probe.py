"""미분류 바이트가 로컬 CRT 자료 절 전체와 일치하는지 조사합니다. 자동 분류는 하지 않습니다."""
import collections
import json
import struct
import sys
from pathlib import Path
import native_inventory as inv

sys.path.insert(0, str(inv.ROOT / 'tasks/THE_HORDE_OF_GORAK'))
from native_coff_math_review import members

LIB = Path('C:/Program Files (x86)/Windows Kits/10/Lib/10.0.22621.0/ucrt/x86/libucrt.lib')

def main():
    original = inv.OUT / 'native_inventory_v2.jsonl'
    rows = [json.loads(x) for x in original.read_text(encoding='utf-8').split('\n') if x]
    groups = collections.defaultdict(list)
    for row in rows:
        if row['classification'] == 'UNKNOWN':
            groups[row['file']].append(row)
    data_by_file = {name: (inv.BASE / name).read_bytes() for name in groups}
    library = LIB.read_bytes()
    sections = []
    for name, member_offset, data in members(library):
        if len(data) < 20 or struct.unpack_from('<H', data)[0] != 0x14c:
            continue
        _, count, _, pointer, symbols_count, optional, _ = struct.unpack_from('<HHIIIHH', data)
        names = data[pointer + symbols_count * 18:]
        symbols = collections.defaultdict(list)
        index = 0
        while index < symbols_count:
            record = data[pointer + index * 18:pointer + (index + 1) * 18]
            if record[:4] == b'\0\0\0\0':
                offset = struct.unpack_from('<I', record, 4)[0]
                symbol = names[offset:].split(b'\0', 1)[0].decode('ascii', 'replace')
            else:
                symbol = record[:8].rstrip(b'\0').decode('ascii', 'replace')
            value, section, _, storage, extra = struct.unpack_from('<IhHBB', record, 8)
            if section > 0 and not symbol.startswith('.'):
                symbols[section].append({'name': symbol, 'offset': value, 'storage': storage})
            index += 1 + extra
        for index in range(count):
            fields = struct.unpack_from('<8sIIIIIIHHI', data, 20 + optional + index * 40)
            label, _, _, size, offset, _, _, relocations, _, flags = fields
            label = label.rstrip(b'\0').decode('ascii', 'replace')
            if flags & 0x20000000 or not flags & 0x40 or relocations or not 8 <= size <= 65536 or label.startswith('.debug'):
                continue
            raw = data[offset:offset + size]
            if len(raw) != size or len(set(raw)) < 4:
                continue
            sections.append({'member': name, 'member_sha256': inv.sha(data), 'member_offset': member_offset,
                             'section': label, 'section_index': index + 1, 'section_data_offset': offset,
                             'section_bytes': size, 'section_sha256': inv.sha(raw), 'symbols': symbols[index + 1], 'raw': raw})
    matches = []
    for file, data in data_by_file.items():
        for section in sections:
            cursor = 0
            while True:
                start = data.find(section['raw'], cursor)
                if start < 0:
                    break
                end = start + len(section['raw'])
                selected = [row for row in groups[file] if start <= row['file_offset'] and row['file_offset'] + row['bytes'] <= end]
                if selected:
                    matches.append({'file': file, 'file_sha256': inv.sha(data), 'start': start, 'end': end,
                                    **{key: value for key, value in section.items() if key != 'raw'},
                                    'covered_offsets': [row['file_offset'] for row in selected],
                                    'candidate_samples': [row['source'] for row in selected[:3]]})
                cursor = end
    inv.save('coff_probe.json', {'library': str(LIB), 'library_sha256': inv.sha(library),
                               'input_inventory_sha256': inv.sha(original.read_bytes()),
                               'sections_examined': len(sections), 'matches': matches,
                               'status': 'NOT_RUN', 'limit': '전체 절 바이트 일치 후보. 용도 판독 후 별도 분류해야 함'})
    print(json.dumps({'sections': len(sections), 'matches': len(matches),
                      'covered': len({(x['file'], p) for x in matches for p in x['covered_offsets']}),
                      'members': dict(collections.Counter(x['member'].rsplit('\\', 1)[-1] for x in matches))}))

if __name__ == '__main__':
    main()
