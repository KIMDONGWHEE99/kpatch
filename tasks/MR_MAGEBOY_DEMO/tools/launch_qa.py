"""사용자 자료 지문과 격리된 검수 프로세스를 기록합니다."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time
from pck_tools import ROOT, WORK

def snapshot():
    roots = [Path(os.environ['APPDATA'])/'Godot/app_userdata/MR MAGEBOY DEMO',
             Path(os.environ['APPDATA'])/'MR MAGEBOY DEMO']
    roots += list(Path('D:/steam/userdata').glob('*/5310040'))
    roots += list(Path('D:/steam/userdata').glob('*/4483400'))
    return [{'root':str(root),'exists':root.exists(),'files':[{'path':p.relative_to(root).as_posix(),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(root.rglob('*')) if p.is_file()] if root.exists() else []} for root in roots]

trial=WORK/sys.argv[1]
assert trial.resolve().parent == WORK.resolve()
if len(sys.argv)>2 and sys.argv[2]=='audit':
    before=json.loads((trial/'user_save_before.json').read_text(encoding='utf-8'))
    after=snapshot()
    (trial/'user_save_after.json').write_text(json.dumps(after,ensure_ascii=False,indent=2),encoding='utf-8')
    assert before==after, '사용자 저장 자료가 달라졌습니다.'
    print('USER_SAVE_PASS')
    sys.exit()
game=trial/'qa_game'
assert game.is_dir()
(trial/'user_save_before.json').write_text(json.dumps(snapshot(),ensure_ascii=False,indent=2),encoding='utf-8')
env=os.environ.copy()
for variable,folder in [('APPDATA','roaming'),('LOCALAPPDATA','local'),('TEMP','temp'),('TMP','temp')]:
    destination=trial/folder
    destination.mkdir(exist_ok=True)
    env[variable]=str(destination)
command=[str(game/'MR MAGEBOY DEMO.exe'),'--windowed','--resolution','1440x720','--position','40,60','--log-file',str(trial/'runtime.log')]
process=subprocess.Popen(command,cwd=game,env=env,stdout=(trial/'stdout.log').open('wb'),stderr=(trial/'stderr.log').open('wb'))
record={'pid':process.pid,'command':command,'time':time.time(),'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in game.iterdir() if p.is_file()},'environment':{k:env[k] for k in ['APPDATA','LOCALAPPDATA','TEMP','TMP']}}
(trial/'launch.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'pid':process.pid,'path':command[0]},ensure_ascii=False))
