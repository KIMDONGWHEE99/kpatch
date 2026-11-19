"""수정한 보조 글꼴의 예약 이름을 변경하고 윤곽과 문자 매핑 보존을 확인합니다."""
from common import *
from pck_tools import patch_pack
import sys,shutil
sys.path.insert(0,str(ROOT/'tools/python_deps'))
from fontTools.ttLib import TTFont

stage=WORK/'full_03';stage.mkdir(exist_ok=True)
src=WORK/'full_01/chinese.otf'
font=TTFont(src);before=font.getBestCmap().copy()
for record in font['name'].names:
    replacements={1:'HEW CJK Support',2:'Regular',3:'HEW-CJK-Support-1.0',4:'HEW CJK Support',6:'HEWCJKSupport',16:'HEW CJK Support',17:'Regular'}
    if record.nameID in replacements:record.string=replacements[record.nameID].encode(record.getEncoding())
if 'CFF ' in font:
    cff=font['CFF '].cff
    cff.fontNames=['HEWCJKSupport']
    cff.topDictIndex[0].FullName='HEW CJK Support'
    cff.topDictIndex[0].FamilyName='HEW CJK Support'
dest=stage/'chinese.otf';font.save(dest)
again=TTFont(dest)
assert again.getBestCmap()==before
assert not again['name'].getDebugName(1).startswith('Source')
for name in before.values():
    a=TTFont(src)['CFF '].cff.topDictIndex[0].CharStrings[name]
    b=again['CFF '].cff.topDictIndex[0].CharStrings[name]
    a.decompile();b.decompile();assert a.program==b.program
out=stage/'chinese.fontdata'
run_gdre(['--path',WORK/'full_01/resource_runtime','--script',ROOT/'tasks/HOW_EMPIRES_WORK/tools/export_font.gd','--',dest,out],stage,'font')
source=ROOT/'build_candidate'/GAME/'full_02';candidate=ROOT/'build_candidate'/GAME/'full_03'
assert not candidate.exists();candidate.mkdir()
for p in source.iterdir():
    if p.name!=PCK:shutil.copy2(p,candidate/p.name)
patch_pack(source/PCK,candidate/PCK,{'KoreanPatch/chinese.fontdata':out.read_bytes()})
manifest=read_json(WORK/'full_02/build.json')
manifest.update(candidate=str(candidate),sha256=sha(candidate/PCK),parent_candidate_sha256=manifest['sha256'],qa='NOT_RUN')
manifest['changes']['KoreanPatch/chinese.fontdata']=sha(out)
write_json(stage/'build.json',manifest)
write_json(stage/'font_adjustment.json',{'reason':'수정 글꼴에 Source 예약 이름을 사용하지 않도록 이름 변경','source_sha256':sha(src),'modified_sha256':sha(dest),'cmap_preserved':True,'outlines_preserved':True,'sha256':sha(out)})
print(manifest['sha256'])
