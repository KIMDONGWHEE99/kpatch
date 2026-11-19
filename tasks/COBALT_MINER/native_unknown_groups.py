"""미분류를 표시 경계 질문 10개로 집계합니다. 이 집계는 분류 판정이 아닙니다."""
import collections
import json
import re
from pathlib import Path
import native_inventory as inv


def main():
    input_path = inv.OUT / 'native_inventory_v3.jsonl'
    rows = [json.loads(x) for x in input_path.read_text(encoding='utf-8').split('\n') if x]
    old = inv.ROOT / 'working_private/THE_HORDE_OF_GORAK'
    calls_path = old / 'investigation_20261031/d3d9_diagnostic_call_groups.json'
    calls = json.loads(calls_path.read_text(encoding='utf-8'))
    diagnostics = {x['offset'] for x in calls if x['call']['instruction'] in [
        'call 0x1007a48f', 'call 0x1000e130', 'call 0x1001a547', 'call 0x1004faa3', 'call 0x1001a5ea', 'call 0x1007a514']}
    json_path = old / 'native_steam_closure_01/json_display_patch.json'
    json_offsets = {x['file_offset'] for x in json.loads(json_path.read_text(encoding='utf-8'))}
    groups = {
        'd3d9_diagnostic_buffer': ('D3D9 진단 버퍼로 모이는 문구', 'cSurface 함수표 +0x188 검증 호출의 오류 버퍼를 현재 EXE/mmfs2가 소비해 표시하는가?', ['0x1007a48f', '0x1000e130', '0x100b8a50', 'vtable 0x100dd61c+0x188']),
        'd3d9_compiler_data': ('D3D9 나머지 컴파일러 문법·식별자 후보', '각 문자열 포인터 표가 파서/바이트코드 생성에만 소비되고 화면 출력 경계로 반환되지 않는가?', ['d3d9_diagnostic_call_groups.json의 나머지 소비 함수/주소표']),
        'd3d8_compiler_data': ('D3D8 컴파일러 문법·진단 후보', 'D3D8 효과 검증의 오류 버퍼를 현재 호스트가 실제 표시 인수로 요청하는가?', ['d3d8_compile_diagnostic_disasm.json']),
        'numeric_or_table_candidates': ('문자열로 오인했을 가능성이 있는 숫자·배열 후보', '후보 바이트를 포함한 전체 상수/포인터/재배치/파서 상태표를 형식과 소비 명령으로 확정할 수 있는가?', ['후보별 PE 절·바이트 범위·포인터 참조 위치']),
        'common_runtime': ('공통 CRT/C++ 오류·형식 처리 상수', '공통 예외 what/형식 처리값이 종료·디버그·로그로 끝나는가, 사용자 표시 창으로 전달되는가?', ['native_cpp_diagnostic_evidence.json', 'native_steam_closure_01/*printf_table_consumer.json']),
        'steam_extension_protocol': ('Steam 확장 상태·언어·오버레이·EDIF 키', 'JSON키/프로토콜 비교와 표현식 반환을 분리하고, 반환 문구를 현재 DAT가 소비하는가?', ['Steamworks.mfx 내부 소비 함수', 'Cobalt DAT: type36 action102 16회, condition/expression 0회']),
        'steam_json_errors': ('Steam 확장 JSON 파싱 오류 표시', 'MessageBoxA 경계에 UTF-8→UTF-16 변환을 넣어 22개 진단을 원문 서식·128바이트 버퍼 제한 내에서 표시할 수 있는가?', ['0x10019a9d', '0x1001ac6b', '0x100184ad MessageBoxA']),
        'steam_api_protocol': ('Steam API 라이브러리 식별자·진단', '공통 인터페이스 조회/레지스트리/파일명/로그 경계를 연결해 사용자 표시 진단만 분리할 수 있는가?', ['native_steam_closure_01/steam_api.dll_3b404f00.json', 'steam_api.dll_3b406560.json']),
        'd3d11_library': ('D3D11 그래픽 라이브러리 예외·인수명', 'DirectXTK/동시성 런타임 예외가 잡혀 화면에 표시되는 경계가 있는가?', ['DirectXTK SpriteBatch/PrimitiveBatch 오류 생성 함수']),
        'engine_extension_boundary': ('게임 호스트·확장 모듈의 경로·키·표시 후보', 'GetProcAddress/저장경로/클래스명/개발목록의 실제 소비를 모듈별 공통 경계로 닫을 수 있는가?', ['EXE 확장 함수 조회', 'mmfs2 파일필터/창 클래스', 'kcini 저장경로', 'Layer 목록 출력']),
    }
    items = collections.defaultdict(list)
    common = re.compile(r'(?:vector<|map/set<|list<|invalid .*subscript|bad (?:function|allocation|exception)|regex_error|ios_base|1#(?:INF|QNAN|SNAN|IND)|\(null\)|api-ms-win-|ext-ms-win-|minkernel|__crt_strtox|^!?_is_double$|unknown error|Unknown error|Lock already taken)')
    for row in rows:
        if row['classification'] != 'UNKNOWN':
            continue
        file, offset, source = row['file'], row['file_offset'], row['source']
        if file == 'Modules/Steamworks.mfx' and offset in json_offsets:
            key = 'steam_json_errors'
        elif file == 'Modules/mmf2d3d9.dll' and offset in diagnostics:
            key = 'd3d9_diagnostic_buffer'
        elif common.search(source):
            key = 'common_runtime'
        elif row.get('candidate_type') == 'UNTERMINATED_BYTE_RUN' or (not re.search(r'[a-zA-Z]{4}', source) and len(source) < 32):
            key = 'numeric_or_table_candidates'
        elif file == 'Modules/mmf2d3d9.dll':
            key = 'd3d9_compiler_data'
        elif file == 'Modules/mmf2d3d8.dll':
            key = 'd3d8_compiler_data'
        elif file == 'Modules/Steamworks.mfx':
            key = 'steam_extension_protocol'
        elif file == 'Modules/steam_api.dll':
            key = 'steam_api_protocol'
        elif file == 'Modules/mmf2d3d11.dll':
            key = 'd3d11_library'
        else:
            key = 'engine_extension_boundary'
        items[key].append(row)
    output = []
    for key, group in groups.items():
        selected = items[key]
        samples = []
        for row in sorted(selected, key=lambda x: (x['file'], -len(x['source']))):
            if row['source'] not in [x['source'] for x in samples]:
                samples.append({k: row[k] for k in ['file', 'file_offset', 'source', 'source_bytes_sha256']})
            if len(samples) == 3:
                break
        output.append({'id': key, 'label': group[0], 'count': len(selected), 'single_question': group[1], 'boundaries': group[2],
                       'examples': samples, 'files': dict(collections.Counter(x['file'] for x in selected)),
                       'rows': [{k: x[k] for k in ['file', 'file_sha256', 'file_offset', 'bytes', 'source_bytes_sha256', 'source']} for x in selected]})
    result = {'input_sha256': inv.sha(input_path.read_bytes()), 'status': 'UNKNOWN', 'purpose': '후속 조사 단위 집계. 의미에 따른 자동 제외나 표시 판정을 하지 않음',
              'total': sum(x['count'] for x in output), 'groups': output,
              'source_evidence': [{'path': str(p.relative_to(inv.ROOT)), 'sha256': inv.sha(p.read_bytes())} for p in [calls_path, json_path]]}
    assert result['total'] == sum(x['classification'] == 'UNKNOWN' for x in rows)
    inv.save('unknown_groups.json', result)
    print(json.dumps([{k: x[k] for k in ['id', 'count', 'single_question', 'examples']} for x in output], ensure_ascii=False))


if __name__ == '__main__':
    main()
