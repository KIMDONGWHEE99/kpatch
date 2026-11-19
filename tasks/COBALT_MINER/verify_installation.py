"""실제 설치 전후 파일·원본 백업·사용자 저장을 읽어 대조합니다. 게임은 실행하지 않습니다."""
import argparse
import json
import os
from pathlib import Path
from release_package import ROOT, WORK, sha, write_json, utc_now, file_map
from prepare_qa import snapshot

assert WORK.name == 'COBALT_MINER', '다른 게임의 도구를 가져오면 중단합니다.'

TARGET = Path('D:/steam/steamapps/common/Cobalt Miner').resolve()
CANDIDATE = ROOT / 'build_candidate/COBALT_MINER/ko_candidate_03'
OUT = WORK / 'actual_install_1.0.0_r1'
PACKAGE = WORK / 'package_1.0.0_r1'
STEAM_MANIFEST = Path('D:/steam/steamapps/appmanifest_4601880.acf')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def user_files(state):
    return [r for r in state['files'] if not Path(r['path']).resolve().is_relative_to(TARGET)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['pre', 'post'])
    parser.add_argument('--backup-directory', type=Path)
    args = parser.parse_args()
    mode = args.mode
    package = load(PACKAGE / 'package.json')
    tests = load(PACKAGE / 'installer_tests.json')
    assert tests['status'] == 'PASS' and tests['zip_sha256'] == package['zip_sha256']
    assert sha(package['archive']) == package['zip_sha256']
    manifest = load(PACKAGE / 'from_final_zip/manifest.json')
    assert sha(PACKAGE / 'from_final_zip/manifest.json') == package['manifest_sha256']
    before_path = OUT / 'before.json'
    if mode == 'pre':
        assert not OUT.exists()
        OUT.mkdir(parents=True)
        expected = {r['path']: r['sha256'] for r in manifest['baseline']}
        assert {n: sha(p) for n, p in file_map(TARGET).items()} == expected
        text = STEAM_MANIFEST.read_text(encoding='utf-8')
        assert '"24347666"' in text and '"4601880"' in text
        before = snapshot()
        write_json(before_path, dict(status='PASS', recorded_utc=utc_now(), target=str(TARGET),
                                     zip_sha256=package['zip_sha256'], steam_manifest_sha256=sha(STEAM_MANIFEST),
                                     snapshot=before, user_files=user_files(before)))
        print(json.dumps(dict(status='PASS', original_files=len(expected), user_files=len(user_files(before)))))
        return
    before = load(before_path)
    assert before['target'] == str(TARGET) and before['zip_sha256'] == package['zip_sha256']
    actual = {n: sha(p) for n, p in file_map(TARGET).items()}
    candidate = {n: sha(p) for n, p in file_map(CANDIDATE).items()}
    assert actual == candidate
    after = snapshot()
    assert user_files(after) == before['user_files']
    assert sha(STEAM_MANIFEST) == before['steam_manifest_sha256']
    import hashlib
    root_key = hashlib.sha256(str(TARGET).lower().encode('utf-8')).hexdigest().upper()[:16]
    backup = args.backup_directory or Path(os.environ['LOCALAPPDATA']) / 'CobaltMinerKoreanPatch/working_private' / root_key / 'build_24347666'
    backup = backup.resolve()
    assert backup.name == 'build_24347666' and backup.parent.name == root_key
    receipt = load(backup / 'receipt.json')
    assert receipt['status'] == 'COMPLETE' and receipt['mode'] == 'Install'
    assert receipt['manifest_sha256'] == package['manifest_sha256'] and Path(receipt['game_directory']).resolve() == TARGET
    backups = []
    for index, row in enumerate(manifest['changes']):
        path = backup / f'cache/{index}/original'
        assert sha(path) == row['original_sha256']
        backups.append(dict(path=row['path'], original_sha256=sha(path)))
    result = dict(status='PASS', completed_utc=utc_now(), target=str(TARGET), zip_sha256=package['zip_sha256'],
                  actual_files=actual, candidate_match='PASS', changed_files=len(backups), original_backups=backups,
                  backup_directory=str(backup), receipt_sha256=sha(backup / 'receipt.json'),
                  user_integrity='PASS', preserved_user_files=len(before['user_files']),
                  steam_manifest_unchanged='PASS', game_launch_after_install='NOT_RUN', after=after)
    write_json(OUT / 'verification.json', result)
    print(json.dumps({k: result[k] for k in ('status', 'target', 'changed_files', 'candidate_match', 'preserved_user_files', 'backup_directory')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
