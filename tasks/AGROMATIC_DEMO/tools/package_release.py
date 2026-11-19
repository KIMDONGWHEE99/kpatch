"""후보 전체를 대조한 뒤 차이 파일·설치기를 묶고 최종 ZIP을 별도 위치에 풉니다."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from common import ROOT, BASE, WORK

GAME = 'AGROMATIC_DEMO'
BUILD = '25850896'
APP = '4252500'
EXE = 'AgromaticDemo.exe'
PACK = EXE
BASELINE = BASE
TEMPLATE = ROOT / 'tasks' / GAME / 'release_template'
SOURCE_MANIFEST = WORK / 'baseline/source_manifest.json'
TOOL_ROOT = ROOT / 'tasks/SUPERREAP_DEMO/tools/third_party/xdelta3-3.2.0'
ENCODER = TOOL_ROOT / 'extracted/xdelta3-3.2.0-windows-x86_64/xdelta3.exe'
FONT_LICENSE = ROOT / 'tasks/TFC2/third_party/NotoSansKR/OFL.txt'
BUILD_ANCHORS = [EXE, 'data_Agromatic_windows_x86_64/Agromatic.dll',
                 'libgodotsteam.windows.template_release.x86_64.dll',
                 'libpathfinding.windows.template_release.x86_64.dll',
                 'libstorage_db.windows.template_release.x86_64.dll', 'steam_api64.dll']


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def require_inside(path, roots):
    path = Path(path).resolve()
    if not any(path.is_relative_to(Path(root).resolve()) for root in roots):
        raise ValueError('허용된 작업 경로 밖입니다: ' + str(path))
    return path


def make_package(source, candidate, files, changes, release, scratch, version,
                 candidate_id, readme, font_license=FONT_LICENSE):
    """실제 후보와 비공개 합성 자료에 같은 설치·복구 절차를 사용합니다."""
    started = utc_now()
    source = require_inside(source, [BASELINE, WORK])
    candidate = require_inside(candidate, [ROOT / 'build_candidate' / GAME, WORK])
    release = require_inside(release, [ROOT / 'release_output', WORK])
    scratch = require_inside(scratch, [WORK])
    font_license = Path(font_license).resolve()
    if release.exists() or scratch.exists() or (release.parent / (release.name + '.zip')).exists():
        raise FileExistsError('기존 묶음이나 시험 증거를 덮어쓰지 않습니다.')
    if not set(changes).issubset(files) or not changes:
        raise ValueError('변경 파일은 원본 목록에 있어야 합니다.')
    if len(set(files)) != len(files) or len(set(changes)) != len(changes):
        raise ValueError('파일 목록에 중복이 있습니다.')
    for name in files:
        if Path(name).is_absolute() or ':' in name or '..' in Path(name).parts:
            raise ValueError('잘못된 파일 경로: ' + name)
        require_inside(source / name, [source])
        require_inside(candidate / name, [candidate])
        if name not in changes and sha(source / name) != sha(candidate / name):
            raise ValueError('허용하지 않은 파일이 바뀌었습니다: ' + name)
    release.mkdir(parents=True)
    scratch.mkdir(parents=True)
    for directory in ('tools', 'licenses', 'patches'):
        (release / directory).mkdir()
    shutil.copy2(ENCODER, release / 'tools/xdelta3.exe')
    shutil.copy2(TOOL_ROOT / 'LICENSE-APACHE-2.0.txt', release / 'licenses/xdelta3-APACHE-2.0.txt')
    shutil.copy2(font_license, release / 'licenses/font-OFL.txt')
    for name in ('Patch.ps1', 'ChooseGame.ps1'):
        text = (TEMPLATE / name).read_text(encoding='utf-8-sig').replace('@VERSION@', version)
        if '@VERSION@' in text:
            raise ValueError('버전 정보가 남아 있습니다.')
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
        if sha(original) == sha(patched):
            raise ValueError('변경 내용이 없는 파일: ' + name)
        record = {'path': name, 'original_sha256': sha(original), 'patched_sha256': sha(patched)}
        for direction, before, after in (('forward', original, patched), ('reverse', patched, original)):
            relative = f'patches/{index:02d}.{direction}.xdelta'
            delta, rebuilt = release / relative, scratch / f'{index:02d}.{direction}.rebuilt'
            command = [str(ENCODER), '-f', '-e', '-9', '-s', str(before), str(after), str(delta)]
            result = subprocess.run(command, check=True, capture_output=True)
            (scratch / f'{index:02d}.{direction}.encode.log').write_bytes(result.stdout + result.stderr)
            decode = [str(ENCODER), '-d', '-s', str(before), str(delta), str(rebuilt)]
            result = subprocess.run(decode, check=True, capture_output=True)
            (scratch / f'{index:02d}.{direction}.decode.log').write_bytes(result.stdout + result.stderr)
            if sha(rebuilt) != sha(after):
                raise ValueError('차이 복원 내용 불일치: ' + direction)
            record[direction] = relative
            record[direction + '_roundtrip'] = {'status': 'PASS', 'sha256': sha(rebuilt),
                                               'delta_sha256': sha(delta), 'commands': [command, decode]}
        delta_records.append(record)
    baseline = [{'path': name, 'size': (source / name).stat().st_size, 'sha256': sha(source / name)}
                for name in sorted(files)]
    payload = [{'path': path.relative_to(release).as_posix(), 'size': path.stat().st_size, 'sha256': sha(path)}
               for path in sorted(release.rglob('*')) if path.is_file()]
    # 개인 작업 경로와 복원 시험 명령은 공개 목록에 넣지 않습니다.
    public_changes = [{key: value for key, value in record.items() if not key.endswith('_roundtrip')}
                      for record in delta_records]
    manifest = {'game_id': GAME, 'steam_build': BUILD, 'version': version,
                'candidate': candidate_id, 'baseline': baseline, 'changes': public_changes, 'payload': payload}
    write_json(release / 'manifest.json', manifest)
    allow = {'Install.cmd', 'Remove.cmd', 'Patch.ps1', 'ChooseGame.ps1', 'README.txt', 'manifest.json',
             'tools/xdelta3.exe', 'licenses/xdelta3-APACHE-2.0.txt', 'licenses/font-OFL.txt'}
    for record in delta_records:
        allow.update((record['forward'], record['reverse']))
    observed = {path.relative_to(release).as_posix() for path in release.rglob('*') if path.is_file()}
    if observed != allow:
        raise ValueError('배포 허용 목록 불일치')
    archive = release.parent / (release.name + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for name in sorted(allow):
            output.write(release / name, name)
    extracted = scratch / 'from_final_zip'
    with zipfile.ZipFile(archive) as source_zip:
        if len(source_zip.namelist()) != len(allow) or set(source_zip.namelist()) != allow or source_zip.testzip():
            raise ValueError('최종 ZIP 내용 불일치')
        source_zip.extractall(extracted)
    for name in allow:
        if sha(release / name) != sha(extracted / name):
            raise ValueError('최종 ZIP 추출 내용 불일치: ' + name)
    report = {'game_id': GAME, 'steam_build': BUILD, 'candidate': candidate_id, 'version': version,
              'started_utc': started, 'completed_utc': utc_now(), 'archive': str(archive),
              'scratch': str(scratch), 'zip_sha256': sha(archive),
              'manifest_sha256': sha(extracted / 'manifest.json'), 'allowed_files': sorted(allow),
              'encoder_sha256': sha(ENCODER), 'changes': delta_records,
              'font_license_sha256': sha(font_license), 'G6': 'PASS', 'G7': 'NOT_RUN', 'exit_code': 0}
    write_json(scratch / 'package.json', report)
    return report


def default_readme(version):
    return f'''Agromatic Demo 한국어 패치 {version}

지원: Windows 64비트 / Steam 빌드 {BUILD} / 앱 번호 {APP}

설치: 게임을 종료하고 ZIP을 모두 푼 뒤 Install.cmd를 더블클릭하세요.
찾은 게임 폴더를 확인하고 [설치]를 누르세요. 다른 위치라면 [찾아보기…]에서
AgromaticDemo.exe가 들어 있는 게임 폴더를 선택하세요.
설치 후에는 Steam에서 평소처럼 게임을 실행하세요.

제거: 게임을 종료하고 Remove.cmd를 더블클릭한 뒤 [제거]를 누르세요.
원본 백업과 복구 기록은 %LOCALAPPDATA%\\AgromaticKoreanPatch\\working_private
아래에 게임 경로와 지원 빌드별로 보관합니다. 중간에 멈췄다면 같은 설치기를
다시 실행하세요. 게임 업데이트·변조·파일 누락·손상에는 강제로 적용하지 않습니다.
저장 파일·설정·Steam 업적은 설치·제거 과정에서 변경하지 않습니다.

변경 파일: AgromaticDemo.exe 1개. 실행 파일 안의 표시 문구·글꼴 자료를 변경합니다.
번역·화면 검수 범위와 남긴 고유명사·로고 등은 ZIP 밖의 최종 결과 보고서에
기록합니다. 최종 ZIP 설치·복구 시험 결과도 같은 ZIP 내용 지문에 연결합니다.

이 ZIP에는 원본 게임 파일 대신 차이 파일과 설치·제거 도구가 들어 있습니다.
한글 글꼴: SIL Open Font License 1.1 (licenses/font-OFL.txt).
xdelta3 3.2.0: Apache License 2.0 (licenses/xdelta3-APACHE-2.0.txt).
'''


def main():
    parser = argparse.ArgumentParser(description='후보를 고정하여 차이 패치와 최종 ZIP을 만듭니다.')
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--version', default='1.0.0')
    parser.add_argument('--revision', default='r1')
    parser.add_argument('--readme', type=Path)
    parser.add_argument('--font-license', type=Path, default=FONT_LICENSE)
    args = parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+', args.version) or not re.fullmatch(r'[a-z0-9_-]+', args.revision):
        raise ValueError('버전 또는 작업 번호가 올바르지 않습니다.')
    candidate = require_inside(args.candidate, [ROOT / 'build_candidate' / GAME])
    candidate_id = candidate.parent.name if candidate.name == 'game' else candidate.name
    expected = json.loads(SOURCE_MANIFEST.read_text(encoding='utf-8-sig'))
    records = [{**record, 'path': record['path'].replace('\\', '/'), 'sha256': record['sha256'].lower()}
               for record in expected]
    names = {record['path'] for record in records}
    for folder in (BASELINE, candidate):
        if {path.relative_to(folder).as_posix() for path in folder.rglob('*') if path.is_file()} != names:
            raise ValueError('후보·원본의 전체 파일 목록 불일치: ' + str(folder))
    for record in records:
        name = record['path']
        if (BASELINE / name).stat().st_size != record['size'] or sha(BASELINE / name) != record['sha256']:
            raise ValueError('고정 원본 불일치: ' + name)
        if name != EXE and sha(candidate / name) != record['sha256']:
            raise ValueError('허용하지 않은 후보 변경: ' + name)
    if not set(BUILD_ANCHORS).issubset(names):
        raise ValueError('지원 빌드 확인 파일이 없습니다.')
    release = ROOT / 'release_output' / f'{GAME}_KOREAN_PATCH_{args.version}_{args.revision}'
    scratch = WORK / f'package_{args.version}_{args.revision}'
    readme = args.readme.read_text(encoding='utf-8-sig') if args.readme else default_readme(args.version)
    # 설치 대상도 전체 고정 목록을 확인하여 앵커 밖의 업데이트·변조를 거부합니다.
    report = make_package(BASELINE, candidate, [record['path'] for record in records], [EXE], release, scratch,
                          args.version, candidate_id, readme, args.font_license)
    report.update({'source_manifest_sha256': sha(SOURCE_MANIFEST), 'original_file_count': len(records),
                   'unmodified_candidate_count': len(records) - 1, 'package_tool_sha256': sha(Path(__file__))})
    write_json(scratch / 'package.json', report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
