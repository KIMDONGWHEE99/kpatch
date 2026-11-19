"""최종 ZIP에서 나온 설치기로 지정 설치본을 적용하고 백업까지 검증합니다."""
from pck_tools import ROOT,WORK
from pathlib import Path
import os,json,hashlib,subprocess,zipfile,shutil
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
package=WORK/'package_v3';extracted=package/'from_final_zip'
archive=package/'ALCHEMORTIS_DEMO_KOREAN_PATCH_1.0.1.zip'
meta=read(package/'package.json');tests=read(package/'installer_tests.json');edges=read(package/'installer_edge_tests.json')
assert tests['status']==edges['status']=='PASS'
assert len(tests['cases'])+len(edges['cases'])>=24
assert sha(archive)==meta['zip_sha256']==tests['final_zip_sha256']==edges['final_zip_sha256']
with zipfile.ZipFile(archive) as z:
    names=[n for n in z.namelist() if not n.endswith('/')]
    assert set(names)==set(meta['allowed_files'])
    for n in names:assert z.read(n)==(extracted/n).read_bytes(),n
static=read(WORK/'static_validation.json');runtime=read(WORK/'runtime_final_audit.json')
assert static['status']=='PASS' and static['candidate']==runtime['candidate']=='ko_1.0.1_c01'
assert all(runtime[k]['status']=='PASS' for k in ['process','qa_boundary','runtime_data','font','log','user_data'])
manifest=read(extracted/'manifest.json')
target=Path('D:/steam/steamapps/common/Alchemortis Demo').resolve()
assert str(target).lower()==r'D:\steam\steamapps\common\Alchemortis Demo'.lower()
baseline={r['path']:r['sha256'] for r in manifest['baseline']}
expected=dict(baseline,**{r['path']:r['patched_sha256'] for r in manifest['changes']})
def snapshot(folder):return {p.relative_to(folder).as_posix():sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}
def users():
    roots=[Path(os.environ['APPDATA'])/'Alchemortis Demo']+sorted(Path('D:/steam/userdata').glob('*/4974580'))
    return {str(p):snapshot(p) for p in roots}
before=snapshot(target);assert before in [baseline,expected], '실제 설치본이 지원 해시와 다름'
user_before=users();save(WORK/'install_user_before.json',user_before)
key=hashlib.sha256(str(target).lower().encode()).hexdigest()[:16].upper()
legacy=Path(os.environ['LOCALAPPDATA'])/'AlchemortisKoreanPatch/working_private'/key
legacy_before={p.relative_to(legacy).as_posix():sha(p) for p in legacy.rglob('*') if p.is_file() and not p.relative_to(legacy).parts[0].isdigit()}
save(WORK/'legacy_backup_before.json',legacy_before)
save(WORK/'install_before.json',before)
ps=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
command=[str(ps),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(extracted/'Patch.ps1'),'-Mode','Install','-GameDirectory',str(target)]
p=subprocess.run(command,capture_output=True,timeout=180)
(WORK/'install.stdout.log').write_bytes(p.stdout);(WORK/'install.stderr.log').write_bytes(p.stderr)
assert p.returncode==0,p.stderr.decode('utf-8',errors='replace')
after=snapshot(target);assert after==expected==static['files']
user_after=users();assert user_before==user_after
key=hashlib.sha256(str(target).lower().encode()).hexdigest()[:16].upper()
backup=Path(os.environ['LOCALAPPDATA'])/'AlchemortisKoreanPatch/working_private'/key/manifest['steam_build']
receipt=read(backup/'receipt.json')
assert receipt['status']=='COMPLETE' and receipt['mode']=='Install' and receipt['candidate']=='ko_1.0.1_c01'
assert receipt['manifest_sha256']==sha(extracted/'manifest.json')
backups=[]
for i,r in enumerate(manifest['changes']):
    original=backup/'cache'/str(i)/'original'
    assert sha(original)==r['original_sha256']
    backups.append({'path':r['path'],'backup':str(original),'sha256':sha(original)})
assert read(backup/'transaction.json')['phase']=='COMPLETE'
assert all((legacy/name).exists() and sha(legacy/name)==digest for name,digest in legacy_before.items()),'이전 빌드 백업 변경'
result={'status':'PASS','candidate':'ko_1.0.1_c01','target':str(target),'files_verified':len(after),'modified_files':len(manifest['changes']),'additional_files':0,'zip_sha256':sha(archive),'receipt':receipt,'backups':backups,'user_files_preserved':sum(len(x) for x in user_after.values()),'user_data_equal':user_before==user_after,'installed_hashes':after}
save(WORK/'installation_final.json',result)
result['legacy_backup_files_preserved']=len(legacy_before)
save(WORK/'installation_final.json',result)
meta['final_zip_tests']='PASS';meta['final_zip_test_cases']=len(tests['cases'])+len(edges['cases']);meta['actual_installation']='PASS';meta['public_release']='NOT_RUN'
save(package/'package.json',meta)
destination=ROOT/'release_output';destination.mkdir(exist_ok=True)
shutil.copy2(archive,destination/archive.name)
folder=destination/'ALCHEMORTIS_DEMO_KOREAN_PATCH_1.0.1';folder.mkdir(exist_ok=True)
for n in names:
    dest=folder/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(extracted/n,dest)
assert sha(destination/archive.name)==sha(archive)
assert snapshot(folder)=={n:sha(extracted/n) for n in names}
print(json.dumps({k:result[k] for k in ['status','target','files_verified','modified_files','additional_files','user_files_preserved','zip_sha256']},ensure_ascii=False))
