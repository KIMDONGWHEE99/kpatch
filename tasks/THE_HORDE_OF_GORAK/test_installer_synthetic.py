"""실제 게임 자료 없이 설치기의 정·역복원과 거래 복구를 시험한다."""
import shutil

from release_package import WORK, make_package, file_map, write_json
from test_installer import InstallerTests


def main():
    root = WORK / 'installer_synthetic_01'
    assert not root.exists(), '기존 합성 시험을 덮어쓰지 않습니다.'
    source, candidate = root / 'source', root / 'candidate'
    source.mkdir(parents=True)
    (source / 'Modules').mkdir()
    (source / 'data').mkdir()
    (source / 'THOG.exe').write_bytes(b'MZ synthetic non-executable fixture' * 64)
    (source / 'THOG.dat').write_bytes(bytes(range(256)) * 32768)
    (source / 'Modules/mmfs2.dll').write_bytes(b'synthetic unchanged module' * 128)
    (source / 'data/other.bin').write_bytes(b'synthetic original' * 65536)
    shutil.copytree(source, candidate)
    (candidate / 'THOG.dat').write_bytes(b'synthetic patched header\0' + (source / 'THOG.dat').read_bytes())
    (candidate / 'data/other.bin').write_bytes(b'synthetic patched second file' * 65536)
    (candidate / 'data/added.bin').write_bytes(b'synthetic new file' * 8192)
    make_package(source, candidate, list(file_map(source)),
                 ['THOG.dat', 'data/other.bin', 'data/added.bin'], root / 'package', root / 'evidence',
                 '0.0.0', 'SYNTHETIC_ONLY', '실제 게임 자료가 없는 설치기 회귀 시험입니다. 배포용이 아닙니다.')
    result = InstallerTests(root / 'evidence/package.json', source).run_all()
    result['scope'] = '게임 자료 없는 합성 3파일 시험. 실제 후보의 G6/G7 또는 최종 공개 ZIP 검사를 대체하지 않음'
    write_json(root / 'synthetic_summary.json', result)


if __name__ == '__main__':
    main()
