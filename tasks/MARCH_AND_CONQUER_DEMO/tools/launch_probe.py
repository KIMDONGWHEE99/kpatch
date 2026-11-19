"""검수 대상 경로와 격리 설정을 확인한 다음 실제 그래픽으로 실행합니다."""
from common import *
import os, subprocess,winreg
run=WORK/'probe_001';game=run/'game';g=generator()
env=load(game/DATA/'sharedassets0.assets',g)
obj=env.file.objects[1712];tree=obj.read_typetree()
texts={'menu_new_game':'새 게임','menu_load_game':'불러오기','menu_options':'설정','options_title':'설정','options_exit_game':'게임 종료','options_close':'닫기'}
for e in tree['entries']:
    if e['key'] in texts:e['value']=texts[e['key']]
obj.save_typetree(tree)
obj=env.file.objects[1415];tree=obj.read_typetree()
for k in tree['m_FontFeatureTable']:tree['m_FontFeatureTable'][k]=[]
obj.save_typetree(tree);(game/DATA/'sharedassets0.assets').write_bytes(env.file.save())
def snapshot():
    folders=[Path(os.environ['USERPROFILE'])/'AppData/LocalLow/PhilipMaxey/March and Conquer Demo']
    userdata=Path('D:/steam/userdata')
    if userdata.exists():folders.extend(p/'5203110' for p in userdata.iterdir() if p.is_dir())
    files=[dict(path=str(p),size=p.stat().st_size,sha256=sha(p.read_bytes())) for d in folders if d.exists() for p in d.rglob('*') if p.is_file()]
    values=[]
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\PhilipMaxey\March and Conquer Demo') as key:
            for i in range(winreg.QueryInfoKey(key)[1]):
                n,v,t=winreg.EnumValue(key,i);values.append([n,v.hex() if isinstance(v,bytes) else v,t])
    except FileNotFoundError: pass
    return dict(files=files,registry=values)
save(run/'user_before.json',snapshot())
exe=game/'March and Conquer Demo.exe'
save(run/'launch_manifest.json',dict(files=[dict(path=p.relative_to(game).as_posix(),sha256=sha(p.read_bytes())) for p in game.rglob('*') if p.is_file()]))
command=[str(exe),'-screen-fullscreen','0','-screen-width','1280','-screen-height','720','-logFile',str(run/'Player.log')]
p=subprocess.Popen(command,cwd=game)
save(run/'launch.json',dict(pid=p.pid,expected_executable=str(exe),command=command,time=datetime.datetime.now(datetime.timezone.utc).isoformat()))
print('PID',p.pid)
