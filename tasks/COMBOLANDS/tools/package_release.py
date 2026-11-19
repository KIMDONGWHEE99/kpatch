"""최종 후보의 차이 파일과 설치기만 묶어 개인용 배포 ZIP을 만듭니다."""
from common import *
import shutil, subprocess, zipfile, datetime

candidate_id='ko_v010_c11'
candidate=ROOT/'build_candidate/COMBOLANDS'/candidate_id
release=ROOT/'release_output/COMBOLANDS_KOREAN_PATCH_1.0.0'
assert not release.exists()
release.mkdir(parents=True)
baseline=json.loads((WORK/'baseline.json').read_text(encoding='utf8'))
originals={r['path']:r for r in baseline['files']}
files={p.relative_to(candidate/'game').as_posix():p for p in (candidate/'game').rglob('*') if p.is_file()}
assert set(originals)<=set(files)
build=json.loads((candidate/'build.json').read_text(encoding='utf8'))
validation=json.loads((candidate/'static_validation.json').read_text(encoding='utf8'))
assert validation['status']=='PASS' and validation['canonical_sha256']==sha(WORK/'canonical_translation.json')
assert build['canonical_sha256']==sha(WORK/'canonical_translation.json')
tool_root=ROOT/'tasks/SUPERREAP_DEMO/tools/third_party/xdelta3-3.2.0'
encoder=tool_root/'extracted/xdelta3-3.2.0-windows-x86_64/xdelta3.exe'
decoder=encoder
(release/'tools').mkdir();(release/'licenses').mkdir();(release/'patches').mkdir()
shutil.copy2(decoder,release/'tools/xdelta3.exe')
shutil.copy2(tool_root/'LICENSE-APACHE-2.0.txt',release/'licenses/xdelta3-APACHE-2.0.txt')
shutil.copy2(ROOT/'tasks/PIBCREMENTAL_DEMO/third_party/NotoSansKR/OFL.txt',release/'licenses/NotoSansKR-OFL.txt')
script=(ROOT/'tasks/COMBOLANDS/release_template/Patch.ps1').read_text(encoding='utf8')
(release/'Patch.ps1').write_text(script,encoding='utf-8-sig')
for filename,mode in [('Install.cmd','Install'),('Remove.cmd','Uninstall')]:
    (release/filename).write_text('@echo off\ncd /d "%~dp0"\npowershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Patch.ps1" -Mode '+mode+' %*\nset "PATCH_EXIT=%ERRORLEVEL%"\npause\nexit /b %PATCH_EXIT%\n',encoding='ascii',newline='\r\n')
(release/'README.txt').write_text('''Combolands 한국어 패치 1.0.0

대상: Windows Steam 빌드 24989173 / 게임 버전 1.0.6

설치
게임을 종료하고 ZIP을 풀어 Install.cmd를 실행합니다.
기본 설치 위치: D:\\steam\\steamapps\\common\\Combolands
다른 위치는 PowerShell에서 다음과 같이 지정합니다.
  .\\Patch.ps1 -Mode Install -GameDirectory "게임 폴더 전체 경로"
설치 후 Steam에서 평소처럼 실행하면 됩니다. 별도의 언어 선택은 없습니다.

제거
게임을 종료하고 Remove.cmd를 실행합니다. 다른 위치는 -Mode Uninstall과
-GameDirectory를 사용합니다. 사용자 저장과 게임 설정은 변경하지 않습니다.
원본 백업은 %LOCALAPPDATA%\\CombolandsKoreanPatch\\working_private 아래에
게임 경로별로 보관하며 설치기에서 정확한 경로를 안내합니다.
설치 중 중단되었다면 같은 설치기를 다시 실행하면 이전 작업을 복구합니다.
업데이트되었거나 다른 내용의 게임 파일에는 강제로 적용하지 않습니다.

반영 범위
메뉴, 설정, 건물·아이템·효과 설명, 도움말, 의회·퀘스트, 승패·해금,
의견 양식과 기능 그림의 한국어 표시 및 한글 글꼴을 반영했습니다.
게임 제목, 제작사·Steam 로고, 제작진 이름과 기술용 표기는 유지합니다.
원본 게임 파일 대신 변경 차이 파일과 설치·제거 도구만 포함합니다.

검수 범위
번역 위치 1,833곳과 코드 25곳을 파일에서 대조했습니다.
제작 중 실제 게임에서 메뉴·설정·진행·상점·툴팁·승리·해금 화면을
확인했습니다. 사용자 요청에 따라 추가 플레이 검수와 설치 실패 상황의
반복 시험을 수행하지 않았습니다. 최종 후보의 모든 화면·전체 분기를 끝까지
검증한 것은 아닙니다. 최종 파일 대조와 차이 파일 복원 확인은 수행합니다.

포함 소프트웨어
Noto Sans KR (굵기 600): SIL Open Font License 1.1, licenses 폴더 참조.
https://github.com/google/fonts/tree/main/ofl/notosanskr
xdelta3 3.2.0: Apache License 2.0, licenses 폴더 참조.
https://github.com/jmacd/xdelta
한국어 표시 보조 코드와 설치 도구: 이 패치를 위해 작성했습니다.
''',encoding='utf-8-sig')
scratch=WORK/'package_1.0.0'
scratch.mkdir(exist_ok=False)
empty=scratch/'empty';empty.write_bytes(b'')
changes=[];roundtrips=[]
for path,target in sorted(files.items()):
    source=SOURCE/path if path in originals else empty
    original_hash=originals[path]['sha256'] if path in originals else None
    target_hash=sha(target)
    if original_hash==target_hash:continue
    index=len(changes)
    forward=f'patches/{index:02}.forward.xdelta'
    reverse=f'patches/{index:02}.reverse.xdelta' if original_hash else None
    subprocess.run([str(encoder),'-e','-9','-s',str(source),str(target),str(release/forward)],check=True,capture_output=True)
    restored=scratch/f'{index:02}.forward'
    subprocess.run([str(decoder),'-d','-s',str(source),str(release/forward),str(restored)],check=True,capture_output=True)
    assert sha(restored)==target_hash
    if reverse:
        subprocess.run([str(encoder),'-e','-9','-s',str(target),str(source),str(release/reverse)],check=True,capture_output=True)
        restored=scratch/f'{index:02}.reverse'
        subprocess.run([str(decoder),'-d','-s',str(target),str(release/reverse),str(restored)],check=True,capture_output=True)
        assert sha(restored)==original_hash
    changes.append(dict(path=path,original_sha256=original_hash,patched_sha256=target_hash,forward=forward,reverse=reverse))
    roundtrips.append(dict(path=path,forward='PASS',reverse='PASS' if reverse else 'NOT_APPLICABLE',original_sha256=original_hash,patched_sha256=target_hash))
    print(path,flush=True)
payload=[dict(path=p.relative_to(release).as_posix(),sha256=sha(p),size=p.stat().st_size) for p in sorted(release.rglob('*')) if p.is_file()]
manifest=dict(game_id='COMBOLANDS',steam_build='24989173',version='1.0.0',candidate=candidate_id,baseline=baseline['files'],changes=changes,payload=payload)
save_json(release/'manifest.json',manifest)
allowed={'Install.cmd','Remove.cmd','Patch.ps1','README.txt','manifest.json','tools/xdelta3.exe','licenses/xdelta3-APACHE-2.0.txt','licenses/NotoSansKR-OFL.txt'}
allowed.update(c['forward'] for c in changes);allowed.update(c['reverse'] for c in changes if c['reverse'])
assert {p.relative_to(release).as_posix() for p in release.rglob('*') if p.is_file()}==allowed
archive=release.parent/(release.name+'.zip')
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for p in sorted(release.rglob('*')):
        if p.is_file():z.write(p,p.relative_to(release).as_posix())
extracted=scratch/'from_final_zip'
with zipfile.ZipFile(archive) as z:
    assert set(z.namelist())==allowed and z.testzip() is None
    z.extractall(extracted)
for rel in allowed:assert sha(extracted/rel)==sha(release/rel)
save_json(scratch/'package_validation.json',dict(status='PASS',candidate=candidate_id,zip_sha256=sha(archive),manifest_sha256=sha(release/'manifest.json'),files=len(allowed),changes=len(changes),roundtrips=roundtrips,extracted=str(extracted),source_assets_in_zip=0))
inputs=candidate/'inputs';inputs.mkdir(exist_ok=True)
for name in ['canonical_translation.json','canonical_code.json','canonical_feedback.json','required_characters.json']:
    shutil.copy2(WORK/name,inputs/name)
save_json(candidate/'provenance.json',dict(candidate=candidate_id,steam_build='24989173',build_sha256=sha(candidate/'build.json'),inputs=[dict(path=p.name,sha256=sha(p)) for p in sorted(inputs.iterdir())],tools=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted((ROOT/'tasks/COMBOLANDS/tools').glob('*.py'))],game_files=[dict(path=path,sha256=sha(p),size=p.stat().st_size) for path,p in sorted(files.items())]))
print('ZIP',archive,'bytes',archive.stat().st_size,flush=True)
