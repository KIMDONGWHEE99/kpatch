"""공식 번역 원본을 이용해 후보 입력과 허용 변경 기록을 준비한다."""
import sys
import json
import re
import hashlib
from pck_tools import ROOT, EXTRACTED, WORK

sys.path.insert(0, str(ROOT/'tools/python_deps'))
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools import subset

target = WORK/'ko_v001'
target.mkdir(parents=True, exist_ok=True)
scripts = target/'scripts'
scripts.mkdir(exist_ok=True)
translation_root = WORK/'translation'
ko_path = translation_root/'ko.json'
ko = json.loads(ko_path.read_text(encoding='utf-8'))
names = {
'Fizzwick':'피즈윅','Bramble':'브램블','Nutmeg':'너트메그','Pippin':'피핀','Snorri':'스노리','Thimble':'심블',
'Wobble':'워블','Juniper':'주니퍼','Cogsworth':'콕스워스','Marigold':'메리골드','Fennel':'페넬','Sprocket':'스프로킷',
'Alfie':'알피','Bram':'브램','Cleo':'클레오','Dorin':'도린','Esme':'에스메','Fenwick':'펜윅','Grizel':'그리젤',
'Hobb':'홉','Isolde':'이졸데','Jasper':'재스퍼','Kira':'키라','Lom':'롬','Milo':'마일로','Nella':'넬라','Odo':'오도',
'Petra':'페트라','Quill':'퀼','Rook':'룩','Sable':'세이블','Tilly':'틸리','Ulf':'울프','Wren':'렌',
}
ko.update({'name.'+k:v for k,v in names.items()})
ko['debug.summary'] = '마법에 걸린 도서관 — 개발 화면\n금화 %d · 정리 %d / %d권 (정돈도 %.1f%%) · 개방 서가 %d/%d · 노움 %d명 · 손님 %d명 · 완독 %d권%s\nQ/E: 회전 · WASD/방향키: 이동 · 휠: 확대/축소 · 드래그: 이동 · U: 업그레이드 · T: 업적'
ko['debug.performance'] = '%s\n초당 프레임: %d · 초당 수입 %.2f ✦'
ko_path.write_text(json.dumps(ko,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
changes = []

def load_script(name):
    return (EXTRACTED/'recovered/scripts'/name).read_text(encoding='utf-8')

def record_script(name, source, target_text):
    assert source != target_text
    (scripts/name).write_text(target_text,encoding='utf-8')
    changes.append({'file':'scripts/'+name,'original_sha256':hashlib.sha256(source.encode()).hexdigest(),'expected_sha256':hashlib.sha256(target_text.encode()).hexdigest()})

src = load_script('i18n.gd')
new = src.replace('["en", "de", "es", "fr"]','["ko", "en", "de", "es", "fr"]').replace('"en": "English",','"ko": "한국어", "en": "English",')
new = new.replace('return loc if loc in LOCALES else "en"','return "ko"')
new += '\n\nstatic func person(value: String) -> String:\n\treturn t("name." + value, value)\n'
record_script('i18n.gd',src,new)

src = load_script('ui_theme.gd')
new = src.replace('static var _theme: Theme','''static var _korean_fonts: = {}

static func korean_font(weight: int = 400) -> FontFile:
	var selected: int = 700 if weight >= 600 else 400
	if not _korean_fonts.has(selected):
		var korean: = FontFile.new()
		korean.data = FileAccess.get_file_as_bytes("res://assets/fonts/Korean%d.ttf" % selected)
		_korean_fonts[selected] = korean
	return _korean_fonts[selected]

static var _theme: Theme''')
new = new.replace('var fb: Array[Font] = f.fallbacks','var fb: Array[Font] = f.fallbacks\n\t\t\tvar korean: = korean_font(700 if "Bold" in path else 400)\n\t\t\tif not fb.has(korean):\n\t\t\t\tfb.append(korean)')
record_script('ui_theme.gd',src,new)

src = load_script('main.gd')
new = src.replace('return GNOME_NAMES[(slot - 1) % GNOME_NAMES.size()]','return I18n.person(GNOME_NAMES[(slot - 1) % GNOME_NAMES.size()])')
new = new.replace('\t_setup_locale()','\t_setup_locale()\n\tgreybox.set_open_sign(library_open)',1)
new = new.replace('fb.append(sym)','fb.append(UITheme.korean_font())\n\t\t\tfb.append(sym)',1)
pattern = r'"SPELLBOUND & SHELVED — greybox\\n.*?T: achievements"'
old = re.search(pattern,new)[0]
new = new.replace(old,'I18n.t("debug.summary", '+old+')')
old = '"""%s\nFPS: %d · income %.2f ✦/s"""'
assert old in new
new = new.replace(old,'I18n.t("debug.performance", '+old+')')
new = new.replace('mono.font_names = ["Menlo", "Consolas", "Courier New", "monospace"]','mono.font_names = ["Menlo", "Consolas", "Courier New", "monospace"]\n\tmono.fallbacks = [UITheme.korean_font()]')
record_script('main.gd',src,new)

for name in ['customer.gd','customers.gd']:
    src = load_script(name)
    new = src.replace('[given_name, ctype.name]','[I18n.person(given_name), ctype.name]').replace('[c.given_name, ctype.name','[I18n.person(c.given_name), ctype.name')
    record_script(name,src,new)

books = json.loads((translation_root/'books_ko.json').read_text(encoding='utf-8'))
(target/'data').mkdir(exist_ok=True)
(target/'data/ko.json').write_text(json.dumps(ko,ensure_ascii=False,indent=2),encoding='utf-8')
(target/'data/book_titles_ko.json').write_text(json.dumps({'titles':[b['target'] for b in books]},ensure_ascii=False,indent=2),encoding='utf-8')
characters=set(''.join(b['target'] for b in books))
for value in ko.values():
    characters.update(''.join(value) if isinstance(value,list) else value)
characters.update(chr(i) for i in list(range(32,127))+list(range(160,256)))
characters -= set('\n\r\t')
font_source=ROOT/'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf'
fonts=target/'fonts';fonts.mkdir(exist_ok=True)
font_report=[]
for weight in [400,700]:
    dest=fonts/f'Korean{weight}.ttf'
    font=TTFont(font_source)
    missing=sorted(c for c in characters if ord(c) not in font.getBestCmap())
    # 특수 기호는 원래 Noto Sans Symbols 2 글꼴에서 검사한다.
    supported={ord(c) for c in characters if ord(c) in font.getBestCmap()}
    font=instantiateVariableFont(font,{'wght':weight},inplace=True)
    options=subset.Options();options.name_IDs=['*'];options.name_legacy=True;options.name_languages=['*']
    sub=subset.Subsetter(options=options);sub.populate(unicodes=supported);sub.subset(font);font.recalcTimestamp=False; font.save(dest)
    checked=TTFont(dest)
    assert supported.issubset(checked.getBestCmap())
    font_report.append({'weight':weight,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'required_characters':len(characters),'font_characters':len(supported),'fallback_required':missing,'static_weight':checked['OS/2'].usWeightClass})
(target/'font_report.json').write_text(json.dumps(font_report,ensure_ascii=False,indent=2),encoding='utf-8')
(target/'required_characters.txt').write_text(''.join(sorted(characters)),encoding='utf-8')
(target/'script_changes.json').write_text(json.dumps(changes,indent=2),encoding='utf-8')
print(json.dumps({'scripts':len(changes),'ui_keys':len(ko),'books':len(books),'fonts':font_report},ensure_ascii=False))
