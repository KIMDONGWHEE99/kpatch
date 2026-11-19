"""Steam·사용자 저장을 격리하고 검수용 코드의 차이만 기록합니다."""
from common import *
from pck_tools import patch_pack,patch_settings,read_pack
import shutil,sys
B=WORK/'full_01';Q=WORK/'q';Q.mkdir(exist_ok=True)
baseline='--baseline' in sys.argv
candidate_id=next((a.split('=',1)[1] for a in sys.argv[1:] if a.startswith('--candidate=')),'full_01')
source=BASELINE if baseline else ROOT/'build_candidate'/GAME/candidate_id
label='baseline' if baseline else 'candidate'
qa=Q/label;qa.mkdir(exist_ok=True)
for p in source.iterdir():
    if p.name!=PCK:shutil.copy2(p,qa/p.name)
steam=(RECOVERED/'Platform/Steam/steamworks.gd').read_text(encoding='utf8')
marker='func initialize_steam() -> void :\n'
assert steam.count(marker)==1
steam=steam.replace(marker,marker+'\tprint("HEW QA: Steam disabled")\n\treturn\n')
scripts=Q/'scripts';scripts.mkdir(exist_ok=True)
(scripts/'steamworks.gd').write_text(steam,encoding='utf8')
shutil.copy2(ROOT/'tasks/HOW_EMPIRES_WORK/tools/qa_driver.gd',scripts/'qa_driver.gd')
run_gdre(['--compile='+(scripts/'*.gd').as_posix(),'--bytecode=4.5.0','--output='+(Q/'compiled').as_posix()],Q,'compile')
_,_,_,entries=read_pack(source/PCK)
settings=next(e['data'] for e in entries if e['name']=='project.binary')
changes={'Platform/Steam/steamworks.gdc':(Q/'compiled/steamworks.gdc').read_bytes(),
    'KoreanPatch/qa_driver.gdc':(Q/'compiled/qa_driver.gdc').read_bytes(),
    'KoreanPatch/qa_driver.gd.remap':b'[remap]\n\npath="res://KoreanPatch/qa_driver.gdc"\n',
    'project.binary':patch_settings(settings,{'application/config/name':'HEW QA '+label,
      'application/config/use_custom_user_dir':True,'application/config/custom_user_dir_name':label,
      'display/window/size/mode':0,'autoload/HEWQA':'*res://KoreanPatch/qa_driver.gd',
      'debug/file_logging/log_path':(Q/(label+'.log')).as_posix()})}
patch_pack(source/PCK,qa/PCK,changes)
write_json(Q/(label+'_boundary.json'),{'source_sha256':sha(source/PCK),'qa_sha256':sha(qa/PCK),'changes':{k:hashlib.sha256(v).hexdigest() for k,v in changes.items()},'qa_only':['steamworks.initialize_steam early return','HEWQA inspection driver','project: app name, custom user dir, window mode, log path, autoload']})
print(label,'QA ready',sha(qa/PCK))
