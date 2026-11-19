"""게임을 실행하지 않고 수정 두 파일·신규 파일의 설치 및 복구를 시험합니다."""
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
    (source / 'KingdomInc_Data').mkdir(parents=True)
    names = ['KingdomInc.exe', 'UnityPlayer.dll', 'KingdomInc_Data/globalgamemanagers',
             'KingdomInc_Data/resources.assets', 'KingdomInc_Data/sharedassets0.assets']
    content = bytes(range(256)) * (4 * 1024 * 1024 // 256)
    for name in names:
        data = content if name.endswith('.assets') else ('합성 시험 전용: ' + name).encode('utf-8')
        (source / name).write_bytes(data)
    shutil.copytree(source, candidate)
    changes = ['KingdomInc_Data/resources.assets', 'KingdomInc_Data/sharedassets0.assets', 'language.ini']
    for name in changes[:2]:
        patched = bytearray((candidate / name).read_bytes())
        replacement = ('한글 설치기 두 파일 되돌림 시험 ' * 100).encode('utf-8')
        patched[1024:1024 + len(replacement)] = replacement
        (candidate / name).write_bytes(patched)
    (candidate / 'language.ini').write_text('language=ko\n', encoding='utf-8')
    report = make_package(source, candidate, names, changes, fixture / 'package', fixture / 'evidence',
                          '1.0.0', 'installer_synthetic', '합성 설치기 시험용. 게임 자산·실제 배포본이 아닙니다.\n')
    write_json(fixture / 'evidence/package.json', report)
    result = InstallerTests(fixture / 'evidence/package.json', source).run_all()
    result['scope'] = '동일 설치기·합성 수정 2파일 및 신규 1파일. 실제 후보의 G6/G7을 대체하지 않습니다.'
    write_json(fixture / 'evidence/installer_tests.json', result)


if __name__ == '__main__':
    main()
