"""사본 삭제 결과와 패치·번역·설치 게임의 보존 상태를 확인한다."""
import json
from pathlib import Path
import shutil
from soulash2_cleanup_plan import ROOT, OUT, digest, tree


def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8-sig'))


def main():
    plan = read('plan.json')
    deletion = read('deletion_result.json')
    protected = read('protected_before.json')
    installed_before = read('installed_before.json')
    remaining = [row['relative'] for row in plan['targets'] if Path(row['path']).exists()]
    changed = []
    for row in protected:
        path = ROOT / row['path']
        if not path.is_file() or path.stat().st_size != row['size'] or digest(path) != row['sha256']:
            changed.append(row['path'])
    installed = Path(plan['installed_game'])
    installed_after = [{'path': p.relative_to(installed).as_posix(), 'size': p.stat().st_size,
                        'mtime_ns': p.stat().st_mtime_ns} for p in tree(installed)]
    installed_same = sorted(installed_before, key=lambda row: row['path']) == sorted(installed_after, key=lambda row: row['path'])
    archive_same = digest(Path(plan['qa_archive']['path'])) == plan['qa_archive']['sha256']
    plan_same = digest(OUT / 'plan.json') == deletion['plan_sha256']
    free = shutil.disk_usage(ROOT).free
    passed = deletion['status'] == 'PASS' and not remaining and not changed and installed_same and archive_same and plan_same
    result = {'status': 'PASS' if passed else 'FAIL', 'deleted_targets': len(plan['targets']),
              'deleted_files': plan['delete_files'], 'deleted_bytes': plan['delete_bytes'],
              'remaining_targets': remaining, 'protected_files': len(protected), 'changed_protected': changed,
              'installed_files': len(installed_after), 'installed_inventory_unchanged': installed_same,
              'qa_archive_files': plan['qa_archive']['files'], 'qa_archive_unchanged': archive_same,
              'plan_unchanged': plan_same, 'disk_free_before': plan['disk_free_before'],
              'disk_free_after': free, 'disk_free_increase': free - plan['disk_free_before'],
              'patch_zip_sha256': digest(ROOT / 'release_output/SOULASH_2_KOREAN_PATCH_1.0.0_20261031.zip')}
    (OUT / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
