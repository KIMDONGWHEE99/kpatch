"""한글 출력·글꼴·스크립트 재저장의 위험을 독립 검수 사본에서 시험합니다."""
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from common import ROOT, BASE, EXTRACTED, WORK, save, sha, run_gdre, patch_settings
from pck_tools import read_pack, patch_pack

sys.path.insert(0, str(ROOT / 'tools/python_deps'))
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools import subset

STAGE = WORK / 'risk_02'
TOOLS = Path(__file__).parent


def comparable(text):
    return [token for token in re.findall(r'""".*?"""|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27|#[^\n]*|[^\s]', text, re.S) if not token.startswith('#')]


def compile_scripts(scripts, stage):
    sources, compiled, recovered = stage / 'sources', stage / 'compiled', stage / 'recovered'
    for path in (sources, compiled, recovered):
        path.mkdir(parents=True, exist_ok=True)
    for name, text in scripts.items():
        path = sources / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    changes = {}
    groups = defaultdict(list)
    for name in scripts:
        groups[str(Path(name).parent)].append(name)
    # 같은 폴더의 파일을 묶되 출력 폴더를 명시하여 이름 충돌을 막습니다.
    for index, (parent, names) in enumerate(groups.items()):
        output = compiled / parent
        output.mkdir(parents=True, exist_ok=True)
        run_gdre(['--compile=' + str(sources / name) for name in names] + ['--bytecode=4.6.2', '--output=' + str(output)], stage.name + '_compile_' + str(index))
        observed = recovered / parent
        observed.mkdir(parents=True, exist_ok=True)
        run_gdre(['--decompile=' + str(output / (Path(name).stem + '.gdc')) for name in names] + ['--bytecode=4.6.2', '--output=' + str(observed)], stage.name + '_recover_' + str(index))
    for name, text in scripts.items():
        generated = compiled / Path(name).with_suffix('.gdc')
        if comparable(text) != comparable((recovered / name).read_text(encoding='utf-8')):
            raise ValueError('스크립트 재분석 내용 불일치: ' + name)
        changes[str(Path(name).with_suffix('.gdc')).replace('\\', '/')] = generated.read_bytes()
    return changes


def prepare_fonts(pack, stage, characters):
    stage.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf'
    needed = {ord(c) for c in characters if c not in '\r\n\t'}
    font_reports = []
    for weight in (400, 700):
        font = TTFont(source)
        unsupported = needed - set(font.getBestCmap())
        if unsupported:
            raise ValueError('원본 한글 글꼴 필요 문자 누락: ' + repr(unsupported))
        font = instantiateVariableFont(font, {'wght': weight}, inplace=True)
        options = subset.Options()
        options.name_IDs = ['*']
        options.name_languages = ['*']
        builder = subset.Subsetter(options=options)
        builder.populate(unicodes=needed)
        builder.subset(font)
        font.recalcTimestamp = False
        target = stage / ('Korean%d.ttf' % weight)
        font.save(target)
        reopened = TTFont(target)
        if not needed.issubset(reopened.getBestCmap()):
            raise ValueError('생성한 한글 글꼴 문자 누락')
        font_reports.append({'weight': weight, 'sha256': sha(target), 'characters': len(needed), 'missing': []})
    entries = []
    for name in pack['entries']:
        if name.endswith('.fontdata'):
            entries.append({'path': name, 'korean_font': str(stage / ('Korean700.ttf' if 'Bold' in name else 'Korean400.ttf')),
                            'output': str(stage / Path(name).name)})
    config = {'fonts': entries, 'characters': list(sorted(characters - set('\r\n\t'))), 'report': str(stage / 'font_resources_report.json')}
    save(stage / 'font_config.json', config)
    run_gdre(['--path', str(WORK / 'tool_runtime'), '--script', str(TOOLS / 'font_fallbacks.gd'), '--', str(BASE / 'AgromaticDemo.exe'), str(stage / 'font_config.json')], stage.name + '_font_resources')
    observed = json.loads((stage / 'font_resources_report.json').read_text(encoding='utf-8'))
    if len(observed) != len(entries) or any(row['missing'] for row in observed):
        raise ValueError('실제 FontFile 대체 연결 검사 실패')
    save(stage / 'font_source_report.json', {'source_sha256': sha(source), 'fonts': font_reports})
    return {entry['path']: Path(entry['output']).read_bytes() for entry in entries}


def qa_scripts(scripts):
    result = dict(scripts)
    for name, marker in [('scripts/SteamManager.gd', 'func _init_steam() -> void :\n'),
                         ('scripts/GameAnalytics.gd', 'func _send_payload(payload: Dictionary) -> void :\n')]:
        before = result.get(name, (EXTRACTED / 'recovered' / name).read_text(encoding='utf-8'))
        if before.count(marker) != 1:
            raise ValueError('검수용 차단 진입점 불일치: ' + name)
        result[name] = before.replace(marker, marker + '\treturn\n')
    return result


def prepare():
    if (STAGE / 'game').exists():
        raise ValueError('기존 위험 시험 사본은 덮어쓰지 않습니다.')
    STAGE.mkdir(parents=True, exist_ok=True)
    pack = read_pack(BASE / 'AgromaticDemo.exe')
    scripts = {}
    for name in ('scripts/TranslationManager.gd', 'scripts/SettingsManager.gd'):
        text = (EXTRACTED / 'recovered' / name).read_text(encoding='utf-8')
        text = text.replace('DEFAULT_LANGUAGE = "en"', 'DEFAULT_LANGUAGE = "ko"')
        text = text.replace('DEFAULT_LANGUAGE: String = "en"', 'DEFAULT_LANGUAGE: String = "ko"')
        if name.endswith('TranslationManager.gd'):
            text = text.replace('TRANSLATIONS_ENABLED: = false', 'TRANSLATIONS_ENABLED: = true')
        else:
            text = text.replace('\tlanguage = "en"\n', '\tlanguage = "ko"\n')
        scripts[name] = text
    changes = compile_scripts(qa_scripts(scripts), STAGE / 'script_build')
    translation = json.loads(pack['entries']['data/translations/translations_en.json']['data'])
    translation['_meta'].update(language='ko', language_name='한국어')
    labels = {'continue': '이어하기', 'new_game': '새 게임', 'new_game_demo': '새 게임 (데모)',
              'load': '불러오기', 'load_game': '불러오기', 'guide': '도움말', 'options': '설정',
              'settings': '설정', 'exit': '종료', 'quit': '종료', 'wishlist': 'Steam 찜 목록에 추가'}
    for key, value in labels.items():
        if key in translation['ui']['buttons']:
            translation['ui']['buttons'][key] = value
    changes['data/translations/translations_ko.json'] = json.dumps(translation, ensure_ascii=False, indent=4).encode('utf-8')
    chars = set(''.join(labels.values()) + '한국어가나다라마바사아자차카타파하') | {chr(n) for n in range(32, 127)}
    changes.update(prepare_fonts(pack, STAGE / 'fonts', chars))
    changes['project.binary'] = patch_settings(pack['entries']['project.binary']['data'], {
        'application/config/name': 'Agromatic_KoreanQA', 'application/config/use_custom_user_dir': False,
        'display/window/size/mode': 0, 'display/window/size/window_width_override': 1440,
        'display/window/size/window_height_override': 810})
    game = STAGE / 'game'
    game.mkdir()
    for source in BASE.iterdir():
        if source.is_dir():
            shutil.copytree(source, game / source.name)
        elif source.name != 'AgromaticDemo.exe':
            shutil.copy2(source, game / source.name)
    report = patch_pack(BASE / 'AgromaticDemo.exe', game / 'AgromaticDemo.exe', changes)
    save(STAGE / 'risk_candidate_report.json', report)
    print('위험 시험 사본 준비:', game)


if __name__ == '__main__':
    prepare()
