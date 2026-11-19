"""실제 설치 전후 게임·원본 백업·사용자 저장의 내용 지문을 대조합니다."""
import argparse
import json
from pathlib import Path
from finish_update_20261104 import monitored_files, read
from update_20261104 import ROOT, WORK, GAME, BACKUP, sha, save


def snapshot(folder):
    return {p.relative_to(folder).as_posix(): sha(p) for p in folder.rglob('*') if p.is_file()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['before', 'after'])
    args = parser.parse_args()
    context_path = WORK / 'actual_install_before.json'
    if args.mode == 'before':
        assert not context_path.exists()
        baseline = read(WORK / 'installed_before.json')
        assert all(sha(GAME/r['path']) == r['sha256'] for r in baseline)
        pre = read(WORK.parent / 'qa_update_exact1104/evidence/prelaunch.json')
        data = {'game_files': snapshot(GAME), 'old_backup': snapshot(BACKUP),
                'user_files': monitored_files(pre['monitored_roots']), 'monitored_roots': pre['monitored_roots'],
                'steam_manifest_sha256': sha(Path('D:/steam/steamapps/appmanifest_4911050.acf'))}
        save(context_path, data)
        print(json.dumps({'status': 'PASS', 'game_files': len(data['game_files']), 'old_backup_files': len(data['old_backup']), 'user_files': len(data['user_files'])}))
        return
    before = read(context_path)
    candidate = read(WORK/'candidate_manifest.json')
    package = read(WORK.parent / 'package_1.0.1_r1/from_final_zip/manifest.json')
    game_hashes = snapshot(GAME)
    assert game_hashes == {r['path']: r['sha256'] for r in candidate['files']}, '실제 설치본 불일치'
    assert snapshot(BACKUP) == before['old_backup'], '이전 빌드 백업 변경'
    assert monitored_files(before['monitored_roots']) == before['user_files'], '사용자 저장 변경'
    assert sha(Path('D:/steam/steamapps/appmanifest_4911050.acf')) == before['steam_manifest_sha256']
    new_backup = BACKUP.parent / 'build_26365992'
    originals = []
    for index, record in enumerate(package['changes']):
        actual = sha(new_backup / f'cache/{index}/original')
        assert actual == record['original_sha256']
        originals.append({'path': record['path'], 'sha256': actual})
    receipt = read(new_backup / 'receipt.json')
    result = {'status': 'PASS', 'game_directory': str(GAME), 'candidate_id': candidate['candidate_id'],
              'game_files': len(game_hashes), 'original_backups': len(originals), 'old_backup_unchanged': True,
              'user_files_unchanged': len(before['user_files']), 'steam_manifest_unchanged': True,
              'new_backup_directory': str(new_backup), 'receipt': receipt, 'originals': originals,
              'post_install_game_execution': 'NOT_RUN', 'reason': '사용자의 화면 검수 종료 요청을 따릅니다.'}
    save(WORK/'actual_install_result.json',result)
    print(json.dumps({k:result[k] for k in ('status','game_files','original_backups','old_backup_unchanged','user_files_unchanged','post_install_game_execution')},ensure_ascii=False))


if __name__ == '__main__':
    main()
