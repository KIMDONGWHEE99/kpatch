"""검수 사본의 저장·로그 경로와 프로세스를 기록하고 실행한다."""
from pathlib import Path
import os,subprocess,json,hashlib,time,sys
from pck_tools import WORK

trial=WORK/(sys.argv[1] if len(sys.argv)>1 else 'risk_01'); game=trial/'game';env=os.environ.copy()
assert trial.parent==WORK and game.is_dir()
save_roots=[Path(os.environ['APPDATA'])/'Alchemortis Demo']
save_roots += list(Path('D:/steam/userdata').glob('*/4974580'))
save_state=[]
for root in save_roots:
    save_state.append({'path':str(root),'exists':root.exists(),'files':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in root.rglob('*') if p.is_file()] if root.exists() else []})
(trial/'user_save_before.json').write_text(json.dumps(save_state,ensure_ascii=False,indent=2),encoding='utf-8')
for key,folder in [('APPDATA','roaming'),('LOCALAPPDATA','local'),('TEMP','temp'),('TMP','temp')]:
    d=trial/folder;d.mkdir(exist_ok=True);env[key]=str(d)
env['DOTNET_CLI_TELEMETRY_OPTOUT']='1'
cmd=[str(game/'Alchemortis Demo.exe'),'--windowed','--resolution','1280x720','--position','80,80']
p=subprocess.Popen(cmd,cwd=game,env=env,stdout=(trial/'stdout.log').open('wb'),stderr=(trial/'stderr.log').open('wb'))
(trial/'launch.json').write_text(json.dumps({'pid':p.pid,'command':cmd,'time':time.time(),'exe_sha256':hashlib.sha256(Path(cmd[0]).read_bytes()).hexdigest(),'pck_sha256':hashlib.sha256((game/'Alchemortis Demo.pck').read_bytes()).hexdigest()},ensure_ascii=False,indent=2),encoding='utf-8')
print(p.pid)
