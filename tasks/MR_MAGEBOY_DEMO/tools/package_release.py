"""원본 자산 없이 차이 파일·설치기만 묶고 최종 ZIP을 별도 위치에 풉니다."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from pck_tools import ROOT, BASELINE, WORK

GAME = 'MR_MAGEBOY_DEMO'
BUILD = '25734075'
PACK = 'MR MAGEBOY DEMO.pck'
TEMPLATE = ROOT / 'tasks' / GAME / 'release_template'
TOOL_ROOT = ROOT / 'tasks/SUPERREAP_DEMO/tools/third_party/xdelta3-3.2.0'
ENCODER = TOOL_ROOT / 'extracted/xdelta3-3.2.0-windows-x86_64/xdelta3.exe'
FONT_LICENSE = ROOT / 'tasks/TFC2/third_party/NotoSansKR/OFL.txt'
TITLE_FONT_LICENSE = ROOT / 'tasks/MR_MAGEBOY_DEMO/third_party/Galmuri/LICENSE.txt'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def make_package(source, candidate, files, changes, release, scratch, version, candidate_id, readme):
    """격리된 합성 자료에서도 같은 설치기와 묶음 생성 절차를 시험합니다."""
    started = utc_now()
    assert not release.exists(), '기존 배포 폴더를 덮어쓰지 않습니다.'
    assert not scratch.exists(), '기존 시험 증거를 덮어쓰지 않습니다.'
    release.mkdir(parents=True)
    scratch.mkdir(parents=True)
    for directory in ('tools', 'licenses', 'patches'):
        (release / directory).mkdir()
    shutil.copy2(ENCODER, release / 'tools/xdelta3.exe')
    shutil.copy2(TOOL_ROOT / 'LICENSE-APACHE-2.0.txt', release / 'licenses/xdelta3-APACHE-2.0.txt')
    shutil.copy2(FONT_LICENSE, release / 'licenses/NotoSansKR-OFL.txt')
    shutil.copy2(TITLE_FONT_LICENSE, release / 'licenses/Galmuri-OFL.txt')
    for name in ('Patch.ps1', 'ChooseGame.ps1'):
        text = (TEMPLATE / name).read_text(encoding='utf-8-sig').replace('@VERSION@', version)
        assert '@VERSION@' not in text
        (release / name).write_text(text, encoding='utf-8-sig')
    for name, mode in (('Install.cmd', 'Install'), ('Remove.cmd', 'Uninstall')):
        text = ('@echo off\ncd /d "%~dp0"\npowershell.exe -NoLogo -NoProfile '
                '-ExecutionPolicy Bypass -File "%~dp0Patch.ps1" -Mode ' + mode + ' %*\n'
                'set "PATCH_EXIT=%ERRORLEVEL%"\npause\nexit /b %PATCH_EXIT%\n')
        (release / name).write_text(text, encoding='ascii', newline='\r\n')
    (release / 'README.txt').write_text(readme, encoding='utf-8-sig')
    delta_records = []
    for index, name in enumerate(changes):
        original, patched = source / name, candidate / name
        assert sha(original) != sha(patched), name
        record = {'path': name, 'original_sha256': sha(original), 'patched_sha256': sha(patched)}
        for direction, before, after in (('forward', original, patched), ('reverse', patched, original)):
            relative = f'patches/{index:02d}.{direction}.xdelta'
            delta, rebuilt = release / relative, scratch / f'{index:02d}.{direction}.rebuilt'
            subprocess.run([str(ENCODER), '-f', '-e', '-9', '-s', str(before), str(after), str(delta)],
                           check=True, capture_output=True)
            subprocess.run([str(ENCODER), '-d', '-s', str(before), str(delta), str(rebuilt)],
                           check=True, capture_output=True)
            assert sha(rebuilt) == sha(after), direction
            record[direction] = relative
            record[direction + '_roundtrip'] = {'status': 'PASS', 'sha256': sha(rebuilt),
                                               'delta_sha256': sha(delta)}
        delta_records.append(record)
    baseline = [{'path': name, 'size': (source / name).stat().st_size, 'sha256': sha(source / name)}
                for name in sorted(files)]
    payload = [{'path': path.relative_to(release).as_posix(), 'size': path.stat().st_size, 'sha256': sha(path)}
               for path in sorted(release.rglob('*')) if path.is_file()]
    manifest = {'game_id': GAME, 'steam_build': BUILD, 'version': version,
                'candidate': candidate_id, 'baseline': baseline, 'changes': delta_records, 'payload': payload}
    write_json(release / 'manifest.json', manifest)
    allow = {'Install.cmd', 'Remove.cmd', 'Patch.ps1', 'ChooseGame.ps1', 'README.txt', 'manifest.json',
             'tools/xdelta3.exe', 'licenses/xdelta3-APACHE-2.0.txt', 'licenses/NotoSansKR-OFL.txt',
             'licenses/Galmuri-OFL.txt'}
    for record in delta_records:
        allow.update((record['forward'], record['reverse']))
    assert {path.relative_to(release).as_posix() for path in release.rglob('*') if path.is_file()} == allow
    archive = release.parent / (release.name + '.zip')
    assert not archive.exists(), '기존 ZIP을 덮어쓰지 않습니다.'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for name in sorted(allow):
            output.write(release / name, name)
    extracted = scratch / 'from_final_zip'
    with zipfile.ZipFile(archive) as source_zip:
        assert len(source_zip.namelist()) == len(allow)
        assert set(source_zip.namelist()) == allow and source_zip.testzip() is None
        source_zip.extractall(extracted)
    for name in allow:
        assert sha(release / name) == sha(extracted / name), name
    report = {'game_id': GAME, 'steam_build': BUILD, 'candidate': candidate_id, 'version': version,
              'started_utc': started, 'completed_utc': utc_now(), 'archive': str(archive),
              'scratch': str(scratch), 'zip_sha256': sha(archive),
              'manifest_sha256': sha(extracted / 'manifest.json'), 'allowed_files': sorted(allow),
              'encoder_sha256': sha(ENCODER), 'changes': delta_records,
              'font_licenses': {'NotoSansKR-OFL.txt': sha(FONT_LICENSE), 'Galmuri-OFL.txt': sha(TITLE_FONT_LICENSE)},
              'G6': 'PASS', 'G7': 'NOT_RUN', 'exit_code': 0}
    write_json(scratch / 'package.json', report)
    return report


def default_readme(version):
    return f'''MR MAGEBOY DEMO 한국어 패치 {version}

지원: Windows 64비트 / Steam 빌드 {BUILD} / 앱 번호 5310040

설치: 게임을 종료하고 ZIP을 모두 푼 뒤 Install.cmd를 더블클릭하세요.
찾은 게임 폴더를 확인하고 [설치]를 누르세요. 다른 위치라면 [찾아보기…]에서
MR MAGEBOY DEMO.exe가 들어 있는 게임 폴더를 선택하세요.
설치 후에는 Steam에서 평소처럼 게임을 실행하세요.

제거: 게임을 종료하고 Remove.cmd를 더블클릭한 뒤 [제거]를 누르세요.
원본 백업은 %LOCALAPPDATA%\\MRMageboyKoreanPatch\\working_private 아래에
게임 경로와 지원 빌드별로 보관합니다. 중간에 멈췄다면 같은 설치기를 다시 실행하세요.
게임 업데이트·변조·파일 누락·손상에는 강제로 적용하지 않습니다.
저장 파일·설정·Steam 업적은 설치·제거 과정에서 변경하지 않습니다.

변경 파일: MR MAGEBOY DEMO.pck 1개. 원본 실행 파일과 Steam 파일은 유지합니다.
번역·글꼴·화면 검수 범위와 남긴 고유명사·로고 등은 ZIP 밖의 최종 결과 보고서에
기록합니다. 최종 ZIP 설치·복구 시험의 결과도 같은 ZIP 지문에 연결합니다.

이 ZIP에는 원본 게임 자산 대신 차이 파일과 설치·제거 도구만 들어 있습니다.
Noto Sans KR: SIL Open Font License 1.1 (licenses 폴더).
https://github.com/google/fonts/tree/main/ofl/notosanskr
타이틀 부제 글꼴: Galmuri11 Bold를 필요한 문자만 담은 MageboyKoreanTitle로 수정.
SIL Open Font License 1.1 (licenses/Galmuri-OFL.txt).
https://github.com/quiple/galmuri
xdelta3 3.2.0: Apache License 2.0 (licenses 폴더).
https://github.com/jmacd/xdelta
'''


def main():
    parser = argparse.ArgumentParser(description='후보를 고정하여 차이 패치와 최종 ZIP을 만듭니다.')
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--version', default='1.0.0')
    parser.add_argument('--revision', default='r1')
    parser.add_argument('--readme', type=Path)
    args = parser.parse_args()
    assert re.fullmatch(r'\d+\.\d+\.\d+', args.version)
    assert re.fullmatch(r'[a-z0-9_-]+', args.revision)
    candidate = args.candidate.resolve()
    candidate.relative_to((ROOT / 'build_candidate' / GAME).resolve())
    expected = json.loads((WORK / 'baseline.json').read_text(encoding='utf-8'))
    assert expected['game_id'] == GAME and expected['build_id'] == BUILD
    names = [record['path'] for record in expected['files']]
    assert {path.relative_to(BASELINE).as_posix() for path in BASELINE.rglob('*') if path.is_file()} == set(names)
    assert {path.relative_to(candidate).as_posix() for path in candidate.rglob('*') if path.is_file()} == set(names)
    for record in expected['files']:
        assert (BASELINE / record['path']).stat().st_size == record['size']
        assert sha(BASELINE / record['path']) == record['sha256'], record['path']
        if record['path'] != PACK:
            assert sha(candidate / record['path']) == record['sha256'], record['path']
    release = ROOT / 'release_output' / f'{GAME}_KOREAN_PATCH_{args.version}_{args.revision}'
    scratch = WORK / f'package_{args.version}_{args.revision}'
    readme = args.readme.read_text(encoding='utf-8-sig') if args.readme else default_readme(args.version)
    report = make_package(BASELINE, candidate, names, [PACK], release, scratch, args.version, candidate.name, readme)
    report['baseline_json_sha256'] = sha(WORK / 'baseline.json')
    report['package_tool_sha256'] = sha(Path(__file__))
    write_json(scratch / 'package.json', report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
