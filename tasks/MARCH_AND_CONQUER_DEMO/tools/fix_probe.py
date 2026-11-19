"""Unity 새 버전의 메타데이터를 원형 보존하여 시험판을 재구성합니다."""
from common import *
import subprocess
g=generator();run=WORK/'probe_003';game=run/'game';assert not game.exists()
shutil.copytree(BASE,game)
previous=WORK/'probe_001/game'
env=load(BASE/DATA/'sharedassets0.assets',g);patched=load(previous/DATA/'sharedassets0.assets',g)
for pid in (333,1415,1712):env.file.objects[pid].set_raw_data(patched.file.objects[pid].get_raw_data())
(game/DATA/'sharedassets0.assets').write_bytes(preserve_save(BASE/DATA/'sharedassets0.assets',env))
a=(BASE/DATA/'globalgamemanagers').read_bytes();assert a.count(b'PhilipMaxey')==1 and a.count(b'March and Conquer Demo')==1
company=b'KoreanQA003';product=b'MarchConquerQA_0000003'
assert len(company)==len(b'PhilipMaxey') and len(product)==len(b'March and Conquer Demo')
result=a.replace(b'PhilipMaxey',company).replace(b'March and Conquer Demo',product)
assert len(result)==len(a)
(game/DATA/'globalgamemanagers').write_bytes(result)
(game/DATA/'app.info').write_bytes(company+b'\r\n'+product+b'\r\n')
exe=game/'March and Conquer Demo.exe'
command=[str(exe),'-screen-fullscreen','0','-screen-width','1280','-screen-height','720','-logFile',str(run/'Player.log')]
p=subprocess.Popen(command,cwd=game)
save(run/'launch.json',dict(pid=p.pid,expected_executable=str(exe),command=command,time=datetime.datetime.now(datetime.timezone.utc).isoformat()))
print('PID',p.pid)
