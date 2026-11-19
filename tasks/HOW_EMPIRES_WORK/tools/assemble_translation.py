"""번역 원본을 위치별로 결합하고 미번역·서식 손상을 분리합니다."""
from common import *
import re, collections

manual = {}
for path in sorted((WORK/'translation').glob('*.tsv')):
    if path.name.startswith('direct_'):
        continue
    for number,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        if not line:
            continue
        key,value = line.split('\t',1)
        if key in manual:
            raise ValueError(('중복 번역',key,path.name,number))
        manual[key] = value.replace('\\n','\n').replace('\\t','\t')
records = read_json(WORK/'translation/locale_inventory.json')
kept = {'USER_REPORT_EMAIL_PLACEHOLDER':'이메일 입력 형식을 보여 주는 예시 주소',
        'MOD_MISMATCH_MISSING_ENTRY_NO_VERSION':'목록 기호와 동적 모드 이름 자리표시자'}
token_re = re.compile(r'\{[^{}]+\}|(?<!\d)%(?:\d+\$)?[-+0#]*\d*(?:\.\d+)?[sdifuxXoegGc%]|\[img[^\]]*\].*?\[/img\]')
failures = []
for record in records:
    source = record['source']
    key = record['key']
    target = manual.get(record['category']+'/'+key,manual.get(key))
    reason = '문맥별 한국어 번역'
    if target is None and re.fullmatch(r'(?:\{@[^{}]+\}|\s|\[/?[^\]]+\]|[^A-Za-z{}])*',source):
        target,reason = source,'다른 번역 키 참조 또는 색상 태그·숫자·기호만 포함; 표시 시 한국어 참조로 해석'
    if target is None and key in kept:
        target,reason = source,kept[key]
    record.update(target=target,classification='UNKNOWN' if target is None else ('VISIBLE_KEEP' if target==source else 'VISIBLE_TRANSLATE'),evidence=reason if target is not None else '번역 대기')
    if target is not None:
        if not target.strip() and source.strip():
            failures.append({'id':record['id'],'reason':'빈 번역'})
        if collections.Counter(token_re.findall(source)) != collections.Counter(token_re.findall(target)):
            failures.append({'id':record['id'],'reason':'자리표시자 차이','source':source,'target':target})
        if source.count('\n')!=target.count('\n'):
            failures.append({'id':record['id'],'reason':'제어 줄바꿈 차이'})
write_json(WORK/'translation/canonical.json',records)
write_json(WORK/'translation/format_failures.json',failures)
summary = {'classifications':dict(collections.Counter(r['classification'] for r in records)),
           'remaining_by_category':dict(collections.Counter(r['category'] for r in records if r['target'] is None)),
           'format_failures':len(failures)}
write_json(WORK/'translation/progress.json',summary)
print(json.dumps(summary,ensure_ascii=False))
