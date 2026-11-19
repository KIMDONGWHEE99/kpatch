"""언어표의 모든 칸을 위치 기준으로 목록화합니다(G2의 언어표 계층).

GDRE가 복원한 CSV는 키 이름을 못 찾은 문구가 있으므로 참고용으로만 쓰고,
기준은 원본 .translation 파일의 칸 위치입니다.
"""
import collections
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, BASE, EXTRACTED, RECOVERED, WORK, PCK_NAME, save, load, run_gdre, sha_text
import optimized_translation as ot

LOCALES = ['en', 'kr', 'ja', 'de', 'zh_Hans', 'zh_Hant', 'pl', 'pt_BR', 'es', 'Description']
OUT = WORK / 'census'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {e['path']: e for e in load(EXTRACTED / 'pck_manifest.json')['entries']}
    config = {'translations': [f'res://locale/locale.{name}.translation' for name in LOCALES],
              'report': str(OUT / 'translation_dump.json')}
    save(OUT / 'translation_dump_config.json', config)
    run_gdre(['--path', WORK / 'tool_runtime', '--script', Path(__file__).parent / 'dump_translations.gd', '--',
              BASE / PCK_NAME, OUT / 'translation_dump_config.json'], 'dump_translations')
    dump = load(OUT / 'translation_dump.json')
    tables = {}
    for name in LOCALES:
        raw = dump[f'res://locale/locale.{name}.translation']
        slots = ot.parse(raw['hash_table'], raw['bucket_table'], raw['messages'])
        tables[name] = {'size': len(raw['hash_table']), 'slots': slots, 'index': ot.index_slots(slots),
                        'class': raw['class'], 'strings_size': raw['strings_size']}
    english = tables['en']
    # CSV의 키 이름을 칸 위치에 연결하고, 엔진이 돌려준 문구와 CSV 문구가 같은지 확인합니다.
    rows = list(csv.DictReader((RECOVERED / 'locale/locale.csv').open(encoding='utf-8-sig', newline='')))
    key_of, mismatches, missing_rows = {}, [], []
    for row in rows:
        key = row['key']
        if not key:
            continue
        if key.startswith('<!MissingKey:'):
            missing_rows.append(row)
            continue
        slot = ot.find(english['index'], english['size'], key)
        if slot is None:
            mismatches.append({'key': key, 'problem': '영어 표에 칸 없음'})
            continue
        if slot['message'] != row['en']:
            mismatches.append({'key': key, 'problem': '문구 불일치', 'csv': row['en'], 'table': slot['message']})
        key_of[slot['slot']] = key
    records = []
    for slot in english['slots']:
        record = {'id': 'locale/locale.en.translation::' + slot['slot'], 'slot': slot['slot'],
                  'table_index': slot['table_index'], 'element': slot['element'], 'seed': slot['seed'],
                  'key_hash': slot['key_hash'], 'key': key_of.get(slot['slot']),
                  'file': 'locale/locale.en.translation', 'file_sha256': manifest['locale/locale.en.translation']['sha256'],
                  'source': slot['message'], 'source_sha256': sha_text(slot['message']),
                  'classification': 'UNKNOWN', 'target': None, 'reference': {}}
        # 다른 언어의 같은 키 해시 칸을 참고 번역으로 붙입니다(같은 키라면 표 크기·씨앗이 달라도 찾을 수 있게 키로 조회).
        for name in ('ja', 'de', 'zh_Hans'):
            other = None
            if record['key']:
                other = ot.find(tables[name]['index'], tables[name]['size'], record['key'])
            record['reference'][name] = other['message'] if other else None
        records.append(record)
    # 키를 모르는 칸은 GDRE CSV의 MissingKey 행과 영어 문구로 짝지어 다른 언어 참고를 붙입니다.
    unknown = [r for r in records if r['key'] is None]
    by_text = collections.defaultdict(list)
    for row in missing_rows:
        by_text[row['en']].append(row)
    for record in unknown:
        rows_for = by_text.get(record['source'], [])
        if len(rows_for) == 1:
            for name in ('ja', 'de', 'zh_Hans'):
                record['reference'][name] = rows_for[0][name] or None
    save(OUT / 'locale_inventory.json', records)
    summary = {'english_slots': len(records), 'known_keys': len(key_of), 'unknown_key_slots': len(unknown),
               'csv_missing_rows': len(missing_rows), 'mismatches': mismatches,
               'tables': {name: {'class': t['class'], 'table_size': t['size'], 'slots': len(t['slots']),
                                 'strings_size': t['strings_size'],
                                 'non_empty': sum(1 for s in t['slots'] if s['message'])} for name, t in tables.items()},
               'duplicate_sources': sum(1 for _, c in collections.Counter(r['source'] for r in records).items() if c > 1),
               'source_chars': sum(len(r['source']) for r in records)}
    save(OUT / 'locale_summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
