"""검증된 ZIP과 공개할 문서·설치기만 전용 저장소용으로 준비합니다(올리지는 않음).

HOW_EMPIRES_WORK의 prepare_github.py를 이 게임에 맞게 고쳤습니다.
게임 원본 자료, 번역 원문 파일, 검수 코드, 개인 경로는 넣지 않습니다.
"""
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'working_private/CLICKY_ISLANDS'
PUBLIC = WORK / 'github_publish_1.0.0_r1'
STAGE = PUBLIC / 'staging'
OWNER = 'KIMDONGWHEE99'
REPOSITORY = 'clicky-islands-korean-patch'
REMOTE = f'https://github.com/{OWNER}/{REPOSITORY}'
TAG = 'v1.0.0-r1'
NAME = 'CLICKY_ISLANDS_KOREAN_PATCH_1.0.0_r1.zip'
PRIVATE_PATH = re.compile(r'[A-Z]:[\\/](?:Users|steam|kpatch)|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_|Bearer [A-Za-z0-9]|7656119[0-9]{10}')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf8', newline='\n')


def main():
    package = read(WORK / 'package_1.0.0_r1/package.json')
    tests = read(WORK / 'package_1.0.0_r1/installer_tests.json')
    gate = read(WORK / 'release_gate/ko_c03/gate.json')
    static = read(WORK / 'ko_c03/verify/validation_report.json')
    ledger = read(WORK / 'qa/c03_a/qa_ledger.json')
    archive = ROOT / 'release_output' / NAME
    assert sha(archive) == package['zip_sha256'] == tests['zip_sha256']
    assert tests['status'] == 'PASS' and static['status'] == 'PASS' and gate['status'] == 'PASS'
    assert static['inputs']['candidate_pck_sha256'] == package['changes'][0]['patched_sha256']
    PUBLIC.mkdir(exist_ok=True)
    assert not STAGE.exists(), '기존 준비 폴더를 덮어쓰지 않습니다.'
    STAGE.mkdir()
    expected = {'ChooseGame.ps1', 'Install.cmd', 'Patch.ps1', 'README.txt', 'Remove.cmd', 'manifest.json',
                'licenses/NotoSansKR-OFL.txt', 'licenses/xdelta3-APACHE-2.0.txt',
                'patches/00.forward.xdelta', 'patches/00.reverse.xdelta', 'tools/xdelta3.exe'}
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist()) == expected and len(z.namelist()) == len(expected) and z.testzip() is None
        manifest = json.loads(z.read('manifest.json'))
        assert hashlib.sha256(z.read('manifest.json')).hexdigest() == package['manifest_sha256']
        assert {r['path'] for r in manifest['payload']} == expected - {'manifest.json'}
        for item in manifest['payload']:
            data = z.read(item['path'])
            assert len(data) == item['size'] and hashlib.sha256(data).hexdigest() == item['sha256']
        for name in ('Patch.ps1', 'ChooseGame.ps1', 'Install.cmd', 'Remove.cmd', 'manifest.json'):
            dest = STAGE / 'installer' / name
            dest.parent.mkdir(exist_ok=True)
            dest.write_bytes(z.read(name))
        for name in sorted(n for n in expected if n.startswith('licenses/')):
            dest = STAGE / name
            dest.parent.mkdir(exist_ok=True)
            dest.write_bytes(z.read(name))
    passed = sum(r['status'] == 'PASS' for r in tests['tests'])
    unavailable = sum(r['status'] == 'NOT_APPLICABLE' for r in tests['tests'])
    size_mb = round(archive.stat().st_size / 1048576, 1)
    observed = ledger['observed_strings']
    download = f'{REMOTE}/releases/download/{TAG}/{NAME}'
    readme = f'''# Clicky Islands 한국어 패치 1.0.0

[**한글패치 ZIP 다운로드 — 약 {size_mb}MB**]({download}) · [버전·검증 안내](docs/VERIFICATION.md)

Clicky Islands의 Windows Steam 버전을 위한 비공식 한국어 패치입니다. **Steam 앱 4178790 / 빌드 26701014**를 기준으로 만들었습니다. 원본 게임을 설치한 상태에서 적용하는 차이 패치이며, 게임 원본 파일은 들어 있지 않습니다.

## 설치·제거

1. 게임을 종료하고 위의 **한글패치 ZIP 다운로드**를 누릅니다.
2. ZIP 전체를 새 폴더에 풉니다.
3. `Install.cmd`를 실행합니다. 게임 위치가 자동으로 나타나면 [설치]를 누르고, 찾지 못하면 `Clicky Islands.exe`가 있는 폴더를 고릅니다.
4. Steam에서 게임을 실행합니다. Windows가 한국어이면 처음부터 한국어로 시작합니다. 영어로 나오면 설정 → 언어 → **한국어**를 누릅니다.

제거하려면 같은 묶음의 `Remove.cmd`를 실행합니다. 중단된 설치는 같은 설치기를 다시 실행하면 복구됩니다. 원본 백업 위치는 설치 완료 메시지에 표시됩니다. 게임 파일이 지원 대상과 다르면(게임 업데이트 등) 설치를 거부하고 아무것도 바꾸지 않습니다.

저장소의 **Code → Download ZIP**은 문서와 설치기 소스 묶음입니다. 실제 설치에는 위의 패치 ZIP을 쓰세요. `installer/` 폴더만으로는 설치할 수 없습니다.

## 무엇이 바뀌나요

- 게임 폴더의 `Clicky Islands.pck` 한 파일만 바뀝니다. 실행 파일과 DLL, 저장 파일은 그대로입니다.
- 게임에 비어 있던 한국어 칸을 채우는 방식이라 영어 등 다른 8개 언어도 그대로 고를 수 있습니다.
- 언어 선택 화면과 설정의 언어 탭에 "한국어" 버튼이 생깁니다.
- 한글 글꼴로 Noto Sans KR(보통·굵게)을 넣었습니다.

## 한글화·확인 범위

언어표 **1,078칸**과 언어표 밖 직접 문구 **46개**, 무작위 섬 이름 50개를 번역했습니다. 패치된 파일을 다시 풀어 모든 칸이 번역 원본과 같은지 대조했고, 최종 ZIP의 설치·제거·복구 {passed}개 시험을 통과했습니다.

실제 화면은 첫 화면, 설정, 기본 화면과 툴팁, 항구, 섬 단계 상승, 임무 편지, 허수아비, 항해 화면(특성·화석·유물·도전 과제), 게임 완료 창, 저장 불러오기를 확인했습니다. 화면에서 글자 그대로 확인한 번역문은 셀 수 있는 고유 번역 {observed['countable_unique_translations']}개 가운데 {observed['matched_unique_translations']}개입니다. **전체 회차와 모든 건물·분기를 플레이한 검수는 아닙니다.** 시장, 가마솥, 화산, 후반 단계의 건물 화면 등은 화면으로 확인하지 못했습니다.

알아 둘 점:

- 튜토리얼의 짧은 시연 영상 12종은 영어 화면을 녹화한 것이라 영상 속 글자가 영어입니다. 옆의 설명문과 목표는 한국어입니다.
- 게임 제목, 제작진 이름, 로고, 개발자 명령창은 영어 그대로입니다.
- 원작에 번역 항목이 없는 문구 일부는 원작처럼 내부 이름이 그대로 보일 수 있습니다.
- Steam의 파일 무결성 검사나 게임 업데이트 뒤에는 원본으로 돌아갑니다. 같은 빌드라면 `Install.cmd`를 다시 실행하면 됩니다.

원본 게임 파일·개인 저장·검수용 코드는 배포하지 않습니다. 게임의 권리는 원 권리자(Karrot Games, Pocketpair Publishing)에게 있으며, 포함된 도구와 글꼴의 라이선스는 패치 ZIP과 [licenses](licenses)에 있습니다. 이 저장소는 게임 제작사와 무관한 비공식 패치 배포 저장소입니다.

ZIP SHA-256: `{package['zip_sha256']}`
'''
    write(STAGE / 'README.md', readme)
    write(STAGE / 'CHANGELOG.md', '''# 변경 이력

## 1.0.0 r1 — 2026-11-19

- 최초 공개판입니다. Steam 빌드 26701014용.
- 언어표 1,078칸, 직접 문구 46개, 섬 이름 50개 번역. 한글 글꼴과 "한국어" 버튼 추가.
- 검수 중 발견한 설정 언어 탭의 버튼 배치 문제를 고친 후보로 만들었습니다.
''')
    public = {'patch_version': '1.0.0', 'revision': 'r1', 'steam_app_id': 4178790, 'steam_build': '26701014',
              'zip_name': NAME, 'zip_sha256': package['zip_sha256'], 'zip_bytes': archive.stat().st_size,
              'candidate_pck_sha256': package['changes'][0]['patched_sha256'], 'original_pck_sha256': package['changes'][0]['original_sha256'],
              'locale_slots_translated': 1078, 'direct_strings': 46, 'island_names': 50,
              'static_checks': {name: check['status'] for name, check in static['checks'].items()},
              'package_allowlist_files': len(expected), 'delta_roundtrips': 'PASS',
              'installer_tests_pass': passed, 'installer_tests_not_applicable': unavailable,
              'installer_tests': [{'id': r['id'], 'status': r['status']} for r in tests['tests']],
              'graphics_scope': '첫 화면, 설정 5개 탭, 기본 화면과 툴팁, 항구, 섬 단계 상승, 임무 편지, 허수아비, 항해 화면, 게임 완료 창, 저장 불러오기',
              'observed_unique_translations': observed['matched_unique_translations'],
              'countable_unique_translations': observed['countable_unique_translations'],
              'unreached_screens': ledger['unreached_screens'],
              'tutorial_videos_kept_in_english': 12, 'full_playthrough': 'NOT_RUN', 'post_install_steam_launch': 'NOT_RUN'}
    write(STAGE / 'docs/verification.json', json.dumps(public, ensure_ascii=False, indent=2) + '\n')
    write(STAGE / 'docs/VERIFICATION.md', f'''# 버전·검증 안내

2026-11-19 · 패치 1.0.0 r1 · Windows Steam 빌드 26701014 (Godot 4.5.2)

| 항목 | 결과 |
| --- | --- |
| 조사 | 스크립트·장면·자원의 문자열 62,508개를 분류, 미분류 0, 추출 오류 0. 이미지 250개와 기본 영상 21개는 직접 확인 |
| 번역 | 언어표 1,078칸·직접 문구 46개·섬 이름 50개. 자리표시자·태그·줄바꿈 검사 문제 0 |
| 패치 파일 재검증 | 다시 풀어 대조: 칸 1,078/1,078 일치, 직접 문구 46/46 일치. PCK 안에서 바뀐 항목 8개, 나머지 5,142개는 원본과 동일 |
| 글꼴 | 번역에 쓰인 문자 838종이 게임 글꼴 또는 한글 글꼴에 모두 있음 |
| 화면 | 저장과 Steam을 분리한 사본으로 실제 실행. 필수 화면군의 대표 화면 확인, 글자 깨짐 경고 0 |
| 묶음 | ZIP 안 {len(expected)}개 파일이 허용 목록·해시와 일치, 차이 파일의 정방향·역방향 복원 일치 |
| 최종 ZIP 설치기 | {passed}개 PASS, {unavailable}개 해당 없음. 중복 설치·제거, 변조·누락 거부, 파일 잠금, 강제 종료 후 복구 포함 |

[시험 항목과 지문](verification.json)에서 실제 결과를 볼 수 있습니다. 각 시험은 최종 ZIP `{NAME}`을 기준으로 했습니다.

확인하지 못한 것: 전체 회차와 모든 분기, 시장·가마솥·화산과 후반 단계의 건물 화면, 설치 후 Steam으로 실행한 화면. 튜토리얼 시연 영상 12종은 영어 화면 녹화라 그대로 두었습니다. 게임이 업데이트되어 파일이 바뀌면 새 패치가 필요합니다.
''')
    write(STAGE / 'installer/README.md', '''# 설치기 소스

검증한 패치 ZIP에서 꺼낸 설치·제거기와 파일 목록입니다. 코드 확인용이며 이 폴더만으로는 실행할 수 없습니다. 차이 파일·실행 도구·라이선스를 모두 포함한 [패치 ZIP](../README.md)을 내려받아 설치하세요.
''')
    write(STAGE / 'SHA256SUMS.txt', package['zip_sha256'] + '  ' + NAME + '\n')
    write(STAGE / '.gitattributes', '* -text\n')
    write(STAGE / '.gitignore', '''# 원본·개인 저장·임시 검수 자료는 포함하지 않습니다.
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
    allowed = {'.gitignore', '.gitattributes', 'README.md', 'CHANGELOG.md', 'SHA256SUMS.txt', 'docs/VERIFICATION.md', 'docs/verification.json',
               'installer/README.md', 'installer/Patch.ps1', 'installer/ChooseGame.ps1', 'installer/Install.cmd', 'installer/Remove.cmd',
               'installer/manifest.json', *{p for p in expected if p.startswith('licenses/')}}
    assert {p.relative_to(STAGE).as_posix() for p in STAGE.rglob('*') if p.is_file()} == allowed
    for p in STAGE.rglob('*'):
        if p.is_file():
            assert not PRIVATE_PATH.search(p.read_text(encoding='utf-8-sig')), p
    write(PUBLIC / 'publication_manifest.json', json.dumps({
        'repository': REMOTE, 'tag': TAG,
        'zip': {'path': str(archive), 'name': NAME, 'sha256': package['zip_sha256'], 'size': archive.stat().st_size},
        'files': [{'path': p.relative_to(STAGE).as_posix(), 'size': p.stat().st_size, 'sha256': sha(p)} for p in sorted(STAGE.rglob('*')) if p.is_file()]},
        ensure_ascii=False, indent=2))
    write(PUBLIC / 'release_notes.md', f'''## Clicky Islands 한국어 패치 1.0.0 r1

Steam 앱 4178790 / Windows 빌드 26701014용 비공식 한국어 패치입니다.

아래 **{NAME}**을 내려받아 전체를 풀고, 게임을 종료한 뒤 `Install.cmd`를 실행하세요. 제거는 같은 묶음의 `Remove.cmd`를 씁니다.

언어표 1,078칸과 직접 문구 46개를 번역했고, 최종 ZIP의 설치·복구 {passed}개 시험을 통과했습니다. 전체 회차·모든 분기를 플레이한 검수는 아니며, 튜토리얼 시연 영상 12종은 영어 화면 그대로입니다. 자세한 내용은 [설치 안내]({REMOTE}#설치제거)와 [검증 안내]({REMOTE}/blob/main/docs/VERIFICATION.md)를 확인하세요.

SHA-256: `{package['zip_sha256']}`
''')
    print(json.dumps({'files': len(allowed), 'zip_bytes': archive.stat().st_size, 'zip_sha256': package['zip_sha256'], 'installer_pass': passed}, ensure_ascii=False))


if __name__ == '__main__':
    main()
