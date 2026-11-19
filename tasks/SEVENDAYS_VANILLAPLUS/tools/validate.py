import collections
import copy
import csv
import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
GAME = 'SEVENDAYS_VANILLAPLUS'
BASE = ROOT / 'source_original' / GAME / '1.6.0'
WORK = ROOT / 'working_private' / GAME / 'ko_0.1.0'
CANDIDATE = ROOT / 'build_candidate' / GAME / 'ko_0.1.0'
OUT = ROOT / 'validation' / GAME / 'ko_0.1.0'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parse(data):
    return list(csv.reader(io.StringIO(data.decode('utf-8-sig')), strict=True))


def check(original, actual, expected):
    errors = []
    if original[0] != actual[0]:
        return ['header']
    if len(original) != len(actual):
        errors.append('row_count')
    col = original[0].index('koreana')
    english_col = original[0].index('english')
    seen = set()
    for n, (x, y) in enumerate(zip(original[1:], actual[1:]), 2):
        if len(x) != len(y) or len(y) != len(actual[0]):
            errors.append(f'{n}:width')
            continue
        key, en, ko = x[0], x[english_col], y[col]
        if y[0] in seen:
            errors.append(f'{n}:duplicate')
        seen.add(y[0])
        if y[:col] + y[col+1:] != x[:col] + x[col+1:]:
            errors.append(f'{n}:non_korean_change')
        if not ko.strip() or '\ufffd' in ko:
            errors.append(f'{n}:empty_or_corrupt')
        if expected.get(key) != ko:
            errors.append(f'{n}:expected_translation')
        tag_en = re.findall(r'\[[^\]]*\]|<[^>]*>', en)
        tag_ko = re.findall(r'\[[^\]]*\]|<[^>]*>', ko)
        if tag_en != tag_ko:
            errors.append(f'{n}:tag_sequence')
        stack = []
        for tag in tag_ko:
            if re.fullmatch(r'\[[0-9A-Fa-f]{6,8}\]', tag):
                stack.append(tag)
            elif tag == '[-]':
                if not stack:
                    errors.append(f'{n}:tag_nesting')
                else:
                    stack.pop()
            else:
                errors.append(f'{n}:unknown_tag')
        if stack:
            errors.append(f'{n}:unclosed_tag')
        # 수치의 위치는 번역 원본에서 검수했고, 여기서는 부호와 값의 손실도 따로 검출한다.
        strip = lambda text: re.sub(r'\[[^\]]*\]|<[^>]*>', '', text)
        numeric = lambda text: collections.Counter(re.findall(r'[+-]?\d+(?:\.\d+)?', strip(text)))
        if numeric(en) != numeric(ko):
            errors.append(f'{n}:numbers')
        for token in ('\\n', '\n', '\r', '\t', '%'):
            if en.count(token) != ko.count(token):
                errors.append(f'{n}:control:{token}')
        placeholders = lambda text: collections.Counter(re.findall(r'\{[^}]+\}', text))
        if placeholders(en) != placeholders(ko):
            errors.append(f'{n}:placeholders')
    return errors


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    raw = (BASE / 'VanillaPlus/Config/Localization.csv').read_bytes()
    candidate = (CANDIDATE / 'VanillaPlus/Config/Localization.csv').read_bytes()
    canonical_data = (WORK / 'canonical_translation.json').read_bytes()
    canonical = json.loads(canonical_data)
    expected = {r['key']: r['koreana'] for r in canonical}
    assert len(expected) == len(canonical) == 4235
    original, actual = parse(raw), parse(candidate)
    errors = check(original, actual, expected)
    manifest = json.loads((BASE / 'manifest.json').read_text(encoding='utf-8'))
    for r in manifest['files']:
        if sha((BASE / r['path']).read_bytes()) != r['sha256']:
            errors.append('baseline:' + r['path'])
    # 아래의 결함 주입은 누락·위치 교환·태그·수치 오류를 검사기가 실제 거부하는지 확인한다.
    mutants = {}
    col = original[0].index('koreana')
    value = copy.deepcopy(actual); value[1][col] = ''; mutants['empty'] = value
    value = copy.deepcopy(actual); value[1][col], value[2][col] = value[2][col], value[1][col]; mutants['swapped'] = value
    value = copy.deepcopy(actual); value[1][1] = 'changed'; mutants['other_column'] = value
    value = copy.deepcopy(actual); value.pop(1); mutants['removed_row'] = value
    value = copy.deepcopy(actual); value[1][0] = value[2][0]; mutants['duplicate'] = value
    value = copy.deepcopy(actual); value[1][col] = value[1][col].replace('[F0B232]', '[-]', 1); mutants['tag_order'] = value
    value = copy.deepcopy(actual); value[2][col] = value[2][col].replace('10', '11', 1); mutants['number'] = value
    selftest = {name: bool(check(original, value, expected)) for name, value in mutants.items()}
    assert all(selftest.values()), selftest
    # 명시적인 이름·설명 참조를 모으고 쉼표 목록을 개별 키로 해석한다.
    lookup = {}
    for file in (BASE / 'base_game_Localization.csv', BASE / 'VanillaPlus/Config/Localization.csv'):
        with file.open(encoding='utf-8-sig', newline='') as f:
            lookup.update({r['Key']: r for r in csv.DictReader(f) if r.get('Key')})
    refs, ui, extraction_errors = [], [], []
    for file in (BASE / 'VanillaPlus').rglob('*.xml'):
        data = file.read_bytes()
        try:
            tree = ET.fromstring(data)
        except Exception as exc:
            extraction_errors.append({'file': str(file.relative_to(BASE)), 'error': str(exc)})
            continue
        for index, element in enumerate(tree.iter()):
            for attr, value in element.attrib.items():
                if attr in ('name_key', 'desc_key', 'long_desc_key', 'text_key'):
                    for key in value.split(','):
                        refs.append({'file': str(file.relative_to(BASE)), 'element': index, 'field': attr,
                            'key': key.strip(), 'file_sha256': sha(data)})
            if element.tag == 'property' and element.get('name') == 'DescriptionKey':
                refs.append({'file': str(file.relative_to(BASE)), 'element': index, 'field': 'value',
                    'key': element.get('value'), 'file_sha256': sha(data)})
            if element.tag == 'label' and element.get('text'):
                ui.append({'file': str(file.relative_to(BASE)), 'element': index,
                    'text': element.get('text'), 'text_key': element.get('text_key'), 'file_sha256': sha(data)})
    missing = [r for r in refs if r['key'] not in lookup and r['key'] != '${empty_slot_text_key}']
    base_windows = BASE / 'base_XUi_InGame_windows.xml'
    dynamic_keys = [element.get('empty_slot_text_key') for element in ET.parse(base_windows).iter()
        if element.get('empty_slot_text_key')]
    assert dynamic_keys and all(key in lookup and lookup[key].get('koreana') for key in dynamic_keys)
    for r in refs:
        r['classification'] = 'INTERNAL'
        r['reason'] = '표시 문구를 가져오는 언어 표 참조 키'
        r['resolved'] = r not in missing
    for item in ui:
        text = item['text']
        if item['text_key']:
            item.update(classification='INTERNAL', reason='실제 표시값은 text_key의 기존 언어 표 번역을 사용')
        elif text == '{partname}':
            item.update(classification='INTERNAL', reason='부품 아이템 이름의 실행 중 바인딩')
        elif text == '[F0B232]Vanilla +[-]':
            item.update(classification='VISIBLE_KEEP', reason='원본 모드 브랜드 표기')
        else:
            item.update(classification='UNKNOWN', reason='추가 검토 필요')
            errors.append('unknown_ui')
    allowed = {'R', 'SMG5', 'AK47', 'M60', 'LED', 'BBQ', 'AZ', 'Pop-N-Pills', 'Savage', 'Country',
        'Mo', 'Power', 'Electronics', 'Working', 'Stiff', 'Tools', 'TFP', 'USA', 'OSB', 'T', 'A', 'B', 'C'}
    kept = []
    for r in canonical:
        words = re.findall(r'[A-Za-z][A-Za-z0-9_\x27.-]*', re.sub(r'\[[^\]]*\]|\\n', ' ', r['koreana']))
        unknown = [w for w in words if w not in allowed and not re.fullmatch(r'[xX][0-9xX]+|m', w)]
        if unknown:
            errors.append('unreviewed_latin:' + r['key'])
        r['classification'] = 'VISIBLE_TRANSLATE' if re.search('[가-힣]', r['koreana']) else 'VISIBLE_KEEP'
        if words:
            kept.append({'key': r['key'], 'source_sha256': r['source_sha256'], 'tokens': words,
                'reason': '무기 모델·키 입력·단위·규격·재질 약어·간판 상표의 식별 표기를 보존'})
    required = ''.join(sorted(set(''.join(expected.values()))))
    (WORK / 'required_characters.txt').write_text(required, encoding='utf-8')
    (WORK / 'source_inventory.json').write_text(json.dumps({'csv': canonical, 'references': refs, 'ui': ui,
        'kept_tokens': kept, 'extraction_errors': extraction_errors, 'missing_references': missing}, ensure_ascii=False, indent=2), encoding='utf-8')
    if missing or extraction_errors:
        errors.append('source_extraction_or_reference')
    report = {'game_id': GAME, 'build_id': 'ko_0.1.0', 'started_utc': started,
        'ended_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status': 'FAIL' if errors else 'PASS', 'source_sha256': sha(raw), 'candidate_sha256': sha(candidate),
        'canonical_sha256': sha(canonical_data), 'validator_sha256': sha(Path(__file__).read_bytes()),
        'python': sys.version, 'rows': len(actual)-1, 'columns': len(actual[0]), 'xml_files': 18,
        'localization_references': len(refs), 'missing_references': len(missing), 'ui_text_occurrences': len(ui),
        'dynamic_slot_bindings': len(dynamic_keys), 'dynamic_slot_keys': sorted(set(dynamic_keys)),
        'base_window_sha256': sha(base_windows.read_bytes()),
        'required_characters': len(required), 'empty_translations': sum(not r.strip() for r in expected.values()),
        'errors': errors, 'fault_injection_checks': selftest,
        'graphics_and_font_rendering': 'NOT_RUN', 'graphics_reason': '사용자가 직접 플레이 테스트를 수행하도록 요청함',
        'scope': '모드 언어 표 및 명시적 XML 번역 참조. 기본 게임 이미지 픽셀과 실제 화면은 미검증.'}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'static_checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    assert not errors, errors


if __name__ == '__main__':
    main()
