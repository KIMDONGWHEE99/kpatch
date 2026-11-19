"""후보를 새로 읽어 위치별 번역·자산·코드 변경 경계를 독립 대조한다."""
from pck_tools import ROOT,WORK,BASELINE,EXTRACTED,read_pack,patch_settings
from po_format import parse
import json,hashlib,collections,re,copy

candidate=__import__('pathlib').Path(json.loads((WORK/'candidate_changes.json').read_text(encoding='utf-8'))['candidate'])
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
original={p.relative_to(BASELINE).as_posix():sha(p) for p in BASELINE.rglob('*') if p.is_file()}
actual={p.relative_to(candidate).as_posix():sha(p) for p in candidate.rglob('*') if p.is_file()}
assert set(original)==set(actual)
changed=[p for p in original if original[p]!=actual[p]]
assert set(changed)=={'Alchemortis Demo.pck','data_Alchemortis_windows_x86_64/Alchemortis.dll'}
source_pack={r['name']:r['data'] for r in read_pack(BASELINE/'Alchemortis Demo.pck')[3]}
observed={r['name']:r['data'] for r in read_pack(candidate/'Alchemortis Demo.pck')[3]}
config=read(WORK/'candidate_changes.json')
expected_changes={'project.binary':patch_settings(source_pack['project.binary'],config['settings']),'resources/translations/ko.po':(WORK/'translation/ko_full.po').read_bytes()}
for extension in ['gd','tscn']:expected_changes['korean_patch/inventory_labels.'+extension]=(ROOT/('tasks/ALCHEMORTIS_DEMO/tools_v101/inventory_labels.'+extension)).read_bytes()
for row in read(WORK/'fonts/config.json')['fonts']:expected_changes[row['path']]=__import__('pathlib').Path(row['output']).read_bytes()
assert set(observed)==set(source_pack)|set(expected_changes)
for name,data in observed.items():assert data==expected_changes.get(name,source_pack.get(name)),name

expected=read(WORK/'translation/ko_full.json')
rows=parse(observed['resources/translations/ko.po'].decode('utf-8'))
values={r['key']:r['text'] or r['forms'].get(0) for r in rows if r['key']}
def verify_values(data):
    assert set(data)==set(expected),'번역 위치 누락·증가'
    for key,value in data.items():assert value==expected[key] and value and value.strip(),key
verify_values(values)
source_rows=read(WORK/'translation/source.json')
format_results=[]
for r in source_rows[1:]:
    before=r['text'] or r['forms']['0'];after=values[r['key']]
    assert re.findall(r'\[/?(?:b|i|color|font|img|indent|center|right|left|url)(?:[^\]]*)\]',before)==re.findall(r'\[/?(?:b|i|color|font|img|indent|center|right|left|url)(?:[^\]]*)\]',after),r['key']
    tokens=lambda s:collections.Counter(re.findall(r'(?<!\{)\{\d+(?:[^{}]*)\}(?!\})',s))
    keys=lambda s:collections.Counter(re.findall(r'\{\{(!?keyword_\w+)(?:\([^{}]*\))?\}\}',s))
    assert tokens(before)==tokens(after) and keys(before)==keys(after) and before.count('\n')==after.count('\n'),r['key']
    if r['plural_key'] is not None:
        candidate_row=next(x for x in rows if x['key']==r['key'])
        assert candidate_row['plural_key']==r['plural_key'] and set(candidate_row['forms'])=={0}

before=read(WORK/'discovery/original_code.json.snapshot.json')
after=read(WORK/'discovery/candidate_code.json.snapshot.json')
assert before['types']==after['types'],'형식·필드·속성 변경'
expected_methods={m['method']:copy.deepcopy(m) for m in before['methods']}
def insert(instructions,at,added):
    for i in instructions:
        if i['operand'].startswith('branch:'):
            old=int(i['operand'][7:]);i['operand']='branch:'+str(old+len(added) if old>=at else old)
        elif i['operand'].startswith('switch:'):
            i['operand']='switch:'+','.join(str(int(x)+len(added) if int(x)>=at else int(x)) for x in i['operand'][7:].split(','))
    instructions[at:at]=copy.deepcopy(added)
original_strings=read(WORK/'discovery/original_code.json')
changed_methods=set()
translate_call=[{'opcode':'call','operand':'Godot.StringName Godot.StringName::op_Implicit(System.String)'},{'opcode':'ldnull','operand':''},{'opcode':'call','operand':'Godot.StringName Godot.TranslationServer::Translate(Godot.StringName,Godot.StringName)'},{'opcode':'call','operand':'System.String Godot.StringName::op_Implicit(Godot.StringName)'}]
for r in sorted(read(WORK/'translation/code_changes.json'),key=lambda r:r['offset'],reverse=True):
    method=expected_methods[r['method']];instructions=method['instructions']
    original_row=next(x for x in original_strings if x['method']==r['method'] and x['offset']==r['offset'])
    at=original_row['instruction_index'];assert instructions[at]=={'opcode':'ldstr','operand':r['source']}
    if r.get('translate'):
        insert(instructions,at+1,translate_call);changed_methods.add(r['method'])
    else:instructions[at]['operand']=r['target']
format_method='System.String Game.Util.Keyword::Format(System.Boolean,System.Boolean,System.Boolean,System.String)'
prefix=[{'opcode':'ldarg','operand':'wordOverride'},{'opcode':'brtrue','operand':'branch:9'},{'opcode':'call','operand':'System.String Godot.TranslationServer::GetLocale()'},{'opcode':'ldstr','operand':'ko'},{'opcode':'callvirt','operand':'System.Boolean System.String::StartsWith(System.String)'},{'opcode':'brfalse','operand':'branch:9'},{'opcode':'ldarg.0','operand':''},{'opcode':'call','operand':'System.String Game.Util.Keyword::get_WordLocalized()'},{'opcode':'starg','operand':'wordOverride'}]
insert(expected_methods[format_method]['instructions'],0,prefix);changed_methods.add(format_method)
inventory_method='System.Void Game.Gameplay.PlayerInventory::_Ready()'
inventory_prefix=[{'opcode':'ldarg.0','operand':''},{'opcode':'ldfld','operand':'Godot.TextureRect Game.Gameplay.PlayerInventory::frame'},{'opcode':'ldstr','operand':'res://korean_patch/inventory_labels.tscn'},{'opcode':'call','operand':'!!0 Godot.GD::Load<Godot.PackedScene>(System.String)'},{'opcode':'ldc.i4.0','operand':''},{'opcode':'callvirt','operand':'Godot.Node Godot.PackedScene::Instantiate(Godot.PackedScene/GenEditState)'},{'opcode':'ldc.i4.0','operand':''},{'opcode':'ldc.i4.0','operand':''},{'opcode':'callvirt','operand':'System.Void Godot.Node::AddChild(Godot.Node,System.Boolean,Godot.Node/InternalMode)'}]
insert(expected_methods[inventory_method]['instructions'],0,inventory_prefix);changed_methods.add(inventory_method)
for name in changed_methods:
    for i in expected_methods[name]['instructions']:
        if (i['operand'].startswith('branch:') and i['opcode'].endswith('.s')):i['opcode']=i['opcode'][:-2]
il={r['method']:r['instructions'] for r in read(WORK/'discovery/original_code.json.il.json')}
lang='System.Void Game.UI.LanguageSelectionDialog::.cctor()';font='System.Void Game.Autoload.VisualUtilities::.cctor()'
def index(method,offset):return next(i for i,line in enumerate(il[method]) if line.startswith(f'IL_{offset:04x}:'))
instructions=expected_methods[lang]['instructions']
assert instructions[0]['opcode']=='ldc.i4.7';instructions[0]['opcode']='ldc.i4.8'
option=copy.deepcopy(instructions[index(lang,6):index(lang,46)+1]);option[1]['opcode']='ldc.i4.7'
names=[i for i in option if i['opcode']=='ldstr' and i['operand']=='English'];names[0]['operand']='Korean';names[1]['operand']='한국어'
next(i for i in option if i['operand']=='en-US')['operand']='ko-KR'
at=index(lang,0x125);instructions[at:at]=option
instructions=expected_methods[font]['instructions'];pair=copy.deepcopy(instructions[index(font,0x1bc):index(font,0x1c7)+1])
next(i for i in pair if i['opcode']=='ldstr')['operand']='ko'
at=index(font,0x1cc);instructions[at:at]=pair
for m in after['methods']:assert m==expected_methods[m['method']],m['method']
assert len(after['methods'])==len(before['methods'])
assert read(WORK/'discovery/original_code.json.attributes.json')==read(WORK/'discovery/candidate_code.json.attributes.json'),'속성 인자 변경'
assert read(WORK/'discovery/original_code.json.enums.json')==read(WORK/'discovery/candidate_code.json.enums.json'),'enum 변경'

negative=[]
keys_to_mutate=[k for k,v in values.items() if v!='????'][:2]
for name in ['blank','drop','swap','residual_english']:
    mutation=dict(values);k=keys_to_mutate[0]
    if name=='blank':mutation[k]=''
    elif name=='drop':del mutation[k]
    elif name=='swap':a,b=keys_to_mutate;mutation[a],mutation[b]=mutation[b],mutation[a]
    else:mutation[k]='UNTRANSLATED'
    try:verify_values(mutation)
    except AssertionError:negative.append({'case':name,'status':'PASS'})
    else:raise AssertionError('결함 주입을 검출하지 못함: '+name)
report={'status':'PASS','scope':'파일·번역 위치·문자열 형식·코드 변경 경계의 정적 검증. 전수 분류와 실제 화면 검수는 별도 완료 필요.','candidate':candidate.name,'original_files':len(original),'files':actual,'changed_files':changed,'pck_original_entries':len(source_pack),'pck_candidate_entries':len(observed),'pck_modified_entries':list(expected_changes),'translation_entries':len(values),'plural_entries':sum(r['plural_key'] is not None for r in rows),'unchanged_methods':len(before['methods'])-len(set(r['method'] for r in read(WORK/'translation/code_changes.json'))|{lang,font,format_method,inventory_method}),'mutation_tests':negative}
(WORK/'static_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('위치별 번역',len(values),'파일',len(actual),'코드 경계 검증 PASS')
