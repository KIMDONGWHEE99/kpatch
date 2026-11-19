from pathlib import Path
import sys,json,hashlib,shutil,collections
ROOT=Path.cwd()
TARGET=Path(r'D:\steam\steamapps\common\Silky Rails')
BASE=ROOT/'source_original/SILKY_RAILS/steam_original'
EXTRACT=ROOT/'extracted_private/SILKY_RAILS'
WORK=ROOT/'working_private/SILKY_RAILS'
DATA='Silky Rails_Data'
def sha(data):return hashlib.sha256(data).hexdigest()
def save(path,value):
 path.parent.mkdir(exist_ok=True,parents=True);path.write_text(json.dumps(value,ensure_ascii=True,indent=2),encoding='utf-8')
if __name__=='__main__':
 assert not BASE.exists()
 shutil.copytree(TARGET,BASE)
 files=[dict(path=p.relative_to(BASE).as_posix(),size=p.stat().st_size,sha256=sha(p.read_bytes())) for p in sorted(BASE.rglob('*')) if p.is_file()]
 save(WORK/'baseline.json',files)
 shutil.copy2(r'D:\steam\steamapps\appmanifest_3870990.acf',WORK/'appmanifest.acf')
 print(len(files),sum(x['size'] for x in files))

