import collections
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
GAME = 'SEVENDAYS_VANILLAPLUS'
BASE = ROOT / 'source_original' / GAME / '1.6.0'
WORK = ROOT / 'working_private' / GAME / 'ko_0.1.0'
CANDIDATE = ROOT / 'build_candidate' / GAME / 'ko_0.1.0'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def normalize(line):
    line = line.replace('[F0B232]', '{color}').replace('[-]', '{endcolor}')
    values = {}
    def replace(match):
        name = 'n' + str(len(values))
        values[name] = match[0]
        return '{' + name + '}'
    return re.sub(r'[+-]?\d+(?:\.\d+)?', replace, line), values


def tsv_map(path):
    result = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        key, text = line.split('\t', 1)
        assert int(key) not in result
        result[int(key)] = text
    return result


def field_spans(data):
    # CSV의 따옴표와 줄바꿈을 해석하되 원래 바이트를 그대로 보존한다.
    records, record = [], []
    start, i, quoted = 0, 0, False
    while i < len(data):
        char = data[i]
        if char == 34:
            if quoted and i + 1 < len(data) and data[i + 1] == 34:
                i += 2
                continue
            quoted = not quoted
        elif not quoted and char in (44, 10, 13):
            record.append((start, i))
            if char != 44:
                records.append(record)
                record = []
                if char == 13 and i + 1 < len(data) and data[i + 1] == 10:
                    i += 1
            start = i + 1
        i += 1
    assert not quoted
    if start < len(data) or record:
        record.append((start, len(data)))
        records.append(record)
    return records


def patch_csv(raw, translations):
    parsed = list(csv.reader(io.StringIO(raw.decode('utf-8-sig')), strict=True))
    spans = field_spans(raw)
    assert len(spans) == len(parsed)
    col = parsed[0].index('koreana')
    patches = []
    for record, fields in zip(parsed[1:], spans[1:]):
        assert len(record) == len(fields) == len(parsed[0])
        value = translations[record[0]]
        replacement = ('"' + value.replace('"', '""') + '"').encode('utf-8')
        patches.append((*fields[col], replacement))
    result, end = [], 0
    for a, b, value in patches:
        result.extend((raw[end:a], value))
        end = b
    result.append(raw[end:])
    return b''.join(result)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    official = json.loads((WORK / 'official_matches.json').read_text(encoding='utf-8'))
    units = json.loads((WORK / 'units.json').read_text(encoding='utf-8'))
    localized_units = {}
    for p in sorted(WORK.glob('ko_units_*.tsv')):
        part = tsv_map(p)
        assert not localized_units.keys() & part.keys()
        localized_units.update(part)
    assert set(localized_units) == {r['id'] for r in units}
    unit_map = {r['english']: localized_units[r['id']] for r in units}
    for en, ko in unit_map.items():
        assert collections.Counter(re.findall(r'\{[^}]+\}', en)) == collections.Counter(re.findall(r'\{[^}]+\}', ko)), (en, ko)
    decor = {int(line.split('\t', 1)[0]): line.split('\t', 1)[1] for line in (WORK / 'decor_unique.txt').read_text(encoding='utf-8').splitlines()}
    decor_ko = tsv_map(WORK / 'ko_decor.tsv')
    assert decor.keys() == decor_ko.keys()
    decor_map = {value: '[F0B232]장식[-] ' + decor_ko[key] for key, value in decor.items()}
    raw = (BASE / 'VanillaPlus/Config/Localization.csv').read_bytes()
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    canonical = []
    for row in rows:
        key, en = row['Key'], row['english']
        if key in official:
            ko, method = official[key]['koreana'], 'base_game_exact_english'
        elif en in decor_map:
            ko, method = decor_map[en], 'reviewed_decor'
        else:
            lines = []
            for line in en.split('\\n'):
                if not line:
                    lines.append('')
                    continue
                normal, numbers = normalize(line)
                lines.append(unit_map[normal].format(color='[F0B232]', endcolor='[-]', **numbers))
            ko, method = '\\n'.join(lines), 'reviewed_units'
        # 공식 번역의 화면용 약어를 풀고, 제작 목록의 개발 접두사를 + 표기로 통일한다.
        prior = ko
        ko = ko.replace('POI', '건물 배치용').replace('X-Ray 디스플레이 조명', '엑스레이 판독등').replace('IV 스탠드', '수액 걸이')
        if ko.startswith('USN '):
            ko = '+ ' + ko[4:]
        if key == 'USNdecoairConditionerairConditionVentFanDouble':
            ko = '[F0B232]장식[-] 이중 환기팬'
        if ko != prior:
            method += '_edited'
        canonical.append({'key': key, 'english': en, 'koreana': ko, 'method': method,
            'source_sha256': sha(en.encode('utf-8')), 'location': 'VanillaPlus/Config/Localization.csv/' + key + '/koreana'})
    (WORK / 'canonical_translation.json').write_text(json.dumps(canonical, ensure_ascii=False, indent=2), encoding='utf-8')
    # 소규모 시험: 쉼표·따옴표·실제 줄바꿈·색상·한글을 독립 CSV 파서로 재확인한다.
    sample = b'Key,english,koreana\r\na,"A, B",\r\nb,"Line\nTwo",\r\n'
    test_values = {'a': '[F0B232]한글[-], "따옴표"', 'b': '실제\n줄바꿈'}
    actual = list(csv.DictReader(io.StringIO(patch_csv(sample, test_values).decode('utf-8'))))
    assert {r['Key']: r['koreana'] for r in actual} == test_values
    assert actual[0]['english'] == 'A, B' and actual[1]['english'] == 'Line\nTwo'
    translated = patch_csv(raw, {r['key']: r['koreana'] for r in canonical})
    output = CANDIDATE / 'VanillaPlus/Config/Localization.csv'
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.read_bytes() != translated:
        archive = WORK / ('prior_' + sha(output.read_bytes())[:12] + '.csv')
        if not archive.exists():
            shutil.copy2(output, archive)
    output.write_bytes(translated)
    (WORK / 'build_result.json').write_text(json.dumps({'source_sha256': sha(raw), 'candidate_sha256': sha(translated),
        'entries': len(rows), 'method_counts': dict(collections.Counter(r['method'] for r in canonical)),
        'static_csv_smoke': 'PASS', 'runtime_smoke': 'NOT_RUN'}, indent=2), encoding='utf-8')
    print('번역 후보 생성:', len(rows), '항목', sha(translated))


if __name__ == '__main__':
    main()
