"""격리된 검수 사본에 명령을 전달하고 완료 기록을 확인합니다."""
from common import *
import sys,time

trial=WORK/sys.argv[1]
assert trial.parent==WORK and trial.name.startswith('qa_')
command=json.loads(sys.argv[2])
path=trial/'command.json'
previous=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'serial':0}
command['serial']=previous['serial']+1
temporary=trial/'command.pending.json'
save(temporary,command);temporary.replace(path)
done=trial/f"done_{command['serial']}.json"
deadline=time.monotonic()+180
while not done.exists():
    if time.monotonic()>deadline:raise TimeoutError(str(done))
    time.sleep(.15)
result=json.loads(done.read_text(encoding='utf-8'))
print(json.dumps(result,ensure_ascii=False))
assert result['status']=='PASS'
