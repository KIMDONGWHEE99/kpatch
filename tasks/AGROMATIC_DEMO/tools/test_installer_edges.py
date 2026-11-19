"""게임을 실행하지 않고 같은 설치기의 합성 두 파일 복구 시험을 준비합니다."""
import argparse
import shutil

from package_release import WORK, BUILD_ANCHORS, EXE, make_package, write_json
from test_installer import InstallerTests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', default='r1')
    args = parser.parse_args()
    if not args.revision.replace('_', '').replace('-', '').isalnum():
        raise ValueError('잘못된 작업 번호')
    fixture = WORK / ('installer_synthetic_' + args.revision)
    if fixture.exists():
        raise FileExistsError('기존 합성 시험을 덮어쓰지 않습니다.')
    source, candidate = fixture / 'source', fixture / 'candidate'
    source.mkdir(parents=True)
    # 변경 두 파일 외의 의존 파일도 실제 설치 때 고정 목록으로 검사하는지 확인합니다.
    names = BUILD_ANCHORS + ['synthetic_second.pack', 'synthetic_unchanged_dependency.dat']
    content = bytes(range(256)) * (8 * 1024 * 1024 // 256)
    for name in names:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if name in (EXE, 'synthetic_second.pack')
                         else ('합성 시험 전용: ' + name).encode('utf-8'))
    shutil.copytree(source, candidate)
    for name in (EXE, 'synthetic_second.pack'):
        patched = bytearray((candidate / name).read_bytes())
        replacement = ('한글 설치기 두 파일 되돌림 시험 ' * 100).encode('utf-8')
        patched[1024:1024 + len(replacement)] = replacement
        (candidate / name).write_bytes(patched)
    report = make_package(source, candidate, names, [EXE, 'synthetic_second.pack'],
                          fixture / 'package', fixture / 'evidence', '1.0.0', 'installer_synthetic',
                          '합성 설치기 시험용입니다. 게임 파일이나 실제 배포본이 아닙니다.\n')
    write_json(fixture / 'evidence/package.json', report)
    result = InstallerTests(fixture / 'evidence/package.json', source).run_all()
    result['scope'] = '동일 설치기·합성 2파일. 실제 빌드·후보와 최종 배포 ZIP 검사를 대체하지 않습니다.'
    write_json(fixture / 'evidence/installer_tests.json', result)


if __name__ == '__main__':
    main()
