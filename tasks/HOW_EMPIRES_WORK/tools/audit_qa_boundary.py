"""배포 후보와 검수 사본의 차이 및 검수 코드의 실제 바이트코드를 확인합니다."""
from common import *
from pck_tools import read_pack,read_settings
import re,sys
sys.path.insert(0,str(ROOT/'tasks/MR_MAGEBOY_DEMO/tools'))
from census_text import tokens
candidate_id=sys.argv[1] if len(sys.argv)>1 else 'full_04'
Q=WORK/'q';stage=Q/('boundary_audit_'+candidate_id);stage.mkdir(exist_ok=True)
_,_,_,entries=read_pack(ROOT/'build_candidate'/GAME/candidate_id/PCK)
source={r['name']:r['data'] for r in entries};del entries
_,_,_,entries=read_pack(Q/'candidate'/PCK)
actual={r['name']:r['data'] for r in entries};del entries
differences={p:hashlib.sha256(b).hexdigest() for p,b in actual.items() if source.get(p)!=b}
expected=read_json(Q/'candidate_boundary.json')
assert differences==expected['changes'] and len(differences)==4
assert set(source)<=set(actual) and not any('qa_driver' in p for p in source)
old=read_settings(source['project.binary']);new=read_settings(actual['project.binary'])
settings={p:new[p] for p in new if old.get(p)!=new[p]}
assert set(settings)=={'application/config/name','application/config/use_custom_user_dir','application/config/custom_user_dir_name','display/window/size/mode','autoload/HEWQA','debug/file_logging/log_path'}
for name,path in [('steamworks','Platform/Steam/steamworks.gdc'),('qa_driver','KoreanPatch/qa_driver.gdc')]:
    (stage/(name+'.gdc')).write_bytes(actual[path])
run_gdre(['--decompile='+(stage/'*.gdc').as_posix(),'--bytecode=4.5.0','--output='+(stage/'decompiled').as_posix()],stage,'decompile')
def normalized(text):
    result=[];start=0
    for token in tokens(text,True):
        part=re.sub(r'#[^\n]*','',text[start:token['start']]);result.append(re.sub(r'\s+','',part));result.append(('string',token['value']));start=token['end']
    result.append(re.sub(r'\s+','',re.sub(r'#[^\n]*','',text[start:])))
    return result
for name in ['steamworks','qa_driver']:
    assert normalized((Q/'scripts'/(name+'.gd')).read_text(encoding='utf8'))==normalized((stage/'decompiled'/(name+'.gd')).read_text(encoding='utf8'))
for name in ['HowEmpiresWork.exe','libgodotsteam.windows.template_release.x86_64.dll','steam_api64.dll']:
    assert sha(Q/'candidate'/name)==sha(BASELINE/name)
write_json(stage/'report.json',{'status':'PASS','source_sha256':sha(ROOT/'build_candidate'/GAME/candidate_id/PCK),'qa_sha256':sha(Q/'candidate'/PCK),'changed_entries':differences,'project_fields':{k:hashlib.sha256(v).hexdigest() for k,v in settings.items()},'decompiled_scripts':2,'release_contains_qa_driver':False})
print('QA boundary PASS: 4 entries, 2 decompiled scripts')
