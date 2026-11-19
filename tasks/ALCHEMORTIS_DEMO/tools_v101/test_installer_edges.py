"""부분 제거·손상 도구·잘못된 경로·추가 Steam 라이브러리를 확인합니다."""
from common import *
from pathlib import Path
import os,json,subprocess
save_json=save
def sha(path):return __import__("hashlib").sha256(Path(path).read_bytes()).hexdigest()
import shutil
scratch=WORK/'package_v3';package=scratch/'from_final_zip';game=scratch/'한글 공백 시험본'
env=os.environ.copy();env['LOCALAPPDATA']=str(scratch/'test_local')
ps=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
baseline=json.loads((WORK/'discovery/baseline_manifest.json').read_text(encoding='utf-8'));expected={r['path']:r['sha256'] for r in baseline}
def snapshot():return {p.relative_to(game).as_posix():sha(p) for p in game.rglob('*') if p.is_file()}
results=[]
def run(case,mode,root=package,target=game,code=0):
    p=subprocess.run([str(ps),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(root/'Patch.ps1'),'-Mode',mode,'-GameDirectory',str(target)],env=env,capture_output=True,timeout=120)
    (scratch/(case+'.log')).write_bytes(p.stdout+p.stderr)
    assert (p.returncode==0)==(code==0),(case,p.stderr[-1000:])
    results.append(dict(case=case,status='PASS'));print(case,'PASS',flush=True)
fake=scratch/'가상 Steam';library=scratch/'추가 게임 라이브러리';install=library/'steamapps/common/Alchemortis Demo'
(fake/'steamapps').mkdir(parents=True);install.mkdir(parents=True)
(fake/'steamapps/libraryfolders.vdf').write_text('"libraryfolders"\n{\n "1"\n {\n  "path" "'+str(library).replace('\\','\\\\')+'"\n }\n}\n',encoding='utf-8')
(library/'steamapps/appmanifest_4974580.acf').write_text('"AppState"\n{\n"installdir" "Alchemortis Demo"\n}\n',encoding='utf-8')
for name in ('Alchemortis Demo.exe','Alchemortis Demo.pck'):
    (install/name).parent.mkdir(parents=True,exist_ok=True);(install/name).write_bytes(b'PATH_DISCOVERY_ONLY')
quote=lambda x:"'"+str(x).replace("'","''")+"'"
script=scratch/'check_discovery.ps1'
script.write_text("$ErrorActionPreference='Stop'\n. "+quote(package/'ChooseGame.ps1')+"\n$found=@(Get-GameLocations -SteamRoots @("+quote(fake)+") -NearbyPaths @() -ReceiptRoot '')\nif ($found.Count -ne 1 -or $found[0] -ne "+quote(install)+") { throw '추가 라이브러리 탐색 실패' }\n$real=@(Get-GameLocations -SteamRoots @('D:\\steam') -NearbyPaths @() -ReceiptRoot '')\nif ($real -notcontains 'D:\\steam\\steamapps\\common\\Alchemortis Demo') { throw '실제 라이브러리 탐색 실패' }\nWrite-Output 'DISCOVERY_PASS'\n",encoding='utf-8-sig')
p=subprocess.run([str(ps),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)],env=env,capture_output=True,timeout=60)
(scratch/'library_discovery.log').write_bytes(p.stdout+p.stderr);assert p.returncode==0,p.stderr
results.extend([dict(case='additional_library_discovery',status='PASS'),dict(case='actual_steam_discovery',status='PASS')])
key=__import__('hashlib').sha256(str(game.resolve()).lower().encode()).hexdigest()[:16].upper()
receipt_root=Path(env['LOCALAPPDATA'])/'AlchemortisKoreanPatch/working_private'
legacy=receipt_root/key
(legacy/'cache/0').mkdir(parents=True,exist_ok=True)
(legacy/'cache/0/original').write_bytes(b'LEGACY_BACKUP_UNCHANGED')
(legacy/'receipt.json').write_text('{"version":"1.0.0","game_directory":"legacy_marker_not_a_game"}',encoding='utf-8')
legacy_files={p:sha(p) for p in [legacy/'cache/0/original',legacy/'receipt.json']}
run('legacy_backup_coexistence','Install')
assert all(sha(p)==digest for p,digest in legacy_files.items())
script=scratch/'check_build_receipt.ps1'
script.write_text("$ErrorActionPreference='Stop'\n. "+quote(package/'ChooseGame.ps1')+"\n$found=@(Get-GameLocations -SteamRoots @() -NearbyPaths @() -ReceiptRoot "+quote(receipt_root)+")\nif ($found.Count -ne 1 -or $found[0] -ne "+quote(game)+") { throw '빌드별 설치 기록 탐색 실패' }\n",encoding='utf-8-sig')
p=subprocess.run([str(ps),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)],env=env,capture_output=True,timeout=60)
(scratch/'build_receipt_discovery.log').write_bytes(p.stdout+p.stderr)
assert p.returncode==0,p.stderr
results.append(dict(case='build_scoped_receipt_discovery',status='PASS'))
run('legacy_backup_preserved_on_remove','Uninstall')
assert all(sha(p)==digest for p,digest in legacy_files.items())
assert snapshot()==expected
save_json(scratch/'installer_edge_tests.json',dict(status='PASS',cases=results,final_zip_sha256=sha(scratch/'ALCHEMORTIS_DEMO_KOREAN_PATCH_1.0.1.zip')))
print('EDGE_ALL_PASS',len(results))
