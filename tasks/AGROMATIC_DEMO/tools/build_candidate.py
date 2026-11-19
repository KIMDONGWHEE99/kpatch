"""원본 위치에 연결된 번역으로 후보를 만들며 동작 데이터 변경을 막습니다."""
from pathlib import Path
from collections import defaultdict
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from common import ROOT, BASE, EXTRACTED, WORK, save, sha, patch_settings, run_gdre
from pck_tools import read_pack, patch_pack
from risk_probe import compile_scripts, prepare_fonts, qa_scripts
import dynamic_display

RECOVERED = EXTRACTED / 'recovered'
TOOLS = Path(__file__).parent


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def assign(value, pointer, target):
    for key in pointer[:-1]:
        value = value.setdefault(key, {}) if isinstance(value, dict) else value[key]
    value[pointer[-1]] = target


def lookup(value, pointer, default=None):
    for key in pointer:
        if not isinstance(value, (dict, list)) or isinstance(value, dict) and key not in value:
            return default
        value = value[key]
    return value


def flatten(value, pointer=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from flatten(child, pointer + (key,))
    elif isinstance(value, list):
        for key, child in enumerate(value):
            yield from flatten(child, pointer + (key,))
    else:
        yield pointer, value


def text_tokens(text):
    spec = importlib.util.spec_from_file_location('private_audit', WORK / 'discovery/audit_scripts.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.tokens(text)


def build(version_id):
    stage = ROOT / 'build_candidate/AGROMATIC_DEMO' / version_id
    if stage.exists():
        raise ValueError('후보 폴더는 덮어쓰지 않습니다: ' + str(stage))
    stage.mkdir(parents=True)
    pack = read_pack(BASE / 'AgromaticDemo.exe')
    inputs = [WORK / 'translations' / name for name in ('ko_part_a.json', 'ko_part_b.json', 'supplemental_ko.json', 'resource_extra_ko.json', 'resource_story_extra_ko.json', 'supplemental_extra_ko.json', 'root_extra_ko.json')]
    dependency_inputs = inputs + [WORK/'discovery'/name for name in ('audit_scripts.py','direct_string_rows.json','translation_call_rows.json','script_string_rows.json','resource_string_rows.json','runtime_text_composition_rows.json')]
    dependency_inputs += [WORK/'media/korean_vector_icons'/(name+'.ctex') for name in ('full_red','full_green','purchase')]
    dependency_inputs += [ROOT/'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf']
    dependency_inputs += [WORK/'translations/display_codes_ko.json']
    input_start = {str(p.relative_to(ROOT)):sha(p) for p in dependency_inputs}
    tables = [row for path in inputs[:2] for row in read(path)]
    supplemental = read(inputs[2]) + read(inputs[5])
    extras = [row for path in (inputs[3],inputs[4],inputs[6]) for row in read(path) if row.get('target')]
    for row in tables + supplemental + extras:
        if not row.get('target') and row.get('source', row.get('source_text')):
            raise ValueError('빈 번역: ' + str(row))
        if row.get('classification') == 'UNKNOWN':
            raise ValueError('미분류 번역: ' + str(row))
    translations = read(RECOVERED / 'data/translations/translations_en.json')
    translations['_meta'].update(language='ko', language_name='한국어')
    for row in tables:
        assign(translations, row['key'].split('.'), row['target'])
    for row in supplemental:
        if row.get('key'):
            assign(translations, row['key'].split('.'), row['target'])
    direct_by_text = {row['source_text']: row['target'] for row in supplemental if row.get('key') is None}
    extra_by_text = {row['source_text']: row['target'] for row in extras}
    expected = []
    changes = {}
    scripts = {}
    resource_texts = {}
    display_pairs = {}
    identifier_pairs = {}
    original_resources = {}
    remaps = {}
    for name, entry in pack['entries'].items():
        if name.endswith('.remap'):
            match = re.search(r'path="res://([^"]+)"', entry['data'].decode('utf-8'))
            if match:
                remaps[name[:-6]] = match[1]

    resource_rows = read(WORK / 'discovery/resource_string_rows.json')
    json_values = {}
    field_ordinals = defaultdict(int)
    for row in resource_rows:
        if not row['classification'].startswith('VISIBLE'):
            continue
        source, target = row['source'], row['target']
        if row['classification'] == 'VISIBLE_TRANSLATE':
            target = extra_by_text.get(source, direct_by_text.get(source, target))
            if target is None:
                raise ValueError('미번역 자원 위치: ' + row['location_id'])
        path = row['path']
        if row['kind'] == 'json':
            if path not in json_values:
                json_values[path] = read(RECOVERED / path)
            # 번역표와 데이터에 같은 항목이 있을 때 해당 항목의 의미를 우선합니다.
            category = Path(path).stem
            pointer = row['pointer']
            canonical = [category] + pointer
            if category == 'items' and pointer[-1] == 'display_name':
                canonical[-1] = 'name'
            if category in {'items', 'buildings', 'contracts', 'pipeline', 'research', 'stores', 'traits'}:
                current = lookup(translations, canonical)
                if isinstance(current, str):
                    target = current
                else:
                    assign(translations, canonical, target)
            assign(json_values[path], pointer, target)
            selector = {'pointer': pointer}
            pack_path = path
            if pointer and pointer[-1] in ('display_name', 'name') and len(pointer) > 1 and isinstance(pointer[0], str):
                identifier_pairs[pointer[0]] = target
                identifier_pairs[pointer[0].replace('_', ' ').capitalize()] = target
                identifier_pairs[pointer[0].replace('_', ' ').title()] = target
        else:
            pack_path = remaps.get(path, path)
            original_resources[path] = pack_path
            if path not in resource_texts:
                resource_texts[path] = (RECOVERED / path).read_text(encoding='utf-8')
            selector = {'field': row['field'], 'ordinal': field_ordinals[(path, row['field'])]}
            field_ordinals[(path, row['field'])] += 1
        expected.append({'kind': row['kind'], 'path': pack_path, 'source_path': path, 'location_id': row['location_id'],
                         'source_asset_sha256': hashlib.sha256(pack['entries'][pack_path]['data']).hexdigest(), 'source_text_sha256':row['source_sha256'], 'source': source, 'target': target,
                         'selector': selector, 'expected_count': 1})
        row['final_target'] = target
    for path, value in json_values.items():
        original = read(RECOVERED / path)
        original_leaves = dict(flatten(original))
        new_leaves = dict(flatten(value))
        allowed = {tuple(row['pointer']) for row in resource_rows if row['kind'] == 'json' and row['path'] == path and row['classification'].startswith('VISIBLE')}
        if set(original_leaves) != set(new_leaves) or any(original_leaves[k] != new_leaves[k] for k in original_leaves if k not in allowed):
            raise ValueError('게임 동작 데이터 변경: ' + path)
        changes[path] = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
    for path in resource_texts:
        text = resource_texts[path]
        for row in sorted((r for r in resource_rows if r['kind'] == 'resource' and r['path'] == path and r['classification'].startswith('VISIBLE')), key=lambda r:r['offset'], reverse=True):
            escaped = json.dumps(row['final_target'], ensure_ascii=False)[1:-1]
            text = text[:row['offset']] + escaped + text[row['end_offset']:]
        resource_texts[path] = text

    direct_rows = read(WORK / 'discovery/direct_string_rows.json') + read(WORK / 'discovery/translation_call_rows.json')
    all_rows = read(WORK / 'discovery/script_string_rows.json')
    grouped = defaultdict(list)
    for row in all_rows:
        grouped[row['source']].append(row)
    ordinals = {r['location_id']: n for values in grouped.values() for n,r in enumerate(sorted(values, key=lambda x:x['offset']))}
    replacements = defaultdict(list)
    for row in direct_rows:
        source = row['text']
        target = source if row['classification'] == 'VISIBLE_KEEP' else direct_by_text.get(source, extra_by_text.get(source))
        if row.get('translation_key'):
            target = lookup(translations, row['translation_key'].split('.'), target)
        if target is None:
            raise ValueError('미번역 스크립트 위치: ' + row['location_id'] + ' ' + source)
        path = row['source'].removeprefix('recovered/')
        if not row.get('direct_replace', True):
            if source != target:
                display_pairs[source] = target
            target = source
        replacements[path].append((row['offset'], row['end_offset'], source, target))
        expected.append({'kind':'script', 'path':remaps.get(path, path.replace('.gd','.gdc')), 'source_path':path,
                         'location_id':row['location_id'], 'source_asset_sha256':hashlib.sha256(pack['entries'][remaps.get(path,path.replace('.gd','.gdc'))]['data']).hexdigest(), 'source_text_sha256':row['source_sha256'], 'source':source,
                         'target':target, 'selector':{'ordinal':ordinals[row['location_id']]}, 'expected_count':1,
                         'preservation':not row.get('direct_replace',True)})
    for path, rows in replacements.items():
        text = (RECOVERED / path).read_text(encoding='utf-8')
        original_tokens = {token['start']:token for token in text_tokens(text)}
        for start,end,source,target in sorted(rows,reverse=True):
            if original_tokens[start]['text'] != source or original_tokens[start]['end'] != end:
                raise ValueError('원본 스크립트 위치 불일치: ' + path)
            text = text[:start] + json.dumps(target, ensure_ascii=False) + text[end:]
        scripts[path] = text

    # 내부 실패 코드는 유지하고 화면으로 전달하는 순간에만 번역합니다.
    source_map = {**direct_by_text, **extra_by_text, **display_pairs, **identifier_pairs, **dynamic_display.display_pairs()}
    source_map.update({k.upper():v for k,v in list(source_map.items()) if re.fullmatch(r'[A-Za-z_ ]+',k)})
    source_map = {k:v for k,v in source_map.items() if k and k != v and not re.fullmatch(r'[\W\d]+',k)}
    changes['data/translations/display_ko.json'] = json.dumps(source_map,ensure_ascii=False,indent=2).encode('utf-8')
    context_codes = read(WORK/'translations/display_codes_ko.json')
    if context_codes != dynamic_display.context_pairs():
        raise ValueError('출처와 연결한 문맥 사전과 제작 도구 사전이 다릅니다.')
    changes['data/translations/display_codes_ko.json'] = json.dumps(context_codes,ensure_ascii=False,indent=2).encode('utf-8')
    dynamic_changes = dynamic_display.apply(scripts)
    tm = scripts.get('scripts/TranslationManager.gd', (RECOVERED / 'scripts/TranslationManager.gd').read_text(encoding='utf-8'))
    tm = tm.replace('DEFAULT_LANGUAGE = "en"','DEFAULT_LANGUAGE = "ko"').replace('TRANSLATIONS_ENABLED: = false','TRANSLATIONS_ENABLED: = true')
    tm += (TOOLS / 'display_boundary.gd').read_text(encoding='utf-8')
    scripts['scripts/TranslationManager.gd'] = tm
    settings = scripts.get('scripts/SettingsManager.gd',(RECOVERED/'scripts/SettingsManager.gd').read_text(encoding='utf-8'))
    settings = settings.replace('DEFAULT_LANGUAGE: String = "en"','DEFAULT_LANGUAGE: String = "ko"').replace('\tlanguage = "en"\n','\tlanguage = "ko"\n')
    scripts['scripts/SettingsManager.gd'] = settings
    boundary_changes = []
    for path, before, after in [
        ('scripts/Worker.gd', 'worker_name + ": " + reason, "failure"', 'worker_name + ": " + TranslationManager.translate_display(reason), "failure"'),
        ('scripts/NotificationManager.gd', 'func show_notification(title: String, description: String = "",', 'func show_notification(title: String, description: String = "",'),
        ('scripts/ContractUI.gd', 'regex.compile("Level\\\\s+(\\\\d+)")', 'regex.compile("(?:Level|레벨)\\\\s+(\\\\d+)|(\\\\d+)\\\\s*단계")')]:
        if before == after:
            continue
        text = scripts.get(path,(RECOVERED/path).read_text(encoding='utf-8'))
        if text.count(before) != 1:
            raise ValueError('표시 경계 불일치: ' + path + ' ' + before)
        scripts[path] = text.replace(before,after)
        boundary_changes.append({'path':path,'before':before,'after':after})
    # 알림의 설명은 내부 오류 사전에서 전달될 수 있습니다.
    path = 'scripts/NotificationManager.gd'
    text = scripts.get(path,(RECOVERED/path).read_text(encoding='utf-8'))
    match = re.search(r'(func show_notification\([^\n]+\n)',text)
    if not match:
        raise ValueError('알림 표시 함수 없음')
    text = text[:match.end()] + '\ttitle = TranslationManager.translate_display(title)\n\tdescription = TranslationManager.translate_display(description)\n' + text[match.end():]
    scripts[path] = text
    # 한글 단계명 검색 후 첫 번째 또는 두 번째 숫자 그룹을 읽습니다.
    path = 'scripts/ContractUI.gd'
    text = scripts[path]
    text = text.replace('return int(result.get_string(1))', 'return int(result.get_string(1) if not result.get_string(1).is_empty() else result.get_string(2))')
    scripts[path] = text
    # 추가 함수는 파일 끝에 붙이므로 기존 문자열 위치 순서는 보존됩니다.
    changes.update(compile_scripts(scripts, stage/'script_build'))

    for short in ('purchase_land','icon_full'):
        path = 'assets/atlas.sprites/ui_game/' + short + '.tres'
        text = resource_texts.get(path,(RECOVERED/path).read_text(encoding='utf-8'))
        old = 'path="res://assets/atlas.png"'
        text = text.replace(old,'path="res://assets/sprites/ui_game/'+short+'.png"')
        # 구별되는 독립 텍스처의 식별자로 교체하여 원본 아틀라스 조각을 쓰지 않습니다.
        uid = 'uid://bej2m6h7m5xoh' if short=='purchase_land' else 'uid://safhsqa37e4d'
        text = text.replace('uid="uid://betknl634p02x"', 'uid="'+uid+'"')
        size = 48 if short=='purchase_land' else 24
        text = re.sub(r'region = Rect2\([^\n]+\)', 'region = Rect2(0, 0, %d, %d)'%(size,size),text)
        resource_texts[path]=text
        original_resources[path]=remaps.get(path,path)
    entries=[]
    for path,text in resource_texts.items():
        target=original_resources[path]
        source=stage/'resource_inputs'/path
        output=stage/'resource_outputs'/target
        source.parent.mkdir(parents=True,exist_ok=True)
        output.parent.mkdir(parents=True,exist_ok=True)
        source.write_text(text,encoding='utf-8')
        entries.append({'source':str(source),'original':str(EXTRACTED/'pack'/target),'output':str(output)})
    save(stage/'resource_config.json',{'entries':entries,'report':str(stage/'resource_report.json')})
    run_gdre(['--path',str(WORK/'tool_runtime'),'--script',str(TOOLS/'resource_convert.gd'),'--',str(stage/'resource_config.json')],version_id+'_resources')
    for path,target in original_resources.items():
        changes[target]=(stage/'resource_outputs'/target).read_bytes()
    for fragment,name in [('a14fe8ea','full_red'),('d9d556dd','full_green'),('1b0bc8fe','purchase')]:
        targets=[p for p in pack['entries'] if fragment in p and p.endswith('.ctex')]
        if len(targets)!=1:raise ValueError('그림 위치 불일치')
        changes[targets[0]]=(WORK/'media/korean_vector_icons'/(name+'.ctex')).read_bytes()
    changes['data/translations/translations_ko.json']=json.dumps(translations,ensure_ascii=False,indent=2).encode('utf-8')
    for path in ('data/translations/translations_ko.json','data/translations/display_ko.json','data/translations/display_codes_ko.json'):
        for pointer,value in flatten(json.loads(changes[path])):
            if isinstance(value,str):
                expected.append({'kind':'json','path':path,'source_path':path,'location_id':path+'#'+'/'.join(map(str,pointer)),
                    'source_asset_sha256':None,'source':None,'target':value,'selector':{'pointer':list(pointer)},'expected_count':1})
    chars=set('가득구매')|{chr(i) for i in range(32,127)}
    for row in expected: chars.update(row['target'])
    changes.update(prepare_fonts(pack,stage/'fonts',chars))
    game=stage/'game';game.mkdir()
    for source in BASE.iterdir():
        if source.is_dir():shutil.copytree(source,game/source.name)
        elif source.name!='AgromaticDemo.exe':shutil.copy2(source,game/source.name)
    report=patch_pack(BASE/'AgromaticDemo.exe',game/'AgromaticDemo.exe',changes)
    save(stage/'build_report.json',report)
    save(stage/'expected_locations.json',expected)
    assets = []
    for path,text in scripts.items():
        assets.append({'kind':'script','path':remaps.get(path,path.replace('.gd','.gdc')),'source_path':path,
            'source_string_count':len(text_tokens((RECOVERED/path).read_text(encoding='utf-8'))),
            'candidate_string_count':len(text_tokens(text)),'source_asset_sha256':hashlib.sha256(pack['entries'][remaps.get(path,path.replace('.gd','.gdc'))]['data']).hexdigest(),'source_text_sha256':sha(RECOVERED/path)})
    field_pattern = re.compile(r'^([\w/]+) = "((?:\\.|[^"\\])*)"', re.M)
    for path,text in resource_texts.items():
        fields = defaultdict(int)
        for match in field_pattern.finditer(text):fields[match[1]]+=1
        assets.append({'kind':'resource','path':original_resources[path],'source_path':path,
            'fields':dict(fields),'source_asset_sha256':hashlib.sha256(pack['entries'][original_resources[path]]['data']).hexdigest(),'source_text_sha256':sha(RECOVERED/path)})
    for path,data in changes.items():
        if path.endswith('.json'):
            original_data=pack['entries'].get(path)
            assets.append({'kind':'json','path':path,'source_path':path,
                'source_string_count':sum(isinstance(v,str) for _,v in flatten(json.loads(original_data['data'].decode('utf-8-sig')))) if original_data else 0,
                'candidate_string_count':sum(isinstance(v,str) for _,v in flatten(json.loads(data))),
                'source_asset_sha256':hashlib.sha256(original_data['data']).hexdigest() if original_data else None})
    save(stage/'asset_expectations.json',assets)
    if input_start != {str(p.relative_to(ROOT)):sha(p) for p in dependency_inputs}:
        raise ValueError('제작 도중 입력이 바뀌어 후보를 고정할 수 없습니다.')
    save(stage/'input_fingerprint.json',{'inputs':input_start,'source_manifest_sha256':sha(WORK/'baseline/source_manifest.json'),
                                     'tools':{str(p.relative_to(ROOT)):sha(p) for p in TOOLS.iterdir() if p.is_file()},'candidate_sha256':sha(game/'AgromaticDemo.exe')})
    save(stage/'display_boundary_changes.json',boundary_changes)
    save(stage/'dynamic_display_changes.json',dynamic_changes)
    save(stage/'expected_script_sources.json',{p:sha(stage/'script_build/sources'/p) for p in scripts})
    qa=WORK/('qa_'+version_id)
    qa_sources=qa_scripts(scripts)
    qa_sources={p:qa_sources[p] for p in ('scripts/SteamManager.gd','scripts/GameAnalytics.gd')}
    if (TOOLS/'qa_driver.gd').exists():
        qa_sources['scripts/KoreanQaDriver.gd']=(TOOLS/'qa_driver.gd').read_text(encoding='utf-8')
    qa_changes=compile_scripts(qa_sources,qa/'script_build')
    qa_changes['project.binary']=patch_settings(pack['entries']['project.binary']['data'],{'application/config/name':'Agromatic_KoreanQA','application/config/use_custom_user_dir':False,
        'display/window/size/mode':0,'display/window/size/window_width_override':1440,'display/window/size/window_height_override':810,
        **({'autoload/KoreanQaDriver':'*res://scripts/KoreanQaDriver.gdc'} if 'scripts/KoreanQaDriver.gd' in qa_sources else {})})
    qa_changes={**changes,**qa_changes}
    qa_game=qa/'game';qa_game.mkdir()
    for source in game.iterdir():
        if source.is_dir():shutil.copytree(source,qa_game/source.name)
        elif source.name!='AgromaticDemo.exe':shutil.copy2(source,qa_game/source.name)
    save(qa/'qa_boundary_report.json',patch_pack(BASE/'AgromaticDemo.exe',qa_game/'AgromaticDemo.exe',qa_changes))
    print('후보 준비 완료:',stage, '표시 위치:',len(expected),'수정 묶음:',len(changes))


if __name__=='__main__':
    build(sys.argv[1])
