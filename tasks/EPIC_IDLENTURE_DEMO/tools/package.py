"""허용 목록만으로 차이 패치 ZIP을 만들고 정·역방향 복원과 압축 해제를 검증합니다."""
from common import *
import zipfile,subprocess
build='ko_c03';candidate=ROOT/'build_candidate/EPIC_IDLENTURE_DEMO'/build;release=ROOT/'release_output/EPIC_IDLENTURE_DEMO_KOREAN_PATCH_1.0.0';scratch=WORK/'package';assert not release.exists();release.mkdir(parents=True);scratch.mkdir(exist_ok=True)
assert json.loads((WORK/(build+'_independent.json')).read_text(encoding='utf8'))['status']=='PASS'
template=ROOT/'release_output/MARCH_AND_CONQUER_DEMO_KOREAN_PATCH_1.0.0'
replacements=[('March and Conquer Demo.exe','Epic Idlenture.exe'),('March and Conquer Demo_Data','Epic Idlenture_Data'),("Get-Process -Name 'March and Conquer Demo'","Get-Process -Name 'Epic Idlenture'"),('March and Conquer Demo','Epic Idlenture Demo'),('MARCH_AND_CONQUER_DEMO','EPIC_IDLENTURE_DEMO'),('MarchConquerKoreanPatch','EpicIdlentureKoreanPatch'),('25323013','23762546'),('5203110','4114020'),('.march-korean-new','.epic-korean-new')]
for name in ['Patch.ps1','ChooseGame.ps1','Install.cmd','Remove.cmd']:
    s=(template/name).read_text(encoding='utf-8-sig')
    for a,b in replacements:s=s.replace(a,b)
    (release/name).write_text(s,encoding='utf-8-sig' if name.endswith('.ps1') else 'utf-8')
(release/'README.txt').write_text('''Epic Idlenture Demo 한국어 패치 1.0.0
지원: Windows Steam 앱 4114020, 빌드 23762546, 게임 버전 0.2.1.

설치: 게임을 종료하고 Install.cmd를 실행한 뒤 게임 폴더를 선택하세요.
제거: Remove.cmd를 실행하고 같은 폴더를 선택하세요.
설치 후 평소처럼 Steam에서 실행하면 한국어가 적용됩니다.

범위: 자산 문구 1,159곳, 실행 코드의 게임 문구 61곳 및 진단 안내 104곳,
화면 이름 191개 변환표와 한글 글꼴. 숫자·저장 식별자·게임 규칙은 보존합니다.
게임 제목/로고, Steam·SRDebugger 등 제품명, 입력 키, 기술 진단 원문,
Unity 엔진 워터마크 및 사용하지 않는 비활성 개발 화면 시안은 유지합니다.
미해금 항목의 물음표는 게임의 숨김 처리입니다.

첫 화면·설정·전투·관리 창·도움말·대사·패배·종료 화면을 실제 그래픽 장치에서
검수했습니다. 전체 회차를 끝까지 플레이했다는 보증은 아닙니다.
검수 사본은 저장과 Steam 연동을 분리했으며 검수 도구는 배포본에 없습니다.
기존 저장 파일을 삭제하거나 초기화할 필요가 없습니다.

원본 백업·복구 기록: %LOCALAPPDATA%\EpicIdlentureKoreanPatch\working_private
설치 중 실패하면 시작 전 상태로 복원합니다. 강제 종료 후에는 같은 설치기를
다시 실행하여 복구하세요. 게임 업데이트/미지원 파일에는 강제 적용하지 않습니다.
원본 게임 자산·전체 게임 파일·저장 파일·검수 코드는 ZIP에 포함하지 않았습니다.
Noto Sans KR (SIL OFL 1.1), xdelta3 3.2.0 (Apache 2.0). licenses 폴더 참고.
''',encoding='utf-8-sig')
toolroot=ROOT/'tasks/SUPERREAP_DEMO/tools/third_party/xdelta3-3.2.0';encoder=toolroot/'extracted/xdelta3-3.2.0-windows-x86_64/xdelta3.exe'
for d in ['tools','licenses','patches']:(release/d).mkdir()
shutil.copy2(encoder,release/'tools/xdelta3.exe');shutil.copy2(toolroot/'LICENSE-APACHE-2.0.txt',release/'licenses/xdelta3-APACHE-2.0.txt');shutil.copy2(ROOT/'tasks/TFC2/third_party/NotoSansKR/OFL.txt',release/'licenses/NotoSansKR-OFL.txt')
base=json.loads((WORK/'baseline.json').read_text(encoding='utf8'));changes=[]
for row in base:
    name=row['path'];a=BASE/name;b=candidate/name;assert sha(a.read_bytes())==row['sha256']
    if sha(a.read_bytes())==sha(b.read_bytes()):continue
    i=len(changes);forward=f'patches/{i:02}.forward.xdelta';reverse=f'patches/{i:02}.reverse.xdelta'
    for source,target,path,label in [(a,b,forward,'forward'),(b,a,reverse,'reverse')]:
        subprocess.run([str(encoder),'-e','-f','-s',str(source),str(target),str(release/path)],check=True,capture_output=True)
        recovered=scratch/f'{i:02}.{label}.recovered';subprocess.run([str(encoder),'-d','-f','-s',str(source),str(release/path),str(recovered)],check=True,capture_output=True);assert sha(recovered.read_bytes())==sha(target.read_bytes())
    changes.append(dict(path=name,original_sha256=sha(a.read_bytes()),patched_sha256=sha(b.read_bytes()),forward=forward,reverse=reverse));print('차이 복원',name,flush=True)
assert len(changes)==7
payload=[dict(path=p.relative_to(release).as_posix(),size=p.stat().st_size,sha256=sha(p.read_bytes())) for p in sorted(release.rglob('*')) if p.is_file()]
save(release/'manifest.json',dict(game_id='EPIC_IDLENTURE_DEMO',steam_build='23762546',version='1.0.0',candidate=build,baseline=base,changes=changes,payload=payload))
allow={'Install.cmd','Remove.cmd','Patch.ps1','ChooseGame.ps1','README.txt','manifest.json','tools/xdelta3.exe','licenses/xdelta3-APACHE-2.0.txt','licenses/NotoSansKR-OFL.txt'}|{r[k] for r in changes for k in ['forward','reverse']};assert {p.relative_to(release).as_posix() for p in release.rglob('*') if p.is_file()}==allow
archive=release.parent/(release.name+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name in sorted(allow):z.write(release/name,name)
with zipfile.ZipFile(archive) as z:assert z.testzip() is None;z.extractall(scratch/'from_final_zip')
save(scratch/'package.json',dict(candidate=build,zip_sha256=sha(archive.read_bytes()),files=len(allow),changed=len(changes),roundtrip='PASS',bytes=archive.stat().st_size,allowed=sorted(allow)))
print('ZIP',archive.stat().st_size)
