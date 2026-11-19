import csv
import hashlib
import io
import json
import re
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
GAME = 'SEVENDAYS_VANILLAPLUS'
BASE = ROOT / 'source_original' / GAME / '1.6.0'
WORK = ROOT / 'working_private' / GAME / 'ko_0.1.0'
SOURCE = Path(r'C:/Users/PC/Downloads/VanillaPlus 11972 1.6.0 2026-08-31T14-21Z SmKjhdwLf.zip')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    BASE.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    archive = BASE / 'VanillaPlus_1.6.0.zip'
    if not archive.exists():
        shutil.copy2(SOURCE, archive)
    assert digest(archive.read_bytes()) == '0ecd9323c633fe75648c0a0dd606951b3860af4c80a15b2330172a38a2fe91bd'
    manifest = []
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for entry in z.infolist():
            target = (BASE / entry.filename).resolve()
            assert target.is_relative_to(BASE.resolve())
            data = z.read(entry)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                assert target.read_bytes() == data
            else:
                target.write_bytes(data)
            manifest.append({'path': entry.filename, 'size': len(data), 'sha256': digest(data)})
    vanilla = BASE / 'base_game_Localization.csv'
    if not vanilla.exists():
        shutil.copy2(Path('D:/steam/steamapps/common/7 Days To Die/Data/Config/Localization.csv'), vanilla)
    save_json(BASE / 'manifest.json', {'archive_sha256': digest(archive.read_bytes()), 'files': manifest,
        'base_localization_sha256': digest(vanilla.read_bytes()), 'steam_build_id': '24994517',
        'python_version': sys.version})
    with (BASE / 'VanillaPlus/Config/Localization.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    with vanilla.open(encoding='utf-8-sig', newline='') as f:
        original = {r['Key']: r for r in csv.DictReader(f) if r.get('Key')}
    english = {}
    for r in original.values():
        if r.get('english') and r.get('koreana'):
            english.setdefault(r['english'], set()).add(r['koreana'])
    matches, pending = {}, []
    for r in rows:
        key, en = r['Key'], r['english']
        bare, prefix = en, ''
        for label, translated in (('[F0B232]+[-] ', '[F0B232]+[-] '), ('[F0B232]Decor[-] ', '[F0B232]장식[-] '), ('+ ', '+ ')):
            if en.startswith(label):
                bare, prefix = en[len(label):], translated
                break
        ko = None
        source = None
        for k in (key.removeprefix('USN'), key.removeprefix('USNdeco')):
            if k in original and original[k].get('koreana') and original[k].get('english') == bare:
                ko, source = original[k]['koreana'], k
                break
        if ko is None and bare in english and len(english[bare]) == 1:
            ko, source = next(iter(english[bare])), 'unique_english_match'
        if ko is not None:
            matches[key] = {'english': en, 'koreana': prefix + ko, 'method': 'base_game', 'source': source}
        else:
            pending.append(r)
    save_json(WORK / 'official_matches.json', matches)
    save_json(WORK / 'pending.json', pending)
    (WORK / 'pending.tsv').write_text('\n'.join(f"{r['Key']}\t{r['english']}" for r in pending), encoding='utf-8')
    decor = list(dict.fromkeys(r['english'] for r in pending if r['english'].startswith('[F0B232]Decor[-] ')))
    (WORK / 'decor_unique.txt').write_text('\n'.join(f'{i}\t{value}' for i, value in enumerate(decor)), encoding='utf-8')
    units = {}
    for r in pending:
        if r['english'].startswith('[F0B232]Decor[-] '):
            continue
        for line in r['english'].split('\\n'):
            if not line:
                continue
            numbers = []
            def replace(match):
                numbers.append(match[0])
                return '{n' + str(len(numbers)-1) + '}'
            line = line.replace('[F0B232]', '{color}').replace('[-]', '{endcolor}')
            normal = re.sub(r'[+-]?\d+(?:\.\d+)?', replace, line)
            units.setdefault(normal, []).append(r['Key'])
    unit_rows = [{'id': i, 'english': en, 'count': len(keys), 'example_key': keys[0]} for i, (en, keys) in enumerate(units.items())]
    save_json(WORK / 'units.json', unit_rows)
    (WORK / 'units.txt').write_text('\n'.join(f"{r['id']}\t{r['english']}" for r in unit_rows), encoding='utf-8')
    windows = BASE / 'base_XUi_InGame_windows.xml'
    if not windows.exists():
        shutil.copy2(Path('D:/steam/steamapps/common/7 Days To Die/Data/Config/XUi_InGame/windows.xml'), windows)
    print(json.dumps({'entries': len(rows), 'official_matches': len(matches), 'pending': len(pending),
        'pending_unique_english': len(set(r['english'] for r in pending)),
        'work': str(WORK)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
