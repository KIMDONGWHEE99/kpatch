"""같은 후보에서 양방향 차이 파일과 검증할 최종 ZIP을 생성합니다."""
from common import *
import subprocess,zipfile
build='ko_v005';candidate=ROOT/'build_candidate'/GAME/build/'game';scratch=WORK/'package_v2';release=scratch/'package'
assert not release.exists();release.mkdir(parents=True)
static=json.loads((candidate.parent/'static_validation.json').read_text(encoding='utf-8'));assert static['status']=='PASS'
assert static['build_manifest_sha256']==sha((candidate.parent/'build.json').read_bytes())
template=ROOT/'release_output/THE_LOOPLER_KOREAN_PATCH_1.0.0'
for name in ['Patch.ps1','ChooseGame.ps1']:
    s=(template/name).read_text(encoding='utf-8-sig')
    for a,b in [('The Loopler_Data\\data.unity3d','March and Conquer Demo_Data\\sharedassets0.assets'),('TheLooplerKoreanPatch','MarchConquerKoreanPatch'),('The Loopler','March and Conquer Demo'),('THE_LOOPLER',GAME),('25262314','25323013'),('4150860','5203110'),('.loopler-korean-new','.march-korean-new')]:s=s.replace(a,b)
    assert 'Loopler' not in s and 'LOOPLER' not in s
    (release/name).write_text(s,encoding='utf-8-sig')
for name,mode in [('Install.cmd','Install'),('Remove.cmd','Uninstall')]:
    (release/name).write_bytes(('@echo off\r\nchcp 65001 >nul\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Patch.ps1" -Mode '+mode+' %*\r\nset "PATCH_EXIT=%ERRORLEVEL%"\r\necho.\r\npause\r\nexit /b %PATCH_EXIT%\r\n').encode('utf-8'))
(release/'README.txt').write_text('''March and Conquer Demo 한국어 패치 1.0.0

지원: Windows Steam 빌드 25323013 / 앱 5203110 / 게임 v1.1.
이 버전의 원본 파일 또는 이 패치와 정확히 일치하는 파일에만 적용합니다.

설치: 게임을 종료한 뒤 ZIP 전체를 풀고 Install.cmd를 실행합니다.
March and Conquer Demo.exe가 있는 폴더를 선택하세요.
기존 English 언어 항목을 한국어로 대체합니다. 설정의 언어 목록에서
한국어를 선택할 수 있습니다. 기존 독일어 항목은 유지합니다.
제거: Remove.cmd를 실행하고 같은 게임 폴더를 선택하세요.
게임 저장 형식과 게임 규칙·수치는 변경하지 않습니다.

설치 중 실패하면 시작 전 상태로 되돌립니다. 강제로 중단되었다면
같은 설치기를 다시 실행해 복구하세요. 원본 백업과 복구 기록은
%LOCALAPPDATA%\\MarchConquerKoreanPatch\\working_private 에 보관합니다.
게임 업데이트·다른 모드·파일 변조를 감지하면 강제 적용하지 않습니다.

범위: 언어표 391행(중복 키 포함), 직접 문구·유닛·기술 설명 등
1,099개 표시 위치, 코드 문구 85곳 및 생산/전투 상태 한국어 표시,
한글 대체 글꼴과 한국어 단어 단위 줄바꿈을 적용했습니다.
숫자·기호·버전, Unity/게임 제목 로고, 원본 음원 이름은 유지합니다.
원본 게임 파일과 검수용 코드는 포함하지 않습니다.

검수 범위와 설치·복구 시험은 ZIP 밖 결과 보고서에 별도로 기록합니다.
대표 화면·기술 설명 검수와 전체 무작위 회차 완주는 구분합니다.

포함 도구: xdelta3 3.2.0 (Apache License 2.0).
한글 글꼴: Noto Sans KR, 굵기 400 (SIL Open Font License 1.1).
라이선스 전문은 licenses 폴더에 있습니다.
''',encoding='utf-8-sig')
toolroot=ROOT/'tasks/SUPERREAP_DEMO/tools/third_party/xdelta3-3.2.0';encoder=toolroot/'extracted/xdelta3-3.2.0-windows-x86_64/xdelta3.exe'
(release/'tools').mkdir();(release/'licenses').mkdir();(release/'patches').mkdir()
shutil.copy2(encoder,release/'tools/xdelta3.exe');shutil.copy2(toolroot/'LICENSE-APACHE-2.0.txt',release/'licenses/xdelta3-APACHE-2.0.txt');shutil.copy2(ROOT/'tasks/TFC2/third_party/NotoSansKR/OFL.txt',release/'licenses/NotoSansKR-OFL.txt')
baseline=json.loads((WORK/'baseline.json').read_text(encoding='utf-8'))['files'];changes=[];roundtrips=[]
for row in baseline:
    name=row['path'];a=BASE/name;b=candidate/name
    assert sha(a.read_bytes())==row['sha256']
    if sha(a.read_bytes())==sha(b.read_bytes()):continue
    i=len(changes);forward=f'patches/{i:02}.forward.xdelta';reverse=f'patches/{i:02}.reverse.xdelta'
    for source,target,path,label in [(a,b,forward,'forward'),(b,a,reverse,'reverse')]:
        subprocess.run([str(encoder),'-e','-f','-s',str(source),str(target),str(release/path)],check=True,capture_output=True)
        recovered=scratch/f'{i:02}.{label}.recovered';subprocess.run([str(encoder),'-d','-f','-s',str(source),str(release/path),str(recovered)],check=True,capture_output=True)
        assert sha(recovered.read_bytes())==sha(target.read_bytes());roundtrips.append(dict(path=name,direction=label,status='PASS',sha256=sha(recovered.read_bytes())))
    changes.append(dict(path=name,original_sha256=sha(a.read_bytes()),patched_sha256=sha(b.read_bytes()),forward=forward,reverse=reverse));print('차이 복원',name,flush=True)
assert len(changes)==4
payload=[dict(path=p.relative_to(release).as_posix(),size=p.stat().st_size,sha256=sha(p.read_bytes())) for p in sorted(release.rglob('*')) if p.is_file()]
save(release/'manifest.json',dict(game_id=GAME,steam_build='25323013',version='1.0.0',candidate=build,baseline=baseline,changes=changes,payload=payload))
allow={'Install.cmd','Remove.cmd','Patch.ps1','ChooseGame.ps1','README.txt','manifest.json','tools/xdelta3.exe','licenses/xdelta3-APACHE-2.0.txt','licenses/NotoSansKR-OFL.txt'}|{r[k] for r in changes for k in ['forward','reverse']}
assert {p.relative_to(release).as_posix() for p in release.rglob('*') if p.is_file()}==allow
archive=scratch/(GAME+'_KOREAN_PATCH_1.0.0.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for name in sorted(allow):z.write(release/name,name)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None and set(z.namelist())==allow;z.extractall(scratch/'from_final_zip')
for name in allow:assert sha((release/name).read_bytes())==sha((scratch/'from_final_zip'/name).read_bytes())
save(scratch/'package.json',dict(candidate=build,zip_sha256=sha(archive.read_bytes()),manifest_sha256=sha((release/'manifest.json').read_bytes()),allowed_files=sorted(allow),roundtrips=roundtrips,final_zip_tests='NOT_RUN',public_release='NOT_RUN'))
print('ZIP 생성',archive.stat().st_size,'바이트')
