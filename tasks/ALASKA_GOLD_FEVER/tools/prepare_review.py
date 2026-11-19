"""영어·기존 한국어를 키와 위치에 맞춰 교정 입력으로 준비합니다."""
from extract_localization import ROOT, OUT, save
import hashlib
import json

WORK = ROOT / 'working_private/ALASKA_GOLD_FEVER/translation'

def main():
    tables = json.loads((OUT / 'tables.json').read_text('utf-8'))
    shared = json.loads((OUT / 'shared.json').read_text('utf-8'))
    selected = {}
    for table in tables:
        locale = table['tree']['m_LocaleId']['m_Code']
        if locale not in ('en', 'ko'):
            continue
        collection = table['tree']['m_Name'].rsplit('_', 1)[0]
        assert (collection, locale) not in selected
        selected[collection, locale] = table
    output = []
    for collection, group in shared.items():
        keys = {r['m_Id']: r['m_Key'] for r in group['tree']['m_Entries']}
        en, ko = selected[collection, 'en'], selected[collection, 'ko']
        en_rows = {r['m_Id']: r for r in en['tree']['m_TableData']}
        ko_rows = {r['m_Id']: r for r in ko['tree']['m_TableData']}
        rows = []
        for item_id, english in en_rows.items():
            korean = ko_rows.get(item_id)
            source = english['m_Localized']
            old = None if korean is None else korean['m_Localized']
            rows.append({'collection': collection, 'id': str(item_id), 'key': keys.get(item_id),
                'english': source, 'korean_original': old, 'translation': old,
                'review_status': 'UNKNOWN', 'review_note': '',
                'english_sha256': hashlib.sha256(source.encode()).hexdigest(),
                'korean_sha256': None if old is None else hashlib.sha256(old.encode()).hexdigest(),
                'location': {'bundle': ko['bundle'], 'bundle_sha256': ko['sha256'],
                             'asset': ko['asset'], 'path_id': ko['path_id'],
                             'field': 'm_TableData[m_Id=' + str(item_id) + '].m_Localized'},
                'english_metadata': english.get('m_Metadata'),
                'korean_metadata': None if korean is None else korean.get('m_Metadata')})
        save(WORK / (collection + '.json'), rows)
        output.extend(rows)
    save(WORK / 'inventory_original.json', output)
    print(json.dumps({'rows': len(output), 'missing_ko': [{'collection':r['collection'], 'key':r['key'], 'english':r['english']} for r in output if r['korean_original'] is None]},ensure_ascii=False,indent=2))
    for collection in shared:
        rows = [r for r in output if r['collection'] == collection]
        print('\n' + collection)
        for row in rows[:12]:
            print(json.dumps({k:row[k] for k in ('key','english','korean_original')}, ensure_ascii=False))

if __name__ == '__main__':
    main()
