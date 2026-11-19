"""원본을 읽기 전용으로 조사하고 해시가 일치하는 사본을 보관합니다."""
from pathlib import Path
import hashlib, json, shutil, sys, datetime, collections
ROOT = Path(__file__).resolve().parents[3]
GAME = 'MARCH_AND_CONQUER_DEMO'
BASE = ROOT/'source_original'/GAME/'steam_25323013'
WORK = ROOT/'working_private'/GAME
EXTRACT = ROOT/'extracted_private'/GAME/'steam_25323013'
SOURCE = Path('D:/steam/steamapps/common/March and Conquer Demo')
DATA = 'March and Conquer Demo_Data'
def sha(data): return hashlib.sha256(data).hexdigest()
def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),encoding='utf-8')
if __name__ == '__main__':
    manifest=[]
    for p in sorted(SOURCE.rglob('*')):
        if not p.is_file(): continue
        rel=p.relative_to(SOURCE); data=p.read_bytes(); target=BASE/rel
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,target)
        assert sha(target.read_bytes())==sha(data),str(rel)
        manifest.append(dict(path=rel.as_posix(),size=len(data),sha256=sha(data)))
    save(WORK/'baseline.json',dict(game_id=GAME,build_id='steam_25323013',time=datetime.datetime.now(datetime.timezone.utc).isoformat(),files=manifest))
    print('원본',len(manifest),'파일',sum(r['size'] for r in manifest),'바이트, 사본 해시 일치')
