"""번역 원본을 조립하고 재추출 비교 후 별도 실행 검수 사본을 만듭니다."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import ast
import collections
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pck_tools import ROOT, GAME, BASELINE, EXTRACTED, WORK, read_pack, patch_pack, patch_settings, read_settings, variant

sys.path.insert(0, str(ROOT / 'tools/python_deps'))
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools import subset
from fontTools.pens.recordingPen import RecordingPen

PCK = 'MR MAGEBOY DEMO.pck'
TOOL = ROOT / 'tools/gdre_2.6.4/bin/gdre_tools.exe'
TOOLS = ROOT / 'tasks/MR_MAGEBOY_DEMO/tools'
CSV_SOURCE = 'addons/maaacks_game_template/base/translations/menus_translations.csv'
EN_RESOURCE = 'addons/maaacks_game_template/base/translations/menus_translations.en.translation'
TITLE_FONT_RESOURCE = 'korean_patch/fonts/TitlePixel.ttf'
TITLE_TEXT = '채집 마법사'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def snapshot_inputs(modified, translation, stage, extra_inputs=None):
    # 조립 중 작성자가 수정해도 고정 사본만 읽고, 복제 중 변경은 즉시 차단합니다.
    modified = Path(modified).resolve()
    translation = Path(translation).resolve() if translation else None
    source_files = {('modified/' + p.relative_to(modified).as_posix()): p
                    for p in sorted(modified.rglob('*')) if p.is_file()}
    if translation:
        for path in sorted(translation.parent.glob('*.json')):
            source_files['translation_meta/' + path.name] = path
        source_files['translation_meta/' + translation.name] = translation
    for name, path in (extra_inputs or {}).items():
        assert not Path(name).is_absolute() and '..' not in Path(name).parts, name
        assert name not in source_files, ('고정 입력 경로 중복', name)
        source_files[name] = Path(path).resolve()
    inventory = {name: sha(path) for name, path in source_files.items()}
    input_lock = {'source_pck_sha256': sha(BASELINE / PCK), 'files': inventory,
                  'modified_source': str(modified),
                  'translation_source': str(translation) if translation else None,
                  'extra_sources': {name: str(Path(path).resolve()) for name, path in (extra_inputs or {}).items()}}
    lock_path = stage / 'input_lock.json'
    snapshot = stage / 'inputs'
    if lock_path.exists():
        assert read(lock_path) == input_lock, '조립 입력이 바뀌었으므로 새 후보 번호가 필요합니다.'
    for name, path in source_files.items():
        payload = path.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == inventory[name], ('복제 중 입력 변경', name)
        destination = snapshot / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            assert sha(destination) == inventory[name], ('고정 사본 해시 불일치', name)
        else:
            destination.write_bytes(payload)
        assert sha(destination) == inventory[name], ('고정 사본 복제 불일치', name)
    after_files = {('modified/' + p.relative_to(modified).as_posix()): p
                   for p in sorted(modified.rglob('*')) if p.is_file()}
    if translation:
        after_files.update({'translation_meta/' + p.name: p for p in sorted(translation.parent.glob('*.json'))})
        after_files['translation_meta/' + translation.name] = translation
    after_files.update({name: Path(path).resolve() for name, path in (extra_inputs or {}).items()})
    assert {name: sha(path) for name, path in after_files.items()} == inventory, '복제 중 입력 목록·내용이 바뀌었습니다.'
    assert {p.relative_to(snapshot).as_posix(): sha(p) for p in snapshot.rglob('*') if p.is_file()} == inventory, '고정 사본 목록·내용이 다릅니다.'
    write(lock_path, input_lock)
    return snapshot / 'modified', snapshot / 'translation_meta' / translation.name if translation else None


def verify_snapshot(stage):
    snapshot = stage / 'inputs'
    actual = {p.relative_to(snapshot).as_posix(): sha(p) for p in snapshot.rglob('*') if p.is_file()}
    assert actual == read(stage / 'input_lock.json')['files'], '조립 도중 고정 사본이 바뀌었습니다.'


def comparable(text):
    # 복원기가 제거하는 주석만 제외하며 문자열 속 #과 코드 토큰은 보존합니다.
    tokens = re.findall(r'""".*?"""|\x27\x27\x27.*?\x27\x27\x27|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27|\#[^\r\n]*|[^\s]', text, re.S)
    result = []
    for token in tokens:
        if token.startswith('#'):
            continue
        if token.startswith(('"', "'")):
            # 줄바꿈의 \\n 표기와 자산 복원기의 실제 줄바꿈은 같은 문자열 값입니다.
            try:
                value = json.loads(token, strict=False) if token.startswith('"') and not token.startswith('"""') else ast.literal_eval(token)
            except (ValueError, SyntaxError):
                delimiter = 3 if token.startswith(('"""', "'''")) else 1
                value = token[delimiter:-delimiter]
                escapes = {'n': '\n', 'r': '\r', 't': '\t', '"': '"', "'": "'", '\\': '\\'}
                value = re.sub(r'\\([nrt"\x27\\])', lambda match: escapes[match.group(1)], value)
            result.append(('STRING', value))
        else:
            result.append(('CODE', token))
    return result


def resource_comparable(text):
    # 복원기가 논리 경로에서 되붙인 루트 UID는 원본 binary의 metadata로 다시 고정합니다.
    lines = text.splitlines(True)
    lines[0] = re.sub(r' uid="[^"]*"', '', lines[0])
    return comparable(''.join(lines))


def run_tool(args, stage, label):
    runtime = stage / 'resource_probe'
    runtime.mkdir(parents=True, exist_ok=True)
    if not (runtime / 'project.godot').exists():
        (runtime / 'project.godot').write_text('config_version=5\n[application]\nconfig/name="MR Mageboy Resource Build"\n', encoding='utf-8')
    env = os.environ.copy()
    env['APPDATA'] = str(runtime / 'roaming')
    env['LOCALAPPDATA'] = str(runtime / 'local')
    command = [str(TOOL), '--headless'] + [p.as_posix() if isinstance(p, Path) else str(p) for p in args]
    started = datetime.now(timezone.utc).isoformat()
    proc = subprocess.run(command, env=env, capture_output=True, timeout=240)
    completed = datetime.now(timezone.utc).isoformat()
    (runtime / (label + '.stdout.log')).write_bytes(proc.stdout)
    (runtime / (label + '.stderr.log')).write_bytes(proc.stderr)
    write(runtime / (label + '.command.json'), {'command': command, 'exit_code': proc.returncode,
          'tool_sha256': sha(TOOL), 'game_id': GAME, 'steam_build': '25734075',
          'started_utc': started, 'completed_utc': completed,
          'stdout_sha256': hashlib.sha256(proc.stdout).hexdigest(), 'stderr_sha256': hashlib.sha256(proc.stderr).hexdigest()})
    assert proc.returncode == 0, (label, proc.returncode, proc.stderr[-2000:])


def run_script(script, args, stage, label):
    run_tool(['--path', stage / 'resource_probe', '--script', TOOLS / script, '--'] + args, stage, label)


def target_for(source, remaps, originals):
    target = remaps.get(source, source)
    assert target in originals, ('원본 target 없는 수정', source, target)
    return target


def compile_scripts(sources, modified, stage, remaps, originals):
    expected_dir = stage / 'script_inputs'
    roundtrip_dir = stage / 'script_roundtrip'
    staged = []
    for source in sources:
        rel = source.relative_to(modified)
        copy = expected_dir / rel
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, copy)
        staged.append(copy)
    # GDRE는 출력 경로를 생략하면 현재 폴더에 저장하므로 부모별 경로를 명시합니다.
    groups = collections.defaultdict(list)
    for copy in staged:
        groups[copy.parent].append(copy)
    for index, (directory, group) in enumerate(groups.items()):
        run_tool(['--compile=' + p.as_posix() for p in group] + ['--bytecode=4.5.0', '--output=' + directory.as_posix()], stage, 'scripts_compile_%03d' % index)
    for copy in staged:
        compiled = copy.with_suffix('.gdc')
        assert compiled.exists(), compiled
        dest = roundtrip_dir / compiled.relative_to(expected_dir)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(compiled, dest)
    compiled_files = sorted(roundtrip_dir.rglob('*.gdc'))
    groups = collections.defaultdict(list)
    for compiled in compiled_files:
        groups[compiled.parent].append(compiled)
    for index, (directory, group) in enumerate(groups.items()):
        run_tool(['--decompile=' + p.as_posix() for p in group] + ['--bytecode=4.5.0', '--output=' + directory.as_posix()], stage, 'scripts_decompile_%03d' % index)
    changes = {}
    rows = []
    for copy in staged:
        logical = copy.relative_to(expected_dir).as_posix()
        observed = roundtrip_dir / copy.relative_to(expected_dir)
        assert comparable(copy.read_text(encoding='utf-8')) == comparable(observed.read_text(encoding='utf-8')), logical
        target = target_for(logical, remaps, originals)
        assert target.endswith('.gdc'), (logical, target)
        changes[target] = copy.with_suffix('.gdc').read_bytes()
        rows.append({'source': logical, 'target': target, 'input_sha256': sha(copy), 'compiled_sha256': sha(copy.with_suffix('.gdc')),
                     'decompiled_sha256': sha(observed), 'token_roundtrip': 'PASS'})
    write(stage / 'script_roundtrip.json', rows)
    return changes


def compile_resources(sources, modified, stage, remaps, originals):
    entries = []
    for source in sources:
        logical = source.relative_to(modified).as_posix()
        target = target_for(logical, remaps, originals)
        output = stage / 'resource_outputs' / target
        output.parent.mkdir(parents=True, exist_ok=True)
        entries.append({'source': source.as_posix(), 'logical': logical, 'target': target,
                        'output': output.as_posix(), 'original': (EXTRACTED / 'raw' / target).as_posix()})
    config = stage / 'resources.json'
    write(config, {'entries': entries, 'report': (stage / 'resources_report.json').as_posix()})
    if entries:
        run_script('resource_convert.gd', [config], stage, 'resources_build')
    text_entries = []
    for entry in entries:
        output = stage / 'resource_roundtrip' / entry['logical']
        output.parent.mkdir(parents=True, exist_ok=True)
        text_entries.append({'source': entry['output'], 'output': output.as_posix(), 'mode': 'text'})
    check = stage / 'resources_roundtrip.json'
    write(check, {'entries': text_entries, 'report': (stage / 'resources_roundtrip_report.json').as_posix()})
    if text_entries:
        run_script('resource_convert.gd', [check], stage, 'resources_roundtrip')
        for entry, report in zip(entries, read(stage / 'resources_report.json')):
            expected = Path(entry['source']).read_text(encoding='utf-8')
            observed = (stage / 'resource_roundtrip' / entry['logical']).read_text(encoding='utf-8')
            assert resource_comparable(expected) == resource_comparable(observed), entry['logical']
            for key in ('ver_major', 'ver_minor', 'uid', 'using_named_scene_ids', 'stored_big_endian', 'stored_use_real64'):
                assert report['original_info'][key] == report['output_info'][key], (entry['logical'], key)
    return {entry['target']: Path(entry['output']).read_bytes() for entry in entries}


def build_fonts(characters, stage, originals):
    fonts = stage / 'fonts'
    fonts.mkdir(exist_ok=True)
    source = ROOT / 'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf'
    coverage = []
    required = {ord(c) for c in characters if not c.isspace()}
    for weight in (400, 700):
        font = TTFont(source)
        supported = required.intersection(font.getBestCmap())
        missing_hangul = sorted(code for code in required - supported if 0xAC00 <= code <= 0xD7A3 or 0x1100 <= code <= 0x11FF or 0x3130 <= code <= 0x318F)
        assert not missing_hangul, ('원본 한글 글꼴 문자 누락', missing_hangul)
        font = instantiateVariableFont(font, {'wght': weight}, inplace=True)
        options = subset.Options()
        options.name_IDs = ['*']
        options.name_languages = ['*']
        builder = subset.Subsetter(options=options)
        builder.populate(unicodes=supported)
        builder.subset(font)
        font.recalcTimestamp = False
        dest = fonts / ('Korean%d.ttf' % weight)
        font.save(dest)
        checked = TTFont(dest)
        assert supported.issubset(checked.getBestCmap()) and checked['OS/2'].usWeightClass == weight
        coverage.append({'weight': weight, 'sha256': sha(dest), 'supported_characters': len(supported), 'original_font_fallback_required': sorted(required - supported)})
    paths = sorted(k for k in originals if k.endswith('.fontdata') and 'PixelOperator' in k)
    assert len(paths) == 2
    config = {'characters': sorted(set(characters) - set('\r\n\t ')), 'fonts': [
        {'path': k, 'output': (fonts / Path(k).name).as_posix(), 'korean_font': (fonts / ('Korean700.ttf' if 'Bold' in k else 'Korean400.ttf')).as_posix()}
        for k in paths], 'report': (fonts / 'engine_report.json').as_posix()}
    write(fonts / 'config.json', config)
    run_script('font_fallbacks.gd', [BASELINE / PCK, fonts / 'config.json'], stage, 'fonts_build')
    native = read(fonts / 'engine_report.json')
    assert not any(r['missing'] for r in native), native
    write(fonts / 'coverage.json', {'source_sha256': sha(source), 'required_characters': len(required), 'fonts': coverage,
                                  'dynamic_font_reopen': 'PASS', 'native_missing': 0})
    (stage / 'required_characters.txt').write_text(''.join(sorted(set(characters))), encoding='utf-8')
    return {k: (fonts / Path(k).name).read_bytes() for k in paths}


def build_title_font(stage):
    source = stage / 'inputs/fonts/title/Source.ttf'
    asset = stage / 'inputs/fonts/title/TitlePixel.ttf'
    license_path = stage / 'inputs/fonts/title/LICENSE.txt'
    manifest_path = stage / 'inputs/fonts/title/source_manifest.json'
    source_manifest = read(manifest_path)
    assert source_manifest['source_sha256'] == sha(source), '제목 글꼴 원본 명세 해시 불일치'
    assert source_manifest['output_sha256'] == sha(asset), '제목 글꼴 선택 명세 해시 불일치'
    assert source_manifest['license_sha256'] == sha(license_path), '제목 글꼴 라이선스 명세 해시 불일치'
    assert source_manifest['title'] == TITLE_TEXT, '제목 글꼴 명세 문구 불일치'
    original = TTFont(source)
    selected = TTFont(asset)
    original_cmap, selected_cmap = original.getBestCmap(), selected.getBestCmap()
    required = sorted({ord(character) for character in TITLE_TEXT})
    assert set(required).issubset(original_cmap), '제목 원본 글꼴 문자 누락'
    assert set(required) == set(selected_cmap), '제목 선택 글꼴 문자 범위 불일치'
    assert selected['OS/2'].usWeightClass == 700 and selected['OS/2'].fsSelection & 32, '제목 굵기 속성 불일치'
    assert selected['head'].macStyle & 1, '제목 굵기 표기 불일치'
    assert selected['name'].getDebugName(1) == 'MageboyKoreanTitle', '제목 글꼴 파생 이름 불일치'
    original_glyphs, selected_glyphs = original.getGlyphSet(), selected.getGlyphSet()
    for code in required:
        before, after = RecordingPen(), RecordingPen()
        original_glyphs[original_cmap[code]].draw(before)
        selected_glyphs[selected_cmap[code]].draw(after)
        assert before.value == after.value, ('제목 글리프 모양 변경', code)
        assert original['hmtx'].metrics[original_cmap[code]] == selected['hmtx'].metrics[selected_cmap[code]], ('제목 글리프 간격 변경', code)
    assert license_path.exists() and license_path.stat().st_size > 0, '제목 글꼴 라이선스 누락'
    report = {'resource': TITLE_FONT_RESOURCE, 'required_text': TITLE_TEXT, 'required_characters': required,
              'source_sha256': sha(source), 'asset_sha256': sha(asset), 'license_sha256': sha(license_path),
              'source_manifest_sha256': sha(manifest_path),
              'font_family': selected['name'].getDebugName(1), 'weight_class': selected['OS/2'].usWeightClass,
              'fs_selection': selected['OS/2'].fsSelection, 'mac_style': selected['head'].macStyle,
              'source_cmap_coverage': 'PASS', 'subset_cmap_coverage': 'PASS',
              'glyph_outline_and_advance_match': 'PASS', 'native_glyph_lookup': 'NOT_RUN'}
    write(stage / 'title_font_report.json', report)
    return {TITLE_FONT_RESOURCE: asset.read_bytes()}


def check_title_font(candidate, stage):
    config = {'resource': TITLE_FONT_RESOURCE, 'characters': sorted(set(TITLE_TEXT)),
              'expected_data_sha256': sha(stage / 'inputs/fonts/title/TitlePixel.ttf'),
              'report': (stage / 'title_font_native_report.json').as_posix()}
    write(stage / 'title_font_native_config.json', config)
    run_script('title_font_probe.gd', [candidate / PCK, stage / 'title_font_native_config.json'], stage, 'title_font_native')
    native = read(stage / 'title_font_native_report.json')
    assert native['missing'] == [] and native['font_data_sha256'] == config['expected_data_sha256'], '제목 글꼴 원시 로딩·글리프 실패'
    report = read(stage / 'title_font_report.json')
    report['native_glyph_lookup'] = 'PASS'
    report['native_report_sha256'] = sha(stage / 'title_font_native_report.json')
    write(stage / 'title_font_report.json', report)


def build_translation(path, stage, originals):
    values = read(path)
    assert isinstance(values, dict) and all(isinstance(v, str) for v in values.values())
    with (EXTRACTED / 'recovered' / CSV_SOURCE).open(encoding='utf-8-sig', newline='') as stream:
        original = {r['key']: r['en'] for r in csv.DictReader(stream)}
    assert set(original).issubset(values), ('기존 번역표 키 삭제', set(original) - set(values))
    additions_path = Path(path).parent / 'translation_table_additions.json'
    additions = read(additions_path) if additions_path.exists() else {}
    assert set(additions) == set(values) - set(original), ('표시 전용 허용 추가키 불일치', set(values) - set(original), set(additions))
    assert all(values[key] == target for key, target in additions.items()), '표시 전용 추가값 불일치'
    config = {'values': Path(path).as_posix(), 'locale': 'en', 'output': (stage / 'menus_translations.en.translation').as_posix(),
              'report': (stage / 'translation_report.json').as_posix(), 'original': (EXTRACTED / 'raw' / EN_RESOURCE).as_posix()}
    write(stage / 'translation_config.json', config)
    run_script('translation_build.gd', [stage / 'translation_config.json'], stage, 'translation_build')
    observed = read(stage / 'translation_report.json')
    assert observed['values'] == values and observed['locale'] == 'en'
    assert EN_RESOURCE in originals
    return {EN_RESOURCE: (stage / 'menus_translations.en.translation').read_bytes()}, ''.join(values.values())


def settings_values(path):
    section = ''
    values = {}
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
        elif re.match(r'^[A-Za-z_][A-Za-z_0-9/.]*=', line):
            key, value = line.split('=', 1)
            values[(section + '/' if section else '') + key] = value
    return values


def build_settings(source, stage, originals):
    original = settings_values(EXTRACTED / 'recovered/project.godot')
    desired = settings_values(source)
    assert set(original) == set(desired), '번역 작업에서 게임 설정 키를 추가·삭제할 수 없습니다.'
    fields = {}
    binary_original = read_settings(originals['project.binary'])
    for key in original:
        if original[key] == desired[key]:
            continue
        before, after = json.loads(original[key]), json.loads(desired[key])
        assert isinstance(before, (str, int, bool)) and type(after) is type(before), (key, before, after)
        assert binary_original[key] == variant(before), ('원본 설정 위치 불일치', key)
        fields[key] = after
    if not fields:
        return {}
    output = patch_settings(originals['project.binary'], fields)
    observed = read_settings(output)
    assert set(observed) == set(binary_original)
    for key in observed:
        assert observed[key] == (variant(fields[key]) if key in fields else binary_original[key]), key
    write(stage / 'project_settings_changes.json', fields)
    return {'project.binary': output}


def prepare_qa(candidate, stage, modified, remaps, candidate_pack, driver_path=None):
    qa = stage / 'qa_game'
    assert not qa.exists()
    shutil.copytree(candidate, qa)
    logical = 'game/scripts/steamworks.gd'
    source = modified / logical
    if not source.exists():
        source = EXTRACTED / 'recovered' / logical
    text = source.read_text(encoding='utf-8')
    marker = 'func initialize_steam(app_id: int) -> void :\n'
    assert text.count(marker) == 1
    changed = text.replace(marker, marker + '\tprint("Korean QA: Steam initialization disabled")\n\treturn\n')
    qa_sources = stage / 'qa_scripts'
    input_path = qa_sources / logical
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text(changed, encoding='utf-8')
    scripts = compile_scripts([input_path], qa_sources, stage / 'qa_compile', remaps, candidate_pack)
    driver_name = 'korean_qa_driver.gd'
    config_name = 'korean_qa_config.json'
    screens = stage / 'screens'
    screens.mkdir(exist_ok=True)
    write(stage / 'command.json', {})
    driver_config = {'command': (stage / 'command.json').as_posix(), 'info': (stage / 'runtime_info.json').as_posix(),
                     'screens': screens.as_posix(), 'ledger': (stage / 'screens.json').as_posix()}
    properties = {'application/config/name': 'MR_MAGEBOY_KO_QA_' + candidate.name,
                  'application/config/use_custom_user_dir': False,
                  'debug/file_logging/log_path': (qa / 'runtime.log').as_posix(),
                  'display/window/size/mode': 0,
                  'maaacks_game_template/disable_update_check': True,
                  'autoload/KoreanQA': '*res://' + driver_name}
    changes = {'project.binary': patch_settings(candidate_pack['project.binary'], properties),
               driver_name: Path(driver_path or TOOLS / 'qa_driver.gd').read_bytes(),
               config_name: json.dumps(driver_config, ensure_ascii=False).encode('utf-8'), **scripts}
    patch_pack(candidate / PCK, qa / PCK, changes)
    actual = {e['name']: e['data'] for e in read_pack(qa / PCK)[3]}
    diff = {k for k in set(actual) | set(candidate_pack) if actual.get(k) != candidate_pack.get(k)}
    assert diff == set(changes), diff
    write(stage / 'qa_manifest.json', {'candidate': candidate.name, 'candidate_pck_sha256': sha(candidate / PCK),
          'candidate_source_path': str(candidate),
          'qa_pck_sha256': sha(qa / PCK), 'qa_changes': {k: hashlib.sha256(v).hexdigest() for k,v in changes.items()},
          'project_properties': properties, 'steam_method': 'initialize_steam 진입점에서 return',
          'launch_path': str(qa / 'MR MAGEBOY DEMO.exe'), 'environment': {'APPDATA': str(stage / 'roaming'),
          'LOCALAPPDATA': str(stage / 'local')}, 'driver_config': driver_config, 'graphics_status': 'NOT_RUN'})
    check_qa_parser(qa, stage)


def check_qa_parser(qa, stage):
    driver_name = 'korean_qa_driver.gd'
    # 배포 실행기는 검사 전용 옵션을 지원하지 않으므로 게임을 실행하지 않고 bytecode 왕복만 검사합니다.
    payloads = {entry['name']: entry['data'] for entry in read_pack(qa / PCK)[3]}
    lexical = stage / 'driver_lexical'
    lexical.mkdir(exist_ok=True)
    source = lexical / driver_name
    source.write_bytes(payloads[driver_name])
    run_tool(['--compile=' + source.as_posix(), '--bytecode=4.5.0', '--output=' + lexical.as_posix()], stage, 'qa_driver_compile')
    compiled = source.with_suffix('.gdc')
    assert compiled.exists(), '검수 스크립트 컴파일 실패'
    observed = lexical / 'roundtrip'
    observed.mkdir(exist_ok=True)
    run_tool(['--decompile=' + compiled.as_posix(), '--bytecode=4.5.0', '--output=' + observed.as_posix()], stage, 'qa_driver_roundtrip')
    assert comparable(source.read_text(encoding='utf-8')) == comparable((observed / driver_name).read_text(encoding='utf-8')), '검수 스크립트 왕복 토큰 불일치'
    write(stage / 'parser_report.json', {'game_id': GAME, 'candidate': stage.name, 'status': 'BLOCKED',
          'reason': '배포 실행기의 --main-pack 금지 및 --check-only/--script CLI 미지원 확인',
          'lexical_compile_roundtrip': 'PASS', 'engine_sha256': sha(qa / 'MR MAGEBOY DEMO.exe'),
          'qa_pck_sha256': sha(qa / PCK), 'driver_sha256': sha(source),
          'compiled_driver_sha256': sha(compiled), 'graphics_status': 'NOT_RUN'})


def build(candidate_id, modified, translation, title_font=None, title_font_source=None):
    modified = Path(modified).resolve()
    assert modified.is_dir()
    candidate = ROOT / 'build_candidate' / GAME / candidate_id
    stage = WORK / candidate_id
    assert not candidate.exists(), '이미 고정된 후보는 덮어쓰지 않습니다.'
    stage.mkdir(parents=True, exist_ok=True)
    extra_inputs = {}
    if title_font:
        assert title_font_source, '제목 글꼴의 원본 경로가 필요합니다.'
        extra_inputs = {'fonts/title/TitlePixel.ttf': title_font, 'fonts/title/Source.ttf': title_font_source,
                        'fonts/title/LICENSE.txt': ROOT / 'tasks/MR_MAGEBOY_DEMO/third_party/Galmuri/LICENSE.txt',
                        'fonts/title/source_manifest.json': Path(title_font).parent / 'title_font_manifest.json'}
    modified, translation = snapshot_inputs(modified, translation, stage, extra_inputs)
    originals = {e['name']: e['data'] for e in read_pack(BASELINE / PCK)[3]}
    remaps = {r['source']: r['target'] for r in read(WORK / 'remap_targets.json')}
    files = sorted(p for p in modified.rglob('*') if p.is_file())
    unsupported = [p for p in files if p.suffix not in ('.gd', '.tscn', '.tres', '.csv') and p.name != 'project.godot']
    assert not unsupported, unsupported
    scripts = [p for p in files if p.suffix == '.gd']
    resources = [p for p in files if p.suffix in ('.tscn', '.tres')]
    changes = compile_scripts(scripts, modified, stage, remaps, originals)
    changes.update(compile_resources(resources, modified, stage, remaps, originals))
    if (modified / 'project.godot').exists():
        changes.update(build_settings(modified / 'project.godot', stage, originals))
    characters = ''.join(p.read_text(encoding='utf-8') for p in files)
    if translation:
        table, table_characters = build_translation(Path(translation).resolve(), stage, originals)
        changes.update(table)
        characters += table_characters
    # 모든 ASCII·숫자·동적으로 표시될 자모는 번역 원본과 함께 검사합니다.
    characters += ''.join(chr(i) for i in range(32, 127)) + '한국어'
    changes.update(build_fonts(characters, stage, originals))
    if title_font:
        changes.update(build_title_font(stage))
    verify_snapshot(stage)
    shutil.copytree(BASELINE, candidate)
    patch_pack(BASELINE / PCK, candidate / PCK, changes)
    reopened = {e['name']: e['data'] for e in read_pack(candidate / PCK)[3]}
    allowed_added = {TITLE_FONT_RESOURCE} if title_font else set()
    assert set(reopened) == set(originals) | allowed_added, '허용된 제목 글꼴 외의 자산을 추가하지 않습니다.'
    observed = {k for k in set(originals) | set(reopened) if originals.get(k) != reopened.get(k)}
    assert observed == set(changes), ('변경 경계 불일치', observed.symmetric_difference(changes))
    for k in originals:
        assert reopened[k] == changes.get(k, originals[k]), k
    for k in allowed_added:
        assert reopened[k] == changes[k], k
    if title_font:
        check_title_font(candidate, stage)
    for path in BASELINE.iterdir():
        if path.is_file() and path.name != PCK:
            assert sha(path) == sha(candidate / path.name)
    write(stage / 'build_manifest.json', {'game_id': GAME, 'steam_build': '25734075', 'candidate': candidate_id,
          'source_pck_sha256': sha(BASELINE / PCK), 'candidate_pck_sha256': sha(candidate / PCK),
          'modified_inputs': [{'path': p.relative_to(modified).as_posix(), 'sha256': sha(p)} for p in files],
          'translation_input_sha256': sha(translation) if translation else None,
          'input_lock_sha256': sha(stage / 'input_lock.json'), 'snapshot_status': 'PASS',
          'allowed_added_assets': sorted(allowed_added),
          'title_font_report_sha256': sha(stage / 'title_font_report.json') if title_font else None,
          'pck_changes': {k: hashlib.sha256(v).hexdigest() for k,v in changes.items()},
          'files': [{'path': p.name, 'size': p.stat().st_size, 'sha256': sha(p)} for p in sorted(candidate.iterdir()) if p.is_file()],
          'script_count': len(scripts), 'resource_count': len(resources), 'status': 'PASS', 'graphics_status': 'NOT_RUN'})
    prepare_qa(candidate, stage, modified, remaps, reopened)
    verify_snapshot(stage)
    print(json.dumps({'candidate': str(candidate), 'qa': str(stage / 'qa_game'), 'pck_changes': len(changes), 'status': 'PASS'}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('candidate_id')
    parser.add_argument('--modified', required=True)
    parser.add_argument('--translation-json')
    parser.add_argument('--title-font')
    parser.add_argument('--title-font-source')
    args = parser.parse_args()
    build(args.candidate_id, args.modified, args.translation_json, args.title_font, args.title_font_source)
