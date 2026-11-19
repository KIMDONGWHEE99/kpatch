"""대량 번역 전 한글 출력·저장 격리 후보를 준비합니다."""
from common import *
from pck_tools import read_pack, patch_pack, patch_settings
import sys, shutil, csv, re

sys.path.insert(0, str(ROOT / 'tools/python_deps'))
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools import subset

RISK = WORK / 'risk_01'
RISK.mkdir(parents=True, exist_ok=True)
messages = {'MAIN_MENU_QUICK_START':'빠른 시작', 'MAIN_MENU_MODS':'모드',
            'MAIN_MENU_QUIT':'종료', 'MAIN_MENU_CONTINUE_GAME':'이어하기',
            'MAIN_MENU_NEW_GAME':'새 게임', 'MAIN_MENU_NEW_GAME_GLORY_MODE':'새 게임 - 영광 모드',
            'MAIN_MENU_LOAD_GAME':'불러오기', 'MAIN_MENU_SETTINGS':'설정'}
chars = ''.join(sorted(set(''.join(messages.values())+'한국어 저장 시험')))
font = TTFont(ROOT / 'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf')
font = instantiateVariableFont(font, {'wght':400}, inplace=True)
options = subset.Options()
options.name_IDs = ['*']
options.name_languages = ['*']
subsetter = subset.Subsetter(options=options)
subsetter.populate(text=chars)
subsetter.subset(font)
font.save(RISK / 'korean.ttf')
assert all(ord(c) in font.getBestCmap() for c in chars if not c.isspace())
config = {'translations':[], 'fonts':[], 'characters':list(chars.replace(' ','')),
          'korean_font':(RISK/'korean.ttf').as_posix(), 'report':(RISK/'resource_report.json').as_posix()}
for path in (RECOVERED/'Data/Localization').rglob('*.csv'):
    rows = list(csv.DictReader(path.open(encoding='utf-8-sig', newline='')))
    chosen = {r['key']:messages[r['key']] for r in rows if r['key'] in messages}
    if chosen:
        name = path.relative_to(RECOVERED).with_suffix('.en.translation').as_posix()
        out = RISK/'resources'/name
        out.parent.mkdir(parents=True, exist_ok=True)
        config['translations'].append({'path':name, 'output':out.as_posix(), 'messages':chosen})
for entry in read_json(WORK/'pck_inventory.json'):
    if entry['path'].endswith('.fontdata'):
        out = RISK/'resources'/entry['path']
        out.parent.mkdir(parents=True, exist_ok=True)
        config['fonts'].append({'path':entry['path'], 'output':out.as_posix()})
write_json(RISK/'resource_config.json', config)
runtime = RISK/'resource_runtime'
runtime.mkdir(exist_ok=True)
(runtime/'project.godot').write_text('config_version=5\n[application]\nconfig/name="HEW resource probe"\n', encoding='utf-8')
run_gdre(['--path',runtime,'--script',ROOT/'tasks/HOW_EMPIRES_WORK/tools/resource_probe.gd','--',BASELINE/PCK,RISK/'resource_config.json'],RISK,'resources')
report = read_json(RISK/'resource_report.json')
assert not any(r['failures'] for r in report['translations'])
assert not any(r['missing'] for r in report['fonts'])
scripts = RISK/'scripts'
scripts.mkdir(exist_ok=True)
steam = (RECOVERED/'Platform/Steam/steamworks.gd').read_text(encoding='utf-8')
marker = 'func initialize_steam() -> void :\n'
assert steam.count(marker) == 1
steam = steam.replace(marker, marker+'\tprint("HEW QA: Steam disabled")\n\treturn\n')
(scripts/'steamworks.gd').write_text(steam, encoding='utf-8')
run_gdre(['--compile='+(scripts/'*.gd').as_posix(),'--bytecode=4.5.0','--output='+(RISK/'compiled').as_posix()],RISK,'compile')
changes = {entry['path']:Path(entry['output']).read_bytes() for entry in config['translations']+config['fonts']}
candidate = ROOT/'build_candidate'/GAME/'risk_01'
assert not candidate.exists()
shutil.copytree(BASELINE, candidate)
patch_pack(BASELINE/PCK,candidate/PCK,changes)
qa = RISK/'qa_game'
shutil.copytree(candidate,qa)
settings = (EXTRACTED/'raw/project.binary').read_bytes()
qa_changes = {'Platform/Steam/steamworks.gdc':(RISK/'compiled/steamworks.gdc').read_bytes(),
    'project.binary':patch_settings(settings, {'application/config/name':'HEW_KO_QA_RISK_01',
     'debug/file_logging/log_path':(RISK/'runtime.log').as_posix(), 'display/window/size/mode':0})}
patch_pack(candidate/PCK,qa/PCK,qa_changes)
write_json(RISK/'build.json', {'candidate_sha256':sha(candidate/PCK),'qa_sha256':sha(qa/PCK),
    'candidate_changes':{k:hashlib.sha256(v).hexdigest() for k,v in changes.items()},
    'qa_changes':{k:hashlib.sha256(v).hexdigest() for k,v in qa_changes.items()},
    'status':'PASS','graphics':'NOT_RUN'})
print('Risk candidate ready',len(changes),'resources')
