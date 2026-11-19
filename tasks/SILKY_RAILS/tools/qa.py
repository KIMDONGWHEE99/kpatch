"""사용자 저장·설정을 관찰하고 검수 사본의 저장 위치와 외부 초기화를 격리합니다."""
from common import *
import os,winreg,subprocess,datetime
RUN=WORK/'qa_002';GAME=RUN/'game'
def snapshot():
 folders=[Path(os.environ['USERPROFILE'])/'AppData/LocalLow/JoyDoza/Silky Rails']
 steam=Path('D:/steam/userdata')
 if steam.exists():folders.extend(x/'3870990' for x in steam.iterdir() if x.is_dir())
 files=[dict(path=str(p),size=p.stat().st_size,sha256=sha(p.read_bytes())) for d in folders if d.exists() for p in sorted(d.rglob('*')) if p.is_file()]
 values=[]
 try:
  with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\JoyDoza\Silky Rails') as key:
   for i in range(winreg.QueryInfoKey(key)[1]):
    n,v,t=winreg.EnumValue(key,i);values.append([n,v.hex() if isinstance(v,bytes) else v,t])
 except FileNotFoundError:pass
 return dict(files=files,registry=values)
if __name__=='__main__':
 if sys.argv[1]=='prepare':
  assert not GAME.exists();shutil.copytree(ROOT/'build_candidate/SILKY_RAILS/ko_v003',GAME)
  f=GAME/DATA/'globalgamemanagers';env=UnityPy.load(str(f));obj=env.file.objects[1];a=obj.get_raw_data();assert a.count(b'JoyDoza')==a.count(b'Silky Rails')==1
  obj.set_raw_data(a.replace(b'JoyDoza',b'SRK_QA_').replace(b'Silky Rails',b'Silky QA002'));f.write_bytes(preserve_save(f,env))
  (GAME/DATA/'app.info').write_bytes(b'SRK_QA_\r\nSilky QA002\r\n')
  assembly=Path(DATA)/'Managed/Assembly-CSharp.dll'
  subprocess.run(['dotnet',str(WORK/'assembly_tool/AssemblyTool.dll'),'qa',str(ROOT/'build_candidate/SILKY_RAILS/ko_v003'/assembly),str(GAME/assembly),str(RUN/'code_overrides.json')],check=True)
  sdk=Path(DATA)/'Managed/GameAnalyticsSDK.dll';subprocess.run(['dotnet',str(WORK/'assembly_tool/AssemblyTool.dll'),'qasdk',str(BASE/sdk),str(GAME/sdk),str(RUN/'sdk_overrides.json')],check=True)
  save(RUN/'user_before.json',snapshot());save(RUN/'qa_manifest.json',dict(candidate='ko_v003',changes=['PlayerSettings companyName/productName','app.info','SteamManager.Awake','AnalyticsManager.Awake'],files=[dict(path=p.relative_to(GAME).as_posix(),sha256=sha(p.read_bytes())) for p in GAME.rglob('*') if p.is_file()]))
 elif sys.argv[1]=='launch':
  assert snapshot()==json.loads((RUN/'user_before.json').read_text())
  command=[str(GAME/'Silky Rails.exe'),'-screen-fullscreen','0','-screen-width','1280','-screen-height','720','-logFile',str(RUN/'Player.log')]
  p=subprocess.Popen(command,cwd=GAME,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);save(RUN/'launch.json',dict(pid=p.pid,expected_executable=command[0],command=command,utc=datetime.datetime.now(datetime.timezone.utc).isoformat()));print('PID',p.pid)
 elif sys.argv[1]=='verify':
  after=snapshot();save(RUN/'user_after.json',after);assert after==json.loads((RUN/'user_before.json').read_text());print('사용자 저장·설정 동일')

