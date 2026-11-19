"""검증 후보를 복제하고 저장·Steam·통계 전송만 격리합니다."""
from common import *
from build_candidate import CANDIDATE,REPORT,read_tree,differences
from native_support import method_address
import json,struct,shutil,copy

QA=WORK/'qa_c04/game'
assert not (QA.parent/'isolation.json').exists()
shutil.copytree(CANDIDATE,QA,dirs_exist_ok=True)
overrides=[];gen=generator();configure_references(gen)
path=QA/'The Loopler_Data/data.unity3d';env=UnityPy.load(str(path));env.typetree_generator=gen
for obj in env.objects:
    if obj.type.name not in ('PlayerSettings','UnityConnectSettings'):continue
    before=read_tree(obj);after=copy.deepcopy(before)
    if obj.type.name=='PlayerSettings':after['productName']='LooplerKQA5'
    else:
        after['m_Enabled']=False;after['InsightsSettings']['m_EngineDiagnosticsEnabled']=False
        after['UnityAnalyticsSettings']['m_Enabled']=False;after['UnityAnalyticsSettings']['m_InitializeOnStartup']=False
    for field,b,a in differences(before,after):overrides.append({'asset':obj.assets_file.name,'path_id':obj.path_id,'field':field,'before':b,'after':a})
    obj.save_typetree(after)
path.write_bytes(env.file.save(packer='lz4'))
binary=bytearray((QA/'GameAssembly.dll').read_bytes())
def patch(cls,name,code):
    info=method_address(cls,name);p=info['Offset'];before=bytes(binary[p:p+len(code)])
    binary[p:p+len(code)]=code;overrides.append({'method':cls+'.'+name,'rva':info['RVA'],'offset':p,'before':before.hex(),'after':code.hex()})
patch('SteamManager','Awake',b'\xc3');patch('SteamManager','get_Initialized',b'\x31\xc0\xc3')
for name in ('Bootstrap','InitializeAnalytics','RequestDataCollectionEnabled'):patch('RunAnalyticsReporter',name,b'\xc3')
src=method_address('UnityEngine.Application','get_persistentDataPath');dst=method_address('UnityEngine.Application','get_dataPath')
patch('UnityEngine.Application','get_persistentDataPath',b'\xe9'+struct.pack('<i',dst['RVA']-src['RVA']-5))
(QA/'GameAssembly.dll').write_bytes(binary)
options=json.loads((WORK/'risk_probe/game/The Loopler_Data/Options.json').read_text('utf-8'))
options.update({'languageCode':'ko','tutorial':True,'analyticsOptIn':False,'masterVol':0.0,'fullscreen':False})
write_json(QA/'The Loopler_Data/Options.json',options)
manifest=[]
for p in sorted(CANDIDATE.rglob('*')):
    if p.is_file():manifest.append({'path':p.relative_to(CANDIDATE).as_posix(),'candidate_sha256':sha(p),'qa_sha256':sha(QA/p.relative_to(CANDIDATE))})
write_json(QA.parent/'isolation.json',{'overrides':overrides,'files':manifest,'candidate_build_sha256':sha(REPORT/'build.json'),'persistent_data_path':'검수 사본의 The Loopler_Data','product_name':'LooplerKQA5','steam':'초기화·업적·클라우드 연결 차단','analytics':'게임 및 Unity 엔진 자동 초기화 차단'})
print('qa prepared',len(manifest),'files',len(overrides),'overrides')
