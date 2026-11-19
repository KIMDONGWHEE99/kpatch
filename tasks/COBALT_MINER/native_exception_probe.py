"""MSVC x86 예외 처리 표를 읽어 실제 catch 처리 함수만 좁힙니다. 분류는 바꾸지 않습니다."""
import collections
import json
import struct
from pathlib import Path
import pefile
import native_inventory as inv


def main():
    header = Path('C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.43.34808/include/ehdata.h')
    rows = [json.loads(x) for x in (inv.OUT / 'native_inventory_v17.jsonl').read_text(encoding='utf-8').split('\n') if x]
    files = sorted({r['file'] for r in rows if r['classification'] == 'UNKNOWN'})
    result = {'status': 'INVESTIGATION_ONLY', 'header': str(header), 'header_sha256': inv.sha(header.read_bytes()), 'files': {}}
    for file in files:
        data = (inv.BASE / file).read_bytes()
        pe = pefile.PE(data=data)
        base = pe.OPTIONAL_HEADER.ImageBase
        relocs = {pe.get_offset_from_rva(r.rva): struct.unpack_from('<I', data, pe.get_offset_from_rva(r.rva))[0]
                  for block in pe.DIRECTORY_ENTRY_BASERELOC for r in block.entries if r.type == 3}

        def off(va):
            assert pe.get_section_by_rva(va - base) is not None
            return pe.get_offset_from_rva(va - base)

        funcs, failures = [], []
        for version in (0x19930520, 0x19930521, 0x19930522):
            at = 0
            token = struct.pack('<I', version)
            while (at := data.find(token, at)) >= 0:
                start = at
                at += 1
                va = base + pe.get_rva_from_offset(start)
                refs = [p for p, value in relocs.items() if value == va]
                thunks = []
                for p in refs:
                    sec = pe.get_section_by_rva(pe.get_rva_from_offset(p))
                    if sec.Characteristics & 0x20000000 and data[p - 1] == 0xb8 and data[p + 4] == 0xe9:
                        target = base + pe.get_rva_from_offset(p + 9) + struct.unpack_from('<i', data, p + 5)[0]
                        thunks.append({'start': base + pe.get_rva_from_offset(p - 1), 'bytes': data[p - 1:p + 9].hex(), 'handler_target': target})
                if not thunks:
                    continue
                values = struct.unpack_from('<9I', data, start)
                count, table = values[3:5]
                record = {'offset': start, 'va': va, 'dwords': list(values), 'sha256': inv.sha(data[start:start + 36]), 'thunks': thunks, 'try_blocks': []}
                try:
                    assert count < 100
                    if count:
                        cursor = off(table)
                        for index in range(count):
                            entry = struct.unpack_from('<5I', data, cursor + 20 * index)
                            handler_count, handlers = entry[3:]
                            assert 0 < handler_count < 100
                            handlers_at = off(handlers)
                            block = {'offset': cursor + 20 * index, 'dwords': list(entry), 'handlers': []}
                            for number in range(handler_count):
                                handler_at = handlers_at + 16 * number
                                flags, typedesc, displacement, code = struct.unpack_from('<4I', data, handler_at)
                                section = pe.get_section_by_rva(code - base)
                                assert section is not None and section.Characteristics & 0x20000000
                                name = None
                                if typedesc:
                                    type_at = off(typedesc) + 8
                                    end = data.index(b'\0', type_at, type_at + 1000)
                                    name = data[type_at:end].decode('ascii')
                                block['handlers'].append({'offset': handler_at, 'flags': flags, 'typedesc': typedesc, 'type': name,
                                                          'object_displacement': displacement, 'code': code, 'raw_sha256': inv.sha(data[handler_at:handler_at + 16])})
                            record['try_blocks'].append(block)
                    funcs.append(record)
                except (AssertionError, ValueError, UnicodeError, struct.error) as error:
                    failures.append({'offset': start, 'error_type': type(error).__name__, 'dwords': list(values)})
        result['files'][file] = {'sha256': inv.sha(data), 'funcinfo': funcs, 'unparsed_candidates': failures}
    inv.save('exception_handler_probe.json', result)
    summary = {}
    for file, record in result['files'].items():
        handlers = [h for f in record['funcinfo'] for b in f['try_blocks'] for h in b['handlers']]
        summary[file] = {'functions': len(record['funcinfo']), 'try_blocks': sum(len(f['try_blocks']) for f in record['funcinfo']),
                         'handler_types': dict(collections.Counter(h['type'] or 'catch(...)' for h in handlers)),
                         'handler_addresses': sorted({hex(h['code']) for h in handlers}), 'unparsed_candidates': record['unparsed_candidates']}
    inv.save('exception_handler_summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
