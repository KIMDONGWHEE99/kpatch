"""합성 자료를 ZIP으로 고정한 뒤 그 안의 설치기로 실패·복구를 시험한다."""
import argparse
import json
import re
import shutil

from soulash2_release_package import WORK, make_package, write_json
from soulash2_release_installer_test import InstallerTests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    assert re.fullmatch(r'[a-z0-9_-]+', args.revision)
    fixture = WORK / 'release_preparation' / ('installer_synthetic_' + args.revision)
    assert not fixture.exists(), '기존 시험 증거를 덮어쓰지 않습니다.'
    source, candidate = fixture / 'source', fixture / 'candidate'
    (source / 'data/mods/core_2/entities').mkdir(parents=True)
    names = ['Soulash 2.exe', 'SDL2.dll', 'data/mods/core_2/messages.json', 'data/mods/core_2/entities/test.json']
    for name in names:
        # 게임의 원본 코드·자산을 넣지 않은 독립 합성 자료입니다.
        content = bytes(range(256)) * (4 * 1024 * 1024 // 256) if name.endswith('.json') else ('합성 시험 전용: ' + name).encode('utf-8')
        (source / name).write_bytes(content)
    shutil.copytree(source, candidate)
    changes = names[2:] + ['language.ini']
    for name in names[2:]:
        data = bytearray((candidate / name).read_bytes())
        replacement = ('한글 설치기 되돌림 시험 ' * 100).encode('utf-8')
        data[1024:1024 + len(replacement)] = replacement
        (candidate / name).write_bytes(data)
    (candidate / 'language.ini').write_text('language=ko\n', encoding='utf-8')
    report = make_package(source, candidate, names, changes, fixture / 'package', fixture / 'evidence',
                          '1.0.0', 'installer_synthetic', 'Soulash 2 설치기 합성 시험. 실제 게임 패치가 아닙니다.\n')
    write_json(fixture / 'evidence/package.json', report)
    result = InstallerTests(fixture / 'evidence/package.json', source).run_all()
    result['scope'] = '동일 설치기 합성 수정2파일·추가1파일. 실제 최종 후보와 ZIP의 G6/G7을 대체하지 않습니다.'
    result['actual_game_g6'] = result['actual_game_g7'] = 'NOT_RUN'
    write_json(fixture / 'evidence/installer_tests.json', result)
    print(json.dumps({'status': result['status'], 'tests': len(result['tests']), 'evidence': str(fixture / 'evidence')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
