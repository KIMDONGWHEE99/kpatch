"""복원한 스크립트·장면·자원·설정의 모든 문자열을 위치별로 목록화합니다(G2).

MR_MAGEBOY_DEMO의 census_text.py(문자열 추출기)와 HOW_EMPIRES_WORK의 census.py(위치 연결)를
이 게임에 맞게 합쳤습니다. 새 항목의 기본값은 UNKNOWN이며, 여기서는 구조로 확정할 수 있는
것만 INTERNAL로 판정합니다. 나머지 판정은 classify.py가 근거와 함께 붙입니다.
"""
import bisect
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import EXTRACTED, RECOVERED, PACK, WORK, save, load, sha, sha_text
import optimized_translation as ot

OUT = WORK / 'census'
TEXT_SUFFIXES = ('.gd', '.tscn', '.tres', '.godot', '.json', '.cfg', '.gdshader', '.gdextension', '.import')


def tokens(text, script=False, config=False):
    """따옴표 문자열을 위치와 함께 뽑습니다. 주석 안의 따옴표는 건너뜁니다."""
    index = 0
    while index < len(text):
        if (script and text[index] == '#') or (config and text[index] == ';'):
            index = text.find('\n', index)
            if index < 0:
                break
            continue
        if text[index] not in ('"', "'"):
            index += 1
            continue
        quote = text[index]
        width = 3 if text[index:index + 3] == quote * 3 else 1
        start = index
        index += width
        inner = index
        while index < len(text):
            if text[index] == '\\':
                index += 2
                continue
            if text[index:index + width] == quote * width:
                break
            index += 1
        if index >= len(text):
            raise ValueError(f'문자열 종료 누락: {start}')
        raw = text[inner:index]
        value = re.sub(r'\\([nrt"\'\\])', lambda m: {'n': '\n', 'r': '\r', 't': '\t'}.get(m[1], m[1]), raw)
        index += width
        yield {'start': start, 'end': index, 'raw': raw, 'value': value, 'quote': quote * width}


def original_of(rel, manifest):
    """복원 파일이 원본 PCK의 어느 항목에서 왔는지 찾습니다."""
    if rel.endswith('.gd'):
        return rel[:-3] + '.gdc'
    if rel + '.remap' in manifest:
        match = re.search(r'path="res://([^"]+)"', (PACK / (rel + '.remap')).read_text(encoding='utf-8'))
        return match[1] if match else None
    if rel == 'project.godot':
        return 'project.binary'
    return rel if rel in manifest else None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {e['path']: e for e in load(EXTRACTED / 'pck_manifest.json')['entries']}
    locale = load(OUT / 'locale_inventory.json')
    index = ot.index_slots([{'table_index': r['table_index'], 'seed': r['seed'], 'key_hash': r['key_hash'], 'slot': r['slot']} for r in locale])
    table_size = 1543
    records, errors, files, key_hits = [], [], [], collections.Counter()
    for path in sorted(RECOVERED.rglob('*')):
        rel = path.relative_to(RECOVERED).as_posix()
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if rel.startswith('.godot/') or rel == 'gdre_export.log':
            continue
        original = original_of(rel, manifest)
        info = manifest.get(original, {}) if original else {}
        file_row = {'path': rel, 'original': original, 'original_sha256': info.get('sha256'), 'recovered_sha256': sha(path)}
        files.append(file_row)
        try:
            text = path.read_text(encoding='utf-8-sig')
            scan = text
            if path.suffix == '.gdshader':
                scan = re.sub(r'/\*.*?\*/|//[^\n]*', lambda m: re.sub(r'[^\n]', ' ', m[0]), text, flags=re.S)
            newlines = [m.start() for m in re.finditer('\n', text)]
            for ordinal, token in enumerate(tokens(scan, path.suffix == '.gd', path.suffix in ('.godot', '.cfg', '.import', '.gdextension'))):
                line_start = text.rfind('\n', 0, token['start']) + 1
                line_end = text.find('\n', token['end'])
                context = text[line_start:line_end if line_end >= 0 else len(text)].strip()
                prefix = text[line_start:token['start']]
                value = token['value']
                status, reason = 'UNKNOWN', '표시 소비 위치 확인 필요'
                slot = ot.find(index, table_size, value) if value else None
                if slot is not None:
                    status, reason = 'INTERNAL', '언어표 키(해시 일치 칸 ' + slot['slot'] + '); 표시 문구는 언어표 칸에서 번역'
                    key_hits[slot['slot']] += 1
                elif value.startswith(('res://', 'uid://', 'user://')):
                    status, reason = 'INTERNAL', '자산·사용자 저장 경로'
                elif path.suffix in ('.tscn', '.tres') and (context.startswith('[') or re.search(r'(ExtResource|SubResource|NodePath)\([^)]*$', prefix)):
                    status, reason = 'INTERNAL', 'Godot 장면/자원의 선언·참조 문법'
                elif path.suffix == '.gd' and token['start'] > 0 and text[token['start'] - 1] in ('&', '$', '^', '%'):
                    status, reason = 'INTERNAL', 'Godot 노드 경로·StringName 식별자 문법'
                records.append({'id': rel + '::' + str(ordinal), 'file': rel, 'original_file': original,
                                'original_sha256': info.get('sha256'), 'recovered_sha256': file_row['recovered_sha256'],
                                'line': bisect.bisect_left(newlines, token['start']) + 1, 'ordinal': ordinal,
                                'source': value, 'source_sha256': sha_text(value), 'start': token['start'], 'end': token['end'],
                                'quote': token['quote'], 'context': context[:400], 'prefix': prefix.strip()[:200],
                                'key_slot': slot['slot'] if slot else None, 'classification': status, 'evidence': reason})
        except Exception as error:
            errors.append({'file': rel, 'original_file': original, 'original_sha256': info.get('sha256'), 'error': str(error), 'status': 'UNKNOWN'})
    save(OUT / 'strings.json', records)
    save(OUT / 'text_files.json', files)
    save(OUT / 'extraction_errors.json', errors)
    # 코드·자원 어디에도 글자 그대로 나오지 않는 언어표 칸(키를 실행 중에 조합하거나 쓰지 않는 칸)을 따로 남깁니다.
    unreferenced = [r['slot'] for r in locale if r['source'] and r['slot'] not in key_hits]
    save(OUT / 'unreferenced_slots.json', unreferenced)
    summary = {'files': len(files), 'files_without_original': [f['path'] for f in files if not f['original']],
               'by_suffix': dict(collections.Counter(Path(f['path']).suffix for f in files)),
               'strings': len(records), 'classifications': dict(collections.Counter(r['classification'] for r in records)),
               'unknown_by_suffix': dict(collections.Counter(Path(r['file']).suffix for r in records if r['classification'] == 'UNKNOWN')),
               'errors': errors, 'locale_slots_referenced_literally': len(key_hits), 'locale_slots_not_referenced_literally': len(unreferenced)}
    save(OUT / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
