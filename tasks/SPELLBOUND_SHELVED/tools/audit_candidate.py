"""후보 재추출 결과·위치별 번역·제어 정보·변경 경계를 독립 검증한다."""
from pathlib import Path
import json
import hashlib
import re
import sys
import difflib
from pck_tools import ROOT, BASELINE, EXTRACTED, WORK, read_pack

sys.path.insert(0,str(ROOT/'tools/python_deps'))
from fontTools.ttLib import TTFont

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def flatten(value, prefix=''):
    if isinstance(value, dict):
        for key, item in value.items(): yield from flatten(item,prefix+'/'+str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value): yield from flatten(item,prefix+'/'+str(index))
    elif isinstance(value,str): yield prefix,value

def format_tokens(text):
    return re.findall(r'%%|%(?:\d+\$)?[-+0#]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[sdfxXobc]',text)

def tag_tokens(text):
    tags=re.findall(r'\[(/?)(b|i|u|color|font|url)([^\]]*)\]',text)
    stack=[]
    for closing,name,attrs in tags:
        if closing:
            assert stack and stack.pop()==name, '태그 중첩 오류'
        else:stack.append(name)
    assert not stack,'닫지 않은 태그'
    return tags

def comparable_source(path):
    text=Path(path).read_text(encoding='utf-8')
    # 문자열 밖 공백만 제외한 토큰열을 비교한다.
    return re.findall(r'""".*?"""|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27|[^\s]',text,re.S)

def run(candidate_id, recovered_path):
    candidate=ROOT/'build_candidate/SPELLBOUND_SHELVED'/candidate_id
    recovered=Path(recovered_path)
    w=WORK/'ko_v001'
    expected=json.loads((WORK/'translation/ko.json').read_text(encoding='utf-8'))
    actual=json.loads((recovered/'data/i18n/ko.json').read_text(encoding='utf-8'))
    assert actual==expected,'위치별 번역 불일치'
    en=json.loads((EXTRACTED/'pck/data/i18n/en.json').read_text(encoding='utf-8'))
    rows=[]
    for location,source in flatten(en):
        value=dict(flatten(expected))[location]
        assert value.strip(),location
        original_tokens,translated_tokens=format_tokens(source),format_tokens(value)
        assert [t for t in original_tokens if t!='%%']==[t for t in translated_tokens if t!='%%'],(location,original_tokens,translated_tokens)
        assert original_tokens.count('%%')==translated_tokens.count('%%'),location
        assert tag_tokens(source)==tag_tokens(value),location
        assert source.count('\n')==value.count('\n'),location
        # 화면 기호는 번역에 그대로 남아 있어야 한다.
        for symbol in ['✦','➔']:
            assert source.count(symbol)==value.count(symbol),location
        rows.append({'location':'data/i18n/en.json'+location,'target_location':'data/i18n/ko.json'+location,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'target_sha256':hashlib.sha256(value.encode()).hexdigest(),'status':'PASS'})
    books=json.loads((WORK/'translation/books_ko.json').read_text(encoding='utf-8'))
    originals=json.loads((EXTRACTED/'pck/data/books.json').read_text(encoding='utf-8'))['books']
    titles=json.loads((recovered/'data/book_titles_ko.json').read_text(encoding='utf-8'))['titles']
    assert len(books)==len(titles)==len(originals)==2625
    for i,(b,t,o) in enumerate(zip(books,titles,originals)):
        assert b['source']==o['title'] and b['id']==o['id'] and b['target']==t
        assert t.strip() and re.search('[가-힣]',t)
        assert re.findall(r'\d+',b['source'])==re.findall(r'\d+',t)
        rows.append({'location':f'data/books.json/books/{i}/title','id':o['id'],'target_location':f'data/book_titles_ko.json/titles/{i}','source_sha256':b['source_sha256'],'target_sha256':hashlib.sha256(t.encode()).hexdigest(),'status':'PASS'})
    original_entries={e['name']:e for e in read_pack(BASELINE/'windows/SpellboundShelved.pck')[3]}
    entries={e['name']:e for e in read_pack(candidate/'windows/SpellboundShelved.pck')[3]}
    expected_changes=json.loads((w/'pck_expected.json').read_text())
    assert set(entries)==set(original_entries)|set(expected_changes)
    for name,e in entries.items():
        if name in expected_changes:
            assert hashlib.sha256(e['data']).hexdigest()==expected_changes[name],name
        else: assert e['data']==original_entries[name]['data'],name
    for original_file in BASELINE.rglob('*'):
        if original_file.is_file() and original_file.relative_to(BASELINE).as_posix()!='windows/SpellboundShelved.pck':
            assert digest(original_file)==digest(candidate/original_file.relative_to(BASELINE))
    for script in (w/'scripts').glob('*.gd'):
        assert comparable_source(script)==comparable_source(recovered/'scripts'/script.name),script.name
    chars=(w/'required_characters.txt').read_text(encoding='utf-8')
    symbol=TTFont(EXTRACTED/'recovered/assets/fonts/NotoSansSymbols2-Regular.ttf').getBestCmap()
    for weight in [400,700]:
        f=TTFont(w/f'fonts/Korean{weight}.ttf')
        assert f['OS/2'].usWeightClass==weight
        assert not [c for c in chars if ord(c) not in f.getBestCmap() and ord(c) not in symbol]
    # 알려진 불량 입력을 정상 검사와 함께 확인한다.
    mutation_checks={}
    mutation_checks['empty']=({**actual,'menu.settings':''}!=expected)
    swapped=dict(actual);swapped['menu.settings'],swapped['menu.new_game']=swapped['menu.new_game'],swapped['menu.settings']
    mutation_checks['swapped']=swapped!=expected
    mutation_checks['missing_key']=({k:v for k,v in actual.items() if k!='menu.settings'}!=expected)
    mutation_checks['wrong_placeholder']=format_tokens('%d / %s')!=format_tokens('%s / %d')
    try:tag_tokens('[b][color=red]문구[/b][/color]');mutation_checks['bad_tag']=False
    except AssertionError:mutation_checks['bad_tag']=True
    assert all(mutation_checks.values())
    report={'game_id':'SPELLBOUND_SHELVED','steam_build':'25171813','candidate_id':candidate_id,'pck_sha256':digest(candidate/'windows/SpellboundShelved.pck'),'status':'PASS','original_pck_files':len(original_entries),'candidate_pck_files':len(entries),'modified_original_files':sum(n in original_entries for n in expected_changes),'added_files':sum(n not in original_entries for n in expected_changes),'ui_keys':len(actual),'ui_original_occurrences':len(list(flatten(en))),'book_occurrences':len(books),'code_roundtrip_files':5,'mutation_checks':mutation_checks,'location_checks':rows}
    (w/(candidate_id+'_static.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='location_checks'},ensure_ascii=False))

if __name__=='__main__':run(sys.argv[1],sys.argv[2])
