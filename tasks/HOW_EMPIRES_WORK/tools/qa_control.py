"""검수 사본의 공개된 게임 메서드를 호출하고 요청·화면 자료를 기록합니다."""
from common import *
import sys,time,datetime
label='baseline' if '--baseline' in sys.argv else 'candidate'
if '--baseline' in sys.argv:sys.argv.remove('--baseline')
q=WORK/'q/APPDATA'/label
action=sys.argv[1] if len(sys.argv)>1 else 'dump'
request={'action':action}
request['token']=datetime.datetime.now().isoformat()
if action=='capture':
    request.update(action='dump',capture=sys.argv[2])
if action=='call':
    request.update(node=sys.argv[2],method=sys.argv[3],args=json.loads(sys.argv[4]) if len(sys.argv)>4 else [])
if action=='hover':
    request.update(position=[float(sys.argv[2]),float(sys.argv[3])],capture=sys.argv[4])
path=q/'qa_request.json'
assert not path.exists(),'앞선 요청 처리 대기 중'
path.write_text(json.dumps(request,ensure_ascii=False),encoding='utf8')
limit=time.monotonic()+30
while path.exists() and time.monotonic()<limit:time.sleep(0.15)
assert not path.exists(),'검수 프로세스가 요청을 처리하지 않음'
state={}
while time.monotonic()<limit:
    try:state=read_json(q/'qa_state.json')
    except (OSError,ValueError):pass
    if state.get('request')==request:break
    time.sleep(0.15)
assert state.get('request')==request,'검수 결과가 요청과 일치하지 않음'
folder=WORK/'q/states';folder.mkdir(exist_ok=True)
stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
write_json(folder/(stamp+'.json'),state)
print(json.dumps({'request':request,'locale':state['locale'],'nodes':len(state['nodes'])},ensure_ascii=False))
