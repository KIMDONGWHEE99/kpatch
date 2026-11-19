"""최종 ZIP을 만들고 꺼낸 설치기로 원본 설치·제거·중복 적용을 시험합니다."""
from common import *
import zipfile,subprocess,os
build='ko_v003';candidate=ROOT/'build_candidate/SILKY_RAILS'/build;release=ROOT/'release_output/SILKY_RAILS_KOREAN_PATCH_1.0.0';scratch=WORK/'package';assert not release.exists();release.mkdir(parents=True);scratch.mkdir(exist_ok=True)
assert json.loads((WORK/(build+'_independent.json')).read_text())['status']=='PASS'
template=ROOT/'release_output/MARCH_AND_CONQUER_DEMO_KOREAN_PATCH_1.0.0'
for name in ['Patch.ps1','ChooseGame.ps1','Install.cmd','Remove.cmd']:
 s=(template/name).read_text(encoding='utf-8-sig')
 for a,b in [('March and Conquer Demo','Silky Rails'),('MARCH_AND_CONQUER_DEMO','SILKY_RAILS'),('MarchConquerKoreanPatch','SilkyRailsKoreanPatch'),('25323013','25487146'),('5203110','3870990'),('.march-korean-new','.silky-korean-new')]:s=s.replace(a,b)
 (release/name).write_text(s,encoding='utf-8-sig' if name.endswith('.ps1') else 'utf-8')
(release/'README.txt').write_text('''Silky Rails 한국어 패치 1.0.0
지원: Windows Steam 앱 3870990, 빌드 25487146.

게임 종료 후 Install.cmd 실행 → 게임 폴더 선택.
제거는 Remove.cmd 실행 → 같은 폴더 선택.
기존 포르투갈어 항목을 한국어로 대체합니다. 새 설정은 한국어로 시작합니다.
기존 저장이 있다면 설정의 언어 목록에서 한국어를 선택하세요.

범위: 14개 번역표 985항목, 직접 표시 문구 283곳, 코드 문구 65곳,
한글 대체 글꼴 연결. 게임 규칙·수치·저장 형식은 변경하지 않습니다.
게임 제목·로고·제작자 이름·Discord·키 이름과 일부 개발용 임시 문구는 유지합니다.

사용자 요청으로 검수는 최소화했습니다. 모든 분기·회차·이미지 속 문구·개발 화면을
검수한 완성 보증판이 아닙니다. 실제 확인 범위와 설치 시험은 별도 결과 보고서에 기록합니다.

원본 백업·복구 기록: %LOCALAPPDATA%\SilkyRailsKoreanPatch\working_private
설치 실패 시 시작 전 상태로 되돌립니다. 강제 중단 후 같은 설치기를 다시 실행하면 복구합니다.
게임 업데이트로 파일이 달라진 경우 강제 적용하지 않습니다.
게임 원본·전체 게임 파일·검수 코드는 이 ZIP에 포함하지 않았습니다.
Noto Sans KR (SIL OFL 1.1), xdelta3 3.2.0 (Apache 2.0). licenses 폴더 참고.
''',encoding='utf-8-sig')
toolroot=ROOT/'tasks/SUPERREAP_DEMO/tools/third_party/xdelta3-3.2.0';encoder=toolroot/'extracted/xdelta3-3.2.0-windows-x86_64/xdelta3.exe'
for d in ['tools','licenses','patches']:(release/d).mkdir()
shutil.copy2(encoder,release/'tools/xdelta3.exe');shutil.copy2(toolroot/'LICENSE-APACHE-2.0.txt',release/'licenses/xdelta3-APACHE-2.0.txt');shutil.copy2(ROOT/'tasks/TFC2/third_party/NotoSansKR/OFL.txt',release/'licenses/NotoSansKR-OFL.txt')
base=json.loads((WORK/'baseline.json').read_text());changes=[]
for row in base:
 name=row['path'];a=BASE/name;b=candidate/name;assert sha(a.read_bytes())==row['sha256']
 if sha(a.read_bytes())==sha(b.read_bytes()):continue
 i=len(changes);forward=f'patches/{i:02}.forward.xdelta';reverse=f'patches/{i:02}.reverse.xdelta'
 for source,target,path,label in [(a,b,forward,'forward'),(b,a,reverse,'reverse')]:
  subprocess.run([str(encoder),'-e','-f','-s',str(source),str(target),str(release/path)],check=True,capture_output=True)
  recovered=scratch/f'{i:02}.{label}.recovered';subprocess.run([str(encoder),'-d','-f','-s',str(source),str(release/path),str(recovered)],check=True,capture_output=True);assert sha(recovered.read_bytes())==sha(target.read_bytes())
 changes.append(dict(path=name,original_sha256=sha(a.read_bytes()),patched_sha256=sha(b.read_bytes()),forward=forward,reverse=reverse));print('차이 복원',name,flush=True)
assert len(changes)==4
payload=[dict(path=p.relative_to(release).as_posix(),size=p.stat().st_size,sha256=sha(p.read_bytes())) for p in sorted(release.rglob('*')) if p.is_file()]
save(release/'manifest.json',dict(game_id='SILKY_RAILS',steam_build='25487146',version='1.0.0',candidate=build,baseline=base,changes=changes,payload=payload))
allow={'Install.cmd','Remove.cmd','Patch.ps1','ChooseGame.ps1','README.txt','manifest.json','tools/xdelta3.exe','licenses/xdelta3-APACHE-2.0.txt','licenses/NotoSansKR-OFL.txt'}|{r[k] for r in changes for k in ['forward','reverse']};assert {p.relative_to(release).as_posix() for p in release.rglob('*') if p.is_file()}==allow
archive=release.parent/(release.name+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for name in sorted(allow):z.write(release/name,name)
with zipfile.ZipFile(archive) as z:assert z.testzip() is None;z.extractall(scratch/'from_final_zip')
test=scratch/'설치 시험/game';assert not test.exists();shutil.copytree(BASE,test);env=os.environ.copy();env['LOCALAPPDATA']=str(scratch/'install_state');results=[]
for mode in ['Install','Install','Uninstall','Uninstall','Install']:
 command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(scratch/'from_final_zip/Patch.ps1'),'-Mode',mode,'-GameDirectory',str(test)]
 p=subprocess.run(command,env=env,capture_output=True,timeout=120);(scratch/f'test_{len(results)}.log').write_bytes(p.stdout+p.stderr);assert p.returncode==0,p.stderr.decode(errors='replace')
 expected=candidate if mode=='Install' else BASE
 for r in base:assert sha((test/r['path']).read_bytes())==sha((expected/r['path']).read_bytes()),r['path']
 results.append(dict(mode=mode,status='PASS'));print('설치기',mode,'PASS',flush=True)
save(scratch/'package.json',dict(candidate=build,zip_sha256=sha(archive.read_bytes()),files=len(allow),changed=len(changes),roundtrip='PASS',tests=results))
print('최종 ZIP',archive.stat().st_size)
