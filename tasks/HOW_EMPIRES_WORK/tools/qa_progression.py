"""자원 추가 명령 없이 실제 세금·모집 버튼을 눌러 진행을 검증합니다."""
from common import *
import time,sys
control=Path(__file__).with_name('qa_control.py')
userdata=WORK/'q/APPDATA/candidate'
stage=WORK/'progression_fix'
def command(*args):
    p=subprocess.run([sys.executable,'-X','utf8',str(control),*args],capture_output=True,timeout=45)
    assert p.returncode==0,p.stderr.decode('utf8')
    return read_json(userdata/'qa_state.json')
def press(identifier):
    deadline=time.monotonic()+35
    while True:
        state=command('dump')
        ready=any(c['command_id']==identifier and c.get('enabled') for c in state.get('capital_commands',[]))
        if ready:break
        assert time.monotonic()<deadline,identifier+' 버튼 준비 시간 초과'
        time.sleep(1)
    nodes=[n for n in state['nodes'] if n.get('command_id')==identifier and n.get('visible')]
    assert len(nodes)==1,(identifier,len(nodes))
    return command('call',nodes[0]['path'],'_on_command_button_pressed')
records=[]
for i in range(1,12):
    time.sleep(3.2)
    state=press('collect_taxes')
    state=command('capture','fix_tax_'+str(i))
    assert state['progress']['commands_executed'].get('collect_taxes')==i,(i,state['progress'])
    records.append({'tax_clicks':i,'money':state['money'],'progress':state['progress'],'military_enabled':state['systems']['military']['enabled'],'commands':state['capital_commands']})
    print('tax',i,'money',state['money'],'military',state['systems']['military']['enabled'],flush=True)
    if i==5:assert state['systems']['military']['enabled']
assert state['progress']['money_thresholds_step']==3
assert any(c['command_id']=='clear_bandits' for c in state['capital_commands'])
time.sleep(3.2)
state=press('recruit_soldiers_small')
state=command('capture','fix_first_recruit')
assert state['progress']['military_thresholds_step']>=1 and state['systems']['taxes']['enabled'],state['progress']
records.append({'action':'recruit_soldiers_small','progress':state['progress'],'systems':state['systems'],'money':state['money'],'military':state['military'],'commands':state['capital_commands']})
write_json(stage/'natural_progression.json',{'status':'PASS','candidate_sha256':read_json(WORK/'q/candidate_boundary.json')['source_sha256'],'records':records,'method':'새 게임에서 실제 세금 징수 및 전사 소집 UI 메서드. 자원 지급·기능 강제 해제 없음'})
print('NATURAL PROGRESSION PASS',flush=True)
