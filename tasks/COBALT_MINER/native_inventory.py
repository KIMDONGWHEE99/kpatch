"""동일 모듈·영역의 기존 근거를 지문으로 검증하고 새 PE 위치에 연결합니다.

예전 PASS를 복사하지 않습니다. 기존 UNKNOWN은 그대로 유지하며 게임 접근성은
정적 소비 사실과 구분합니다. 원본·재사용 근거 파일은 읽기만 합니다.
"""
from __future__ import annotations

import collections
import copy
import hashlib
import io
import json
import re
import struct
import sys
from pathlib import Path

import pefile
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tasks/THE_HORDE_OF_GORAK'))
from native_string_inventory import dialog_fields

BASE = ROOT / 'source_original/COBALT_MINER/steam_24347666'
OLD = ROOT / 'working_private/THE_HORDE_OF_GORAK/investigation_20261031'
OUT = ROOT / 'working_private/COBALT_MINER/investigation_20261101/native'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def save(name, data):
    p = OUT / name
    if name.endswith('.jsonl'):
        p.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in data), encoding='utf-8')
    else:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def identity(entry):
    return {'kind': 'name', 'name': str(entry.name)} if entry.name is not None else {'kind': 'id', 'id': entry.id}

def resource_key(row):
    return tuple(json.dumps(row[k], sort_keys=True) for k in ('type', 'name', 'language'))

def resources(image, data):
    result = []
    for typ in getattr(getattr(image, 'DIRECTORY_ENTRY_RESOURCE', None), 'entries', []):
        for name in typ.directory.entries:
            for lang in name.directory.entries:
                descriptor = lang.data.struct
                offset = image.get_offset_from_rva(descriptor.OffsetToData)
                raw = data[offset:offset + descriptor.Size]
                if len(raw) != descriptor.Size:
                    raise ValueError('PE 리소스 경계 밖')
                result.append({'index': len(result), 'type': identity(typ), 'name': identity(name),
                               'language': identity(lang), 'code_page': descriptor.CodePage,
                               'data_entry_location': {'offset': descriptor.get_file_offset(), 'bytes': 16},
                               'payload': {'rva': descriptor.OffsetToData,
                                           'location': {'offset': offset, 'bytes': len(raw)}, 'sha256': sha(raw)}})
    return result

def fields(resource, data):
    start = resource['payload']['location']['offset']
    size = resource['payload']['location']['bytes']
    raw = data[start:start + size]
    kind = resource['type'].get('id')
    result = []
    if kind == 6:
        cursor = 0
        for index in range(16):
            length = struct.unpack_from('<H', raw, cursor)[0]
            cursor += 2
            if length:
                result.append({'kind': 'RT_STRING', 'string_id': (resource['name']['id'] - 1) * 16 + index,
                               'source': raw[cursor:cursor + 2 * length].decode('utf-16le'),
                               'offset': start + cursor, 'bytes': length * 2})
            cursor += length * 2
        if cursor != len(raw):
            raise ValueError('문자열 리소스 끝 불일치')
    elif kind == 5:
        for item in dialog_fields(raw):
            result.append({'kind': 'RT_DIALOG', 'role': item['role'], 'source': item['source'],
                           'offset': start + item['offset'], 'bytes': item['size']})
    return result

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    old_manifest = read(OLD / 'baseline_manifest.json')
    baseline_path = OUT.parent / 'baseline_manifest.json'
    baseline = read(baseline_path)
    old_coverage = read(OLD / 'native_candidate_coverage.json')
    old_files = {x['file']: x for x in old_coverage['files']}
    old_resources = read(OLD / 'native_pe_resources_evidence.json')
    old_rows_path = OLD / 'native_string_inventory.jsonl'
    old_rows = [json.loads(x) for x in old_rows_path.read_text(encoding='utf-8').split('\n') if x]
    sources, mapping, files, resource_records, structured = {}, {}, [], [], {}
    errors = []
    for item in baseline['files']:
        if item['path'].endswith('.dat'):
            continue
        name = Path(item['path']).name
        old_name = 'THOG.exe' if name == 'COBALT MINER.exe' else name
        raw = (BASE / item['path']).read_bytes()
        if sha(raw) != item['sha256']:
            raise ValueError('기준선 지문 변경: ' + item['path'])
        image = pefile.PE(data=raw)
        original = old_files[old_name]
        matching = [x for x in old_manifest['files'] if x['sha256'] == item['sha256']]
        sections = []
        for section in image.sections:
            label = section.Name.rstrip(b'\0').decode('ascii')
            old_section = next((x for x in original['sections'] if x['name'] == label), None)
            match = bool(old_section and old_section['sha256'] == sha(section.get_data())
                         and old_section['rva'] == section.VirtualAddress
                         and int(old_section['characteristics'], 16) == section.Characteristics)
            sections.append({'name': label, 'rva': section.VirtualAddress, 'offset': section.PointerToRawData,
                             'bytes': len(section.get_data()), 'sha256': sha(section.get_data()),
                             'same_historical_section': match,
                             'historical_offset': old_section['raw_offset'] if old_section else None})
        parsed = resources(image, raw)
        extracted = []
        for resource in parsed:
            try:
                extracted.extend(fields(resource, raw))
            except Exception as exc:
                errors.append({'file': item['path'], 'resource': resource_key(resource), 'status': 'UNKNOWN', 'error': str(exc)})
            resource_records.append({'file': item['path'], 'file_sha256': item['sha256'], **resource})
        sources[old_name] = {'path': item['path'], 'data': raw, 'image': image, 'sha256': item['sha256'],
                             'resources': parsed, 'fields': extracted, 'sections': sections,
                             'same_whole_file': bool(matching)}
        mapping[old_name] = item['path']
        files.append({'file': item['path'], 'sha256': item['sha256'], 'historical_file': old_name,
                      'same_whole_file': bool(matching), 'historical_sha256': original['sha256'],
                      'sections': sections, 'resource_count': len(parsed), 'parsed_display_fields': len(extracted)})
        structured[item['path']] = {'normalized_result': {'artifact': {'sha256': item['sha256'], 'bytes': len(raw)},
                                                         'resources': parsed},
                                    'provenance': '현재 원본을 pefile로 직접 구조 해석. REA 응답을 가장하지 않음'}
    rows, consumed = [], set()
    for old_row in old_rows:
        old_name = old_row['file']
        if old_name not in sources:
            continue
        source = sources[old_name]
        row = copy.deepcopy(old_row)
        offset, size = row['file_offset'], row['bytes']
        proof = 'whole-file-sha256' if source['same_whole_file'] else None
        if not proof and 'resource_type' in row:
            key = tuple(json.dumps(row['resource_' + part], sort_keys=True) for part in ('type', 'name', 'language'))
            resource = next((x for x in source['resources'] if resource_key(x) == key), None)
            old_resource = next((x for x in old_resources[old_name]['normalized_result']['resources'] if resource_key(x) == key), None)
            if resource and old_resource and resource['payload']['sha256'] == old_resource['payload']['sha256']:
                offset += resource['payload']['location']['offset'] - old_resource['payload']['location']['offset']
                proof = 'resource-payload-sha256-and-identical-code-sections'
            else:
                candidates = [x for x in source['fields'] if x['kind'] == row['kind'] and
                              (x.get('string_id') == row.get('string_id') if row['kind'] == 'RT_STRING' else x.get('role') == row.get('role'))]
                if len(candidates) == 1 and candidates[0]['source'] == row['source']:
                    offset, size = candidates[0]['offset'], candidates[0]['bytes']
                    proof = 'resource-id-text-and-identical-code-sections'
                elif (len(candidates) == 1 and row['kind'] == 'RT_STRING' and row['string_id'] == 192
                      and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', candidates[0]['source'])):
                    # 게임별로 달라지는 런타임 GUID. 실제 현행 값을 기록하고 이전 값과 같다고 하지 않습니다.
                    offset, size = candidates[0]['offset'], candidates[0]['bytes']
                    row.update(source=candidates[0]['source'], source_bytes_sha256=sha(source['data'][offset:offset + size]),
                               classification='INTERNAL', reason='RT_STRING192 게임별 런타임 GUID. 같은 실행 코드·리소스 ID의 식별 값이며 자연어 표시 문구가 아님')
                    proof = 'current-resource-id192-guid-structure-and-identical-code'
            if resource:
                row['resource_sha256'] = resource['payload']['sha256']
        elif not proof:
            section = next((x for x in source['sections'] if x['same_historical_section'] and
                            x['historical_offset'] <= offset < x['historical_offset'] + x['bytes']), None)
            if section:
                offset += section['offset'] - section['historical_offset']
                proof = 'section-sha256-rva-characteristics'
        if not proof or sha(source['data'][offset:offset + size]) != row['source_bytes_sha256']:
            errors.append({'file': source['path'], 'old_offset': old_row['file_offset'], 'status': 'UNKNOWN',
                           'error': '기존 근거와 현행 바이트 대응 실패', 'source': old_row['source']})
            row.update(classification='UNKNOWN', reason='기존 근거와 현행 바이트 대응 실패')
        row.update(file=source['path'], file_sha256=source['sha256'], file_offset=offset, bytes=size,
                   rva=hex(source['image'].get_rva_from_offset(offset)),
                   preferred_va=hex(source['image'].OPTIONAL_HEADER.ImageBase + source['image'].get_rva_from_offset(offset)))
        row['reuse'] = {'historical_inventory': str(old_rows_path.relative_to(ROOT)).replace('\\', '/'),
                        'historical_file': old_name, 'historical_file_sha256': old_row['file_sha256'],
                        'historical_file_offset': old_row['file_offset'], 'proof': proof,
                        'limit': '정적 필드/소비 근거만 재사용. Cobalt의 실제 창 접근·출력 확인은 별도'}
        rows.append(row)
        if row['kind'] in ('RT_STRING', 'RT_DIALOG'):
            consumed.add((source['path'], offset, row['source']))
    for old_name, source in sources.items():
        for field in source['fields']:
            if (source['path'], field['offset'], field['source']) not in consumed:
                errors.append({'file': source['path'], 'status': 'UNKNOWN', 'error': '독립 PE 추출 필드가 재사용 목록에 없음', **field})
    # 코드·비ASCII 보강 색인도 현행 바이트로 대조합니다. 분류 완료를 주장하지 않습니다.
    secondary = []
    for filename in ('native_code_byte_candidates.jsonl', 'native_nonascii_pointer_candidates.jsonl'):
        path = OLD / filename
        count = 0
        fresh_exe = []
        for line in path.read_text(encoding='utf-8').split('\n'):
            if not line:
                continue
            item = json.loads(line)
            if item['file'] not in sources:
                continue
            src = sources[item['file']]
            offset, size = item['offset'], item['bytes']
            if item['file'] == 'THOG.exe' and filename == 'native_nonascii_pointer_candidates.jsonl':
                # 새 게임 아이콘이 있는 .rsrc를 가리킨 해석은 그대로 재사용하지 않습니다.
                continue
            if sha(src['data'][offset:offset + size]) != item['source_bytes_sha256']:
                errors.append({'file': src['path'], 'status': 'UNKNOWN', 'error': '보강 색인 바이트 불일치', 'offset': offset, 'index': filename})
            count += 1
        if filename == 'native_nonascii_pointer_candidates.jsonl':
            src = sources['THOG.exe']
            raw, image = src['data'], src['image']
            pointers = collections.defaultdict(list)
            for block in getattr(image, 'DIRECTORY_ENTRY_BASERELOC', []):
                for entry in block.entries:
                    if entry.type != 3:
                        continue
                    try:
                        where = image.get_offset_from_rva(entry.rva)
                        value = struct.unpack_from('<I', raw, where)[0]
                        target = image.get_offset_from_rva(value - image.OPTIONAL_HEADER.ImageBase)
                        if 0 <= target < len(raw):
                            pointers[target].append(where)
                    except (pefile.PEFormatError, ValueError, struct.error):
                        continue
            for start, consumers in sorted(pointers.items()):
                end, valid = start, True
                while end + 2 <= len(raw) and end - start < 4096:
                    code = struct.unpack_from('<H', raw, end)[0]
                    if code == 0:
                        break
                    if (code < 32 and code not in (9, 10, 13)) or 0xd800 <= code <= 0xdfff or code in (0xfffe, 0xffff):
                        valid = False
                        break
                    end += 2
                if not valid or end == start or end - start >= 4096 or raw[end:end + 2] != b'\0\0':
                    continue
                value = raw[start:end].decode('utf-16le')
                if len(value) < 4 or all(ord(c) < 128 for c in value):
                    continue
                fresh_exe.append({'file': src['path'], 'file_sha256': src['sha256'], 'offset': start, 'bytes': end - start,
                                  'source': value, 'source_bytes_sha256': sha(raw[start:end]), 'pointer_offsets': consumers,
                                  'classification': 'UNKNOWN', 'reason': '현행 PE 재배치 참조 시작점의 UTF16 해석 후보. 실제 문자열 여부는 별도 판독'})
            save('exe_nonascii_pointer_candidates.jsonl', fresh_exe)
        secondary.append({'path': str(path.relative_to(ROOT)).replace('\\', '/'), 'sha256': sha(path.read_bytes()),
                          'selected_count': count, 'fresh_exe_count': len(fresh_exe), 'byte_validation': 'PASS' if not errors else 'FAIL',
                          'limit': '원시 후보 색인 재사용이며 기계어/숫자 오탐 분류와 실제 표시 검증은 별도'})
    save('native_inventory.jsonl', rows)
    save('native_resources.jsonl', resource_records)
    save('native_pe_resources.json', structured)
    save('extraction_errors.json', errors)
    old_audit_path = ROOT / 'working_private/THE_HORDE_OF_GORAK/native_candidate_03/native_patch_audit.json'
    old_audit = read(old_audit_path)
    translation_map = {(x['file'], x['file_offset'], x['source_bytes_sha256']): x['target'] for x in old_audit['translations']}
    worklist = []
    for row in rows:
        if row['classification'] != 'VISIBLE_TRANSLATE':
            continue
        reuse = row['reuse']
        key = (reuse['historical_file'], reuse['historical_file_offset'], row['source_bytes_sha256'])
        target = translation_map.get(key)
        worklist.append({**row, 'translation': target, 'translation_source': str(old_audit_path.relative_to(ROOT)).replace('\\', '/') if target else None})
    save('native_visible_worklist.json', worklist)
    evidence_names = sorted({name for row in rows for name in
                             re.findall(r'[A-Za-z0-9_./-]+\.json(?:l)?', str(row.get('classification_evidence', '')))})
    evidence_manifest = []
    for name in evidence_names:
        path = OLD / name
        if not path.is_file():
            raise ValueError('재사용 판정의 근거 파일 누락: ' + name)
        evidence_manifest.append({'path': str(path.relative_to(ROOT)).replace('\\', '/'),
                                  'sha256': sha(path.read_bytes()), 'bytes': path.stat().st_size})
    save('reuse_evidence_manifest.json', {'classification_evidence_files': evidence_manifest,
                                        'limit': '예전 근거의 정적 사실을 동일 입력 지문에 연결함. Cobalt 실행 검수 승계 아님'})
    summary = {'game_id': 'COBALT_MINER', 'build_id': 'steam_24347666', 'status': 'NOT_RUN',
               'scope': '정적 문자열 위치/분류 재사용과 독립 리소스 추출. G2 전체 완료 아님',
               'files': files, 'native_file_count': len(files), 'identical_modules': sum(x['same_whole_file'] for x in files),
               'records': len(rows), 'classifications': dict(collections.Counter(x['classification'] for x in rows)),
               'unknown_by_file': dict(collections.Counter(x['file'] for x in rows if x['classification'] == 'UNKNOWN')),
               'visible_fields': len(worklist), 'reusable_translations': sum(x['translation'] is not None for x in worklist),
               'parse_and_reuse_errors': len(errors), 'secondary_indexes': secondary,
               'classification_evidence_manifest': 'reuse_evidence_manifest.json',
               'evidence_inputs': [{'path': str(p.relative_to(ROOT)).replace('\\', '/'), 'sha256': sha(p.read_bytes())}
                                   for p in [baseline_path, OLD / 'baseline_manifest.json', OLD / 'native_candidate_coverage.json',
                                             OLD / 'native_pe_resources_evidence.json', old_rows_path, old_audit_path]],
               'limits': ['기존 UNKNOWN은 승격하지 않음', '이전 게임 런타임 관찰은 Cobalt 런타임 근거가 아님',
                          '리소스 이미지·아이콘은 별도 판독 필요', '기존 증거의 제공자가 Ghidra가 아니면 Ghidra라고 표시하지 않음']}
    save('summary.json', summary)
    print(json.dumps({k: summary[k] for k in ['native_file_count', 'identical_modules', 'records', 'classifications', 'visible_fields', 'reusable_translations', 'parse_and_reuse_errors']}, ensure_ascii=False))

if __name__ == '__main__':
    main()
