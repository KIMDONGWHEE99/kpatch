"""게임을 실행하지 않고 동일 설치기의 두 파일 되돌림과 보호 동작을 시험합니다."""
import argparse
import shutil

from package_release import WORK, make_package, write_json
from test_installer import InstallerTests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', default='r1')
    args = parser.parse_args()
    assert args.revision.replace('_', '').replace('-', '').isalnum()
    fixture = WORK / ('installer_synthetic_' + args.revision)
    assert not fixture.exists(), '기존 합성 시험을 덮어쓰지 않습니다.'
    source, candidate = fixture / 'source', fixture / 'candidate'
    source.mkdir(parents=True)
    names = ['MR MAGEBOY DEMO.exe', 'MR MAGEBOY DEMO.pck', 'steam_api64.dll',
             'libgodotsteam.windows.template_release.x86_64.dll', 'synthetic_second.pack']
    content = bytes(range(256)) * (8 * 1024 * 1024 // 256)
    for name in names:
        data = content if name.endswith(('.pck', '.pack')) else ('합성 시험 전용: ' + name).encode('utf-8')
        (source / name).write_bytes(data)
    shutil.copytree(source, candidate)
    for name in ('MR MAGEBOY DEMO.pck', 'synthetic_second.pack'):
        patched = bytearray((candidate / name).read_bytes())
        replacement = ('한글 설치기 두 파일 되돌림 시험 ' * 100).encode('utf-8')
        patched[1024:1024 + len(replacement)] = replacement
        (candidate / name).write_bytes(patched)
    report = make_package(source, candidate, names, ['MR MAGEBOY DEMO.pck', 'synthetic_second.pack'],
                          fixture / 'package', fixture / 'evidence', '1.0.0', 'installer_synthetic',
                          '합성 설치기 시험용입니다. 게임 자산이나 실제 배포본이 아닙니다.\n')
    write_json(fixture / 'evidence/package.json', report)
    result = InstallerTests(fixture / 'evidence/package.json', source).run_all()
    result['scope'] = '동일 설치기·합성 2파일. 실제 Steam 빌드·후보 G6/G7을 대체하지 않습니다.'
    write_json(fixture / 'evidence/installer_tests.json', result)


if __name__ == '__main__':
    main()
