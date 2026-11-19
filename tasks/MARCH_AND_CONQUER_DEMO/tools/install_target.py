"""검증한 최종 ZIP 설치기로 사용자가 지정한 게임에 적용합니다."""
from baseline import *
import os,subprocess
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
pkg=WORK/'package_v2';unpacked=pkg/'from_final_zip';archive=pkg/(GAME+'_KOREAN_PATCH_1.0.0.zip')
ready=read(WORK/'release_ready.json');assert ready['status']=='PASS' and ready['zip_sha256']==sha(archive.read_bytes())
manifest=read(unpacked/'manifest.json');assert manifest['candidate']==ready['candidate']=='ko_v005'
before={p.relative_to(SOURCE).as_posix():sha(p.read_bytes()) for p in SOURCE.rglob('*') if p.is_file()}
baseline={r['path']:r['sha256'] for r in manifest['baseline']};assert before==baseline,'설치본이 제작 중 변경되었습니다'
ps=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
command=[str(ps),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(unpacked/'Patch.ps1'),'-Mode','Install','-GameDirectory',str(SOURCE)]
p=subprocess.run(command,capture_output=True,timeout=180)
(WORK/'actual_install.stdout.log').write_bytes(p.stdout);(WORK/'actual_install.stderr.log').write_bytes(p.stderr)
assert p.returncode==0,('설치 실패',p.returncode,p.stderr[-1000:])
expected={r['path']:r['sha256'] for r in read(ROOT/'build_candidate'/GAME/'ko_v005/build.json')['files']}
after={p.relative_to(SOURCE).as_posix():sha(p.read_bytes()) for p in SOURCE.rglob('*') if p.is_file()};assert after==expected
rootkey=sha(str(SOURCE).lower().encode('utf-8')).upper()[:16];backup=Path(os.environ['LOCALAPPDATA'])/'MarchConquerKoreanPatch/working_private'/rootkey
receipt=read(backup/'receipt.json');assert receipt['status']=='COMPLETE' and receipt['mode']=='Install'
assert receipt['manifest_sha256']==sha((unpacked/'manifest.json').read_bytes())
originals=[]
for i,row in enumerate(manifest['changes']):
    h=sha((backup/'cache'/str(i)/'original').read_bytes());assert h==row['original_sha256'];originals.append(dict(path=row['path'],sha256=h))
output=ROOT/'release_output';output.mkdir(exist_ok=True)
zipout=output/archive.name;assert not zipout.exists();shutil.copy2(archive,zipout);assert sha(zipout.read_bytes())==ready['zip_sha256']
folder=output/archive.stem;assert not folder.exists();shutil.copytree(unpacked,folder)
for path in unpacked.rglob('*'):
    if path.is_file():assert sha(path.read_bytes())==sha((folder/path.relative_to(unpacked)).read_bytes())
save(WORK/'actual_install.json',dict(status='PASS',time=datetime.datetime.now(datetime.timezone.utc).isoformat(),game_directory=str(SOURCE),candidate='ko_v005',files=len(after),changed_files=len(originals),extra_files=0,zip_sha256=ready['zip_sha256'],backup_directory=str(backup),backup_originals=originals,installed_hashes=after,receipt_sha256=sha((backup/'receipt.json').read_bytes())))
print('INSTALL PASS',len(after),'files',len(originals),'original backups')
