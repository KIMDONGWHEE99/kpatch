"""정적으로 표시 경로가 확인된 네이티브 167필드의 번역 후보를 만듭니다.

미분류 해소나 실제 화면 검수를 대신하지 않습니다. 기존 설치본은 읽지도 쓰지도
않으며 보존된 기준선에서만 작업합니다.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import re
import struct
import sys
from pathlib import Path
import pefile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tasks/THE_HORDE_OF_GORAK'))
from build_native_candidate import read_string_block, write_string_block, rebuild_dialog
from native_string_inventory import dialog_fields
from dat_container import utf16z

BASE = ROOT / 'source_original/COBALT_MINER/steam_24347666'
WORK = ROOT / 'working_private/COBALT_MINER/investigation_20261101/native'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate-id', default='native_candidate_01')
    args = parser.parse_args()
    if not re.fullmatch(r'native_candidate_[a-zA-Z0-9_]+', args.candidate_id):
        raise ValueError('새 비공개 후보 ID가 필요합니다.')
    out = ROOT / 'working_private/COBALT_MINER' / args.candidate_id
    if out.exists():
        raise ValueError('기존 후보를 덮어쓰지 않습니다.')
    worklist_path = WORK / 'native_visible_worklist.json'
    resources_path = WORK / 'native_pe_resources.json'
    worklist, resources = read(worklist_path), read(resources_path)
    if read(WORK / 'extraction_errors.json'):
        raise ValueError('위치 대응 오류가 남아 있습니다.')
    groups = collections.defaultdict(list)
    for row in worklist:
        source, target = row['source'], row['translation']
        if not target or '\0' in target or source == target:
            raise ValueError('번역값 누락·NUL·원문 잔존')
        tokens = r'%(?:\d+\$)?[-+ #0]*(?:\d+|\*)?(?:\.(?:\d+|\*))?(?:hh|h|ll|l|j|z|t|L)?[diuoxXfFeEgGaAcspn]|%%'
        if re.findall(tokens, source) != re.findall(tokens, target):
            raise ValueError('서식 지정자 형식·순서 불일치: ' + source)
        if re.findall(r'\r\n|\r|\n', source) != re.findall(r'\r\n|\r|\n', target):
            raise ValueError('제어 줄바꿈 불일치: ' + source)
        if '|' in source and source.split('|')[1:] != target.split('|')[1:]:
            raise ValueError('파일 필터 규칙 변경: ' + source)
        groups[row['file']].append({**row, 'target': target})
    generated, file_reports, translations = {}, [], []
    for name, rows in groups.items():
        original = (BASE / name).read_bytes()
        if any(sha(original) != row['file_sha256'] for row in rows):
            raise ValueError('지원하지 않는 원본 모듈: ' + name)
        candidate, image = bytearray(original), pefile.PE(data=original)
        allowed, checks = [], []
        by_resource = collections.defaultdict(list)
        for row in rows:
            offset, size = row['file_offset'], row['bytes']
            if sha(original[offset:offset + size]) != row['source_bytes_sha256']:
                raise ValueError('원문 위치 지문 불일치')
            if row['kind'] == 'section_string':
                assert row['encoding'] == 'utf-16le' and row['null_terminated']
                assert original[offset:offset + size].decode('utf-16le') == row['source']
                assert original[offset + size:offset + size + 2] == b'\0\0'
                encoded = row['target'].encode('utf-16le')
                if len(encoded) > size:
                    raise ValueError('고정 문자열 슬롯 초과')
                candidate[offset:offset + size + 2] = encoded.ljust(size + 2, b'\0')
                allowed.append((offset, offset + size + 2))
                checks.append({'kind': 'literal', 'offset': offset, 'bytes': size + 2, 'expected': row['target']})
            else:
                key = tuple(row['resource_' + x]['id'] for x in ('type', 'name', 'language'))
                by_resource[key].append(row)
        for key, selected in by_resource.items():
            resource = next(r for r in resources[name]['normalized_result']['resources']
                            if tuple(r[x].get('id') for x in ('type', 'name', 'language')) == key)
            start, size = resource['payload']['location']['offset'], resource['payload']['location']['bytes']
            raw = original[start:start + size]
            assert sha(raw) == resource['payload']['sha256']
            if key[0] == 6:
                expected = read_string_block(raw)
                assert write_string_block(expected) == raw
                for row in selected:
                    slot = row['string_id'] % 16
                    assert expected[slot] == row['source']
                    expected[slot] = row['target']
                replacement = write_string_block(expected)
                checks.append({'kind': 'string_block', 'offset': start, 'bytes': len(replacement), 'expected': expected})
            else:
                assert key[0] == 5 and rebuild_dialog(raw, {}) == raw
                mapping = {row['file_offset'] - start: row['target'] for row in selected}
                replacement = rebuild_dialog(raw, mapping)
                before, after = dialog_fields(raw), dialog_fields(replacement)
                expected = [{'role': item['role'], 'source': mapping.get(item['offset'], item['source'])} for item in before]
                assert [{'role': item['role'], 'source': item['source']} for item in after] == expected
                reverse = {new['offset']: old['source'] for old, new in zip(before, after) if old['source'] != new['source']}
                assert rebuild_dialog(replacement, reverse) == raw
                checks.append({'kind': 'dialog', 'offset': start, 'bytes': len(replacement), 'expected': expected})
            if len(replacement) > size:
                raise ValueError('고정 리소스 슬롯 초과: ' + str(key))
            candidate[start:start + size] = replacement.ljust(size, b'\0')
            size_offset = resource['data_entry_location']['offset'] + 4
            struct.pack_into('<I', candidate, size_offset, len(replacement))
            allowed.extend([(start, start + size), (size_offset, size_offset + 4)])
        if image.OPTIONAL_HEADER.CheckSum:
            offset = image.OPTIONAL_HEADER.get_field_absolute_offset('CheckSum')
            struct.pack_into('<I', candidate, offset, 0)
            struct.pack_into('<I', candidate, offset, pefile.PE(data=bytes(candidate)).generate_checksum())
            allowed.append((offset, offset + 4))
            assert pefile.PE(data=bytes(candidate)).verify_checksum()
        assert len(candidate) == len(original)
        changed = [i for i, (a, b) in enumerate(zip(original, candidate)) if a != b]
        assert all(any(start <= index < end for start, end in allowed) for index in changed)
        reopened = pefile.PE(data=bytes(candidate))
        layout = lambda obj: [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData, s.Characteristics) for s in obj.sections]
        assert layout(reopened) == layout(image)
        for check in checks:
            raw = bytes(candidate[check['offset']:check['offset'] + check['bytes']])
            if check['kind'] == 'literal':
                value, end = utf16z(raw)
                assert value == check['expected'] and not any(raw[end:])
            elif check['kind'] == 'string_block':
                assert read_string_block(raw) == check['expected']
            else:
                assert [{'role': x['role'], 'source': x['source']} for x in dialog_fields(raw)] == check['expected']
        generated[name] = bytes(candidate)
        file_reports.append({'file': name, 'source_sha256': sha(original), 'candidate_sha256': sha(candidate),
                             'fields': len(rows), 'allowed_ranges': allowed, 'changed_bytes': len(changed),
                             'source_has_certificate': bool(image.OPTIONAL_HEADER.DATA_DIRECTORY[4].Size),
                             'boundary_validation': 'PASS', 'pe_reopen': 'PASS', 'checks': checks})
        translations.extend(rows)
    inputs = [Path(__file__), ROOT / 'tasks/THE_HORDE_OF_GORAK/build_native_candidate.py',
              ROOT / 'tasks/THE_HORDE_OF_GORAK/native_string_inventory.py', ROOT / 'tasks/THE_HORDE_OF_GORAK/dat_container.py',
              worklist_path, resources_path, WORK / 'summary.json']
    out.mkdir(parents=True)
    for name, raw in generated.items():
        dest = out / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
    report = {'game_id': 'COBALT_MINER', 'source_build': 'steam_24347666', 'candidate_id': args.candidate_id,
              'selected_fields_static_validation': 'PASS', 'runtime_qa': 'NOT_RUN', 'full_native_classification': 'NOT_RUN',
              'files': file_reports, 'translations': translations,
              'inputs': [{'path': str(p.relative_to(ROOT)).replace('\\', '/'), 'sha256': sha(p.read_bytes())} for p in inputs],
              'limits': ['표시 경로가 확인된 167필드의 정적 후보이며 미분류 2660건은 남아 있음',
                         '소스 파일의 발행자 서명은 변경된 내용에 유효하지 않음. 인증서·보호 코드는 변경하지 않음',
                         '게임에서 해당 오류/정보/개발 창 접근 가능성과 실제 한글 배치는 미검수']}
    (out / 'native_patch_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'candidate': args.candidate_id, 'files': len(generated), 'fields': len(translations), 'runtime_qa': 'NOT_RUN'}))

if __name__ == '__main__':
    main()
