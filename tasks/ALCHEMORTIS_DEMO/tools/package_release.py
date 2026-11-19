"""원본 게임 파일을 포함하지 않는 양방향 차이 패치 ZIP을 만듭니다."""
from common import *
import subprocess,zipfile
candidate=Path(json.loads((WORK/'candidate_changes.json').read_text(encoding='utf-8'))['candidate'])
scratch=WORK/'package_v2';release=scratch/'package'
assert not release.exists();release.mkdir(parents=True)
static=json.loads((WORK/'static_validation.json').read_text(encoding='utf-8'));assert static['status']=='PASS' and static['candidate']==candidate.name
template=ROOT/'release_output/THE_LOOPLER_KOREAN_PATCH_1.0.0'
for name in ['Patch.ps1','ChooseGame.ps1']:
    text=(template/name).read_text(encoding='utf-8-sig')
    for before,after in [('The Loopler_Data\\data.unity3d','Alchemortis Demo.pck'),('TheLooplerKoreanPatch','AlchemortisKoreanPatch'),('The Loopler','Alchemortis Demo'),('THE_LOOPLER',GAME),('25262314','25423154'),('4150860','4974580'),('.loopler-korean-new','.alchemortis-korean-new')]:text=text.replace(before,after)
    assert 'Loopler' not in text and 'LOOPLER' not in text
    (release/name).write_text(text,encoding='utf-8-sig')
for name,mode in [('Install.cmd','Install'),('Remove.cmd','Uninstall')]:
    (release/name).write_bytes(('@echo off\r\nchcp 65001 >nul\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Patch.ps1" -Mode '+mode+' %*\r\nset "PATCH_EXIT=%ERRORLEVEL%"\r\necho.\r\npause\r\nexit /b %PATCH_EXIT%\r\n').encode('utf-8'))
(release/'README.txt').write_text('''Alchemortis Demo 한국어 패치 1.0.0

지원: Windows Steam 앱 4974580, 빌드 25423154, v0.22.1-demo.
원본 파일 또는 이 패치와 정확히 일치하는 파일에만 적용합니다.

설치: 게임을 종료한 뒤 ZIP 전체를 풀고 Install.cmd를 실행합니다.
Alchemortis Demo.exe가 있는 폴더를 선택하세요.
새 설정에서는 한국어가 기본이며, 기존 저장된 언어 설정이 있다면
게임 설정의 언어 목록에서 한국어를 선택할 수 있습니다.
기존 7개 언어를 유지하고 한국어를 추가합니다.
제거: Remove.cmd를 실행하고 같은 게임 폴더를 선택하세요.

게임 규칙·수치·저장 형식은 그대로입니다. 원본 백업과 설치 복구 기록은
%LOCALAPPDATA%\\AlchemortisKoreanPatch\\working_private 에 보관합니다.
중간 실패 시 시작 전 상태로 되돌립니다. 강제로 종료했다면 같은
설치기를 다시 실행하세요. 미지원 버전·변조 파일에는 강제 적용하지 않습니다.

범위: 2,022개 번역 항목, 실행 중 조합되는 안내·능력 문구,
한국어 언어 선택과 한글 글꼴을 적용합니다.
보관함·판매 그림 문구도 한국어 화면 표시로 교체합니다.
원본에서 ????로 가려진 425개 항목은 원래대로 유지합니다.
Alchemortis/Demo 로고, 숫자·버전·키 이름·로마 숫자와 원본 음원은 유지합니다.
사용하지 않는 옛 참고 이미지의 영문은 실행 참조가 없음을 별도 확인했습니다.
검수 범위와 실행·설치 시험 결과는 ZIP 밖 제작 보고서에 기록합니다.
모든 무작위 회차와 분기를 완주했다는 의미는 아닙니다.

원본 게임 파일이나 검수용 코드는 포함하지 않습니다.
xdelta3 3.2.0: Apache License 2.0.
Noto Sans KR(400/700): SIL Open Font License 1.1.
라이선스 전문은 licenses 폴더에 있습니다.
''',encoding='utf-8-sig')
toolroot=ROOT/'tasks/SUPERREAP_DEMO/tools/third_party/xdelta3-3.2.0';encoder=toolroot/'extracted/xdelta3-3.2.0-windows-x86_64/xdelta3.exe'
for name in ['tools','licenses','patches']:(release/name).mkdir()
shutil.copy2(encoder,release/'tools/xdelta3.exe')
shutil.copy2(toolroot/'LICENSE-APACHE-2.0.txt',release/'licenses/xdelta3-APACHE-2.0.txt')
shutil.copy2(ROOT/'tasks/TFC2/third_party/NotoSansKR/OFL.txt',release/'licenses/NotoSansKR-OFL.txt')
baseline=json.loads((WORK/'discovery/baseline_manifest.json').read_text(encoding='utf-8'));changes=[];roundtrips=[]
for row in baseline:
    name=row['path'];original=BASE/name;patched=candidate/name
    assert sha(original.read_bytes())==row['sha256']
    assert sha(patched.read_bytes())==static['files'][name]
    if row['sha256']==static['files'][name]:continue
    i=len(changes);forward=f'patches/{i:02}.forward.xdelta';reverse=f'patches/{i:02}.reverse.xdelta'
    for source,target,path,direction in [(original,patched,forward,'forward'),(patched,original,reverse,'reverse')]:
        subprocess.run([str(encoder),'-e','-f','-s',str(source),str(target),str(release/path)],check=True,capture_output=True)
        recovered=scratch/f'{i:02}.{direction}.recovered'
        subprocess.run([str(encoder),'-d','-f','-s',str(source),str(release/path),str(recovered)],check=True,capture_output=True)
        assert sha(recovered.read_bytes())==sha(target.read_bytes())
        roundtrips.append(dict(path=name,direction=direction,status='PASS',sha256=sha(recovered.read_bytes())))
    changes.append(dict(path=name,original_sha256=row['sha256'],patched_sha256=static['files'][name],forward=forward,reverse=reverse));print('차이 복원',name,flush=True)
assert len(changes)==2
payload=[dict(path=p.relative_to(release).as_posix(),size=p.stat().st_size,sha256=sha(p.read_bytes())) for p in sorted(release.rglob('*')) if p.is_file()]
save(release/'manifest.json',dict(game_id=GAME,steam_build='25423154',version='1.0.0',candidate=candidate.name,baseline=baseline,changes=changes,payload=payload))
allow={'Install.cmd','Remove.cmd','Patch.ps1','ChooseGame.ps1','README.txt','manifest.json','tools/xdelta3.exe','licenses/xdelta3-APACHE-2.0.txt','licenses/NotoSansKR-OFL.txt'}|{r[k] for r in changes for k in ['forward','reverse']}
assert {p.relative_to(release).as_posix() for p in release.rglob('*') if p.is_file()}==allow
archive=scratch/(GAME+'_KOREAN_PATCH_1.0.0.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for name in sorted(allow):z.write(release/name,name)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None and set(z.namelist())==allow;z.extractall(scratch/'from_final_zip')
for name in allow:assert sha((release/name).read_bytes())==sha((scratch/'from_final_zip'/name).read_bytes())
save(scratch/'package.json',dict(candidate=candidate.name,zip_sha256=sha(archive.read_bytes()),manifest_sha256=sha((release/'manifest.json').read_bytes()),allowed_files=sorted(allow),roundtrips=roundtrips,final_zip_tests='NOT_RUN',public_release='NOT_RUN'))
print('ZIP 생성',archive.stat().st_size,'바이트',flush=True)
