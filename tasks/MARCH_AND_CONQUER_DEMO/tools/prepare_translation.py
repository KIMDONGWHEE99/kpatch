"""검토한 번역을 원본 위치별 공식 번역표로 고정합니다."""
from common import *
import re
rows=json.loads((EXTRACT/'strings.json').read_text(encoding='utf-8'))
mapping={}
for line in (WORK/'text_map.tsv').read_text(encoding='utf-8').splitlines():
    if not line:continue
    a,b=line.split('\t');key=a.strip().lower()
    assert key not in mapping or mapping[key]==b,key
    mapping[key]=b
long_text={
'start_message_title':'정복의 여정이 시작됩니다...',
'start_message_body':'왕국이 악의 세력에 점령당했습니다!\n\n10개 지역, 200번의 전투를 돌파하여 왕국을 되찾으세요!\n\n전투를 시작하려면 기술 트리에서 병영을 누른 다음 도끼병을 눌러 병력을 훈련하세요. 훈련된 병력은 전장에서 싸웁니다!\n\n적을 많이 물리칠수록 금화와 마나를 더 많이 모아 전투를 이어갈 수 있습니다!\n\n다른 기술을 해금하고 등급을 올려 병력을 강화하세요.\n\n부대를 신중하게 구성하세요!\n\n(우두머리에게 승리할 때마다 게임이 저장됩니다.)\n행운을 빕니다!',
'demo_start_message_body':'짧은 체험판에 오신 것을 환영합니다. 총 60번의 전투를 통해 정식 게임의 일부를 즐길 수 있습니다.\n\n왕국이 악의 세력에 점령당했습니다! 싸워서 되찾으세요!\n\n먼저 기술 트리에서 병영을 누른 다음 도끼병을 눌러 병력을 훈련하세요. 훈련된 병력은 전장에서 싸웁니다!\n\n적을 많이 물리칠수록 금화와 마나를 더 많이 모아 전투를 이어갈 수 있습니다!\n\n다른 기술을 해금하고 등급을 올려 병력을 강화하세요.\n\n(병력 아이콘을 누르면 자동 훈련을 멈추거나 재개합니다.)\n행운을 빕니다!',
'demo_end_message_body':'데모의 마지막에 도달했습니다. March and Conquer를 플레이해 주셔서 감사합니다. 정식 게임은 2026년 11월 출시 예정입니다! 찜 목록에 추가해 주세요!'
}
english=json.loads((EXTRACT/'trees/sharedassets0.assets_1712.json').read_text(encoding='utf-8'))
language={}; missing=[]
for e in english['entries']:
    target=long_text.get(e['key'],mapping.get(e['value'].strip().lower()))
    if target is None:missing.append((e['key'],e['value']));continue
    if e['key'] in language:assert language[e['key']]==target
    language[e['key']]=target;mapping[e['value'].strip().lower()]=target
save(WORK/'language_ko.json',language)
trees={};canonical=[]
visible_fields={'m_text','m_Text','displayName','description','fallbackText'}
keep_pattern=re.compile(r'^[\s\d\W_]+$')
for row in rows:
    field=row['field'];source=row['source'];target=None;reason=None
    if row['file']=='sharedassets0.assets' and row['path_id']==1712:
        if re.fullmatch(r'/entries/\d+/value',field):
            idx=int(field.split('/')[2]);key=english['entries'][idx]['key'];target=language.get(key);reason='영어 언어 슬롯의 한국어 번역, 키 '+key
        elif field=='/languageDisplayName':target='한국어';reason='언어 선택 표시'
        elif field=='/languageCode':target='ko';reason='한국어 언어 슬롯 식별'
    elif row['type']=='MonoBehaviour' and field.split('/')[-1] in visible_fields:
        # 기존 언어표를 우선하는 게임 동작과 동일하게, 해당 표시 필드의 문맥을 연결합니다.
        tree_key=(row['file'],row['path_id'])
        if tree_key not in trees:trees[tree_key]=json.loads((EXTRACT/'trees'/f'{tree_key[0]}_{tree_key[1]}.json').read_text(encoding='utf-8'))
        tree=trees[tree_key]
        key=None
        if field in ('/displayName','/description'):
            ident=tree.get('nodeId',tree.get('unitId'))
            if ident:key=ident+('_name' if field=='/displayName' else '_description')
        if field=='/fallbackText':key=tree.get('textKey')
        if key in language:target=language[key];reason='동일 유닛/기술/문구의 공식 언어표와 일치: '+key
        else:target=mapping.get(source.strip().lower());reason='표시 필드 원문별 번역'
        if target is not None and re.findall(r'\{[^{}]+\}',source)!=re.findall(r'\{[^{}]+\}',target):
            target=mapping.get(source.strip().lower());reason='서식 처리를 거치지 않는 직접 표시용 기본값은 원문의 자리표시자 구조 유지'
        if source=='Wishlist on\nSteam!':target='Steam에서\n찜하기!'
        if target is not None:
            if source.endswith('\n') and not target.endswith('\n'):target+='\n'
        elif keep_pattern.fullmatch(source) or source in ['v1.1','O','G','X','B','Z','R','Y','A','W']:
            canonical.append(dict(row,classification='VISIBLE_KEEP',reason='숫자·기호·버전 또는 디버그 색상/벡터 성분 식별자',target=source));continue
        else:missing.append((row['file'],row['path_id'],field,source))
    if target is not None:canonical.append(dict(row,classification='VISIBLE_TRANSLATE',target=target,reason=reason))
save(WORK/'translation.json',canonical);save(WORK/'translation_missing.json',missing)
print('언어 키',len(language),'위치',len(canonical),'미번역',len(missing));print(json.dumps(missing,ensure_ascii=False,indent=2))
