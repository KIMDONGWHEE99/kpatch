"""추가 Windows 이름·경로 API의 직접 인수만 확인합니다."""
import collections
import json
import struct
from pathlib import Path
import pefile
import native_inventory as inv
from native_api_boundary_review import API_ARGUMENTS, Decoder, consume


def main():
    for suffix in ('A', 'W'):
        for name, index, role in [('RegOpenKey', 1, '레지스트리 경로'), ('RegOpenKeyEx', 1, '레지스트리 경로'),
                                 ('RegQueryValueEx', 1, '레지스트리 값 이름'), ('RegSetValueEx', 1, '레지스트리 값 이름'),
                                 ('GetEnvironmentVariable', 0, '환경 변수 이름'), ('FindResource', 2, '리소스 형식 이름'),
                                 ('GetPrivateProfileInt', 0, '설정 섹션 이름'), ('GetPrivateProfileString', 0, '설정 섹션 이름')]:
            API_ARGUMENTS[name + suffix] = index, role
    source = inv.OUT / 'native_inventory_v16.jsonl'
    rows = [json.loads(x) for x in source.read_text(encoding='utf-8').split('\n') if x]
    decoder, images, changes = Decoder(), {}, []
    for row in rows:
        if row['classification'] != 'UNKNOWN' or not row.get('static_references'):
            continue
        file = row['file']
        if file not in images:
            data = (inv.BASE / file).read_bytes()
            pe = pefile.PE(data=data)
            imports = {item.address: module.dll.decode() + ':' + item.name.decode()
                       for module in pe.DIRECTORY_ENTRY_IMPORT for item in module.imports if item.name}
            relocations = {pe.get_offset_from_rva(x.rva) for b in pe.DIRECTORY_ENTRY_BASERELOC for x in b.entries if x.type == 3}
            images[file] = data, pe, imports, relocations
        data, pe, imports, relocations = images[file]
        assert inv.sha(data) == row['file_sha256']
        assert inv.sha(data[row['file_offset']:row['file_offset'] + row['bytes']]) == row['source_bytes_sha256']
        results, complete, prefixes = [], True, []
        for reference in row['static_references']:
            actual = reference['target_offset']
            if actual != row['file_offset']:
                pointer_field = actual - 4
                if pointer_field not in relocations or not pointer_field <= row['file_offset'] < actual:
                    complete = False
                    break
                pointer = struct.unpack_from('<I', data, pointer_field)[0]
                if pe.get_section_by_rva(pointer - pe.OPTIONAL_HEADER.ImageBase) is None:
                    complete = False
                    break
                prefixes.append({'field_offset': pointer_field, 'pointer': hex(pointer), 'actual_literal_start': actual})
            target = pe.OPTIONAL_HEADER.ImageBase + pe.get_rva_from_offset(actual)
            for pointer in reference['pointer_offsets']:
                assert struct.unpack_from('<I', data, pointer)[0] == target
                proof = consume(decoder, imports, data, pe, pointer, target)
                if proof is None:
                    complete = False
                    break
                results.append({'pointer_offset': pointer, **proof})
            if not complete:
                break
        if not complete or not results:
            continue
        row.update(classification='INTERNAL', reason='Windows API의 ' + '·'.join(sorted({x['role'] for x in results})) + ' 인수로 직접 소비되는 식별자',
                   additional_evidence={'method': '현재 원본의 PE 재배치 참조와 분기 없는 실제 인수 전달 명령 확인',
                                        'consumers': results, 'adjacent_pointer_prefixes': prefixes,
                                        'limitation': '확인되지 않은 간접 호출과 표시 본문 인수는 미분류로 남김'})
        changes.append(row)
    inv.save('native_inventory_v17.jsonl', rows)
    inv.save('api_key_classification_v17.json', {'input_sha256': inv.sha(source.read_bytes()), 'tool_sha256': inv.sha(Path(__file__).read_bytes()), 'changes': changes})
    summary = {'records': len(rows), 'classifications': dict(collections.Counter(x['classification'] for x in rows)),
               'additional_internal': len(changes), 'full_native_classification': 'NOT_RUN',
               'output_sha256': inv.sha((inv.OUT / 'native_inventory_v17.jsonl').read_bytes()), 'native_candidate_04_content_affected': False}
    inv.save('summary_v17.json', summary)
    print(json.dumps(summary))
    print(json.dumps([(r['file'], r['file_offset'], r['source']) for r in changes], ensure_ascii=False))


if __name__ == '__main__':
    main()
