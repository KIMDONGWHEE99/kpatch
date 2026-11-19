"""실제 그래픽 장치에서 검수 사본을 실행하고 사용자 저장 지문을 비교합니다."""
from common import *
import datetime,sys
Q=WORK/'q';label='baseline' if '--baseline' in sys.argv else 'candidate'
qa=Q/label
roots=[Path('C:/Users/PC/AppData/Roaming/Godot/app_userdata/How Empires Work')]
roots += [p/'4663730' for p in Path('D:/steam/userdata').iterdir() if p.is_dir()]
def snapshot():
    return {str(root):{p.relative_to(root).as_posix():{'size':p.stat().st_size,'sha256':sha(p)} for p in root.rglob('*') if p.is_file()} if root.exists() else None for root in roots}
before=snapshot();write_json(Q/(label+'_user_before.json'),before)
env=os.environ.copy()
for key in ('APPDATA','LOCALAPPDATA'):
    dest=Q/key;dest.mkdir(exist_ok=True);env[key]=str(dest)
userdata=Q/'APPDATA'/label;userdata.mkdir(parents=True,exist_ok=True)
if not (userdata/'settings.cfg').exists():
    (userdata/'settings.cfg').write_text('[general]\nlanguage="'+('en' if label=='baseline' else 'ko')+'"\n[audio]\nmaster_volume=0.0\n[graphics]\nresolution="1280x720"\nfullscreen=false\n',encoding='utf8')
(userdata/'qa_request.json').write_text('{"action":"dump"}',encoding='utf8')
command=[str(qa/'HowEmpiresWork.exe'),'--windowed','--resolution','1280x720','--audio-driver','Dummy','--log-file',str(Q/(label+'.log'))]
startup=subprocess.STARTUPINFO()
startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow = 4
process=subprocess.Popen(command,cwd=qa,env=env,startupinfo=startup,stdout=(Q/(label+'.stdout.log')).open('wb'),stderr=(Q/(label+'.stderr.log')).open('wb'))
write_json(Q/(label+'_launch.json'),{'pid':process.pid,'command':command,'started':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exe_sha256':sha(qa/'HowEmpiresWork.exe'),'pck_sha256':sha(qa/PCK),'userdata':str(userdata)})
print('QA PID',process.pid,flush=True)
code=process.wait();after=snapshot()
write_json(Q/(label+'_user_after.json'),after)
write_json(Q/(label+'_exit.json'),{'pid':process.pid,'exit_code':code,'user_saves_unchanged':before==after})
print('QA exit',code,'user saves unchanged',before==after,flush=True)
assert before==after
