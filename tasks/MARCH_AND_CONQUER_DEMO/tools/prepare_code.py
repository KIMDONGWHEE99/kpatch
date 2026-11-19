"""원본 메서드와 값에 묶인 코드 번역·유지 근거를 생성합니다."""
from baseline import *
import re
rows=json.loads((EXTRACT/'code_literals.json').read_text(encoding='utf-8'))
mapping={a.lower():b for a,b in [line.split('\t') for line in (WORK/'text_map.tsv').read_text(encoding='utf-8').splitlines() if line]}
extra={
'Land Conquered!':'지역 정복!','State: {0}':'상태: {0}','BOSS ':'우두머리 ', 'Unknown':'알 수 없음',
'Afternoon':'오후','Evening':'저녁','Night':'밤','Summer':'여름','Autumn':'가을','Winter':'겨울',
'Ashen Hills':'잿빛 언덕','Golden Plains':'황금 평원','Storm Coasst':'폭풍 해안','Sunscar Desert':'햇볕에 그을린 사막','Barren Wastland':'메마른 황무지','Moonfen':'달빛 늪','Ember Peaks':'잿불 봉우리',
'Missing Language':'언어 없음','Tutorial: Off':'도움말: 꺼짐','Tutorial: On':'도움말: 켜짐',
'Prestige Level {0}\n\n':'명성 등급 {0}\n\n','Your new campaign will begin with:\n\n':'새 원정은 다음 자원으로 시작합니다:\n\n',
'{0} Gold\n':'금화 {0}\n','{0} Mana\n\n':'마나 {0}\n\n','The campaign will restart from Battle 1.':'원정이 첫 번째 전투부터 다시 시작됩니다.',
"You've reached the end of the demo. Thanks for playing 1000 Battles.":'데모의 마지막에 도달했습니다. 1000 Battles를 플레이해 주셔서 감사합니다.',
'Battle Over\nPlayer Won':'전투 종료\n아군 승리','Welcome':'환영합니다','Demo Version':'데모 버전','Begin your journey.':'여정을 시작하세요.',
'This demo ends after a limited number of battles.':'이 데모는 정해진 전투 횟수에 도달하면 종료됩니다.',
'{0:0.#}s':'{0:0.#}초','{0}G / {1}M':'금화 {0} / 마나 {1}','Max Rank':'최고 등급','Cooldown: {0}s':'재사용 대기: {0}초','0G / 0M':'금화 0 / 마나 0','Paused':'일시정지',
}
mapping.update({k.lower():v for k,v in extra.items()})
# 이 인덱스는 고정된 원본 DLL의 전체 367개 ldstr를 실제 메서드별 검토한 결과입니다.
translated=set([30,32,58,72,74,76,78,80,91,115,118,121,124,126,132,133,134,135,136,138,*range(142,146),*range(147,151),*range(152,162),189,194,196,204,205,206,213,214,*range(215,220),221,224,228,232,235,238,241,243,247,250,*range(257,261),274,277,279,281,283,285,287,290,302,303,304,305,306,307,308,309,310,311,312,316])
patch=[];ledger=[]
for i,r in enumerate(rows):
    if i in translated:
        target=mapping.get(r['source'].lower());assert target is not None,(i,r)
        assert re.findall(r'\{[^{}]+\}',r['source'])==re.findall(r'\{[^{}]+\}',target)
        assert r['source'].count('\n')==target.count('\n')
        patch.append(dict(r,target=target));kind='VISIBLE_TRANSLATE';reason='화면에 출력하는 기본값·대체 문구·숫자 조합. 원본 메서드와 인접 명령 참조'
    else:
        target=r['source'];kind='INTERNAL';reason='원본 코드의 언어/저장 키·애니메이션/정렬/객체 이름·진단 로그 또는 수치 서식. 메서드와 인접 명령 참조'
        if i in set(range(5,25))|{27,60,61,66,67,86,113,116,119,122,127,128,129,130,131,140,141,146,151,162,165,190,191,192,193,197,198,199,200,207,208,209,210,222,225,226,229,230,233,236,239,244,276,280,284,288,291,292,293,294,295,301,313,314,315}:
            kind='VISIBLE_KEEP';reason='화면 수치·퍼센트·시간·해상도·기호 또는 빈 표시값; 형식 인수와 숫자 동작 보존'
    ledger.append(dict(r,index=i,classification=kind,target=target,reason=reason))
save(WORK/'code_translation.json',patch);save(WORK/'code_ledger.json',ledger)
print('코드 번역',len(patch),'유지/내부',len(ledger)-len(patch))
