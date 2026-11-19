"""번역 원본을 독립적으로 대조하고 제어 정보와 미검토 항목을 찾습니다."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / 'working_private/ALASKA_GOLD_FEVER/translation'

# 영어 원본의 잘못된 닫기 순서를 그대로 복제하지 않습니다.
# 아래 여섯 문구의 기존 한국어는 정상 중첩이며 표시 속성은 같습니다.
TAG_REPAIRS = {
    'thank_you_demo_wishlist_title': ('</b></size>', '</size></b>'),
    'thank_you_playtestdemo_wishlist_title': ('</b></size>', '</size></b>'),
    'thank_you_demo_discord_title': ('</b></size>', '</size></b>'),
    'thank_you_demo_quickpanel_title': ('</b></size>', '</size></b>'),
    'thank_you_demo_steamreview_title': ('</b></size>', '</size></b>'),
    'readAndAcceptContestRules': ('</u></color>', '</color></u>'),
}

# 영어에만 남아 있고 한국어 값·공유 키가 없는 정확한 한 행입니다.
# 추출기가 만든 location은 표의 위치이며 해당 m_Id의 존재를 뜻하지 않습니다.
ORPHAN = {
    'collection': 'AlaskaStoryTranslations', 'id': '56888088429502464', 'key': None,
    'english': 'Earn money to buy out the Riverside Mine',
    'english_sha256': '29b0758d325aec49515197178f4b7806ac561f400be3a61345cd1dd6a504c247',
    'korean_original': None, 'korean_sha256': None, 'korean_metadata': None,
    'location': {
        'bundle': 'localization-string-tables-korean_assets_all.bundle',
        'bundle_sha256': '4674f9c8ccc47b1bedf57e04f77154e0bc8606626060c44cb7e55eefa172fe2c',
        'asset': 'CAB-6cd60965dc541c07fbaca8a41b15842c', 'path_id': -4104805338317468757,
        'field': 'm_TableData[m_Id=56888088429502464].m_Localized',
    },
}


def is_known_orphan(row):
    return all(key in row and row[key] == value for key, value in ORPHAN.items())


def ko_target_rows(rows):
    omitted = [row for row in rows if is_known_orphan(row)]
    targets = [row for row in rows if not is_known_orphan(row)]
    if len(rows) != 1894 or len(omitted) != 1 or len(targets) != 1893:
        raise ValueError('전체 표 1894행·한국어 대상 1893행·영어 고아 1행 조건이 다릅니다.')
    if omitted[0].get('review_status') != 'OUT_OF_SCOPE' or omitted[0].get('translation') is not None or not omitted[0].get('review_note'):
        raise ValueError('영어 고아행의 제외 근거가 확정되지 않았습니다.')
    return targets

def signature(text):
    return {
        'tags': re.findall(r'<[^>]*>', text),
        'placeholders': dict(Counter(re.findall(r'\{[^{}]*\}', text))),
        'input_tokens': dict(Counter(re.findall(r'\[[A-Za-z][A-Za-z0-9_ .:+/\-]*\]', text))),
        'newlines': re.findall(r'\r\n|\r|\n', text),
        'escaped_newlines': re.findall(r'\\[nr]', text),
    }

def validate(original, reviewed, require_review=True):
    errors = []
    expected = {(r['collection'],r['id']):r for r in original}
    actual = {}
    for row in reviewed:
        key = (row['collection'],row['id'])
        if key in actual:
            errors.append({'id':key,'error':'DUPLICATE'})
        actual[key] = row
    for key in sorted(set(expected) ^ set(actual)):
        errors.append({'id':key,'error':'MISSING_OR_EXTRA'})
    for key in expected.keys() & actual.keys():
        before, after = expected[key], actual[key]
        for field in ('english','english_sha256','korean_original','korean_sha256','location','key'):
            if before[field] != after[field]:
                errors.append({'id':key,'error':'SOURCE_CHANGED','field':field})
        if is_known_orphan(before) and is_known_orphan(after):
            if after.get('translation') is not None or after.get('review_status') != 'OUT_OF_SCOPE' or not after.get('review_note'):
                errors.append({'id':key,'error':'ORPHAN_NOT_EXPLICITLY_EXCLUDED'})
            continue
        value = after.get('translation')
        if not isinstance(value,str) or (before['english'] and not value.strip()):
            errors.append({'id':key,'error':'EMPTY'})
            continue
        if require_review and (after.get('review_status') not in ('EDITED','KEEP') or not after.get('review_note')):
            errors.append({'id':key,'error':'UNREVIEWED'})
        if unicodedata.normalize('NFC',value) != value or '\ufffd' in value:
            errors.append({'id':key,'error':'UNICODE'})
        control_source = before['english']
        if before['collection'] == 'UtilitiesTranslations' and before['key'] in TAG_REPAIRS:
            old, new = TAG_REPAIRS[before['key']]
            control_source = control_source.replace(old, new)
        a, b = signature(control_source), signature(value)
        for field in a:
            if a[field] != b[field]:
                errors.append({'id':key,'key':before['key'],'error':'CONTROL_CHANGED','field':field,'expected':a[field],'actual':b[field]})
    return errors

def main():
    original = json.loads((WORK / 'inventory_original.json').read_text('utf-8'))
    reviewed = []
    inputs = []
    for path in sorted(WORK.glob('*Translations.json')):
        reviewed.extend(json.loads(path.read_text('utf-8')))
        inputs.append({'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    errors = validate(original,reviewed)
    report = {'status':'FAIL' if errors else 'PASS','input_files':inputs,'rows':len(reviewed),
              'edited':sum(r['translation'] != r['korean_original'] for r in reviewed),
              'errors':errors}
    (WORK / 'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'rows':len(reviewed),'edited':report['edited'],'error_counts':dict(Counter(e['error'] for e in errors))},ensure_ascii=False))
    print(json.dumps([e for e in errors if e['error'] != 'UNREVIEWED'][:30],ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
