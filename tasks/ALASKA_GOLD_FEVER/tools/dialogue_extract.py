"""대화 데이터베이스의 원문·한국어와 실제 필드 위치를 연결하여 추출합니다."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from scan_assets import GameGenerator, configure_reader, read_bounded
import UnityPy

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'source_original/ALASKA_GOLD_FEVER/25782395/game'
DATA = SOURCE / 'Alaska Gold Fever_Data'
OUT = ROOT / 'extracted_private/ALASKA_GOLD_FEVER/25782395/dialogue_scan'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def values(fields: list[dict]) -> dict[str, str]:
    keys = [field['title'] for field in fields]
    assert len(keys) == len(set(keys)), ('중복 대화 필드', keys)
    return {field['title']: field['value'] for field in fields}


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    OUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    generator = GameGenerator('6000.0.62f1')
    generator.load_local_dll_folder(str(OUT.parent / 'code/dummy'))
    configure_reader(generator)
    databases, records, other_fields, errors, files = [], [], [], [], []
    # 전수 자산 검색 결과와 별도로 빠르게 확인한 출처입니다. 전체 자산 조사를 대신하지 않습니다.
    for name in ['resources.assets', 'globalgamemanagers.assets', 'sharedassets0.assets',
                 'sharedassets1.assets', 'sharedassets2.assets', 'sharedassets3.assets', 'sharedassets5.assets']:
        path = DATA / name
        raw = path.read_bytes()
        file_sha = sha(raw)
        environment = UnityPy.load(raw)
        environment.path = str(DATA)
        environment.typetree_generator = generator
        files.append({'path': str(path.relative_to(SOURCE)).replace('\\', '/'), 'sha256': file_sha})
        for obj in environment.objects:
            if obj.type.name != 'MonoBehaviour':
                continue
            try:
                script = obj.parse_monobehaviour_head().m_Script.deref_parse_as_object()
            except Exception as exc:
                errors.append({'file': name, 'path_id': obj.path_id, 'stage': 'script', 'error': str(exc)})
                continue
            if script.m_ClassName != 'DialogueDatabase':
                continue
            source = {'file': str(path.relative_to(SOURCE)).replace('\\', '/'), 'file_sha256': file_sha,
                      'path_id': obj.path_id, 'raw_sha256': sha(obj.get_raw_data()),
                      'class': script.m_Namespace + '.' + script.m_ClassName}
            try:
                tree = read_bounded(obj)
            except Exception as exc:
                errors.append({**source, 'stage': 'database', 'error': str(exc)})
                continue
            save(name + '_' + str(obj.path_id) + '.json', tree)
            source['database'] = tree['m_Name']
            actors = {str(actor['id']): values(actor['fields']).get('Name', '') for actor in tree['actors']}
            count = Counter()
            for conversation_index, conversation in enumerate(tree['conversations']):
                conversation_fields = values(conversation['fields'])
                for entry_index, entry in enumerate(conversation['dialogueEntries']):
                    fields = values(entry['fields'])
                    count['entries'] += 1
                    location = f'/conversations/{conversation_index}/dialogueEntries/{entry_index}'
                    base = {**source, 'conversation_id': conversation['id'],
                            'conversation': conversation_fields.get('Title', ''),
                            'conversation_description': conversation_fields.get('Description', ''),
                            'entry_id': entry['id'], 'actor_id': fields.get('Actor', ''),
                            'actor_name': actors.get(fields.get('Actor', ''), ''),
                            'links': entry.get('outgoingLinks', []), 'conditions': entry.get('conditionsString', ''),
                            'script': entry.get('userScript', ''), 'sequence': fields.get('Sequence', '')}
                    for index, field in enumerate(entry['fields']):
                        title, value = field['title'], field['value']
                        if title not in ('ko', 'Menu Text ko'):
                            continue
                        menu = title == 'Menu Text ko'
                        english = fields.get('Menu Text en' if menu else 'en', '') or fields.get('Menu Text' if menu else 'Dialogue Text', '')
                        expected_field = location + f'/fields/{index}/value'
                        record = {**base, 'id': f'{name}|{obj.path_id}|{conversation["id"]}|{entry["id"]}|{title}',
                                  'field': expected_field, 'field_title': title, 'english': english,
                                  'original_korean': value, 'english_sha256': sha(english.encode('utf-8')),
                                  'original_sha256': sha(value.encode('utf-8')),
                                  'classification': 'VISIBLE_TRANSLATE' if value or english else 'UNKNOWN',
                                  'review_status': 'NOT_RUN'}
                        records.append(record)
                        count['ko_fields'] += 1
                        if value or english:
                            count['nonempty_ko_fields'] += 1
                    if 'ko' not in fields:
                        for title in ('Dialogue Text', 'Menu Text'):
                            if fields.get(title):
                                index = next(i for i, value in enumerate(entry['fields']) if value['title'] == title)
                                other_fields.append({**base, 'field': location + f'/fields/{index}/value',
                                                     'field_title': title, 'text': fields[title],
                                                     'classification': 'UNKNOWN',
                                                     'reason': '한국어 필드가 없는 기본·검수 대화. 호출 위치 확인 필요'})
            # 표시 이름 등 대사 밖 언어 필드도 빈 값까지 위치를 보존합니다.
            for scope in ('actors', 'items', 'locations', 'variables', 'conversations'):
                for index, item in enumerate(tree[scope]):
                    for field_index, field in enumerate(item.get('fields', [])):
                        if field['title'] == 'ko' or field['title'].endswith(' ko'):
                            other_fields.append({**source, 'field': f'/{scope}/{index}/fields/{field_index}/value',
                                                 'field_title': field['title'], 'text': field['value'],
                                                 'classification': 'UNKNOWN',
                                                 'reason': '대사 밖 한국어 필드; 소비 함수와 기본값 규칙 조사 필요'})
            databases.append({**source, 'conversations': len(tree['conversations']), **count})
            print(name, obj.path_id, tree['m_Name'], dict(count), flush=True)
    assert len({row['id'] for row in records}) == len(records)
    save('dialogue_entries.json', records)
    save('dialogue_other_fields.json', other_fields)
    save('dialogue_inventory.json', {'game_id': 'ALASKA_GOLD_FEVER', 'build_id': '25782395',
                                   'status': 'FAIL' if errors else 'PASS', 'scope': '명시한 7개 자산 파일의 대화 데이터베이스 추출',
                                   'full_asset_discovery': 'NOT_RUN', 'started_utc': started,
                                   'finished_utc': datetime.now(timezone.utc).isoformat(),
                                   'tool_sha256': sha(Path(__file__).read_bytes()), 'files': files,
                                   'databases': databases, 'ko_fields': len(records),
                                   'nonempty_ko_fields': sum(bool(row['english'] or row['original_korean']) for row in records),
                                   'other_fields': len(other_fields), 'errors': errors})
    print(json.dumps({'databases': len(databases), 'ko_fields': len(records),
                      'nonempty_ko_fields': sum(bool(row['english'] or row['original_korean']) for row in records),
                      'errors': len(errors)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
