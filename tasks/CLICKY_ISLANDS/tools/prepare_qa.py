"""Steam·사용자 저장을 분리한 검수 사본을 만들고, 검수용으로만 바꾼 것을 기록합니다.

사용: python prepare_qa.py <build_id | baseline> <run_id>
검수 사본에만 들어가는 변경(배포본에는 없음):
  - godot_steam.gdc: Steam 초기화를 건너뜀(업적·통계·클라우드 쓰기 차단)
  - korean_patch_qa/qa_driver.gdc: 화면 이동·캡처용 검수 코드(자동 실행 목록에 추가)
  - project.binary: 앱 이름, 저장 폴더 이름, 자동 실행 1개
HOW_EMPIRES_WORK의 prepare_qa.py를 고쳐 썼습니다.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, BASE, RECOVERED, WORK, CANDIDATE, PCK_NAME, save, sha, sha_bytes, run_gdre, patch_settings
from pck_tools import patch_pack, read_pack

TOOLS = Path(__file__).parent


def main():
    build_id, run_id = sys.argv[1], sys.argv[2]
    source = BASE if build_id == 'baseline' else CANDIDATE / build_id
    run = WORK / 'qa' / run_id
    game = run / 'game'
    if game.exists():
        raise SystemExit('같은 검수 실행 ID가 이미 있습니다: ' + run_id)
    game.mkdir(parents=True)
    for path in source.iterdir():
        if path.name != PCK_NAME:
            shutil.copy2(path, game / path.name)
    steam = (RECOVERED / 'globals/godot_steam/godot_steam.gd').read_text(encoding='utf-8')
    marker = 'func initialize_steam() -> void :\n'
    assert steam.count(marker) == 1
    steam = steam.replace(marker, marker + '\tprint("KOREAN QA: Steam disabled")\n\treturn\n')
    scripts = run / 'scripts'
    scripts.mkdir()
    (scripts / 'godot_steam.gd').write_text(steam, encoding='utf-8', newline='\n')
    shutil.copy2(TOOLS / 'qa_driver.gd', scripts / 'qa_driver.gd')
    compiled = run / 'compiled'
    compiled.mkdir()
    for name in ('godot_steam.gd', 'qa_driver.gd'):
        run_gdre(['--compile=' + str(scripts / name), '--bytecode=4.5.0', '--output=' + str(compiled)], f'qa_{run_id}_{name}')
    pack = read_pack(source / PCK_NAME)
    settings = pack['entries']['project.binary']['data']
    user_dir = 'ClickyIslands_KoreanQA/' + run_id
    changes = {'globals/godot_steam/godot_steam.gdc': (compiled / 'godot_steam.gdc').read_bytes(),
               'korean_patch_qa/qa_driver.gdc': (compiled / 'qa_driver.gdc').read_bytes(),
               'korean_patch_qa/qa_driver.gd.remap': b'[remap]\n\npath="res://korean_patch_qa/qa_driver.gdc"\n',
               'project.binary': patch_settings(settings, {'application/config/name': 'ClickyIslands KoreanQA ' + run_id,
                                                           'application/config/custom_user_dir_name': user_dir,
                                                           'autoload/KoreanQA': '*res://korean_patch_qa/qa_driver.gd'})}
    report = patch_pack(source / PCK_NAME, game / PCK_NAME, changes)
    save(run / 'qa_boundary.json', {'build_id': build_id, 'run_id': run_id, 'source': source.relative_to(ROOT).as_posix(),
                                    'source_pck_sha256': sha(source / PCK_NAME), 'qa_pck_sha256': sha(game / PCK_NAME),
                                    'exe_sha256': sha(game / 'Clicky Islands.exe'), 'user_dir_name': user_dir,
                                    'qa_only_changes': {k: sha_bytes(v) for k, v in changes.items()},
                                    'qa_only': ['godot_steam.initialize_steam 즉시 반환', '검수 코드 qa_driver 자동 실행',
                                                'project.binary: 앱 이름·저장 폴더 이름·자동 실행 1개'], 'pack': report})
    print('QA copy ready', run_id, report['output_sha256'])


if __name__ == '__main__':
    main()
