"""실제 사용자 계정으로 실행하여 저장·설정 상태를 읽기 전용 기록합니다."""
from baseline import *
import os,winreg
folders=[Path('C:/Users/PC/AppData/LocalLow/PhilipMaxey/March and Conquer Demo')]
userdata=Path('D:/steam/userdata')
if userdata.exists():folders.extend(p/'5203110' for p in userdata.iterdir() if p.is_dir())
files=[dict(path=str(p),size=p.stat().st_size,sha256=sha(p.read_bytes())) for d in folders if d.exists() for p in d.rglob('*') if p.is_file()]
values=[]
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\PhilipMaxey\March and Conquer Demo') as key:
        for i in range(winreg.QueryInfoKey(key)[1]):
            n,v,t=winreg.EnumValue(key,i);values.append([n,v.hex() if isinstance(v,bytes) else v,t])
except FileNotFoundError:pass
save(WORK/sys.argv[1],dict(user=os.environ.get('USERNAME'),files=files,registry=values))
print('사용자',os.environ.get('USERNAME'),'파일',len(files),'설정',len(values))
