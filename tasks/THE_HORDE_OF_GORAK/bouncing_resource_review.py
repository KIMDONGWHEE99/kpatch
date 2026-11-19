"""물리 이동 모듈 리소스72개의 소비 근거와 별도 분류 제안을 기록한다."""
import json
import struct
from pathlib import Path

import pefile
from dat_container import sha
from native_inspect import disassemble

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'source_original/THE_HORDE_OF_GORAK/steam_26336311'
OUT = ROOT / 'working_private/THE_HORDE_OF_GORAK/investigation_20261031'
EXPECTED_SHA = 'd73d3b21b3f14d833cc7f0cf6fd152cde4de66ca4eb7c5da6a6b618ac84e06ef'
CALLS = {0x108C: 274, 0x10C8: 275, 0x18DE: 217, 0x18F8: 102,
         0x2011: 239, 0x2040: 240, 0x208A: 243, 0x20D2: 245,
         0x211C: 246, 0x2163: 247, 0x21AA: 248,
         0x2A01: 274, 0x2A38: 275, 0x38D7: 102}
DEBUG_TRANSLATIONS = {239: '유형: 반사공', 240: '속도: %i', 243: '각도: %i도',
                      245: '중력: %i%%', 246: '마찰: %i', 247: '탄성: %i', 248: '밀도: %i'}


def main():
    path = BASE / 'Box2DBouncingBall.mvx'
    data = path.read_bytes()
    assert sha(data) == EXPECTED_SHA
    image = pefile.PE(data=data)
    iat = next(item.address for module in image.DIRECTORY_ENTRY_IMPORT for item in module.imports
               if item.name == b'LoadStringW')
    references = []
    for section in image.sections:
        if not section.Characteristics & 0x20000000:
            continue
        raw = section.get_data()
        cursor = 0
        while True:
            cursor = raw.find(struct.pack('<I', iat), cursor)
            if cursor < 0:
                break
            assert raw[cursor-2:cursor] == b'\xff\x15'
            call = section.VirtualAddress + cursor - 2
            assert call in CALLS
            references.append({'call_rva': hex(call), 'resource_id': CALLS[call],
                               'call_bytes': raw[cursor-2:cursor+4].hex()})
            cursor += 4
    assert {int(row['call_rva'], 16) for row in references} == set(CALLS)
    import_names = {item.name.decode() for module in image.DIRECTORY_ENTRY_IMPORT for item in module.imports if item.name}
    assert not import_names.intersection({'FindResourceW', 'FindResourceA', 'LoadResource', 'LockResource'})
    assert struct.unpack('<I', image.get_data(0x15330, 4))[0] == 0x10001FD0
    assert struct.unpack('<I', image.get_data(0x1532C, 4))[0] == 0x10002220
    assert image.get_data(0x1D000, 32).hex() == '008064000080650000806600008067000080680000806a0000806900ffff0000'
    regions = {'constructor': (0x10001000, 0x13D), 'load_settings': (0x100028D0, 0x1D7),
               'copy_to_runtime': (0x100024C1, 0x113), 'joint_call': (0x10001D80, 0x99),
               'debug_item': (0x10001FD0, 0x24D), 'debug_tree': (0x10002220, 6),
               'create_runtime': (0x10001E20, 0x28)}
    code = {name: disassemble(path, address, size) for name, (address, size) in regions.items()}
    host_path = BASE / 'THOG.exe'
    host_code = {'create_runtime': disassemble(host_path, 0x447430, 0xDD),
                 'load_factory': disassemble(host_path, 0x44C7D7, 0x1D)}
    # 모든 분류를 입력 리소스의 위치·내용·해시로 고정한다. 공용 목록은 이 스크립트가 수정하지 않는다.
    inventory = [json.loads(line) for line in (OUT / 'native_string_inventory.jsonl').read_text(encoding='utf-8').splitlines()]
    rows = [row for row in inventory if row['file'] == 'Box2DBouncingBall.mvx'
            and row['kind'] == 'RT_STRING' and 200 <= row['string_id'] <= 289 and row['string_id'] != 217]
    assert len(rows) == 72
    decisions = []
    for row in rows:
        identifier = row['string_id']
        original = data[row['file_offset']:row['file_offset']+row['bytes']]
        assert sha(original) == row['source_bytes_sha256']
        decision = {key: row[key] for key in ('file', 'file_sha256', 'file_offset', 'bytes', 'source',
                                            'source_bytes_sha256', 'string_id', 'resource_language', 'resource_sha256')}
        decision['evidence'] = 'bouncing_resource_review_evidence.json'
        if identifier in DEBUG_TRANSLATIONS:
            translation = DEBUG_TRANSLATIONS[identifier]
            assert len(translation.encode('utf-16le')) <= row['bytes']
            decision.update(classification='VISIBLE_TRANSLATE', translation_proposal=translation,
                            reason='런타임 객체의 디버그 표시 가상함수+0x70에서 LoadStringW→호출자 출력버퍼로 포맷. 실제 게임 호출 불가를 충분히 입증하지 못했으므로 표시문구로 보수적으로 번역 대상에 포함.',
                            consumer='vtable 0x100152c0 +0x70 -> 0x10001fd0; IDs100..106 dispatch',
                            runtime_reachability='UNKNOWN', action='원본 슬롯·%i·%% 보존 번역 권고; 아직 후보에 적용하지 않음')
        elif identifier in (274, 275):
            decision.update(classification='INTERNAL',
                            reason='생성/구버전 설정 읽기에서 이동 설정+0x30/+0x60 기본 식별자로 저장. 런타임+0x6c/+0x9c로 복사한 뒤 물리엔진의 접합 생성 함수+0x170에 이름 인수로 전달하며 표시 API로 보내지 않음.',
                            consumer='0x1000108c/10c8; 0x10002a01/2a38; 0x100025a0/25c0; 0x10001dea..1e0d')
        else:
            assert identifier not in CALLS.values()
            decision.update(classification='INTERNAL',
                            reason='물리 이동 편집용 속성명·도움말·선택지. 원본 모듈의 LoadStringW IAT 모든 참조14개가 고정 ID102/217/239/240/243/245/246/247/248/274/275만 읽고 이 ID는 포함하지 않음. 별도 FindResource/LoadResource/LockResource 수입이 없고, 게임은 이동 factory만 불러오며 속성 편집 진입점은 요청하지 않음.',
                            consumer='전체 LoadStringW 호출14개 범위 검사 및 THOG CreateMvt 로더 0x44c7d7..44c7f2',
                            confidence='원본 빌드에 한정한 정적 미사용 판정; 다른 편집기/엔진 빌드에는 적용하지 않음')
        decisions.append(decision)
    evidence_files = ['bouncing_resource_rea_evidence.json', 'runtime_extension_import_tables.json',
                      'native_resource_classifier_disasm.json', 'native_editor_resource_consumers.json',
                      'bouncing_host_movement_disasm.json', 'bouncing_host_debug_candidates.json']
    report = {'status': 'PASS', 'file': path.name, 'file_sha256': sha(data),
              'resource_rows': 72, 'internal': 65, 'visible_translate': 7,
              'loadstring_iat': hex(iat), 'all_executable_iat_references': references,
              'no_generic_resource_imports': True, 'function_regions': code,
              'host_file_sha256': sha(host_path.read_bytes()), 'host_function_regions': host_code,
              'debug_vtable': {'address': '0x100152c0', 'tree_slot': '0x6c', 'item_slot': '0x70',
                               'item_function': '0x10001fd0', 'ids': list(DEBUG_TRANSLATIONS)},
              'evidence_hashes': {name: sha((OUT / name).read_bytes()) for name in evidence_files},
              'tool_sha256': sha(Path(__file__).read_bytes()),
              'limitations': ['REA 깊은 분석 엔진 미설정; GNU objdump 실행 불가. REA PE export Evidence와 원본에 대한 Capstone 국소 판독을 결합.',
                             '디버그 가상함수의 실제 게임 호출 불가능성은 입증하지 못함. 이7개를 INTERNAL로 제외하지 않음.',
                             '설치본·후보·공용 인벤토리·라이브 프로세스를 수정하지 않음']}
    for name, value in [('bouncing_resource_review_evidence.json', report), ('bouncing_resource_classification_patch.json', decisions)]:
        (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': 'PASS', 'rows': len(decisions), 'internal': 65, 'visible_translate': 7}))


if __name__ == '__main__':
    main()
