"""위치별 번역만 적용하고 원본 엔트리는 수정 범위 밖에서 보존합니다."""
from common import *
from pck_tools import read_pack,patch_pack,read_settings,variant
from translation_values import locale_tables,project_translation_paths,encode_settings_raw
import sys,shutil,re,struct,collections

sys.path.insert(0,str(ROOT/'tools/python_deps'))
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools import subset

BUILD=WORK/'full_01'
BUILD.mkdir(exist_ok=True)
locales=read_json(WORK/'translation/canonical.json')
direct=read_json(WORK/'translation/direct_canonical.json')
assert not read_json(WORK/'translation/direct_pending.json')
assert not read_json(WORK/'census/remaining.json')
assert not read_json(WORK/'census/extraction_errors.json')
inventory={r['path']:r for r in read_json(WORK/'pck_inventory.json')}
english,korean,ordered=locale_tables()
changes={};boundaries=[]

# 모든 완성형 한글·자모도 포함하여 한국어 저장 이름을 입력할 수 있습니다.
characters=set(''.join(r['target'] for r in locales+direct))
characters.update(chr(c) for c in range(0xAC00,0xD7A4))
characters.update(chr(c) for c in range(0x3131,0x318F))
characters.update(chr(c) for c in range(0x1100,0x1200))
characters={c for c in characters if not c.isspace() and ord(c)>=32}
font_path=BUILD/'korean.ttf'
if not font_path.exists():
    font=TTFont(ROOT/'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf')
    font=instantiateVariableFont(font,{'wght':400},inplace=True)
    options=subset.Options();options.name_IDs=['*'];options.name_languages=['*']
    worker=subset.Subsetter(options=options)
    worker.populate(text=''.join(sorted(characters)))
    worker.subset(font);font.save(font_path)
font=TTFont(font_path)
missing=[c for c in characters if ord(c) not in font.getBestCmap()]
# 라틴 문자·특수 기호는 기존 폰트와의 실제 폴백 합집합으로 추가 검증합니다.
assert not [c for c in missing if 0xAC00<=ord(c)<=0xD7A3]
config={'translations':[],'fonts':[],'svg':[],'characters':sorted(characters),
    'korean_font':font_path.as_posix(),'korean_output':(BUILD/'resources/KoreanPatch/korean.fontdata').as_posix(),
    'report':(BUILD/'resource_report.json').as_posix()}
Path(config['korean_output']).parent.mkdir(parents=True,exist_ok=True)
config['extra_fonts']=[]
font_inputs=[('emoji',ROOT/'tasks/HOW_EMPIRES_WORK/third_party/notoemoji/NotoEmoji[wght].ttf'),
    ('symbols',ROOT/'tasks/HOW_EMPIRES_WORK/third_party/notosanssymbols2/NotoSansSymbols2-Regular.ttf'),
    ('chinese',RECOVERED/'UI/Fonts/SourceHanSansSC/OTF/SimplifiedChinese/SourceHanSansSC-Normal.otf')]
remaining=set(missing)
for name,source in font_inputs:
    supplemental=TTFont(source)
    needed={ord(c) for c in remaining if ord(c) in supplemental.getBestCmap()}
    if not needed:continue
    if 'fvar' in supplemental:supplemental=instantiateVariableFont(supplemental,{'wght':400},inplace=True)
    options=subset.Options();options.name_IDs=['*'];options.name_languages=['*']
    worker=subset.Subsetter(options=options);worker.populate(unicodes=needed);worker.subset(supplemental)
    dest=BUILD/(name+source.suffix);supplemental.save(dest)
    remaining={c for c in remaining if ord(c) not in needed}
    config['extra_fonts'].append({'source':dest.as_posix(),'output':(BUILD/f'resources/KoreanPatch/{name}.fontdata').as_posix(),'path':f'KoreanPatch/{name}.fontdata'})
assert not remaining,remaining
for source in ordered:
    path=source.replace('.en.translation','.ko.translation')
    out=BUILD/'resources'/path;out.parent.mkdir(parents=True,exist_ok=True)
    messages={r['key']:r['target'] for r in locales if r['file']==source}
    config['translations'].append({'path':path,'output':out.as_posix(),'messages':messages})
for path in inventory:
    if path.endswith('.fontdata'):
        out=BUILD/'resources'/path;out.parent.mkdir(parents=True,exist_ok=True)
        config['fonts'].append({'path':path,'output':out.as_posix()})
for i,r in enumerate(read_json(WORK/'media/svg_review.json')):
    out=BUILD/'svg'/f'{i:02}.png';out.parent.mkdir(exist_ok=True)
    config['svg'].append({'file':r['file'],'source':(RECOVERED/r['file']).as_posix(),'output':out.as_posix()})
write_json(BUILD/'resource_config.json',config)
runtime=BUILD/'resource_runtime';runtime.mkdir(exist_ok=True)
(runtime/'project.godot').write_text('config_version=5\n[application]\nconfig/name="HEW resource build"\n',encoding='utf8')
run_gdre(['--path',runtime,'--script',ROOT/'tasks/HOW_EMPIRES_WORK/tools/build_resources.gd','--',BASELINE/PCK,BUILD/'resource_config.json'],BUILD,'resources')
report=read_json(BUILD/'resource_report.json')
assert not any(r['failures'] for r in report['translations'])
assert not any(r['missing'] for r in report['fonts']),[(r['path'],r['missing']) for r in report['fonts'] if r['missing']]
for entry in config['translations']+config['fonts']:changes[entry['path']]=Path(entry['output']).read_bytes()
changes['KoreanPatch/korean.fontdata']=Path(config['korean_output']).read_bytes()
for entry in config['extra_fonts']:changes[entry['path']]=Path(entry['output']).read_bytes()

groups=collections.defaultdict(list)
for r in direct:
    if r['target']!=r['source']:groups[r['file']].append(r)
scripts={}
for path,rows in groups.items():
    source=(RECOVERED/path).read_text(encoding='utf8')
    assert sha(RECOVERED/path)==rows[0]['recovered_sha256']
    edited=source
    for row in sorted(rows,key=lambda r:r['start'],reverse=True):
        # 리터럴만 교체하므로 저장 ID·조건식·노드 구조는 원문 그대로입니다.
        replacement=json.dumps(row['target'],ensure_ascii=False)
        edited=edited[:row['start']]+replacement+edited[row['end']:]
    if path.endswith('.gd'):
        scripts[path]=edited
    else:
        assert path.endswith(('.tscn','.tres')),path
        target='KoreanPatch/Resources/'+path
        changes[target]=edited.encode('utf8')
        original_remap=(EXTRACTED/'raw'/(path+'.remap')).read_text(encoding='utf8')
        remap=re.sub(r'path="res://[^"]+"','path="res://'+target+'"',original_remap)
        assert remap!=original_remap
        changes[path+'.remap']=remap.encode('utf8')
    boundaries.append({'file':path,'original_sha256':rows[0]['original_sha256'],'recovered_sha256':rows[0]['recovered_sha256'],'locations':[r['id'] for r in rows],'edited_sha256':hashlib.sha256(edited.encode()).hexdigest()})

code_changes=[]
def replace_code(path,before,after,reason):
    value=scripts.get(path,(RECOVERED/path).read_text(encoding='utf8'))
    assert value.count(before)==1,(path,before,value.count(before))
    scripts[path]=value.replace(before,after)
    code_changes.append({'file':path,'before':before,'after':after,'reason':reason})

replace_code('Main/Managers/settings_manager.gd','const DEFAULT_LANGUAGE: String = ""','const DEFAULT_LANGUAGE: String = "ko"','저장된 언어가 없을 때 한국어를 기본값으로 선택')
replace_code('Main/Managers/settings_manager.gd','static func get_language_display_name(locale: String) -> String:\n','static func get_language_display_name(locale: String) -> String:\n\tif locale == "ko":\n\t\treturn "한국어"\n','언어 선택 목록의 한국어 자칭 표시')
playlist={'MENU':'메뉴','MAIN':'기본','WEST_AFRICA_STINGER':'서아프리카','NORTH_AMERICA_STINGER':'북아메리카','CARIBBEAN_STINGER':'카리브해','EAST_INDIES_STINGER':'동인도','SOUTHERN_AFRICA_STINGER':'남아프리카','INDIA_STINGER':'인도','IRELAND_STINGER':'아일랜드','GAME_FINISHED':'게임 완료','NONE':'없음'}
replace_code('UI/Music/ui_music_interface.gd','playlist_selection.add_item(Music.Playlist.keys()[option])','playlist_selection.add_item('+json.dumps(playlist,ensure_ascii=False)+'.get(Music.Playlist.keys()[option], Music.Playlist.keys()[option]))','음악 열거형의 표시 이름만 번역; 내부 값은 유지')
states={'Queued':'대기 중','Active':'진행 중','Blocked':'막힘','Completed':'완료','Cancelled':'취소됨','INACTIVE':'비활성','ACTIVE':'진행 중','VICTORY_PENDING':'승리 대기','DEFEATED':'패배','COMPLETED':'완료'}
for path,expression in [('Main/Managers/console_commands_manager.gd','ProvinceTask.State.keys()[task.state]'),('Main/Managers/console_commands_manager.gd','Conflict.State.keys()[conflict.state]')]:
    value=scripts.get(path,(RECOVERED/path).read_text(encoding='utf8'))
    after=json.dumps(states,ensure_ascii=False)+'.get('+expression+', '+expression+')'
    count=value.count(expression);assert count>0
    scripts[path]=value.replace(expression,after)
    code_changes.append({'file':path,'before':expression,'after':after,'count':count,'reason':'개발 명령창의 열거형 상태 표시만 번역'})
credits=read_json(WORK/'translation/credits.json')
assert ''.join(r['source'] for r in credits)==(RECOVERED/'Data/Credits/credits.txt').read_text(encoding='utf8')
changes['Data/Credits/credits.txt']=''.join(r['target'] for r in credits).encode('utf8')

compile_map={}
for path,text in scripts.items():
    name=hashlib.sha256(path.encode()).hexdigest()[:16]+'.gd'
    out=BUILD/'scripts'/name;out.parent.mkdir(exist_ok=True)
    out.write_text(text,encoding='utf8')
    compile_map[name]=path
write_json(BUILD/'compile_map.json',compile_map)
write_json(BUILD/'code_changes.json',code_changes)
run_gdre(['--compile='+(BUILD/'scripts/*.gd').as_posix(),'--bytecode=4.5.0','--output='+(BUILD/'compiled').as_posix()],BUILD,'compile')
for name,path in compile_map.items():changes[path[:-3]+'.gdc']=(BUILD/'compiled'/Path(name).with_suffix('.gdc')).read_bytes()

settings=read_settings((EXTRACTED/'raw/project.binary').read_bytes())
paths=project_translation_paths((EXTRACTED/'raw/project.binary').read_bytes())
paths+=['res://'+e['path'] for e in config['translations']]
settings['internationalization/locale/translations']=struct.pack('<II',28,len(paths))+b''.join(variant(p) for p in paths)
changes['project.binary']=encode_settings_raw(settings)
candidate=ROOT/'build_candidate'/GAME/'full_01'
candidate.mkdir(parents=True,exist_ok=True)
for path in BASELINE.iterdir():
    if path.name!=PCK and not (candidate/path.name).exists():shutil.copy2(path,candidate/path.name)
patch_pack(BASELINE/PCK,candidate/PCK,changes)
write_json(BUILD/'boundaries.json',boundaries)
write_json(BUILD/'build.json',{'candidate':str(candidate),'sha256':sha(candidate/PCK),'changes':{k:hashlib.sha256(v).hexdigest() for k,v in changes.items()},'direct_locations':sum(len(r) for r in groups.values()),'changed_scripts':len(scripts),'korean_characters':len(characters),'status':'BUILT','qa':'NOT_RUN'})
print(json.dumps({'candidate':str(candidate),'changes':len(changes),'scripts':len(scripts),'sha256':sha(candidate/PCK)},ensure_ascii=False))
