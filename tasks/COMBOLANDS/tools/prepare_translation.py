"""공식 번역 원본에 각 문구의 정확한 위치·원문 지문을 연결합니다."""
from common import *
from collections import Counter
import re

def load_parts():
    translations={}
    for p in sorted(WORK.glob('ko_*.json')):
        part=json.loads(p.read_text(encoding='utf8'))
        assert not (part.keys() & translations.keys()), p
        translations.update(part)
    return translations

def validate_tokens(source,target):
    for pattern in [r'\[[^\]]+\]', r'\{\d+[^{}]*\}', r'<[^>]+>']:
        assert Counter(re.findall(pattern,source))==Counter(re.findall(pattern,target)), (source,target,pattern)
    for c in ['@','\n','\r','\t','{','}']:
        assert source.count(c)==target.count(c),(source,target,c)
    # HTML/TMP 태그의 열고 닫는 순서도 원문과 같아야 합니다.
    assert re.findall(r'<[^>]+>',source)==re.findall(r'<[^>]+>',target),(source,target)
    # 원본에 존재하는 강조용 중괄호의 순서·중첩 상태까지 보존합니다.
    def emphasis(value):return re.findall(r'[{}]',re.sub(r'\{\d+[^{}]*\}','',value))
    assert emphasis(source)==emphasis(target),(source,target,'강조 중첩')

def main():
    parts=load_parts()
    inv=json.loads((EXTRACT/'inventory_fixed.json').read_text(encoding='utf8'))
    canon=[]; source_map={}
    def add(f,r,target,reason):
        validate_tokens(r['source'],target)
        canon.append(dict(file=f['relative_path'],file_sha256=f['sha256'],path_id=r['path_id'],field=r['field_path'],source=r['source'],source_sha256=hashlib.sha256(r['source'].encode()).hexdigest(),target=target,classification='VISIBLE_KEEP' if target==r['source'] else 'VISIBLE_TRANSLATE',reason=reason))
    for f in inv['files']:
        for r in f['strings']:
            if r['class']=='LocalizedStringAsset' and r['field_path']==['_originalString']:
                target=parts[str(r['path_id'])]
                add(f,r,target,'LocalizedStringAsset.GetText에서 화면 표시 문구 반환; 기호 전용 보상은 한국어 이름·수치로 치환됨')
                if r['source'] in source_map: assert source_map[r['source']]==target,(r['source'],target)
                source_map[r['source']]=target
    direct=json.loads((EXTRACT/'direct_visible.json').read_text(encoding='utf8'))
    overrides=json.loads((WORK/'direct_overrides.json').read_text(encoding='utf8'))
    # 제작진 이름·닉네임은 보존하고 역할·감사 문구만 번역합니다.
    credits=direct[68]['source']
    for s,t in [('Logo Design & Animation','로고 디자인·애니메이션'),('Music','음악'),('Main Menu Artwork','주 메뉴 그림'),('Font','글꼴'),('Supported by Evil Landfall?','Evil Landfall? 지원'),('And Future Friends Games','Future Friends Games 지원'),('With Special Thanks To','특별히 감사드리는 분들'),('And Our Wonderful Beta Testers','멋진 베타 테스터 여러분')]: credits=credits.replace(s,t)
    overrides['68']=credits
    direct_map={r['source']:overrides.get(str(i),source_map.get(r['source'])) for i,r in enumerate(direct)}
    assert all(t is not None for t in direct_map.values())
    for f in inv['files']:
        for r in f['strings']:
            visible=(r['class'] in {'TextMeshProUGUI','TextMeshPro','Text','TextAnimator_TMP'} and r['field_path'] in [['m_text'],['_text'],['m_Text']]) or (r['class']=='TMP_Dropdown' and 'm_Options' in r['field_path'] and r['field_path'][-1]=='m_Text') or (r['class']=='FeedbackText' and r['field_path']==['Message'])
            if visible and r['source'] in direct_map: add(f,r,direct_map[r['source']],'직접 표시 필드; 버전·배수·색상/좌표 성분·게임/서비스 고유명만 유지')
    extra=json.loads((WORK/'extra_field_ko.json').read_text(encoding='utf8'))
    for f in inv['files']:
        for r in f['strings']:
            if r['class']=='FeedbackForm' and r['field_path'][-1]=='m_StringArgument': add(f,r,extra[r['source']],'알림 Toast에 전달되는 화면 문구')
            elif r['class']=='EFConfig' and ('CategoryNames' in r['field_path'] or ('Labels' in r['field_path'] and r['field_path'][-1]=='name')): add(f,r,extra[r['source']],'피드백 양식의 분류·중요도 드롭다운 표시 이름; 서비스 ID는 보존')
    textasset=json.loads((WORK/'textasset_ko.json').read_text(encoding='utf8'))
    for f in inv['files']:
        for r in f['text_assets']:
            if str(r['path_id']) in textasset:
                target='\r\n'.join(textasset[str(r['path_id'])])
                add(f,dict(path_id=r['path_id'],field_path=['m_Script'],source=r['text']),target,'MechanicsMatrix 개발 화면의 축·선택 영역에서 표시되는 본문')
    ids=[(r['file'],r['path_id'],tuple(r['field'])) for r in canon]
    assert len(ids)==len(set(ids))
    save_json(WORK/'canonical_translation.json',canon)
    code_parts=json.loads((WORK/'code_ko.json').read_text(encoding='utf8'))
    code=[]
    for r in json.loads((EXTRACT/'code_literals.json').read_text(encoding='utf8')):
        key=r['method']+'|'+str(r['offset'])
        if key in code_parts:
            target=code_parts.pop(key); validate_tokens(r['text'],target)
            code.append(dict(file='Managed/Assembly-CSharp.dll',file_sha256=sha(DATA/'Managed/Assembly-CSharp.dll'),method=r['method'],offset=r['offset'],source=r['text'],target=target,reason='해당 메서드의 표시 컴포넌트에 직접 전달되는 문구'))
    assert not code_parts,code_parts
    save_json(WORK/'canonical_code.json',code)
    feedback=json.loads((WORK/'canonical_feedback.json').read_text(encoding='utf8'))
    extra_ui='불러오는 중…상점휴점체험판자동 완료무한 모드'
    save_json(WORK/'required_characters.json',sorted({ord(c) for r in canon+code+feedback for c in r['target'] if not c.isspace()}|{ord(c) for c in extra_ui}|set(range(32,127))))
    print('공식 번역 위치',len(canon),'번역',sum(r['classification']=='VISIBLE_TRANSLATE' for r in canon))

if __name__=='__main__':main()
