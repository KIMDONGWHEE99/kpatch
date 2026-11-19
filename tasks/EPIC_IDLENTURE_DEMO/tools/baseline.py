"""설치본을 읽기 전용으로 조사하고 원본 사본을 고정합니다."""
from pathlib import Path
import sys,json,hashlib,shutil,collections
ROOT=Path(__file__).resolve().parents[3]
TARGET=Path(r'D:\steam\steamapps\common\Epic Idlenture Demo')
BASE=ROOT/'source_original/EPIC_IDLENTURE_DEMO/steam_23762546'
EXTRACT=ROOT/'extracted_private/EPIC_IDLENTURE_DEMO/steam_23762546'
WORK=ROOT/'working_private/EPIC_IDLENTURE_DEMO'
DATA='Epic Idlenture_Data'
def sha(data):return hashlib.sha256(data).hexdigest()
def save(path,value):
    path.parent.mkdir(exist_ok=True,parents=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':
    assert not BASE.exists()
    before=[dict(path=p.relative_to(TARGET).as_posix(),size=p.stat().st_size,sha256=sha(p.read_bytes())) for p in sorted(TARGET.rglob('*')) if p.is_file()]
    shutil.copytree(TARGET,BASE)
    for row in before:assert sha((BASE/row['path']).read_bytes())==row['sha256']==sha((TARGET/row['path']).read_bytes())
    save(WORK/'baseline.json',before)
    shutil.copy2(r'D:\steam\steamapps\appmanifest_4114020.acf',WORK/'appmanifest.acf')
    print('원본 사본 검증',len(before),sum(x['size'] for x in before),sha((WORK/'baseline.json').read_bytes()))
