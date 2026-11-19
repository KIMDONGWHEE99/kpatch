from pathlib import Path
import hashlib,json,shutil,struct,collections
root=Path.cwd(); source=Path(r'D:\steam\steamapps\common\Alchemortis Demo'); dest=root/'source_original/ALCHEMORTIS_DEMO/steam_25423154'; work=root/'working_private/ALCHEMORTIS_DEMO/discovery'
rows=[]
for p in sorted(source.rglob('*')):
 if not p.is_file(): continue
 rel=p.relative_to(source); out=dest/rel; out.parent.mkdir(parents=True,exist_ok=True)
 original=hashlib.sha256(p.read_bytes()).hexdigest()
 if not out.exists(): shutil.copy2(p,out)
 assert hashlib.sha256(out.read_bytes()).hexdigest()==original
 rows.append(dict(path=rel.as_posix(),size=p.stat().st_size,sha256=original))
(work/'baseline_manifest.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
data=(dest/'Alchemortis Demo.pck').read_bytes()
print('Baseline',len(rows),sum(r['size'] for r in rows)); print('PCK header',data[:64].hex(),struct.unpack_from('<5I',data,0))
