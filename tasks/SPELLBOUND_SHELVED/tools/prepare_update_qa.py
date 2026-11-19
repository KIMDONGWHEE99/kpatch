"""GPU 검수와 원본 경고 비교를 위한 격리 사본을 준비한다."""
import shutil
from update_25274913 import ROOT,WORK,BASELINE,CANDIDATE,write,sha
from pck_tools import read_pack,patch_pack,patch_settings

for name,source in [('qa',CANDIDATE),('baseline_qa',BASELINE)]:
    target=WORK/name;target.mkdir(exist_ok=True)
    shutil.copy2(source/'windows/SpellboundShelved.exe',target/'SpellboundShelved.exe')
    raw={e['name']:e['data'] for e in read_pack(source/'windows/SpellboundShelved.pck')[3]}
    properties={'application/config/name':'SBS_KO_QA_25274913'+('_BASELINE' if name=='baseline_qa' else ''),
        'debug/file_logging/log_path':(target/'runtime.log').as_posix()}
    changes={'.godot/extension_list.cfg':b''}
    if name=='qa':
        properties['autoload/KoreanQA']='*res://qa_update_hook.gd'
        changes['qa_update_hook.gd']=(ROOT/'tasks/SPELLBOUND_SHELVED/tools/qa_update_hook.gd').read_bytes()
    changes['project.binary']=patch_settings(raw['project.binary'],properties)
    patch_pack(source/'windows/SpellboundShelved.pck',target/'SpellboundShelved.pck',changes)
    write(target/'allowed_changes.json',{'source_pck_sha256':sha(source/'windows/SpellboundShelved.pck'),'qa_pck_sha256':sha(target/'SpellboundShelved.pck'),
        'resources':{k:__import__('hashlib').sha256(v).hexdigest() for k,v in changes.items()},'project_properties':properties})
    (target/'scenario.txt').write_text('',encoding='utf-8')
(WORK/'screens').mkdir(exist_ok=True)
print('검수 및 원본 비교 사본 준비 완료')
