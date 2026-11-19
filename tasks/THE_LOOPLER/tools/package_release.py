"""검수 후보를 양방향 차이 파일로 묶습니다. 작업 영역에서 ZIP 시험 후 인계합니다."""
from common import *
from build_candidate import CANDIDATE,REPORT
from pathlib import Path
import json,shutil,zipfile,subprocess

scratch=WORK/'package_v2';scratch.mkdir(exist_ok=True)
release=scratch/'THE_LOOPLER_KOREAN_PATCH_1.0.0'
assert not (release/'manifest.json').exists()
release.mkdir(exist_ok=True)
template=ROOT/'release_output/BOREWORKS_DEMO_KOREAN_PATCH_1.0.0'
for name in ('Patch.ps1','ChooseGame.ps1'):
    s=(template/name).read_text('utf-8-sig')
    replacements=[('BOREWORKS Demo','The Loopler'),('Boreworks Demo','The Loopler'),('BOREWORKS_DEMO','THE_LOOPLER'),('BoreworksKoreanPatch','TheLooplerKoreanPatch'),('Boreworks.exe','The Loopler.exe'),('Boreworks.pck','The Loopler_Data\\data.unity3d'),('23942533','25262314'),('4829140','4150860'),('.boreworks-korean-new','.loopler-korean-new'),('-Name Boreworks ',"-Name 'The Loopler' ")]
    for a,b in replacements:s=s.replace(a,b)
    s=s.replace('Boreworks 폴더','The Loopler 폴더')
    if name=='Patch.ps1':
        helper='''function Set-AtomicReplacement([string]$Temporary, [string]$Target) {
    # 검색/보안 프로그램이 파일을 잠시 여는 경우에만 제한된 시간 동안 재시도합니다.
    for ($attempt=0; $attempt -lt 8; $attempt++) {
        try {
            if ([IO.File]::Exists($Target)) { [IO.File]::Replace($Temporary,$Target,[System.Management.Automation.Language.NullString]::Value,$true) }
            else { [IO.File]::Move($Temporary,$Target) }
            return
        } catch {
            if ($attempt -eq 7 -or -not [IO.File]::Exists($Temporary)) { throw }
            Start-Sleep -Milliseconds 150
        }
    }
}

'''
        s=s.replace('function Write-JsonAtomic',helper+'function Write-JsonAtomic')
        s=s.replace("if ([IO.File]::Exists($Path)) { [IO.File]::Replace($temporary,$Path,[System.Management.Automation.Language.NullString]::Value) } else { [IO.File]::Move($temporary,$Path) }",'Set-AtomicReplacement $temporary $Path')
        s=s.replace("if ([IO.File]::Exists($Target)) { [IO.File]::Replace($temporary,$Target,[System.Management.Automation.Language.NullString]::Value,$true) } else { [IO.File]::Move($temporary,$Target) }",'Set-AtomicReplacement $temporary $Target')
    assert 'Boreworks' not in s and 'BOREWORKS' not in s
    (release/name).write_text(s,'utf-8-sig')
for name,mode in [('Install.cmd','Install'),('Remove.cmd','Uninstall')]:
    s='@echo off\r\nchcp 65001 >nul\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Patch.ps1" -Mode '+mode+'\r\necho.\r\npause\r\n'
    (release/name).write_bytes(s.encode('utf-8'))
(release/'README.txt').write_text('''The Loopler 한국어 패치 1.0.0

지원: Steam 앱 4150860 / 빌드 25262314 / Windows 64비트.
설치한 게임의 원본 파일 내용이 지원 버전과 일치할 때만 적용합니다.

설치: 게임을 종료하고 ZIP 전체를 푼 뒤 Install.cmd를 실행합니다.
The Loopler.exe가 있는 폴더를 선택합니다. Steam에서 게임을 실행한 뒤
Settings > Language에서 태극기를 선택하면 한국어로 표시됩니다.
제거: Remove.cmd를 실행하고 같은 폴더를 선택합니다.
이미 설치한 상태의 중복 설치와 일부 파일만 설치된 상태도 처리합니다.
중간에 설치가 중단되면 같은 설치기를 다시 실행하여 복구하세요.
원본 백업과 복구 기록: %LOCALAPPDATA%\\TheLooplerKoreanPatch\\working_private

적용 범위: 한국어 번역표 1,331행, 직접 표시 문구, 코드 문구 35종,
Steam 업적 47개의 게임 내 이름·설명 연결, 한글 글꼴 및 언어 선택 버튼.
원본에 포함된 LanaPixel 글꼴을 활용합니다. 게임 규칙·수치·업적 조건과
저장 형식은 변경하지 않습니다. 검수용 Steam 차단 코드는 포함하지 않습니다.

게임/제작사 로고, 제작진 고유 이름, 키 표식, 작은 장식 글자, 비활성 이전
홍보물의 픽셀 글자는 유지합니다. 음악·효과음과 Steam 외부 화면은 유지합니다.
모든 무작위 회차와 조합을 끝까지 플레이한 것은 아닙니다.
업데이트 후 지원하지 않는 파일에는 강제로 적용하지 않습니다.

게임 원본은 포함하지 않았습니다. 설치·제거 도구와 차이 파일만 들어 있습니다.
xdelta3: Apache License 2.0. 전문은 licenses 폴더에 있습니다.
''','utf-8-sig')
tool_root=ROOT/'tasks/SUPERREAP_DEMO/tools/third_party/xdelta3-3.2.0'
encoder=tool_root/'extracted/xdelta3-3.2.0-windows-x86_64/xdelta3.exe'
(release/'tools').mkdir();shutil.copy2(encoder,release/'tools/xdelta3.exe')
(release/'licenses').mkdir();shutil.copy2(tool_root/'LICENSE-APACHE-2.0.txt',release/'licenses/xdelta3-APACHE-2.0.txt')
(release/'patches').mkdir()
baseline=json.loads((EXTRACT/'baseline.json').read_text('utf-8'))['files']
changes=[];roundtrips=[]
for f in baseline:
    name=f['path'];a=SOURCE/name;b=CANDIDATE/name
    assert sha(a)==f['sha256']
    if sha(a)==sha(b):continue
    i=len(changes);forward=f'patches/{i:02}.forward.xdelta';reverse=f'patches/{i:02}.reverse.xdelta'
    for source,target,path,label in [(a,b,forward,'forward'),(b,a,reverse,'reverse')]:
        subprocess.run([str(encoder),'-e','-f','-s',str(source),str(target),str(release/path)],check=True,capture_output=True)
        recovered=scratch/f'{i:02}.{label}.recovered'
        subprocess.run([str(encoder),'-d','-f','-s',str(source),str(release/path),str(recovered)],check=True,capture_output=True)
        assert sha(recovered)==sha(target)
        roundtrips.append({'path':name,'direction':label,'status':'PASS','sha256':sha(recovered)})
    changes.append(dict(path=name,original_sha256=sha(a),patched_sha256=sha(b),forward=forward,reverse=reverse))
    print('DELTA PASS',name,flush=True)
assert len(changes)==7,len(changes)
payload=[dict(path=p.relative_to(release).as_posix(),size=p.stat().st_size,sha256=sha(p)) for p in sorted(release.rglob('*')) if p.is_file()]
manifest=dict(game_id='THE_LOOPLER',steam_build='25262314',version='1.0.0',candidate='ko_1.0.0_c04',baseline=baseline,changes=changes,payload=payload)
write_json(release/'manifest.json',manifest)
allow={'Install.cmd','Remove.cmd','Patch.ps1','ChooseGame.ps1','README.txt','manifest.json','tools/xdelta3.exe','licenses/xdelta3-APACHE-2.0.txt'}|{c[k] for c in changes for k in ('forward','reverse')}
assert {p.relative_to(release).as_posix() for p in release.rglob('*') if p.is_file()}==allow
archive=scratch/(release.name+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for path in sorted(allow):z.write(release/path,path)
with zipfile.ZipFile(archive) as z:
    assert set(z.namelist())==allow and z.testzip() is None
    z.extractall(scratch/'from_final_zip')
for p in allow:assert sha(release/p)==sha(scratch/'from_final_zip'/p)
write_json(scratch/'package.json',{'status':'PASS','candidate':'ko_1.0.0_c04','zip_sha256':sha(archive),'manifest_sha256':sha(release/'manifest.json'),'allowed_files':sorted(allow),'roundtrips':roundtrips,'final_zip_tests':'NOT_RUN','release_copy':'NOT_RUN'})
print('PACKAGE PASS',len(changes),'files',archive.stat().st_size,'bytes')
