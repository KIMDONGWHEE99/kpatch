"""실행 검수에서 확인한 주 이름 접두어의 띄어쓰기를 보완합니다."""
from common import *
from pck_tools import patch_pack
import shutil
stage=WORK/'full_04';stage.mkdir(exist_ok=True)
rows=read_json(WORK/'translation/canonical.json')
row=next(r for r in rows if r['key']=='PROVINCE_INITIAL')
assert row['target']=='주'
row['target']='주: '
write_json(WORK/'translation/canonical.json',rows)
table=WORK/'translation/world_system.tsv'
text=table.read_text(encoding='utf8')
assert text.count('PROVINCE_INITIAL\t주\n')==1
table.write_text(text.replace('PROVINCE_INITIAL\t주\n','PROVINCE_INITIAL\t주: \n'),encoding='utf8')
path=row['file'].replace('.en.translation','.ko.translation')
source=ROOT/'build_candidate'/GAME/'full_03';dest=ROOT/'build_candidate'/GAME/'full_04'
assert not dest.exists();dest.mkdir()
out=stage/'province.ko.translation'
run_gdre(['--path',WORK/'full_01/resource_runtime','--script',Path(__file__).with_suffix('.gd'),'--',source/PCK,path,out],stage,'revise_label')
for p in source.iterdir():
    if p.name!=PCK:shutil.copy2(p,dest/p.name)
patch_pack(source/PCK,dest/PCK,{path:out.read_bytes()})
manifest=read_json(WORK/'full_03/build.json')
manifest.update(candidate=str(dest),sha256=sha(dest/PCK),parent_candidate_sha256=manifest['sha256'],qa='NOT_RUN')
manifest['changes'][path]=sha(out)
write_json(stage/'build.json',manifest)
write_json(stage/'label_adjustment.json',{'id':row['id'],'path':path,'previous':'주','target':'주: ','reason':'자동 생성 주 이름과 지명 사이 경계 표시','source_sha256':row['source_sha256']})
print(manifest['sha256'])
