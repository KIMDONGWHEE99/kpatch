"""표시 필드와 원본 위치를 조사하며 미확정 문구는 별도로 남깁니다."""
from pathlib import Path
from collections import defaultdict
import hashlib
import json
import re
from common import ROOT, EXTRACTED, WORK, save, sha


def known_translations():
    result = defaultdict(set)
    for name in ('ko_part_a.json', 'ko_part_b.json'):
        path = WORK / 'translations' / name
        for row in json.loads(path.read_text(encoding='utf-8')):
            result[row['source']].add(row['target'])
            if row.get('effective_source'):
                result[row['effective_source']].add(row['target'])
    return result


def walk(value, pointer=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk(item, pointer + (key,))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk(item, pointer + (index,))
    elif isinstance(value, str):
        yield pointer, value


def main():
    known = known_translations()
    rows = []
    display_fields = {'display_name', 'description', 'name', 'title', 'desc', 'sender', 'sender_title',
                      'subject', 'content', 'objective_title', 'label', 'text', 'role', 'faction'}
    for path in sorted((EXTRACTED / 'recovered/data/json').glob('*.json')):
        values = json.loads(path.read_text(encoding='utf-8-sig'))
        for pointer, value in walk(values):
            fields = [part for part in pointer if isinstance(part, str)]
            field = fields[-1] if fields else ''
            metadata = '_meta' in fields
            proper_name = path.name == 'worker_names.json'
            visible = field in display_fields and not metadata
            if proper_name:
                classification, evidence = 'VISIBLE_KEEP', 'HiringManager.load_worker_names에서 무작위 인명으로 사용하며 원래 인명 표기를 보존합니다.'
            elif visible:
                classification, evidence = 'VISIBLE_TRANSLATE', '게임 데이터의 표시 필드이며 데이터 관리자와 UI가 이름·설명·메시지·대화 값으로 소비합니다.'
            else:
                classification, evidence = 'INTERNAL', '표시 필드와 구분된 동작 식별자·자원 경로·조건 또는 개발용 _meta 자료입니다.'
            targets = known.get(value, set())
            target = next(iter(targets)) if len(targets) == 1 else None
            if classification == 'VISIBLE_KEEP' or not re.search('[A-Za-z]', value):
                target = value
            rows.append({'kind': 'json', 'path': path.relative_to(EXTRACTED / 'recovered').as_posix(),
                         'pointer': list(pointer), 'source': value, 'target': target if visible or proper_name else None,
                         'classification': classification, 'evidence': evidence, 'source_sha256': sha(path),
                         'location_id': path.relative_to(EXTRACTED / 'recovered').as_posix() + '#' + '/'.join(map(str, pointer))})
    visible_fields = {'text', 'placeholder_text', 'tooltip_text', 'title', 'dialog_text'}
    pattern = re.compile(r'^([\w/]+) = "((?:\\.|[^"\\])*)"', re.M)
    for path in sorted([*(EXTRACTED / 'recovered').rglob('*.tscn'), *(EXTRACTED / 'recovered').rglob('*.tres')]):
        text = path.read_text(encoding='utf-8')
        for match in pattern.finditer(text):
            value = json.loads('"' + match[2] + '"', strict=False)
            visible = match[1] in visible_fields or re.fullmatch(r'popup/item_\d+/text', match[1])
            classification = 'VISIBLE_TRANSLATE' if visible and re.search('[A-Za-z]', value) else 'VISIBLE_KEEP' if visible else 'INTERNAL'
            targets = known.get(value, set())
            target = next(iter(targets)) if len(targets) == 1 else None
            if classification == 'VISIBLE_KEEP':
                target = value
            rows.append({'kind': 'resource', 'path': path.relative_to(EXTRACTED / 'recovered').as_posix(),
                         'field': match[1], 'offset': match.start(2), 'end_offset': match.end(2),
                         'line': text[:match.start()].count('\n') + 1, 'source': value, 'target': target if visible else None,
                         'classification': classification, 'evidence': '장면·자원의 표시 속성입니다.' if visible else '자원의 내부 속성·지형 이름·애니메이션·편집기 정보입니다.',
                         'source_sha256': sha(path), 'location_id': path.relative_to(EXTRACTED / 'recovered').as_posix() + '#offset:' + str(match.start(2))})
    save(WORK / 'discovery/resource_string_rows.json', rows)
    missing = defaultdict(list)
    for row in rows:
        if row['classification'] == 'VISIBLE_TRANSLATE' and row['target'] is None:
            missing[row['source']].append({key: row[key] for key in ('path', 'location_id', 'kind')})
    save(WORK / 'translations/resource_missing_rows.json', [
        {'source_text': source, 'target': '', 'locations': locations, 'classification': 'UNKNOWN'}
        for source, locations in missing.items()])
    print('조사 위치:', len(rows), '표시 위치:', sum(row['classification'].startswith('VISIBLE') for row in rows),
          '기존 번역에 없는 고유 문구:', len(missing))


if __name__ == '__main__':
    main()
