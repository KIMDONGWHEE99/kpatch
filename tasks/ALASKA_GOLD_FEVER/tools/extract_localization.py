"""작업 사본의 번역표를 위치와 원문 지문에 연결해 추출합니다."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/python_deps'))
import UnityPy

BASE = ROOT / 'source_original/ALASKA_GOLD_FEVER/25782395/game'
OUT = ROOT / 'extracted_private/ALASKA_GOLD_FEVER/25782395/localization'
BUNDLES = BASE / 'Alaska Gold Fever_Data/StreamingAssets/aa/StandaloneWindows64'

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def main():
    tables, shared, failures, inventory = [], {}, [], []
    for path in sorted(BUNDLES.glob('localization*.bundle')):
        env = UnityPy.load(str(path))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        objects = []
        for obj in env.objects:
            record = {'path_id': obj.path_id, 'type': obj.type.name, 'size': obj.byte_size}
            if obj.type.name == 'MonoBehaviour':
                try:
                    tree = obj.read_typetree()
                    record['name'] = tree.get('m_Name')
                    if 'm_TableData' in tree:
                        item = {'bundle': path.name, 'sha256': digest, 'asset': obj.assets_file.name,
                                'path_id': obj.path_id, 'tree': tree}
                        tables.append(item)
                        record['rows'] = len(tree['m_TableData'])
                    if 'm_Entries' in tree and 'm_TableCollectionName' in tree:
                        shared[str(tree['m_TableCollectionName'])] = {
                            'bundle': path.name, 'sha256': digest, 'path_id': obj.path_id, 'tree': tree}
                except Exception as exc:
                    failures.append({'bundle': path.name, 'sha256': digest, 'path_id': obj.path_id,
                                     'status': 'UNKNOWN', 'error': str(exc)})
            objects.append(record)
        inventory.append({'bundle': path.name, 'sha256': digest, 'objects': objects})
    save(OUT / 'tables.json', tables)
    save(OUT / 'shared.json', shared)
    save(OUT / 'bundle_inventory.json', inventory)
    save(OUT / 'errors.json', failures)
    print(json.dumps({'tables': [{'bundle': t['bundle'], 'name': t['tree']['m_Name'],
                      'locale': t['tree'].get('m_LocaleId'), 'rows': len(t['tree']['m_TableData'])}
                      for t in tables if any(k in t['bundle'] for k in ('english','korean'))],
                      'shared': list(shared), 'errors': failures}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
