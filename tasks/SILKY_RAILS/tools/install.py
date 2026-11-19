"""최종 ZIP 설치기로 지정한 실제 설치본에 적용하고 저장·전체 파일을 대조합니다."""
from qa import snapshot
from baseline import *
import subprocess,datetime
candidate=ROOT/'build_candidate/SILKY_RAILS/ko_v003';package=WORK/'package';manifest=json.loads((package/'from_final_zip/manifest.json').read_text());report=json.loads((package/'package.json').read_text());archive=ROOT/'release_output/SILKY_RAILS_KOREAN_PATCH_1.0.0.zip';assert sha(archive.read_bytes())==report['zip_sha256']
before=snapshot();save(WORK/'install_before.json',before)
# 설치 직전 전체 원본이 확보한 기준선과 같은지 확인합니다.
for r in json.loads((WORK/'baseline.json').read_text()):assert sha((TARGET/r['path']).read_bytes())==r['sha256'],r['path']
p=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(package/'from_final_zip/Patch.ps1'),'-Mode','Install','-GameDirectory',str(TARGET)],capture_output=True,timeout=180)
(WORK/'install_target.log').write_bytes(p.stdout+p.stderr);print(p.stdout.decode('utf-8',errors='replace'));assert p.returncode==0,p.stderr.decode(errors='replace')
files=[]
for r in json.loads((WORK/'baseline.json').read_text()):
 expected=sha((candidate/r['path']).read_bytes());actual=sha((TARGET/r['path']).read_bytes());assert expected==actual,r['path'];files.append(dict(path=r['path'],sha256=actual))
after=snapshot();assert after==before;save(WORK/'install_after.json',after);save(WORK/'installation.json',dict(status='PASS',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),target=str(TARGET),zip_sha256=report['zip_sha256'],files=files,changed_files=4,user_save_unchanged=True))
print('실제 설치 완료:',len(files),'파일 후보 일치, 저장·설정 동일')
