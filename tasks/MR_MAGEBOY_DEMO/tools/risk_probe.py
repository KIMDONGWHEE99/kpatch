"""원본 재저장·한국어 스크립트·글꼴 조립을 별도 사본에서 시험합니다."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pck_tools import ROOT, GAME, BASELINE, EXTRACTED, WORK, read_pack, patch_pack, patch_settings

sys.path.insert(0, str(ROOT / 'tools/python_deps'))
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools import subset

PCK = 'MR MAGEBOY DEMO.pck'
TOOL = ROOT / 'tools/gdre_2.6.4/bin/gdre_tools.exe'
RISK = WORK / 'risk_01'
RUNTIME = RISK / 'resource_probe'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def tool(arguments, label):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env['APPDATA'] = str(RUNTIME / 'roaming')
    env['LOCALAPPDATA'] = str(RUNTIME / 'local')
    command = [str(TOOL), '--headless'] + [a.as_posix() if isinstance(a, Path) else str(a) for a in arguments]
    proc = subprocess.run(command, env=env, capture_output=True, timeout=180)
    (RUNTIME / (label + '.stdout.log')).write_bytes(proc.stdout)
    (RUNTIME / (label + '.stderr.log')).write_bytes(proc.stderr)
    save(RUNTIME / (label + '.command.json'), {'command': command, 'exit_code': proc.returncode})
    assert proc.returncode == 0, (label, proc.returncode, proc.stderr[-1500:])


def comparable(text):
    # 문자열과 문법을 보존한 채 복원기의 공백 정리만 비교에서 제외합니다.
    return re.findall(r'""".*?"""|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27|[^\s]', text, re.S)


def prepare():
    RISK.mkdir(parents=True, exist_ok=True)
    sources = RISK / 'scripts'
    sources.mkdir(exist_ok=True)
    # 새 게임 확인 문구를 바꿔 스크립트 재컴파일 경로도 함께 검증합니다.
    script = 'game/scenes/menus/main_menu/main_menu_with_animations.gd'
    before = (EXTRACTED / 'recovered' / script).read_text(encoding='utf-8')
    after = before.replace('new_game_button.text = "Confirm?"', 'new_game_button.text = "확인할까요?"')
    assert before != after
    (sources / 'main_menu_with_animations.gd').write_text(after, encoding='utf-8')
    (sources / 'noop.gd').write_text(before, encoding='utf-8')
    steam = (EXTRACTED / 'recovered/game/scripts/steamworks.gd').read_text(encoding='utf-8')
    # 검수 사본에서만 초기화 진입을 차단해 업적·통계·클라우드를 건드리지 않습니다.
    marker = 'func initialize_steam(app_id: int) -> void :\n'
    assert steam.count(marker) == 1
    steam = steam.replace(marker, marker + '\tprint("Korean QA: Steam initialization disabled")\n\treturn\n')
    (sources / 'steamworks.gd').write_text(steam, encoding='utf-8')
    compiled = RISK / 'compiled'
    compiled.mkdir(exist_ok=True)
    tool(['--compile=' + (sources / '*.gd').as_posix(), '--bytecode=4.5.0', '--output=' + compiled.as_posix()], 'compile')
    decompiled = RISK / 'decompiled'
    decompiled.mkdir(exist_ok=True)
    tool(['--decompile=' + (compiled / '*.gdc').as_posix(), '--bytecode=4.5.0', '--output=' + decompiled.as_posix()], 'decompile')
    for p in sources.glob('*.gd'):
        assert comparable(p.read_text(encoding='utf-8')) == comparable((decompiled / p.name).read_text(encoding='utf-8')), p.name
    scene = 'game/scenes/menus/main_menu/main_menu_with_animations.tscn'
    scene_source = (EXTRACTED / 'recovered' / scene).read_text(encoding='utf-8')
    scene_target = scene_source.replace('text = "Help by Wishlisting on Steam!"', 'text = "Steam 찜 목록에 추가해 주세요!"')
    assert scene_source != scene_target
    scene_dir = RISK / 'scenes'
    scene_dir.mkdir(exist_ok=True)
    (scene_dir / 'main_menu_with_animations.tscn').write_text(scene_target, encoding='utf-8')
    scene_config = {'entries': [{'source': (scene_dir / 'main_menu_with_animations.tscn').as_posix(),
                                 'output': (scene_dir / 'main_menu_with_animations.scn').as_posix()}],
                    'report': (scene_dir / 'report.json').as_posix()}
    save(scene_dir / 'config.json', scene_config)
    tool(['--path', RUNTIME, '--script', ROOT / 'tasks/MR_MAGEBOY_DEMO/tools/resource_convert.gd', '--', scene_dir / 'config.json'], 'scene_compile')
    assert (scene_dir / 'main_menu_with_animations.scn').exists()
    chars = 'Steam 찜 목록에 추가해 주세요!확인할까요?새 게임환경 설정종료한국어가나다라마바사아자차카타파하'
    fonts = RISK / 'fonts'
    fonts.mkdir(exist_ok=True)
    for weight in (400, 700):
        font = TTFont(ROOT / 'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf')
        font = instantiateVariableFont(font, {'wght': weight}, inplace=True)
        options = subset.Options()
        options.name_IDs = ['*']
        options.name_languages = ['*']
        builder = subset.Subsetter(options=options)
        builder.populate(text=chars)
        builder.subset(font)
        dest = fonts / ('Korean%d.ttf' % weight)
        font.save(dest)
        assert all(ord(c) in TTFont(dest).getBestCmap() for c in chars if not c.isspace())
    font_paths = [e['name'] for e in read_pack(BASELINE / PCK)[3] if e['name'].endswith('.fontdata') and 'PixelOperator' in e['name']]
    assert len(font_paths) == 2
    config = {'characters': sorted(set(chars) - set('\n\r\t ')), 'fonts': [
        {'path': name, 'output': (fonts / Path(name).name).as_posix(),
         'korean_font': (fonts / ('Korean700.ttf' if 'Bold' in name else 'Korean400.ttf')).as_posix()}
        for name in font_paths], 'report': (fonts / 'engine_report.json').as_posix()}
    save(fonts / 'config.json', config)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    (RUNTIME / 'project.godot').write_text('config_version=5\n[application]\nconfig/name="MR Mageboy Resource Probe"\n', encoding='utf-8')
    tool(['--path', RUNTIME, '--script', ROOT / 'tasks/ALCHEMORTIS_DEMO/tools/font_fallbacks.gd', '--', BASELINE / PCK, fonts / 'config.json'], 'fonts')
    report = json.loads((fonts / 'engine_report.json').read_text(encoding='utf-8'))
    assert not any(r['missing'] for r in report)
    remap = (EXTRACTED / 'raw' / (scene + '.remap')).read_text(encoding='utf-8')
    scene_pack_path = remap.split('path="res://', 1)[1].split('"', 1)[0]
    changes = {script[:-3] + '.gdc': (compiled / 'main_menu_with_animations.gdc').read_bytes(),
               scene_pack_path: (scene_dir / 'main_menu_with_animations.scn').read_bytes()}
    changes.update({name: (fonts / Path(name).name).read_bytes() for name in font_paths})
    candidate = ROOT / 'build_candidate' / GAME / 'risk_01'
    assert not candidate.exists(), '위험 시험 후보를 덮어쓰지 않습니다.'
    shutil.copytree(BASELINE, candidate)
    patch_pack(BASELINE / PCK, candidate / PCK, changes)
    # 실행용 사본의 제품명·쓰기 위치·Steam 초기화만 별도로 변경합니다.
    qa = RISK / 'qa_game'
    shutil.copytree(candidate, qa)
    contents = {e['name']: e['data'] for e in read_pack(candidate / PCK)[3]}
    settings = {'application/config/name': 'MR_MAGEBOY_KO_QA_RISK_01',
                'debug/file_logging/log_path': (qa / 'runtime.log').as_posix(),
                'display/window/size/mode': 0}
    qa_changes = {'project.binary': patch_settings(contents['project.binary'], settings),
                  'game/scripts/steamworks.gdc': (compiled / 'steamworks.gdc').read_bytes()}
    patch_pack(candidate / PCK, qa / PCK, qa_changes)
    save(RISK / 'risk_report.json', {'status': 'PASS', 'graphics_status': 'NOT_RUN',
         'source_pck_sha256': sha(BASELINE / PCK), 'noop_pck_sha256': sha(WORK / 'noop.pck'),
         'candidate_pck_sha256': sha(candidate / PCK), 'qa_pck_sha256': sha(qa / PCK),
         'script_roundtrip_files': len(list(sources.glob('*.gd'))), 'font_report': report,
         'candidate_changes': {k: hashlib.sha256(v).hexdigest() for k,v in changes.items()},
         'qa_changes': {k: hashlib.sha256(v).hexdigest() for k,v in qa_changes.items()},
         'qa_project_properties': settings, 'steam_boundary': 'initialize_steam 진입점에 return 추가; 초기화 실패 상태 유지',
         'launch_path': str(qa / 'MR MAGEBOY DEMO.exe')})
    print(json.dumps({'candidate': str(candidate), 'qa': str(qa), 'status': 'PASS', 'graphics_status': 'NOT_RUN'}, ensure_ascii=False))


if __name__ == '__main__':
    prepare()
