"""허용한 차이 파일과 설치·제거 도구만 최종 ZIP에 넣는다."""
import json
import hashlib
import shutil
import subprocess
import zipfile
from pathlib import Path
from pck_tools import ROOT, BASELINE, WORK

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

candidate_id='ko_1.0.0_c02'
candidate=ROOT/'build_candidate/SPELLBOUND_SHELVED'/candidate_id/'windows'
release=ROOT/'release_output/SPELLBOUND_SHELVED_KOREAN_PATCH_1.0.0'
scratch=WORK/'package_1.0.0_r3'
assert not scratch.exists()
if release.exists():
    shutil.copy2(release.parent/(release.name+'.zip'),WORK/'package_1.0.0_r2/previous_draft.zip')
release.mkdir(parents=True,exist_ok=True);scratch.mkdir(parents=True)
for folder in ['tools','licenses','patches']:(release/folder).mkdir(exist_ok=True)
tool_root=ROOT/'tasks/SUPERREAP_DEMO/tools/third_party/xdelta3-3.2.0'
encoder=tool_root/'extracted/xdelta3-3.2.0-windows-x86_64/xdelta3.exe'
shutil.copy2(encoder,release/'tools/xdelta3.exe')
shutil.copy2(tool_root/'LICENSE-APACHE-2.0.txt',release/'licenses/xdelta3-APACHE-2.0.txt')
shutil.copy2(ROOT/'tasks/TFC2/third_party/NotoSansKR/OFL.txt',release/'licenses/NotoSansKR-OFL.txt')
script=(ROOT/'tasks/COMBOLANDS/release_template/Patch.ps1').read_text(encoding='utf-8-sig')
script=script.replace('Combolands','SpellboundShelved').replace('COMBOLANDS','SPELLBOUND_SHELVED').replace('combolands-korean','spellboundshelved-korean').replace('24989173','25171813').replace("'1.0.1'","'1.0.0'")
old="    $gameRoot = [IO.Path]::GetFullPath($GameDirectory).TrimEnd('\\')"
assert old in script
script=script.replace(old,"    if ([IO.File]::Exists((Join-Path $GameDirectory 'windows\\SpellboundShelved.exe'))) { $GameDirectory=Join-Path $GameDirectory 'windows' }\n"+old)
script=script.replace("    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()", """    # 모듈 자동 로딩 여부에 영향을 받지 않도록 Windows 기본 기능으로 계산합니다.
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $inputStream = [IO.File]::OpenRead($Path)
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($inputStream))).Replace('-','').ToLowerInvariant() }
    finally { $inputStream.Dispose(); $algorithm.Dispose() }""")
(release/'Patch.ps1').write_text(script,encoding='utf-8-sig')
script=script.replace("$null -ne $journal -and $journal.phase -eq 'APPLYING'", "$null -ne $journal -and $journal.phase -in @('APPLYING','COMPLETE')")
(release/'Patch.ps1').write_text(script,encoding='utf-8-sig')
chooser=(ROOT/'tasks/COMBOLANDS/release_template/ChooseGame.ps1').read_text(encoding='utf-8-sig')
chooser=chooser.replace('Combolands','SpellboundShelved').replace('4075620','5097840').replace('1.0.1','1.0.0')
chooser=chooser.replace("(Join-Path $common 'SpellboundShelved')","(Join-Path $common 'Spellbound & Shelved')")
chooser=chooser.replace("[IO.Directory]::Exists((Join-Path $resolved 'SpellboundShelved_Data'))","[IO.File]::Exists((Join-Path $resolved 'SpellboundShelved.pck'))")
needle="        if ([IO.File]::Exists((Join-Path $resolved 'SpellboundShelved.exe')) -and"
assert needle in chooser
chooser=chooser.replace(needle,"        if ([IO.File]::Exists((Join-Path $resolved 'windows\\SpellboundShelved.exe'))) { $resolved=Join-Path $resolved 'windows' }\n"+needle)
chooser=chooser.replace("'SpellboundShelved 한국어 패치 1.0.0'","'Spellbound & Shelved 한국어 패치 1.0.0'")
(release/'ChooseGame.ps1').write_text(chooser,encoding='utf-8-sig')
for filename,mode in [('Install.cmd','Install'),('Remove.cmd','Uninstall')]:
    (release/filename).write_text('@echo off\ncd /d "%~dp0"\npowershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Patch.ps1" -Mode '+mode+' %*\nset "PATCH_EXIT=%ERRORLEVEL%"\npause\nexit /b %PATCH_EXIT%\n',encoding='ascii',newline='\r\n')
(release/'README.txt').write_text('''Spellbound & Shelved 한국어 패치 1.0.0

지원 버전: Windows / Steam 빌드 25171813 (앱 번호 5097840)

설치: 게임을 종료하고 ZIP을 모두 푼 뒤 Install.cmd를 더블클릭하세요.
찾은 게임 폴더를 확인하고 [설치]를 누르세요. 다른 위치라면 [찾아보기…]를
사용하세요. Steam의 Spellbound & Shelved 폴더 또는 그 안의 windows 폴더를
선택할 수 있습니다. 설치 후 Steam에서 평소처럼 게임을 실행하세요.
처음 실행하면 한국어를 사용합니다. 기존 언어 설정이 있다면 메뉴의 Language에서
한국어를 선택하세요. 영어·독일어·스페인어·프랑스어도 그대로 선택할 수 있습니다.

제거: 게임을 종료하고 Remove.cmd를 더블클릭해 [제거]를 누르세요.
원본 백업은 %LOCALAPPDATA%\\SpellboundShelvedKoreanPatch\\working_private에
게임 경로별로 보관됩니다. 설치 도중 중단되었으면 같은 설치기를 다시 실행하세요.
지원하지 않는 버전·변조·손상 파일에는 강제로 적용하지 않습니다.
저장 파일과 Steam 업적은 설치·제거 과정에서 변경하지 않습니다.

번역 범위: 메뉴·설정·도움말·대사·활동 설명·업적·업그레이드·결과·개발 화면,
책 제목 2,625개, 노움과 일반 손님 이름 34개. 한국어 번역 키는 총 306개이며
책 제목은 별도의 목록입니다. 본문·굵은 글씨용 한글 글꼴을 포함합니다.

유지 표기: 게임 제목과 원본 로고의 A COZY LIBRARY IDLER 문구, 제작사 로고·주소,
제작진 이름, 실존 게스트 이름(Skoottie, RCE, Sifd, Kosh, Dex, Tristan, Nookrium,
Wanderbots, Aliensrock, SplatterCat, Flotidus, CG Grows), 기술 이름과 단축키.
개발용 참고 그림과 다른 운영체제의 게임 파일은 변경하지 않습니다.

검수: 위치별 번역 대조와 코드 재분석을 수행했습니다. 실제 화면 검수와 최종 ZIP
설치·복구 시험의 최종 결과는 ZIP 밖의 결과 보고서에 기록합니다.
전체 플레이 시간과 모든 무작위 상황을 끝까지 검증했다는 뜻은 아닙니다.

이 패키지에는 원본 게임 자산 대신 차이 파일과 설치·제거 도구만 포함합니다.
Noto Sans KR: SIL Open Font License 1.1 (licenses 폴더).
https://github.com/google/fonts/tree/main/ofl/notosanskr
xdelta3 3.2.0: Apache License 2.0 (licenses 폴더).
https://github.com/jmacd/xdelta
''',encoding='utf-8-sig')
source=BASELINE/'windows/SpellboundShelved.pck';target=candidate/'SpellboundShelved.pck'
for kind,a,b in [('forward',source,target),('reverse',target,source)]:
    delta=release/f'patches/00.{kind}.xdelta'
    subprocess.run([str(encoder),'-f','-e','-9','-s',str(a),str(b),str(delta)],check=True,capture_output=True)
    rebuilt=scratch/f'{kind}.pck'
    subprocess.run([str(encoder),'-d','-s',str(a),str(delta),str(rebuilt)],check=True,capture_output=True)
    assert sha(rebuilt)==sha(b)
baseline=[{'path':f.name,'size':f.stat().st_size,'sha256':sha(f)} for f in sorted((BASELINE/'windows').iterdir()) if f.is_file()]
payload=[{'path':f.relative_to(release).as_posix(),'size':f.stat().st_size,'sha256':sha(f)} for f in sorted(release.rglob('*')) if f.is_file() and f.name!='manifest.json']
manifest={'game_id':'SPELLBOUND_SHELVED','steam_build':'25171813','version':'1.0.0','candidate':candidate_id,'baseline':baseline,'changes':[{'path':'SpellboundShelved.pck','original_sha256':sha(source),'patched_sha256':sha(target),'forward':'patches/00.forward.xdelta','reverse':'patches/00.reverse.xdelta'}],'payload':payload}
(release/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
allow={'Install.cmd','Remove.cmd','Patch.ps1','ChooseGame.ps1','README.txt','manifest.json','tools/xdelta3.exe','licenses/xdelta3-APACHE-2.0.txt','licenses/NotoSansKR-OFL.txt','patches/00.forward.xdelta','patches/00.reverse.xdelta'}
assert {f.relative_to(release).as_posix() for f in release.rglob('*') if f.is_file()}==allow
archive=release.parent/(release.name+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for f in sorted(release.rglob('*')):
        if f.is_file():z.write(f,f.relative_to(release).as_posix())
with zipfile.ZipFile(archive) as z:
    assert set(z.namelist())==allow and z.testzip() is None
    z.extractall(scratch/'from_final_zip')
for path in allow:assert sha(release/path)==sha(scratch/'from_final_zip'/path)
report={'candidate':candidate_id,'zip_sha256':sha(archive),'manifest_sha256':sha(release/'manifest.json'),'archive':str(archive),'allowed_files':sorted(allow),'roundtrip_forward':'PASS','roundtrip_reverse':'PASS','final_zip_tests':'NOT_RUN'}
(scratch/'package.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
