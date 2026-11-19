"""고장 난 초기 저장 사본의 누락 기능만 복구하고 실제 게임에서 다시 읽습니다."""
from common import *
import copy,shutil,time,sys
stage=WORK/'progression_fix'
proof=read_json(stage/'natural_progression.json')
assert proof['status']=='PASS'
natural=next(r for r in proof['records'] if r.get('tax_clicks')==11)
templates={c['command_id']:c for c in natural['commands']}
control=Path(__file__).with_name('qa_control.py')
userdata=WORK/'q/APPDATA/candidate'
ready=stage/'repaired';ready.mkdir(exist_ok=True)
runtime=stage/'runtime_saves';runtime.mkdir(exist_ok=True)
def command(*args):
    result=subprocess.run([sys.executable,'-X','utf8',str(control),*args],capture_output=True,timeout=45)
    assert result.returncode==0,result.stderr.decode('utf8')
    return read_json(userdata/'qa_state.json')
def diff(a,b,path=''):
    if isinstance(a,dict) and isinstance(b,dict):
        return sum((diff(a.get(k),b.get(k),path+'/'+str(k)) for k in set(a)|set(b)),[])
    if isinstance(a,list) and isinstance(b,list) and len(a)==len(b):
        return sum((diff(x,y,path+'/'+str(i)) for i,(x,y) in enumerate(zip(a,b))),[])
    return [] if a==b else [path]
records=[]
for row in read_json(stage/'user_snapshot.json'):
    before=read_json(Path(row['backup']));after=copy.deepcopy(before)
    assert sha(Path(row['backup']))==row['sha256']
    assert after['progress']['money_thresholds_step']==3
    assert all(after['progress'][key]==0 for key in ['military_thresholds_step','military_spent_thresholds_step','controlled_areas_thresholds_step'])
    assert after['systems']['military']=={'enabled':False,'unlock_flags':[]}
    assert after['player']['country']['values']['cfloats']['money']['value']>=0.1
    capital=after['player']['country']['capital_area_id']
    index=next(i for i,a in enumerate(after['geography']['areas']) if a['area_id']==capital)
    commands=after['geography']['areas'][index]['commands']
    assert not any(c['command_id'] in ['recruit_soldiers_small','recruit_soldiers','clear_bandits'] for c in commands)
    for identifier in ['recruit_soldiers_small','clear_bandits']:
        commands.append(copy.deepcopy(templates[identifier]))
    after['systems']['military']={'enabled':True,'unlock_flags':['journey_destination_selection']}
    changes=diff(before,after)
    assert set(changes)=={'/systems/military/enabled','/systems/military/unlock_flags',f'/geography/areas/{index}/commands'},changes
    name=Path(row['path']).name
    write_json(ready/name,after)
    shutil.copy2(ready/name,runtime/name)
    records.append({**row,'repaired':str(ready/name),'repaired_sha256':sha(ready/name),'changed_fields':changes,'money':after['player']['country']['values']['cfloats']['money']['value'],'save_name':after['metadata']['save_name']})
write_json(stage/'save_repair_plan.json',{'status':'READY_FOR_RUNTIME','records':records,'source':'정상 새 게임에서 얻은 명령 상태; 보유 자금·경과 시간·명령 횟수·진행 단계·기타 자료 원형 보존'})
state=command('dump')
save_node=next(n['path'] for n in state['nodes'] if n.get('script','').endswith('/save_manager.gd'))
command('call',save_node,'set_saves_dir_for_tests',json.dumps([runtime.as_posix()+'/']))
manager='/root/Main/Game/Managers/ConsoleCommandsManager'
for i,row in enumerate(records):
    before_paths={n['path'] for n in command('dump')['nodes'] if n.get('command_id')=='collect_taxes'}
    command('call',manager,'console_load_named',json.dumps([row['save_name']],ensure_ascii=False))
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        time.sleep(2)
        state=command('dump')
        paths={n['path'] for n in state['nodes'] if n.get('command_id')=='collect_taxes'}
        if paths and paths!=before_paths and abs(state.get('money',-1)-row['money'])<1e-8:break
    state=command('capture','fix_repaired_'+str(i))
    assert abs(state['money']-row['money'])<1e-8,(row['save_name'],state['money'])
    assert state['systems']['military']['enabled']
    assert {'recruit_soldiers_small','clear_bandits'} <= {c['command_id'] for c in state['capital_commands']}
    row['runtime_load']='PASS'
    print('restored save load',i,'money',state['money'],'PASS',flush=True)
# 마지막 저장에서 정상 비용 지불·모집 후 다음 기능이 열리는지 확인합니다.
recruit=next(n['path'] for n in state['nodes'] if n.get('command_id')=='recruit_soldiers_small' and n.get('visible'))
command('call',recruit,'_on_command_button_pressed')
time.sleep(3)
state=command('capture','fix_repaired_recruit')
assert state['systems']['taxes']['enabled'] and state['military']>=1
command('call',manager,'console_save_named',json.dumps(['복구 검수 왕복']))
command('call',manager,'console_load_named',json.dumps(['복구 검수 왕복']))
time.sleep(8)
state=command('capture','fix_repaired_roundtrip')
assert state['systems']['taxes']['enabled'] and state['military']>=1
write_json(stage/'save_repair_plan.json',{'status':'PASS','candidate_sha256':read_json(WORK/'q/candidate_boundary.json')['source_sha256'],'template_proof_candidate_sha256':proof['candidate_sha256'],'records':records,'next_military_threshold':'PASS','save_reload_after_progress':'PASS','source':'정상 새 게임 명령 상태; 보유 자금·경과 시간·명령 횟수·진행 단계·기타 자료 원형 보존','user_files_modified':False})
print('SAVE REPAIR QA PASS',flush=True)
