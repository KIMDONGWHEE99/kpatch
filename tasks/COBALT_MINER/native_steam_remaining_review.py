"""현재 Ghidra 응답·짧은 실제 인수 전달·공식 API 키 규칙을 연결합니다."""
import collections
import json
import re
import struct
from pathlib import Path
import pefile
import native_inventory as inv
from native_api_boundary_review import Decoder


def main():
    source = inv.OUT / 'native_inventory_v18.jsonl'
    rows = [json.loads(x) for x in source.read_text(encoding='utf-8').split('\n') if x]
    evidence_path = inv.OUT / 'rea_steamworks_remaining.json'
    records = {r['parameters']['procedure']: r for r in inv.read(evidence_path)['records'] if r['operation'] == 'procedure_pseudo_code'}
    data = (inv.BASE / 'Modules/Steamworks.mfx').read_bytes()
    pe = pefile.PE(data=data)
    decoder = Decoder()
    assert all(r['provider']['id'] == 'ghidra' and r['subject']['digest']['sha256'] == inv.sha(data) for r in records.values())
    common = {'path': str(evidence_path.relative_to(inv.ROOT)), 'sha256': inv.sha(evidence_path.read_bytes())}
    assert '_wcscmp((wchar_t *)(piVar1 + 5),param_2)' in records['0x1001b113']['normalized_result']
    assert '(wchar_t *)((int)this + 0x14),param_1' in records['0x1000ea08']['normalized_result']
    changes = []
    rules = {}

    def rule(words, addresses, reason, classification='INTERNAL'):
        for word in words:
            rules[word] = {'addresses': addresses, 'reason': reason, 'classification': classification}

    rule(['temp', 'userdata'], ['0x1000c66d'], '경로 앞부분을 wcsicmp로 비교해 임시 폴더 또는 Steam 사용자 자료 폴더를 선택하는 키')
    rule(['EDIF'], ['0x10018052'], 'FindResourceW로 조회하는 확장 자료의 리소스 형식 이름')
    rule(['%s/%s', '%s/Data/Runtime/%s', '%s/../%s'], ['0x100181d6'], 'GetModuleFileNameW로 얻은 모듈 경로를 조립하고 GetFileAttributesW로 검사하는 파일 검색 서식')
    rule(['steamid', 'appid', 'language', 'product', 'quantity', 'orderid'],
         ['0x10004fc7', '0x100142ff', '0x10001b10', '0x10001a8b'],
         '구매 웹 요청의 이름/값 사전에 저장하는 프로토콜 속성 이름. 값 문자열과 구분되는 키')
    rule(['IAP_CHECKOUT_INIT_TXN', 'IAP_CHECKOUT_WAITING_FOR_MICRO_TRANSACTION_RESPONSE', 'IAP_CHECKOUT_FINISH_TXN'],
         ['0x10004fc7', '0x10013ba9', '0x1000ea08', '0x1001b113'],
         '구매 처리 상태의 ApiSession 이름. 객체+0x14에 저장되고 wcscmp 세션 검색의 식별자로 사용됨')
    rule(['UTF-8', 'UTF-16LEUNICODE', 'Eccs'], ['0x1004694c', '0x10046b5b'],
         'CRT 파일 열기 모드의 인코딩 선택 문법. 길이가 지정된 strnicmp/wcsnicmp 비교 후 코드페이지 플래그로 변환됨')
    rule(['desc', 'hidden'], ['0x1000e634', '0x1000e68e'],
         'SteamUserStats의 도전 과제 속성 조회 키. 반환되는 설명 값과 키 자체를 구분함')
    rule(['Steamworks'], ['0x10016c82'], 'MessageBoxW 제목으로 쓰이는 Steamworks SDK의 고유 이름', 'VISIBLE_KEEP')
    for row in rows:
        if row['classification'] != 'UNKNOWN' or row['file'] != 'Modules/Steamworks.mfx':
            continue
        at = row['file_offset']
        assert inv.sha(data[at:at + row['bytes']]) == row['source_bytes_sha256']
        if row['source'] in rules:
            selected = rules[row['source']]
            for address in selected['addresses']:
                assert address in records
            extra = {'consumers': [records[a]['evidence_id'] for a in selected['addresses']]}
            if row['source'] == 'desc':
                assert data[396340:396345] == b'desc\0'
                assert '&DAT_10061a34' in records['0x1000e634']['normalized_result']
            if row['source'] in ('desc', 'hidden'):
                extra['primary_documentation'] = 'https://partner.steamgames.com/doc/api/ISteamUserStats#GetAchievementDisplayAttribute'
            if row['source'] == 'Eccs':
                assert data[at:at + 10] == b'E\0c\0c\0s\0\0\0'
                assert {r['target_offset'] for r in row['static_references']} == {at + 2}
                assert data[at - 6:at + 2] == b'UNICODE\0'
                extra['overlap'] = '앞 E/NUL은 바로 앞 ASCII UNICODE 토큰의 끝. 실제 UTF-16 문법 키 ccs는 두 바이트 뒤에서 시작함'
            row.update(classification=selected['classification'], reason=selected['reason'], additional_evidence={**common, **extra})
            changes.append(row)
            continue
        if row['source'] in {'Friends', 'Community', 'Players', 'Settings', 'OfficialGameGroup', 'Achievements'}:
            consumers = []
            for reference in row['static_references']:
                assert reference['target_offset'] == at
                for pointer in reference['pointer_offsets']:
                    start = pointer - 7
                    assert data[start:start + 6].hex() == 'ff150c020610'
                    assert data[pointer - 1] == 0x68
                    assert data[pointer + 4:pointer + 11].hex() == '8bc88b10ff5270'
                    consumers.append({'file_offset': start, 'bytes': data[start:pointer + 11].hex(),
                                      'consumer': 'SteamFriends() 결과의 가상 함수 +0x70에 고정 선택자 인수를 전달'})
            row.update(classification='INTERNAL', reason='Steam 오버레이의 대상 대화창을 선택하는 API 식별자. 실제 버튼 문구와 구분됨', additional_evidence={
                **common, 'consumers': consumers,
                'primary_documentation': 'https://partner.steamgames.com/doc/api/isteamfriends#ActivateGameOverlay',
                'ghidra_limit': '이 등록형 leaf 코드의 독립 함수 인식이 실패해 현재 원본의 전체 짧은 인수 전달 명령과 공식 선택자 정의를 대조함. 해당 leaf를 Ghidra 의사코드로 분석했다고 주장하지 않음'})
            changes.append(row)
            continue
        if '%' not in row['source']:
            continue
        proofs = []
        for reference in row.get('static_references', []):
            for pointer in reference['pointer_offsets']:
                # LEA EAX,[EBP+disp32]; PUSH format; PUSH EAX; CALL formatter 형식만 허용합니다.
                start = pointer - 7
                if data[start:start + 2] != b'\x8d\x85' or data[pointer - 1] != 0x68:
                    break
                code = decoder.read(data, start, pe.OPTIONAL_HEADER.ImageBase + pe.get_rva_from_offset(start), {})
                destination = code[0]['instruction'].split(', ', 1)[1]
                registers, stack, formatted = {'eax': destination}, [], False
                consumed = False
                for instruction in code[1:]:
                    mnemonic, _, operands = instruction['instruction'].partition(' ')
                    if mnemonic == 'push':
                        stack.insert(0, registers.get(operands, operands))
                    elif mnemonic == 'lea':
                        reg, value = operands.split(', ', 1)
                        registers[reg] = value
                    elif mnemonic in ('mov', 'xor'):
                        reg, value = operands.split(', ', 1)
                        registers[reg] = registers.get(value, value) if mnemonic == 'mov' else ('0' if reg == value else None)
                    elif mnemonic == 'add' and operands.startswith('esp, '):
                        stack = []
                    elif mnemonic == 'call':
                        if operands == '0x10004403' and not formatted:
                            assert stack[0] == destination and stack[1] == hex(int(row['preferred_va'], 16))
                            formatted = True
                            registers['eax'] = None
                        elif formatted and operands in ('0x1001b032', '0x1000ec06') and len(stack) >= 2 and stack[1] == destination:
                            consumed = True
                            proofs.append({'pointer_offset': pointer, 'destination': destination, 'instructions': code[:code.index(instruction) + 1],
                                           'lookup_evidence_id': records['0x1001b113']['evidence_id']})
                            break
                        else:
                            break
                    elif mnemonic.startswith('j') or mnemonic in ('ret', 'int3'):
                        break
                if not consumed:
                    break
            else:
                continue
            break
        if proofs and len(proofs) == sum(len(r['pointer_offsets']) for r in row['static_references']):
            row.update(classification='INTERNAL', reason='서식 결과를 같은 스택 버퍼에서 ApiSession 검색의 이름 인수로 전달함. 공통 검색 함수가 wcscmp로 객체 이름과 비교하는 내부 작업 식별자',
                       additional_evidence={**common, 'consumers': proofs, 'lookup_evidence_id': records['0x1001b113']['evidence_id']})
            changes.append(row)
    # 독립 미디어 담당이 제출한 같은 어셈블러 함수의 의미 이름 11개를 원시 위치로 검증합니다.
    folder = inv.OUT / 'media_keyword_review_04'
    proposals, structures = inv.read(folder / 'classification_proposals.json'), inv.read(folder / 'structures.json')
    dep = structures['dependencies']
    epath = inv.ROOT / dep['rea_evidence']
    assert inv.sha(epath.read_bytes()) == dep['rea_evidence_sha256']
    erecords = {r['evidence_id']: r for r in inv.read(epath)['records']}
    shader_data = (inv.BASE / 'Modules/mmf2d3d9.dll').read_bytes()
    assert inv.sha(shader_data) == dep['source_sha256']
    shader_pe = pefile.PE(data=shader_data)
    positions = {(r['file'], r['file_offset'], r['encoding']): r for r in rows}
    for proof, proposal in zip(structures['proofs'], proposals['proposals']):
        assert proof['file_offset'] == proposal['file_offset']
        row = positions[proposal['file'], proposal['file_offset'], proposal['encoding']]
        assert row['classification'] == 'UNKNOWN'
        at = row['file_offset']
        assert inv.sha(shader_data[at:at + row['bytes']]) == row['source_bytes_sha256'] == proof['source_bytes_sha256']
        record = erecords[proof['rea_evidence_id']]
        assert record['provider']['id'] == 'ghidra' and record['subject']['digest']['sha256'] == inv.sha(shader_data)
        assert proof['pseudocode_excerpt'] in record['normalized_result']
        for ref in proof['references']:
            # 제안의 file_offset은 4바이트 즉시값 위치이며 opcode는 한 바이트 앞입니다.
            code_at = ref['file_offset'] - 1
            raw = bytes.fromhex(ref['bytes'])
            assert shader_data[code_at:code_at + len(raw)] == raw
            assert struct.unpack_from('<I', raw, 1)[0] == shader_pe.OPTIONAL_HEADER.ImageBase + shader_pe.get_rva_from_offset(at)
        row.update(classification='INTERNAL', reason=proposal['reason'], additional_evidence={
            'proposal_path': str((folder / 'classification_proposals.json').relative_to(inv.ROOT)),
            'proposal_sha256': inv.sha((folder / 'classification_proposals.json').read_bytes()),
            'proof': proof, 'independent_check': '원시 명령 피연산자·문자열 지문·실제 Ghidra 비교 코드 조각을 별도 대조'})
        changes.append(row)
    inv.save('native_inventory_v19.jsonl', rows)
    inv.save('remaining_steam_classification_v19.json', {'input_sha256': inv.sha(source.read_bytes()), 'tool_sha256': inv.sha(Path(__file__).read_bytes()), 'changes': changes})
    summary = {'records': len(rows), 'classifications': dict(collections.Counter(x['classification'] for x in rows)),
               'additional_classified': len(changes), 'full_native_classification': 'NOT_RUN',
               'output_sha256': inv.sha((inv.OUT / 'native_inventory_v19.jsonl').read_bytes()), 'native_candidate_04_content_affected': False}
    inv.save('summary_v19.json', summary)
    print(json.dumps(summary))
    print(json.dumps([(r['file'], r['source']) for r in changes], ensure_ascii=False))


if __name__ == '__main__':
    main()
