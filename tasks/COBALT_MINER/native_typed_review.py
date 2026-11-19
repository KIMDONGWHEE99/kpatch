"""PE 형식·CRT 자료절 전체 일치로 증명한 구조만 추가 분류합니다."""
import collections
import json
import struct
from pathlib import Path
import pefile
import native_inventory as inv

UCRT = Path('C:/Program Files (x86)/Windows Kits/10/Source/10.0.22621.0/ucrt')


def source_ref(name, lines):
    path = UCRT / name
    text = path.read_text(encoding='utf-8-sig').splitlines()
    return {'path': str(path), 'sha256': inv.sha(path.read_bytes()),
            'consumer_lines': [{'line': n, 'text': text[n - 1]} for n in lines]}


def main():
    original = inv.OUT / 'native_inventory_v2.jsonl'
    rows = [json.loads(x) for x in original.read_text(encoding='utf-8').split('\n') if x]
    probe_path = inv.OUT / 'coff_probe.json'
    probe = json.loads(probe_path.read_text(encoding='utf-8'))
    assert probe['input_inventory_sha256'] == inv.sha(original.read_bytes())
    assert inv.sha(Path(probe['library']).read_bytes()) == probe['library_sha256']
    rules = [
        ('parse_floating_point_possible_', '숫자 입력 파서의 INFINITY/NaN 문법 토큰. COFF 자료절 전체와 일치하며 원문에서 입력 문자 비교에 소비됨', 'inc/corecrt_internal_strtox.h', [1264, 1269, 1270, 1272, 1286, 1310, 1311]),
        ('ld12_pow10_', '확장 정밀도 실수 계산용 10의 거듭제곱 표. 전체 348바이트 자료절 일치이며 문자처럼 보인 부분도 수치 배열임', 'convert/atoldbl.cpp', [109, 142, 422, 426]),
        ('__first_127char', '로케일의 문자 분류를 비교하는 ASCII 127바이트 배열. 전체 자료절 일치이며 화면 문자열이 아님', 'locale/wsetlocale.cpp', [16, 734, 735, 741, 744]),
        ('__acrt_stdio_parse_mode', '파일 열기 모드의 문자 인코딩 식별자. 전체 자료절 일치하며 tcsnicmp 입력 비교에 소비됨', 'inc/corecrt_internal_stdio.h', [763, 764, 784, 789]),
    ]
    typed = []
    for match in probe['matches']:
        symbols = ' '.join(x['name'] for x in match['symbols'])
        selected = next((x for x in rules if x[0] in symbols), None)
        if match['member'].endswith('initcon.obj') and match['candidate_samples'] == ['CONOUT$']:
            selected = ('CONOUT$', 'Windows 콘솔 출력 장치명. CRT 자료절 전체 일치, CreateFileW의 경로 인수로 소비됨', 'conio/initcon.cpp', [19, 21, 22, 26])
        if match['member'].endswith('winapi_thunks.obj') and match['candidate_samples'][0] in ['RoInitialize', 'RoUninitialize']:
            selected = ('RoInitialize/RoUninitialize', '동적으로 조회하는 Windows 함수명. CRT 자료절 전체 일치, 함수명 매크로→GetProcAddress로 소비됨', 'internal/winapi_thunks.cpp', [113, 114, 324, 396, 398])
        if not selected:
            continue
        data = (inv.BASE / match['file']).read_bytes()
        assert inv.sha(data) == match['file_sha256']
        assert inv.sha(data[match['start']:match['end']]) == match['section_sha256']
        typed.append({**match, 'type': 'COFF_EXACT_TYPED_DATA', 'reason': selected[1],
                      'source_consumer': source_ref(selected[2], selected[3]),
                      'probe_path': str(probe_path.relative_to(inv.ROOT)), 'probe_sha256': inv.sha(probe_path.read_bytes())})
    for file in sorted({x['file'] for x in rows}):
        data = (inv.BASE / file).read_bytes()
        pe = pefile.PE(data=data)
        ranges = []
        for debug in getattr(pe, 'DIRECTORY_ENTRY_DEBUG', []):
            start = debug.struct.PointerToRawData
            end = start + debug.struct.SizeOfData
            raw = data[start:end]
            if debug.struct.Type == 2 and len(raw) >= 25 and raw[:4] == b'RSDS' and b'\0' in raw[24:]:
                ranges.append({'type': 'PE_CODEVIEW_RSDS', 'start': start, 'end': end,
                               'pdb_path': raw[24:].split(b'\0', 1)[0].decode('utf-8'),
                               'reason': 'PE Debug Directory가 지정한 CodeView RSDS 레코드: 서명·GUID·age·PDB 파일 경로. 게임 표시 문구가 아닌 디버그 기호 연결 정보'})
        if hasattr(pe, 'DIRECTORY_ENTRY_EXPORT'):
            export = pe.DIRECTORY_ENTRY_EXPORT.struct
            start = pe.get_offset_from_rva(export.AddressOfNameOrdinals)
            end = start + export.NumberOfNames * 2
            values = struct.unpack('<' + 'H' * export.NumberOfNames, data[start:end])
            assert all(x < export.NumberOfFunctions for x in values)
            ranges.append({'type': 'PE_EXPORT_NAME_ORDINAL_ARRAY', 'start': start, 'end': end,
                           'entries': len(values), 'element_size': 2,
                           'reason': 'PE 내보내기 디렉터리의 16비트 함수 순번 배열. 모든 순번이 함수 주소표 범위 안임을 확인; 문자열처럼 검색된 숫자 바이트'})
        for item in ranges:
            typed.append({**item, 'file': file, 'file_sha256': inv.sha(data),
                          'raw_sha256': inv.sha(data[item['start']:item['end']])})
    changes = []
    for row in rows:
        if row['classification'] != 'UNKNOWN':
            continue
        owner = next((item for item in typed if item['file'] == row['file'] and item['start'] <= row['file_offset']
                      and row['file_offset'] + row['bytes'] <= item['end']), None)
        if owner:
            row.update(classification='INTERNAL', reason=owner['reason'], additional_evidence=owner)
            changes.append({k: row[k] for k in ['file', 'file_sha256', 'file_offset', 'source', 'source_bytes_sha256', 'classification', 'reason', 'additional_evidence']})
    inv.save('native_inventory_v3.jsonl', rows)
    inv.save('typed_classification.json', {'input_sha256': inv.sha(original.read_bytes()), 'tool_sha256': inv.sha(Path(__file__).read_bytes()),
                                         'structures': typed, 'changes': changes})
    summary = {'records': len(rows), 'classifications': dict(collections.Counter(x['classification'] for x in rows)),
               'additional_internal': len(changes), 'full_native_classification': 'NOT_RUN',
               'output_sha256': inv.sha((inv.OUT / 'native_inventory_v3.jsonl').read_bytes()),
               'selected_translations_changed': False, 'native_candidate_02_content_affected': False}
    inv.save('summary_v3.json', summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
