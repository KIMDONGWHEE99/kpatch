"""차이 파일의 양방향 복원을 확인하고 명시적 허용 목록으로 ZIP을 구성합니다."""
from common import *
import shutil,zipfile

candidate_id='ko_v002'
candidate=ROOT/'build_candidate/BOREWORKS_DEMO'/candidate_id
release=ROOT/'release_output/BOREWORKS_DEMO_KOREAN_PATCH_1.0.0'
scratch=WORK/'package_v1';scratch.mkdir(exist_ok=True)
assert not release.exists()
release.mkdir(parents=True)
template=ROOT/'release_output/SPELLBOUND_SHELVED_KOREAN_PATCH_1.0.0'
for name in ('Patch.ps1','ChooseGame.ps1'):
    s=(template/name).read_text(encoding='utf-8-sig')
    for a,b in [('Spellbound & Shelved','BOREWORKS Demo'),('SPELLBOUND_SHELVED','BOREWORKS_DEMO'),('SpellboundShelved','Boreworks'),('spellboundshelved','boreworks'),('25171813','23942533'),('5097840','4829140')]:s=s.replace(a,b)
    if name=='ChooseGame.ps1':s=s.replace("(Join-Path $common 'BOREWORKS Demo')","(Join-Path $common 'Boreworks Demo')")
    # 이 게임에는 windows 하위 폴더가 없습니다.
    s='\n'.join(line for line in s.splitlines() if "'windows\\Boreworks.exe'" not in line)+'\n'
    (release/name).write_text(s,encoding='utf-8-sig')
for name,mode in [('Install.cmd','Install'),('Remove.cmd','Uninstall')]:
    text='@echo off\r\nchcp 65001 >nul\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Patch.ps1" -Mode '+mode+'\r\necho.\r\npause\r\n'
    (release/name).write_bytes(text.encode('utf-8'))
(release/'README.txt').write_text('''BOREWORKS Demo 한국어 패치 1.0.0

지원: Steam 앱 4829140, 빌드 23942533, 게임 v1.0.5, Windows x64.
이 버전과 원본 해시가 일치하는 게임에만 적용됩니다.

설치: 게임을 종료하고 ZIP 전체를 푼 뒤 Install.cmd를 실행합니다.
게임 폴더를 선택하고 설치를 누릅니다. 이후 Steam에서 실행하세요.
제거: Remove.cmd를 실행하고 같은 게임 폴더를 선택합니다.
이미 설치한 상태에서 다시 설치하거나 일부만 설치된 경우에도 복구합니다.
설치 중 중단되면 같은 설치기를 다시 실행하면 시작 전 상태를 복구한 뒤 진행합니다.
원본 백업과 복구 기록: %LOCALAPPDATA%\\BoreworksKoreanPatch\\working_private

적용 범위: 번역표 505개, 코드 직접 문구 56곳, 한글 글꼴 4개 및 연결.
게임 규칙, 수치, 저장 형식, Steam 연결 코드는 변경하지 않습니다.
로고 BOREWORKS, 제작진 이름, 식별 번호, 키 이름, 경로, 숫자 기호는 유지합니다.
원본 음악과 효과음은 유지합니다. 음성 더빙 패치가 아닙니다.
글자 크기는 접근성 설정에서 조절할 수 있습니다.

검수: 실제 NVIDIA 그래픽에서 21개 메뉴, 진행 4단계, 글꼴/크기 5설정 순회.
시작 안내와 저장·불러오기 흐름을 별도 실행 검수했습니다.
무작위 소행성의 모든 플레이 회차를 끝까지 수행한 것은 아닙니다.

업데이트로 파일이 바뀌면 강제 적용하지 않습니다. 지원 버전용 패치가 필요합니다.
이 ZIP에는 게임 원본을 넣지 않았으며 차이 파일과 설치 도구만 포함합니다.
글꼴: Noto Sans KR (SIL OFL 1.1). 도구: xdelta3 (Apache 2.0).
라이선스 전문은 licenses 폴더에 포함합니다.
''',encoding='utf-8-sig')
tool_root=ROOT/'tasks/SUPERREAP_DEMO/tools/third_party/xdelta3-3.2.0'
encoder=tool_root/'extracted/xdelta3-3.2.0-windows-x86_64/xdelta3.exe'
(release/'tools').mkdir();shutil.copy2(encoder,release/'tools/xdelta3.exe')
(release/'licenses').mkdir()
shutil.copy2(tool_root/'LICENSE-APACHE-2.0.txt',release/'licenses/xdelta3-APACHE-2.0.txt')
shutil.copy2(ROOT/'tasks/TFC2/third_party/NotoSansKR/OFL.txt',release/'licenses/NotoSansKR-OFL.txt')
(release/'patches').mkdir()
changed=['Boreworks.pck','data_Boreworks_windows_x86_64/Boreworks.dll'];changes=[]
for i,name in enumerate(changed):
    a=BASE/name;b=candidate/name
    forward=f'patches/{i:02}.forward.xdelta';reverse=f'patches/{i:02}.reverse.xdelta'
    for source,target,path,label in ((a,b,forward,'forward'),(b,a,reverse,'reverse')):
        subprocess.run([str(encoder),'-e','-f','-s',str(source),str(target),str(release/path)],check=True,capture_output=True)
        recovered=scratch/f'{i:02}.{label}.recovered'
        subprocess.run([str(encoder),'-d','-f','-s',str(source),str(release/path),str(recovered)],check=True,capture_output=True)
        assert sha(recovered.read_bytes())==sha(target.read_bytes())
    changes.append(dict(path=name,original_sha256=sha(a.read_bytes()),patched_sha256=sha(b.read_bytes()),forward=forward,reverse=reverse))
payload=[dict(path=p.relative_to(release).as_posix(),size=p.stat().st_size,sha256=sha(p.read_bytes())) for p in sorted(release.rglob('*')) if p.is_file()]
manifest=dict(game_id='BOREWORKS_DEMO',steam_build='23942533',version='1.0.0',candidate=candidate_id,baseline=json.loads((WORK/'baseline.json').read_text(encoding='utf-8')),changes=changes,payload=payload)
save_json(release/'manifest.json',manifest)
allow={'Install.cmd','Remove.cmd','Patch.ps1','ChooseGame.ps1','README.txt','manifest.json','tools/xdelta3.exe','licenses/xdelta3-APACHE-2.0.txt','licenses/NotoSansKR-OFL.txt'}|{c[k] for c in changes for k in ('forward','reverse')}
assert {p.relative_to(release).as_posix() for p in release.rglob('*') if p.is_file()}==allow
archive=release.with_suffix('.zip')
# 이름의 마지막 .0을 확장자로 해석하지 않도록 전체 폴더 이름 뒤에 붙입니다.
archive=release.parent/(release.name+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for path in sorted(allow):z.write(release/path,path)
with zipfile.ZipFile(archive) as z:
    assert set(z.namelist())==allow and z.testzip() is None
    z.extractall(scratch/'from_final_zip')
for p in allow:assert sha((release/p).read_bytes())==sha((scratch/'from_final_zip'/p).read_bytes())
report=dict(candidate=candidate_id,archive=str(archive),zip_sha256=sha(archive.read_bytes()),manifest_sha256=sha((release/'manifest.json').read_bytes()),allowed_files=sorted(allow),roundtrip_forward='PASS',roundtrip_reverse='PASS',final_zip_tests='NOT_RUN')
save_json(scratch/'package.json',report)
print(json.dumps(report))
