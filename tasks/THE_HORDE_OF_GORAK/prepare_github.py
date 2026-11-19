"""Gorak 전용 공개 저장소에 올릴 파일을 명시적으로 준비하고 검사합니다."""
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'working_private/THE_HORDE_OF_GORAK/github_publish_20261102'
REPO = WORK / 'repository'
ARTICLE = ROOT / 'deliverables/THE_HORDE_OF_GORAK_INTRO_20261102'
REMOTE = 'https://github.com/KIMDONGWHEE99/the-horde-of-gorak-korean-patch'
ZIP_NAME = 'THE_HORDE_OF_GORAK_KOREAN_PATCH_1.0.0_r1.zip'
ZIP_HASH = '22b94d117534760284ae2d2d0f310d646465f0e21cd6058c3ff05f67a5981d2f'


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', newline='\n')


def main():
    assert not REPO.exists()
    REPO.mkdir(parents=True)
    names = ['INTRODUCTION.md', '미리보기.html', '카페_복사용.html', '카페_본문.txt', '이미지_출처.json']
    for name in names:
        shutil.copyfile(ARTICLE / name, REPO / name)
    shutil.copytree(ARTICLE / 'images', REPO / 'images')
    write(REPO / 'README.md', f'''# The Horde of Gorak 한국어 패치 1.0.0

![The Horde of Gorak](images/01_title.jpg)

[**한글패치 ZIP 다운로드**]({REMOTE}/raw/refs/heads/main/downloads/{ZIP_NAME}) · [**게임 소개·리뷰**](INTRODUCTION.md) · [확인 범위·버전 안내](releases/v1.0.0.md)

오크 마을과 군대를 키워 인간의 성을 공략하는 성장형 전략 게임의 비공식 한국어 패치입니다. [Steam 공식 상점](https://store.steampowered.com/app/4911050/The_Horde_of_Gorak/)

## 지원 버전

- Windows Steam 앱 **4911050 / 빌드 26336311 / 게임 v1.1.03** 전용입니다.
- 패치 버전: **1.0.0 · 패키지 r1**. 다른 게임 버전의 호환성을 보장하지 않습니다.
- 일부 검수를 생략한 버전으로 **전체 검수 통과판은 아닙니다**. 세부 범위는 아래와 버전 안내에 공개합니다.

## 설치·제거

1. 게임을 종료하고 위의 **한글패치 ZIP 다운로드**를 누릅니다.
2. 내려받은 ZIP을 새 폴더에 모두 풉니다.
3. `Install.cmd`를 실행해 `THOG.exe`가 있는 게임 폴더를 선택합니다.
4. 설치 완료 후 Steam에서 평소처럼 실행합니다.

제거할 때는 게임을 종료한 뒤 같은 패키지의 `Remove.cmd`에서 같은 게임 폴더를 선택합니다. 설치 완료 메시지에 안내되는 원본 복구 백업을 보관하세요. 설치가 중단되면 같은 버전의 설치기를 다시 실행하여 복구합니다. 게임 업데이트 등으로 지원 파일이 일치하지 않으면 설치를 중단하며 강제로 덮어쓰지 않습니다.

저장소의 **Code → Download ZIP**은 문서와 이미지까지 포함한 보관용 파일입니다. 패치만 설치하려면 맨 위의 **한글패치 ZIP 다운로드**를 사용하세요.

## 한글화 내용

- 본문·메뉴 590종, 총855위치와 실행 모듈의 표시 문구176필드를 반영했습니다.
- 이미지 문구4곳과 한글 글꼴, 진행 상황·결과 화면의 줄 정렬을 수정했습니다.
- 게임 제목·제작진·브랜드 로고는 유지합니다. JSON 해석 오류 등 일부 진단 문구는 영어로 남아 있습니다.

## 확인 범위와 남은 부분

메뉴·설정·지도·특전·전투·저장 후 재실행/이어하기·주요 건물·연구·결과 정렬·용 모집을 확인했습니다. 파일의 번역 위치·글꼴·변경 경계, 차이 파일의 정방향·역방향 복원과 최종 ZIP의 기본 설치·제거도 확인했습니다.

엔딩·전체 분기·일부 예비 화면·추가 코드 전수 분류·최종 ZIP의 확장 실패 복구 시험·실제 설치본의 추가 재실행은 미완료입니다. [버전별 확인 범위](releases/v1.0.0.md)와 ZIP의 `REVIEW_STATUS.json`에 상세히 적었습니다.

원본 게임 파일·개인 저장 파일·검수용 변경을 배포하지 않는 차이 패치입니다. 포함된 도구와 글꼴의 라이선스는 ZIP의 `licenses` 폴더를 확인하세요.

## 소개글과 이미지

[게임 소개·리뷰](INTRODUCTION.md)는 공식 이미지6장과 특징5개, 짧은 리뷰 및 추천 대상을 담았습니다. `미리보기.html`, `카페_복사용.html`, `카페_본문.txt`도 제공합니다. HTML을 PC에서 열려면 문서와 `images` 폴더를 함께 내려받으세요. 소개 이미지는 공식 영문 홍보 화면이며 한글패치 적용 화면이 아닙니다.

ZIP SHA-256: `{ZIP_HASH}`
''')
    write(REPO / 'releases/v1.0.0.md', f'''# The Horde of Gorak 한국어 패치 1.0.0 r1

공개일: 2026-11-02 · 지원 Steam 빌드26336311 / 게임 v1.1.03.

[패치 ZIP]({REMOTE}/raw/refs/heads/main/downloads/{ZIP_NAME}) · [설치·제거 안내](../README.md)

2026-10-31에 마무리한 기존 패치 ZIP을 내용 변경 없이 공개합니다. 당시 개인용으로 마무리하여 ZIP 안 README에는 개인용이라고 적혀 있으며, 이번 업로드가 추가 게임 검수의 완료를 뜻하지는 않습니다.

본문·메뉴855위치, 실행 모듈176필드, 이미지 문구4곳과 한글 글꼴을 반영했습니다. 진행 상황과 결과 화면의 줄 정렬도 수정했습니다. 게임 제목·제작진·브랜드 로고와 일부 오류 진단 문구는 원문으로 유지합니다.

동결 후보의 번역·글꼴 및 정적 재추출, 수정12파일의 정·역방향 차이 복원과 ZIP 구성은 확인했습니다. 최종 ZIP의 기본 사본 설치·제거 각1회와 실제 설치 파일32개·원본 백업12개의 내용 일치도 확인했습니다.

대표 메뉴·설정·지도·특전·전투·정상 저장 후 이어하기·주요 건물·연구·결과 정렬·용 모집은 확인했습니다. 엔딩·전체 분기·용 도감 본문·예비 장면·전체 문구의 실제 표시·최종 설치본 추가 재실행·최종 ZIP의 확장 실패 및 강제 중단 복구 시험은 미완료입니다. 이전 합성 시험을 이 최종 ZIP 전체 검수로 대체하지 않습니다.

G3·G4·G6의 기재한 범위는 PASS이며, G2 전수 분류·G5 전체 실행·G7 확장 설치 복구·G8 전체 완료 판정은 NOT_RUN입니다. 전체 검수 통과판으로 표시하지 않습니다.

파일: `{ZIP_NAME}` · 8,572,090바이트.

SHA-256: `{ZIP_HASH}`
''')
    write(REPO / 'SHA256SUMS.txt', ZIP_HASH + '  downloads/' + ZIP_NAME + '\n')
    write(REPO / '업로드_안내.txt', 'Gorak 소개·리뷰 사용 안내\n\n1. 미리보기.html에서 배치를 확인합니다.\n2. 카페_복사용.html의 본문 선택 버튼으로 글을 복사합니다.\n3. 사진 위치에 images 폴더의 같은 번호 파일을 첨부합니다.\n4. 공식 이미지 출처와 리뷰의 확인 범위를 유지합니다.\n\n카페 게시나 로그인은 수행하지 않았습니다. 소개 이미지는 공식 영문 홍보 화면입니다.\n')
    archive = ROOT / 'release_output' / ZIP_NAME
    raw = archive.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ZIP_HASH
    fixed = {'ChooseGame.ps1', 'Install.cmd', 'Patch.ps1', 'README.txt', 'REVIEW_STATUS.json', 'Remove.cmd', 'manifest.json', 'tools/xdelta3.exe', 'licenses/NotoSansKR-OFL.txt', 'licenses/xdelta3-APACHE-2.0.txt'}
    with zipfile.ZipFile(archive) as z:
        members = [n for n in z.namelist() if not n.endswith('/')]
        manifest = json.loads(z.read('manifest.json'))
        deltas = {c[k] for c in manifest['changes'] for k in ('forward', 'reverse')}
        assert set(members) == fixed | deltas and len(members) == 34
        assert all(re.fullmatch(r'patches/\d+\.(forward|reverse)\.xdelta', n) for n in deltas)
        for entry in manifest['payload']:
            data = z.read(entry['path'])
            assert len(data) == entry['size'] and hashlib.sha256(data).hexdigest() == entry['sha256']
        assert z.testzip() is None
    (REPO / 'downloads').mkdir()
    shutil.copyfile(archive, REPO / 'downloads' / ZIP_NAME)
    files = []
    for p in sorted(REPO.rglob('*')):
        if not p.is_file():
            continue
        data = p.read_bytes()
        if p.suffix in ('.md', '.txt', '.html', '.json'):
            text = data.decode('utf-8')
            assert not re.search(r'(?i)[A-Z]:[\\/](?:Users|steam)[\\/]|file://|gh[pousr]_[A-Za-z0-9]{20}', text), p.name
            assert 'working_private' not in text and '%LOCALAPPDATA%' not in text, p.name
        files.append({'path': p.relative_to(REPO).as_posix(), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'git_blob': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()})
    expected = set(names) | {'README.md', '업로드_안내.txt', 'SHA256SUMS.txt', 'releases/v1.0.0.md', 'downloads/' + ZIP_NAME}
    expected |= {'images/' + p.name for p in (ARTICLE / 'images').iterdir()}
    assert {f['path'] for f in files} == expected and len(files) == 16
    write(WORK / 'upload_manifest.json', json.dumps({'repository': 'KIMDONGWHEE99/the-horde-of-gorak-korean-patch', 'visibility': 'public', 'date': '2026-11-02', 'files': files, 'package_allowlist': 'PASS', 'package_hashes': 'PASS', 'original_game_assets_included': False, 'private_logs_included': False}, ensure_ascii=False, indent=2))
    print(json.dumps({'files': len(files), 'images': 6, 'zip_sha256': ZIP_HASH, 'status': 'PASS'}))


if __name__ == '__main__':
    main()
