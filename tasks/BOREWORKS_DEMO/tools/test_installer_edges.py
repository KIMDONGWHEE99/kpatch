"""부분 제거·손상 도구·잘못된 경로·추가 Steam 라이브러리를 확인합니다."""
from common import *
import shutil
scratch=WORK/'package_v1';package=scratch/'from_final_zip';game=scratch/'한글 공백 시험본'
env=os.environ.copy();env['LOCALAPPDATA']=str(scratch/'test_local')
ps=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
baseline=json.loads((WORK/'baseline.json').read_text(encoding='utf-8'));expected={r['path']:r['sha256'] for r in baseline}
def snapshot():return {p.relative_to(game).as_posix():sha(p.read_bytes()) for p in game.rglob('*') if p.is_file()}
results=[]
def run(case,mode,root=package,target=game,code=0):
    p=subprocess.run([str(ps),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(root/'Patch.ps1'),'-Mode',mode,'-GameDirectory',str(target)],env=env,capture_output=True,timeout=120)
    (scratch/(case+'.log')).write_bytes(p.stdout+p.stderr)
    assert (p.returncode==0)==(code==0),(case,p.stderr[-1000:])
    results.append(dict(case=case,status='PASS'));print(case,'PASS',flush=True)
assert snapshot()==expected
shutil.copy2(ROOT/'build_candidate/BOREWORKS_DEMO/ko_v002/Boreworks.pck',game/'Boreworks.pck')
run('partial_uninstall','Uninstall');assert snapshot()==expected
damaged=scratch/'damaged_decoder';shutil.copytree(package,damaged)
with (damaged/'tools/xdelta3.exe').open('ab') as f:f.write(b'TAMPER')
run('damaged_decoder','Install',root=damaged,code=1);assert snapshot()==expected
wrong=scratch/'없는 게임 위치';assert not wrong.exists()
run('wrong_directory','Install',target=wrong,code=1);assert not wrong.exists() and snapshot()==expected

fake=scratch/'가상 Steam';library=scratch/'추가 게임 라이브러리';install=library/'steamapps/common/Boreworks Demo'
(fake/'steamapps').mkdir(parents=True);install.mkdir(parents=True)
(fake/'steamapps/libraryfolders.vdf').write_text('"libraryfolders"\n{\n "1"\n {\n  "path" "'+str(library).replace('\\','\\\\')+'"\n }\n}\n',encoding='utf-8')
(library/'steamapps/appmanifest_4829140.acf').write_text('"AppState"\n{\n"installdir" "Boreworks Demo"\n}\n',encoding='utf-8')
for name in ('Boreworks.exe','Boreworks.pck'):(install/name).write_bytes(b'PATH_DISCOVERY_ONLY')
quote=lambda x:"'"+str(x).replace("'","''")+"'"
script=scratch/'check_discovery.ps1'
script.write_text("$ErrorActionPreference='Stop'\n. "+quote(package/'ChooseGame.ps1')+"\n$found=@(Get-GameLocations -SteamRoots @("+quote(fake)+") -NearbyPaths @() -ReceiptRoot '')\nif ($found.Count -ne 1 -or $found[0] -ne "+quote(install)+") { throw '추가 라이브러리 탐색 실패' }\n$real=@(Get-GameLocations -SteamRoots @('D:\\steam') -NearbyPaths @() -ReceiptRoot '')\nif ($real -notcontains 'D:\\steam\\steamapps\\common\\Boreworks Demo') { throw '실제 라이브러리 탐색 실패' }\nWrite-Output 'DISCOVERY_PASS'\n",encoding='utf-8-sig')
p=subprocess.run([str(ps),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)],env=env,capture_output=True,timeout=60)
(scratch/'library_discovery.log').write_bytes(p.stdout+p.stderr);assert p.returncode==0,p.stderr
results.extend([dict(case='additional_library_discovery',status='PASS'),dict(case='actual_steam_discovery',status='PASS')])
save_json(scratch/'installer_edge_tests.json',dict(status='PASS',cases=results,final_zip_sha256=sha((ROOT/'release_output/BOREWORKS_DEMO_KOREAN_PATCH_1.0.0.zip').read_bytes())))
print('EDGE_ALL_PASS',len(results))
