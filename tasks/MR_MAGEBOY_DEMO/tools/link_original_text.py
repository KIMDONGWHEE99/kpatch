"""복원 문자열 위치를 원본 PCK 자산의 SHA-256에 연결한다."""
import argparse
import hashlib
import json
import re
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', required=True, type=Path)
    parser.add_argument('--raw', required=True, type=Path)
    parser.add_argument('--inventory', required=True, type=Path)
    args = parser.parse_args()
    inventory = {x['path']: x for x in json.loads(args.inventory.read_text(encoding='utf-8'))}
    records = json.loads((args.directory / 'census.json').read_text(encoding='utf-8'))
    mapping = {}
    errors = []
    for record in records:
        file = record['file']
        if record['kind'] == 'locale':
            locale = record['locale'] if record['locale'] != 'key' else 'en'
            original = str(Path(file).with_suffix(f'.{locale}.translation')).replace('\\', '/')
        elif file in mapping:
            original = mapping[file]
        else:
            remap = args.raw / (file + '.remap')
            if remap.exists():
                content = remap.read_text(encoding='utf-8-sig')
                match = re.search(r'path="res://([^"]+)"', content)
                original = match[1] if match else None
            elif file == 'project.godot':
                original = 'project.binary'
            else:
                original = file
            mapping[file] = original
        original_record = inventory.get(original)
        if original_record is None:
            errors.append({'file': file, 'original': original, 'id': record['id']})
            continue
        record['original_asset'] = original
        record['original_asset_sha256'] = original_record['sha256']
        record['original_asset_size'] = original_record['size']
    (args.directory / 'census.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.directory / 'original_link_errors.json').write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'linked': len(records) - len(errors), 'errors': len(errors), 'distinct_assets': len(set(x.get('original_asset') for x in records))}))

if __name__ == '__main__':
    main()
