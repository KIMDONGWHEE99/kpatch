from pathlib import Path
import sys,json,hashlib,collections
sys.path.insert(0,str(Path('tasks/SPELLBOUND_SHELVED/tools').resolve()))
from pck_tools import read_pack
root=Path.cwd(); dst=root/'extracted_private/ALCHEMORTIS_DEMO/steam_25423154/raw'; work=root/'working_private/ALCHEMORTIS_DEMO/discovery'
data,base,directory,entries=read_pack(root/'source_original/ALCHEMORTIS_DEMO/steam_25423154/Alchemortis Demo.pck')
rows=[]
for e in entries:
 name=e['name'].removeprefix('res://'); assert '..' not in Path(name).parts
 p=dst/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(e['data'])
 rows.append(dict(path=e['name'],size=e['size'],sha256=hashlib.sha256(e['data']).hexdigest(),classification='UNKNOWN'))
(work/'pck_inventory.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print('PCK entries',len(entries),collections.Counter(Path(e['name']).suffix for e in entries))
print('\n'.join(e['name'] for e in entries if any(k in e['name'].lower() for k in ['localiz','translat','font','project.','language'])))
