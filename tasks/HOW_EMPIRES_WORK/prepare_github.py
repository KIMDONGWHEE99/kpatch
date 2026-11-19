"""검증된 ZIP과 공개할 문서·설치기만 별도 저장소에 준비합니다."""
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'working_private/HOW_EMPIRES_WORK'
PUBLIC=WORK/'github_publish_20261110'
STAGE=PUBLIC/'staging'
REMOTE='https://github.com/KIMDONGWHEE99/how-empires-work-korean-patch'
TAG='v1.0.1-r2'
NAME='HOW_EMPIRES_WORK_KOREAN_PATCH_1.0.1_r2.zip'

def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text,encoding='utf8',newline='\n')

def main():
    package=read(WORK/'package_1.0.1_r2/package.json')
    tests=read(WORK/'package_1.0.1_r2/installer_tests.json')
    runtime=read(WORK/'progression_fix/runtime_summary.json')
    static=read(WORK/'final_audit_1.0.1/static_summary.json')
    archive=ROOT/'release_output'/NAME
    assert sha(archive)==package['zip_sha256']==tests['zip_sha256']
    assert all(r['status']=='PASS' for r in (tests,runtime,static))
    assert static['candidate_sha256']==runtime['candidate_sha256']==package['changes'][0]['patched_sha256']
    PUBLIC.mkdir(exist_ok=True);assert not STAGE.exists();STAGE.mkdir()
    expected={'ChooseGame.ps1','Install.cmd','Patch.ps1','README.txt','Remove.cmd','manifest.json',
      'licenses/NotoEmoji-OFL.txt','licenses/NotoSansKR-OFL.txt','licenses/NotoSansSymbols2-OFL.txt',
      'licenses/SourceHanSans-OFL.txt','licenses/xdelta3-APACHE-2.0.txt',
      'patches/00.forward.xdelta','patches/00.reverse.xdelta','tools/xdelta3.exe'}
    with zipfile.ZipFile(archive) as z:
        assert len(z.namelist())==len(expected) and set(z.namelist())==expected
        assert z.testzip() is None
        manifest=json.loads(z.read('manifest.json'))
        assert hashlib.sha256(z.read('manifest.json')).hexdigest()==package['manifest_sha256']
        assert {r['path'] for r in manifest['payload']}==expected-{'manifest.json'}
        for item in manifest['payload']:
            data=z.read(item['path']);assert len(data)==item['size'] and hashlib.sha256(data).hexdigest()==item['sha256']
        for name in ('Patch.ps1','ChooseGame.ps1','Install.cmd','Remove.cmd'):
            dest=STAGE/'installer'/name;dest.parent.mkdir(exist_ok=True);dest.write_bytes(z.read(name))
        for name in sorted(n for n in expected if n.startswith('licenses/')):
            dest=STAGE/name;dest.parent.mkdir(exist_ok=True);dest.write_bytes(z.read(name))
        (STAGE/'installer/manifest.json').write_bytes(z.read('manifest.json'))
    passed=sum(r['status']=='PASS' for r in tests['tests'])
    unavailable=sum(r['status']=='NOT_APPLICABLE' for r in tests['tests'])
    download=f'{REMOTE}/releases/download/{TAG}/{NAME}'
    readme=f'''# How Empires Work 한국어 패치 1.0.1

[**한글패치 ZIP 다운로드 — 약 228MB**]({download}) · [버전·검증 안내](docs/VERIFICATION.md)

How Empires Work의 Windows Steam 버전을 위한 비공식 한국어 패치입니다. **Steam 앱 4663730 / 빌드 26482667**을 기준으로 제작했습니다. 원본 게임을 설치한 상태에서 적용하는 차이 패치입니다.

## 설치·제거

1. 게임을 종료하고 위의 **한글패치 ZIP 다운로드**를 누릅니다.
2. ZIP 전체를 새 폴더에 풉니다.
3. `Install.cmd`를 실행하고 `HowEmpiresWork.exe`가 있는 설치 폴더를 선택합니다.
4. Steam에서 게임을 실행합니다. 기존 언어 설정이 있으면 설정에서 **한국어**를 선택합니다.

제거하려면 같은 묶음의 `Remove.cmd`를 실행합니다. 중단된 설치는 같은 설치기로 다시 실행해 복구할 수 있습니다. 원본 백업 위치는 설치 완료 메시지에 표시됩니다. 게임 파일의 내용이 지원 대상과 다르면 설치를 거부합니다.

저장소의 **Code → Download ZIP**은 문서와 설치기 소스 묶음입니다. 실제 설치에는 위의 패치 ZIP을 사용하세요. `installer/` 폴더만으로는 설치할 수 없습니다.

## 1.0.1에서 수정한 문제

- 초기 제작본에서 세금을 모아도 다음 기능이 열리지 않던 오류를 수정했습니다.
- 무역 자동 판매 확인 창에서 금액·상품명이 제대로 채워지지 않던 문제를 수정했습니다.
- 정상 새 게임에서 누적 5원에 **전사 소집**, 10원에 **도적 대응**이 열리는 것을 확인했습니다.

이전 1.0.0을 설치했다면 이전 묶음의 `Remove.cmd`로 원본을 복원한 뒤 이 버전을 설치하세요. **이미 이전판에서 진행이 막힌 저장은 패치 교체만으로 자동 복구되지 않습니다.** 이 배포 설치기는 저장을 변경하지 않으며, 개별 저장 복구 도구는 포함하지 않습니다.

## 한글화·확인 범위

언어표 **2,553행**, 직접 표시 문구 **2,732위치**를 번역하거나 근거를 갖춰 유지했고 한국어 글꼴을 적용했습니다. 새 게임의 초기 진행, 저장·불러오기, 수정한 무역 화면과 최종 ZIP의 설치·복구 {passed}개 시험을 확인했습니다.

전체 회차와 모든 분기를 완주한 검수는 아닙니다. 설치 후 Steam 설치본의 추가 실행은 하지 않았으며, 원본에서도 발생하는 편집기 확장·종료 자원 정리 등의 경고는 남습니다. 제목·로고·이름·원곡 제목·키보드 표기·명령어와 원작 오디오는 유지합니다. [검증 상세](docs/VERIFICATION.md)

원본 게임 파일·개인 저장·검수용 코드는 배포하지 않습니다. 게임의 권리는 원 권리자에게 있으며, 포함된 도구와 글꼴의 라이선스는 패치 ZIP 및 [licenses](licenses)에 있습니다. 이 저장소는 게임 제작사와 무관한 비공식 패치 배포 저장소입니다.

ZIP SHA-256: `{package['zip_sha256']}`
'''
    write(STAGE/'README.md',readme)
    write(STAGE/'CHANGELOG.md','''# 변경 이력

## 1.0.1 r2 — 2026-11-10

- 초기 진행 이벤트 식별자 11곳을 원래 값으로 복구했습니다.
- 무역 표시용 서식 키 2곳을 복구했습니다.
- 새 게임의 세금→모집→과세 기능 진행과 수정된 무역 표시를 검증했습니다.
- 기존 1.0.0 제거 후 설치, 변조 파일 거부, 중복 설치·제거, 중간 실패·강제 중단 복구를 검사했습니다.

이 저장소의 최초 공개 묶음입니다. 문제가 있었던 1.0.0 및 중간 후보는 배포하지 않습니다.
''')
    public={'patch_version':'1.0.1','revision':'r2','steam_app_id':4663730,'steam_build':'26482667',
      'zip_name':NAME,'zip_sha256':package['zip_sha256'],'zip_bytes':archive.stat().st_size,
      'candidate_sha256':static['candidate_sha256'],'locale_rows':2553,'direct_locations':2732,
      'unknown':static['unknown'],'unresolved_extraction_errors':static['unresolved_extraction_errors'],
      'unresolved_format_errors':static['unresolved_format_errors'],'missing_glyph_warnings':0,
      'package_allowlist_files':len(expected),'delta_roundtrips':'PASS',
      'installer_tests_pass':passed,'installer_tests_not_applicable':unavailable,
      'installer_tests':[{'id':r['id'],'status':r['status']} for r in tests['tests']],
      'graphics_scope':'새 게임 초기 자연 진행·저장/불러오기·무역 확인 창 및 동일 자산의 이전 대표 화면 검수',
      'full_playthrough':'NOT_RUN','post_install_steam_launch':'NOT_RUN','automatic_save_repair_in_package':False}
    write(STAGE/'docs/verification.json',json.dumps(public,ensure_ascii=False,indent=2)+'\n')
    write(STAGE/'docs/VERIFICATION.md',f'''# 버전·검증 안내

2026-11-10 · 패치 1.0.1 r2 · Windows Steam 빌드 26482667

| 항목 | 결과 |
| --- | --- |
| 언어표·직접 문구 | 2,553행·2,732위치, 미분류 및 미해결 추출·서식 오류 0 |
| 코드·글꼴 | 코드 103개 독립 재추출, 글꼴 30개 재검사, 글리프 누락 0 |
| 초기 진행 | 자원 지급·기능 강제 해제 없이 세금 징수→모집→과세 기능 해제 확인 |
| 저장·표시 | 저장 불러오기 및 다음 진행 후 저장·재불러오기, 무역 금액·상품명 표시 확인 |
| 묶음 | ZIP 내부 14파일 명시적 허용 목록·해시, 정방향·역방향 복원 일치 |
| 최종 ZIP 설치기 | {passed}개 PASS, {unavailable}개 NOT_APPLICABLE. 이전판 제거 후 교체·중복·변조 거부·중간 실패·강제 중단 복구 포함 |

[시험 항목과 지문](verification.json)에서 실제 결과를 확인할 수 있습니다. 각 시험은 최종 ZIP `{NAME}`을 기준으로 합니다. 검수 사본은 Steam과 저장·설정·로그를 분리했고, 검수용 변경은 배포본에 포함하지 않았습니다.

원본에서도 나타나는 편집기 확장·UID 경로 대체·빈 과제 분류·미니맵·종료 자원 정리 경고는 남습니다. 전체 회차·모든 분기 완주, 설치 후 Steam 설치본 추가 실행은 NOT_RUN입니다. 미래 게임 업데이트가 파일 내용을 바꾸면 새 패치가 필요할 수 있습니다.

이전 1.0.0의 진행 결함은 내부 이벤트 식별자 오역이 원인이었습니다. 기존의 기능 강제 해제 화면 검수로는 정상 초기 진행을 검증할 수 없어 종전 판정을 무효화하고 실제 세금 징수 흐름으로 다시 검사했습니다. 진행이 막힌 이전 저장의 자동 복구는 이 배포 묶음에 포함되지 않습니다.

ZIP 안의 ‘개인용’ 표기는 제작 당시 이력입니다. 공개를 위해 검증된 ZIP을 다시 만들거나 내용을 바꾸지 않았습니다.
''')
    write(STAGE/'installer/README.md','''# 설치기 소스

검증한 패치 ZIP에서 꺼낸 설치·제거기와 파일 목록입니다. 코드 확인용이며 이 폴더만으로는 실행할 수 없습니다. 차이 파일·실행 도구·라이선스를 모두 포함한 [패치 ZIP](../README.md)을 내려받아 설치하세요.
''')
    write(STAGE/'SHA256SUMS.txt',package['zip_sha256']+'  '+NAME+'\n')
    write(STAGE/'.gitattributes','* -text\n')
    write(STAGE/'.gitignore','''# 원본·개인 저장·임시 검수 자료는 포함하지 않습니다.
source_original/
extracted_private/
working_private/
build_candidate/
saves/
*.pck
*.gdc
*.dll
*.zip
*.log
*.tmp
''')
    allowed={'.gitignore','.gitattributes','README.md','CHANGELOG.md','SHA256SUMS.txt','docs/VERIFICATION.md','docs/verification.json',
      'installer/README.md','installer/Patch.ps1','installer/ChooseGame.ps1','installer/Install.cmd','installer/Remove.cmd','installer/manifest.json',
      *{p for p in expected if p.startswith('licenses/')}}
    assert {p.relative_to(STAGE).as_posix() for p in STAGE.rglob('*') if p.is_file()}==allowed
    for p in STAGE.rglob('*'):
        if p.is_file():
            content=p.read_text(encoding='utf-8-sig')
            assert not re.search(r'[A-Z]:[\\/](?:Users|steam)|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_|Bearer [A-Za-z0-9]',content),p
    write(PUBLIC/'publication_manifest.json',json.dumps({'repository':REMOTE,'tag':TAG,'zip':{'path':str(archive),'name':NAME,'sha256':package['zip_sha256'],'size':archive.stat().st_size},'files':[{'path':p.relative_to(STAGE).as_posix(),'size':p.stat().st_size,'sha256':sha(p)} for p in sorted(STAGE.rglob('*')) if p.is_file()]},ensure_ascii=False,indent=2))
    write(PUBLIC/'release_notes.md',f'''## How Empires Work 한국어 패치 1.0.1 r2

Steam 앱 4663730 / Windows 빌드 26482667용 비공식 한국어 패치입니다.

아래 **{NAME}**을 내려받아 전체를 풀고, 게임을 종료한 뒤 `Install.cmd`를 실행하세요. 제거는 같은 묶음의 `Remove.cmd`를 사용합니다.

세금 징수 후 진행이 막히던 오류와 무역 금액·상품명 표시를 수정했습니다. 최종 ZIP 설치·복구 {passed}개 시험을 확인했습니다. 전체 회차·모든 분기 완주 검수는 아닙니다.

이전 1.0.0은 이전 제거기로 먼저 원본 복원 후 적용하세요. 이전판에서 막힌 저장의 자동 복구는 포함하지 않습니다. 상세 내용은 [설치 안내]({REMOTE}#설치제거)를 확인하세요.

SHA-256: `{package['zip_sha256']}`
''')
    print(json.dumps({'files':len(allowed),'zip_bytes':archive.stat().st_size,'zip_sha256':package['zip_sha256'],'installer_pass':passed},ensure_ascii=False))

if __name__=='__main__':main()
