"""사용자 저장 지문을 고정하고 분리된 그래픽 시험을 실행합니다."""
from common import *
import datetime

RISK = WORK/'risk_01'
qa = RISK/'qa_game'
roots = [Path(os.environ['APPDATA'])/'Godot/app_userdata/How Empires Work']
roots += [p/'4663730' for p in Path('D:/steam/userdata').iterdir() if p.is_dir()]
snapshot = {}
for root in roots:
    snapshot[str(root)] = {p.relative_to(root).as_posix():{'size':p.stat().st_size,'sha256':sha(p)}
                          for p in root.rglob('*') if p.is_file()} if root.exists() else None
write_json(RISK/'user_before.json',snapshot)
env = os.environ.copy()
for key in ('APPDATA','LOCALAPPDATA'):
    dest = RISK/'isolated_profile'/key
    dest.mkdir(parents=True,exist_ok=True)
    env[key] = str(dest)
userdata = Path(env['APPDATA'])/'Godot/app_userdata/HEW_KO_QA_RISK_01'
userdata.mkdir(parents=True,exist_ok=True)
(userdata/'settings.cfg').write_text('[general]\nlanguage="en"\n[audio]\nmaster_volume=0.0\n[graphics]\nresolution="1280x720"\nfullscreen=false\n',encoding='utf-8')
command = [str(qa/'HowEmpiresWork.exe'), '--windowed', '--resolution','1280x720', '--audio-driver','Dummy', '--log-file',str(RISK/'runtime.log')]
process = subprocess.Popen(command,cwd=qa,env=env,stdout=(RISK/'runtime.stdout.log').open('wb'),stderr=(RISK/'runtime.stderr.log').open('wb'))
write_json(RISK/'launch.json',{'pid':process.pid,'command':command,'started':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'exe_sha256':sha(qa/'HowEmpiresWork.exe'),'pck_sha256':sha(qa/PCK),'userdata':str(userdata)})
print('Launched QA PID',process.pid,flush=True)
exit_code = process.wait()
write_json(RISK/'exit.json',{'pid':process.pid,'exit_code':exit_code})
print('QA exit',exit_code,flush=True)
