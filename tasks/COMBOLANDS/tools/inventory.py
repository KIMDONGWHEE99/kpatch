"""원본 지문과 모든 객체·문자열·실패를 기록합니다."""
from common import *
from collections import Counter
import importlib.util

spec = importlib.util.spec_from_file_location('inventory_base', ROOT / 'tasks/SUPERREAP_DEMO/tools/inventory_unity_content.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

def main():
    installed = Path('D:/steam/steamapps/common/Combolands')
    records = []
    for p in sorted(SOURCE.rglob('*')):
        if p.is_file():
            rel = p.relative_to(SOURCE)
            row = dict(path=rel.as_posix(), size=p.stat().st_size, sha256=sha(p))
            assert row['sha256'] == sha(installed / rel), rel
            records.append(row)
    save_json(WORK / 'baseline.json', dict(game_id='COMBOLANDS', steam_build='24989173', files=records))
    g = generator()
    files = [base.inventory_file(p, DATA, g) for p in containers()]
    save_json(EXTRACT / 'inventory_fixed.json', dict(files=files))
    errors = [dict(file=f['relative_path'], **e) for f in files for e in f['errors']]
    save_json(EXTRACT / 'extraction_errors.json', errors)
    print(json.dumps(dict(files=len(records), strings=sum(len(f['strings']) for f in files), errors=errors), ensure_ascii=False))

if __name__ == '__main__':
    main()
