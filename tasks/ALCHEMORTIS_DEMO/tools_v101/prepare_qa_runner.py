"""검수 전용 코드의 변경 경계를 기록하고 새 사본을 준비한다."""
from pck_tools import ROOT,WORK,patch_pack,patch_settings,read_pack
import json,shutil,subprocess,hashlib,sys
revision=sys.argv[1] if len(sys.argv)>1 else '03'
qa_revision=sys.argv[2] if len(sys.argv)>2 else '04'
assert revision.isdigit() and qa_revision.isdigit()
candidate=ROOT/('build_candidate/ALCHEMORTIS_DEMO/ko_1.0.1_c'+revision)
trial=WORK/('qa_'+qa_revision);game=trial/'game'
assert not (trial/'launch.json').exists()
shutil.copytree(candidate,game,dirs_exist_ok=True)
(trial/'user').mkdir(exist_ok=True)
old_options=WORK.parent/'qa_02/user/options.sav'
if old_options.exists():shutil.copy2(old_options,trial/'user/options.sav')
tool=WORK/'toolchain/AssemblyTool/AssemblyTool.dll'
dll='data_Alchemortis_windows_x86_64/Alchemortis.dll'
helper=WORK/'toolchain/QaRunner/QaRunner.dll'
subprocess.run(['dotnet',str(tool),'qa',str(candidate/dll),str(game/dll)],check=True)
temporary=game/'data_Alchemortis_windows_x86_64/Alchemortis.qa.tmp.dll'
subprocess.run(['dotnet',str(tool),'qa_runner',str(game/dll),str(temporary),str(helper)],check=True)
temporary.replace(game/dll)
shutil.copy2(helper,game/'data_Alchemortis_windows_x86_64/QaRunner.dll')
deps=game/'data_Alchemortis_windows_x86_64/Alchemortis.deps.json'
data=json.loads(deps.read_text(encoding='utf-8'))
for target in data['targets'].values():
    if 'Alchemortis/1.0.0' not in target:continue
    target['Alchemortis/1.0.0']['dependencies']['QaRunner']='1.0.0'
    target['QaRunner/1.0.0']={'runtime':{'QaRunner.dll':{}}}
data['libraries']['QaRunner/1.0.0']={'type':'project','serviceable':False,'sha512':''}
deps.write_text(json.dumps(data,indent=2),encoding='utf-8')
qa=json.loads((WORK.parent/'qa_02/qa_settings.json').read_text(encoding='utf-8'))
qa={key:value.replace(WORK.parent.as_posix(),WORK.as_posix()).replace('/qa_02/','/qa_'+qa_revision+'/').replace('/qa_02','/qa_'+qa_revision) if isinstance(value,str) else value for key,value in qa.items()}
qa['korean_qa/candidate']=candidate.name
settings=next(e['data'] for e in read_pack(candidate/'Alchemortis Demo.pck')[3] if e['name']=='project.binary')
patch_pack(candidate/'Alchemortis Demo.pck',game/'Alchemortis Demo.pck',{'project.binary':patch_settings(settings,qa),'korean_qa_observer.gd':(ROOT/'tasks/ALCHEMORTIS_DEMO/tools_v101/qa_observer.gd').read_bytes()})
changed=[]
for path in game.rglob('*'):
    if not path.is_file():continue
    relative=path.relative_to(game);source=candidate/relative
    if not source.exists() or path.read_bytes()!=source.read_bytes():changed.append({'path':relative.as_posix(),'candidate_sha256':hashlib.sha256(source.read_bytes()).hexdigest() if source.exists() else None,'qa_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(trial/'qa_boundary.json').write_text(json.dumps({'candidate':candidate.name,'changes':changed,'methods':['SentryAutoInit::Init -> ret','SteamService::UnlockAchievement -> ret','SteamService::OpenWebOverlay -> ret','VisualUtilities::_Ready -> 검수 도구 Start 호출 추가'],'project_settings':qa,'extra_assembly':'QaRunner.dll; 격리 사본에만 포함'},ensure_ascii=False,indent=2),encoding='utf-8')
print('검수 전용 사본 준비 완료')
