"""미분류 후보 중 구조가 입증되는 로케일 표·가져오기 필드·저장 경로를 보강합니다."""
import copy
import json
import re
import struct
from pathlib import Path
import pefile
import native_inventory as inv

ROOT, BASE, OUT = inv.ROOT, inv.BASE, inv.OUT
SOURCE = Path('C:/Program Files (x86)/Windows Kits/10/Source/10.0.22621.0/ucrt/locale/get_qualified_locale.cpp')

def wide(raw, start):
    end = start
    while raw[end:end + 2] != b'\0\0':
        end += 2
        if end - start > 1000:
            raise ValueError('원문 문자열 경계 초과')
    return raw[start:end].decode('utf-16le')

def main():
    source_text = SOURCE.read_text(encoding='utf-8-sig')
    tables = {}
    for name in ['__acrt_rg_language', '__acrt_rg_country']:
        body = re.search(re.escape(name) + r'\[\]\s*\{(.*?)\};', source_text, re.S).group(1)
        tables[name] = re.findall(r'\{\s*L"([^"]+)"\s*,\s*L"([^"]+)"\s*\}', body)
    source_path = OUT / 'native_inventory.jsonl'
    rows = [json.loads(x) for x in source_path.read_text(encoding='utf-8').split('\n') if x]
    typed = []
    for file in sorted({x['file'] for x in rows}):
        data = (BASE / file).read_bytes()
        image = pefile.PE(data=data)
        for name, pairs in tables.items():
            first_text = (pairs[0][0] + '\0').encode('utf-16le')
            cursor = 0
            while True:
                at = data.find(first_text, cursor)
                if at < 0:
                    break
                cursor = at + len(first_text)
                address = image.OPTIONAL_HEADER.ImageBase + image.get_rva_from_offset(at)
                prefix = struct.pack('<I', address) + (pairs[0][1] + '\0').encode('utf-16le')
                start = data.find(prefix)
                if start < 0:
                    continue
                decoded = []
                try:
                    for index in range(len(pairs)):
                        record = start + index * 12
                        pointer = struct.unpack_from('<I', data, record)[0]
                        key_at = image.get_offset_from_rva(pointer - image.OPTIONAL_HEADER.ImageBase)
                        decoded.append((wide(data, key_at), wide(data, record + 4)))
                except (pefile.PEFormatError, ValueError, struct.error, UnicodeError):
                    continue
                if decoded == pairs:
                    end = start + len(pairs) * 12
                    typed.append({'file': file, 'file_sha256': inv.sha(data), 'start': start, 'end': end,
                                  'type': 'CRT_LOCALE_TRANSLATION_TABLE', 'table': name, 'entries': len(pairs),
                                  'raw_sha256': inv.sha(data[start:end]), 'source_path': str(SOURCE),
                                  'source_sha256': inv.sha(SOURCE.read_bytes()),
                                  'reason': 'CRT 원문의 언어/국가 별칭 표 전체를 32비트 포인터+UTF16 코드 배열로 해석해 모든 키·값·순서를 대조함. 표시 문구가 아닌 로케일 이름 조회 자료'})
        for directory in ('DIRECTORY_ENTRY_IMPORT', 'DIRECTORY_ENTRY_DELAY_IMPORT'):
            for module in getattr(image, directory, []):
                for symbol in module.imports:
                    if symbol.name is None or symbol.name_offset is None:
                        continue
                    start, end = symbol.name_offset - 2, symbol.name_offset + len(symbol.name) + 1
                    typed.append({'file': file, 'file_sha256': inv.sha(data), 'start': start, 'end': end,
                                  'type': 'IMAGE_IMPORT_BY_NAME', 'symbol': symbol.name.decode('ascii'),
                                  'raw_sha256': inv.sha(data[start:end]),
                                  'reason': 'PE 가져오기 함수의 Hint16+함수명+NUL 구조. 문자열 검색이 힌트 바이트까지 합친 오탐 후보'})
    evidence_path = OUT.parent / 'rea_ini_evidence.json'
    bundle = json.loads(evidence_path.read_text(encoding='utf-8'))
    path_evidence = next(r for r in bundle['records'] if r['operation'] == 'procedure_pseudo_code')
    assert path_evidence['provider']['id'] == 'ghidra'
    assert 'MMFApplications' in path_evidence['normalized_result']
    changes = []
    for row in rows:
        if row['classification'] != 'UNKNOWN':
            continue
        owner = next((x for x in typed if x['file'] == row['file'] and
                      x['start'] <= row['file_offset'] and row['file_offset'] + row['bytes'] <= x['end']), None)
        if owner:
            row.update(classification='INTERNAL', reason=owner['reason'], additional_evidence=owner)
        elif row['file'] == 'Modules/kcini.mfx' and row['source'] == 'MMFApplications\\':
            assert row['file_sha256'] == path_evidence['subject']['digest']['sha256']
            row.update(classification='INTERNAL', reason='Ghidra 함수0x10e02980이 저장 폴더 경로에 덧붙이는 하위 경로명. 표시용 문구가 아님',
                       additional_evidence={'path': str(evidence_path.relative_to(ROOT)).replace('\\', '/'),
                                            'sha256': inv.sha(evidence_path.read_bytes()), 'evidence_id': path_evidence['evidence_id']})
        else:
            continue
        changes.append({key: row[key] for key in ['file', 'file_sha256', 'file_offset', 'source_bytes_sha256', 'source', 'classification', 'reason', 'additional_evidence']})
    inv.save('native_inventory_v2.jsonl', rows)
    inv.save('additional_classification.json', {'input_inventory_sha256': inv.sha(source_path.read_bytes()),
                                              'reviewer_script_sha256': inv.sha(Path(__file__).read_bytes()),
                                              'changes': changes, 'typed_structures': typed,
                                              'limits': ['배열 전체 또는 PE 필드 경계로 확인된 항목만 내부용으로 처리함',
                                                         '나머지 미분류와 실제 화면 검수 상태는 그대로임']})
    import collections
    summary = {'records': len(rows), 'classifications': dict(collections.Counter(x['classification'] for x in rows)),
               'additional_internal': len(changes), 'state': 'NOT_RUN', 'full_native_classification': 'NOT_RUN',
               'input_inventory': str(source_path.relative_to(ROOT)).replace('\\', '/'),
               'input_sha256': inv.sha(source_path.read_bytes()),
               'output_sha256': inv.sha((OUT / 'native_inventory_v2.jsonl').read_bytes()),
               'selected_translations_changed': False, 'native_candidate_02_content_affected': False}
    inv.save('summary_v2.json', summary)
    print(json.dumps(summary, ensure_ascii=False))

if __name__ == '__main__':
    main()
