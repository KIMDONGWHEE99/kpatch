"""최종 ZIP에서 추출한 검증된 설치기를 지정 설치본에 적용하고 전후 지문을 확인합니다."""
from common import *
import subprocess,os,datetime
args=sys.argv[:];sys.argv=['probe.py','import'];from probe import snapshot
sys.argv=args
build='ko_c03';candidate=ROOT/'build_candidate/EPIC_IDLENTURE_DEMO'/build;package=WORK/'package/from_final_zip'
for name in ['ko_c03_independent.json','runtime_report.json','classification_summary.json','media_summary.json','package/installer_tests.json','package/installer_edge_tests.json']:
    assert json.loads((WORK/name).read_text(encoding='utf8'))['status']=='PASS',name
archive=ROOT/'release_output/EPIC_IDLENTURE_DEMO_KOREAN_PATCH_1.0.0.zip';zip_hash=sha(archive.read_bytes());assert zip_hash==json.loads((WORK/'package/package.json').read_text(encoding='utf8'))['zip_sha256']
base=json.loads((WORK/'baseline.json').read_text(encoding='utf8'));before=snapshot();save(WORK/'installed_user_before.json',before)
for r in base:assert sha((TARGET/r['path']).read_bytes())==r['sha256'],r['path']
command=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(package/'Patch.ps1'),'-Mode','Install','-GameDirectory',str(TARGET)]
p=subprocess.run(command,capture_output=True,timeout=180);(WORK/'actual_install.log').write_bytes(p.stdout+p.stderr);assert p.returncode==0,p.stderr.decode(errors='replace')
actual={p.relative_to(TARGET).as_posix():sha(p.read_bytes()) for p in TARGET.rglob('*') if p.is_file()}
expected={p.relative_to(candidate).as_posix():sha(p.read_bytes()) for p in candidate.rglob('*') if p.is_file()};assert actual==expected
after=snapshot();save(WORK/'installed_user_after.json',after);assert before==after
state=Path(os.environ['LOCALAPPDATA'])/'EpicIdlentureKoreanPatch/working_private';journal=next(p for p in state.glob('*/transaction.json') if json.loads(p.read_text(encoding='utf-8-sig'))['game_directory']==str(TARGET))
manifest=json.loads((package/'manifest.json').read_text(encoding='utf8'));backups=[]
for i,row in enumerate(manifest['changes']):
    cache=journal.parent/'cache'/str(i)/'original';assert sha(cache.read_bytes())==row['original_sha256'];backups.append(dict(path=row['path'],backup_sha256=sha(cache.read_bytes())))
save(WORK/'installation.json',dict(status='PASS',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),candidate=build,zip_sha256=zip_hash,installed_files=len(actual),changed=len(backups),backups=backups,save_data_unchanged=True,command=command,backup_root=str(journal.parent)))
print('실제 설치 완료:',len(actual),'파일 일치, 원본 백업',len(backups),'개 일치, 사용자 저장·설정 보존')
