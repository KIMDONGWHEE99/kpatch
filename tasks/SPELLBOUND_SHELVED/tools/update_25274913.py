"""새 Steam 빌드에 맞는 입력·후보를 만들고 이전 결과와 분리한다."""
import sys
import json
import hashlib
import shutil
import runpy
from pathlib import Path
import pck_tools as core

ROOT=core.ROOT
BASELINE=ROOT/'source_original/SPELLBOUND_SHELVED/steam_25274913'
EXTRACTED=ROOT/'extracted_private/SPELLBOUND_SHELVED/steam_25274913'
WORK=ROOT/'working_private/SPELLBOUND_SHELVED/update_25274913'
CANDIDATE=ROOT/'build_candidate/SPELLBOUND_SHELVED/ko_1.0.1_c01'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,value):Path(p).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def configure():
    core.BASELINE=BASELINE;core.EXTRACTED=EXTRACTED;core.WORK=WORK

def prepare():
    original=ROOT/'working_private/SPELLBOUND_SHELVED/translation'
    dest=WORK/'translation';dest.mkdir(exist_ok=True)
    for p in original.glob('*.json'):
        if not (dest/p.name).exists():shutil.copy2(p,dest/p.name)
    ko=read(dest/'ko.json')
    added={'settings.hide_gnome_chat':'노움 잡담 숨기기','settings.more_stats':'추가 통계 표시',
        'hover.shelf_fill':'%s (%.0f%% 채움)','hud.floor_books':'바닥에 놓인 책 %d권','settings.game':'게임'}
    en=read(EXTRACTED/'recovered/data/i18n/en.json');old_en=read(ROOT/'extracted_private/SPELLBOUND_SHELVED/steam_25171813/recovered/data/i18n/en.json')
    assert set(en)-set(old_en)==set(added) and all(en[k]==v for k,v in old_en.items())
    ko.update(added);write(dest/'ko.json',ko)
    write(WORK/'translation_changes.json',[{'key':k,'source':en[k],'target':v,'reason':'새 게임 설정 또는 추가 통계 화면'} for k,v in added.items()])
    configure();runpy.run_path(str(ROOT/'tasks/SPELLBOUND_SHELVED/tools/prepare_candidate.py'))
    core.patch_pack(BASELINE/'windows/SpellboundShelved.pck',WORK/'noop.pck',{})
    assert sha(WORK/'noop.pck')==sha(BASELINE/'windows/SpellboundShelved.pck')

def build():
    w=WORK/'ko_v001'
    changes={}
    for source in (w/'scripts').glob('*.gd'):
        compiled=w/'compiled'/source.with_suffix('.gdc').name
        assert compiled.exists();changes['scripts/'+compiled.name]=compiled.read_bytes()
    changes.update({'data/i18n/ko.json':(w/'data/ko.json').read_bytes(),
        'data/book_titles_ko.json':(w/'data/book_titles_ko.json').read_bytes(),
        'assets/fonts/Korean400.ttf':(w/'fonts/Korean400.ttf').read_bytes(),
        'assets/fonts/Korean700.ttf':(w/'fonts/Korean700.ttf').read_bytes()})
    assert not CANDIDATE.exists();shutil.copytree(BASELINE,CANDIDATE)
    core.patch_pack(BASELINE/'windows/SpellboundShelved.pck',CANDIDATE/'windows/SpellboundShelved.pck',changes)
    write(w/'pck_expected.json',{k:hashlib.sha256(v).hexdigest() for k,v in changes.items()})
    print('후보',CANDIDATE.name,'PCK',sha(CANDIDATE/'windows/SpellboundShelved.pck'))

if __name__=='__main__':
    {'prepare':prepare,'build':build}[sys.argv[1]]()
