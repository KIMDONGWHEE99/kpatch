"""명시적으로 검토한 번역과 반복 형식으로 공식 번역 원본을 만듭니다."""
from common import *
import re
sources=json.loads((WORK/'translation_sources.json').read_text(encoding='utf8'));byid={}
for p in sorted(WORK.glob('ko_part*.json')):
    for key,value in json.loads(p.read_text(encoding='utf8')).items():
        assert key not in byid;byid[key]=value
terms={sources[int(i)]:v for i,v in byid.items() if 49<=int(i)<=184}
terms.update({'Warcry':'전투 함성'})
parts={'Weapon':'무기','Helmet':'투구','Armor':'갑옷','Boots':'장화','Gloves':'장갑','Cloak':'망토','Amulet':'목걸이','Ring':'반지'}
stats={'Vitality':'활력','Damage':'공격력','Crit chance':'치명타 확률','Crit damage':'치명타 피해','Dodge':'회피','Defense':'방어력','Loot':'전리품','Stun':'기절','Gold bonus':'금화 보너스','Block chance':'막기 확률','Boss damage':'보스 피해','bonus boss damage':'보스 추가 피해','Gold jelly chance':'황금 젤리 확률','Damage reflect':'피해 반사','Vampirism':'흡혈','Double strike chance':'연속 공격 확률','Healing boost':'치유량 증가','Gun damage':'총기 공격력'}
stats={k.lower():v for k,v in stats.items()}
qualities={k:byid[str(i)] for i,k in enumerate(['Normal','Unique','Rare','Epic','Mythic','Legendary'],209)}
prefixes={'Item level upgrade':'장비 레벨 강화','Quality upgrade':'품질 강화','Extra inventory space':'추가 소지품 칸','Game speed':'게임 속도','Damage multiplier':'공격력 배율','Health multiplier':'체력 배율','Gold multiplier':'금화 배율'}
keep_ids={602,606,608,619,628,630,638,643,655,656,657,658,659,661,662,670,672,674,676,678,682,684,685,686,690,694,700,727,735}
result=[];missing=[]
for i,s in enumerate(sources):
    t=byid.get(str(i));reason='문맥별 수동 번역'
    if t is None:
        for prefix,value in prefixes.items():
            if re.fullmatch(re.escape(prefix)+r' [IVX]+',s):t=value+s[len(prefix):]
        if m:=re.fullmatch(r'Upgrade items to \+(\d+)',s):t=f'장비를 +{m[1]}까지 강화합니다'
        if m:=re.fullmatch(r'Item drop \+(\d+)',s):t=f'+{m[1]} 장비 획득'
        if m:=re.fullmatch(r'Chance for finding \+(\d+) items',s):t=f'+{m[1]} 장비를 발견할 확률이 생깁니다'
        if m:=re.fullmatch(r'Item drop (Unique|Rare|Epic|Mythic|Legendary)',s):t=qualities[m[1]]+' 장비 획득'
        if m:=re.fullmatch(r'Chance for finding (Unique|Rare|Epic|Mythic|Legendary) items',s):t=qualities[m[1]]+' 장비를 발견할 확률이 생깁니다'
        if m:=re.fullmatch(r'Reach floor (\d+)',s):t=m[1]+'층 도달'
        if m:=re.fullmatch(r'(\w+) Socket ([IVX]+)( *)',s):t=parts[m[1]]+' 소켓 '+m[2]+m[3]
        if m:=re.fullmatch(r'Unlocks a gem socket in your (\w+) slot',s):t=parts[m[1]]+' 칸에 보석 소켓을 해금합니다'
        if m:=re.fullmatch(r'(.*?) Gem( *)',s):t=terms[m[1]]+' 보석'+m[2]
        if m:=re.fullmatch(r'Unlocks the (.*?) gem',s):t=terms[m[1]]+' 보석을 해금합니다'
        if m:=re.fullmatch(r'Ability (.*)',s):t=terms[m[1]]+' 기술'
        if m:=re.fullmatch(r'Unlocks (.*?) ability',s):t=terms[m[1]]+' 기술을 해금합니다'
        if m:=re.fullmatch(r'(.*?) upgrades ([IVX]+)',s):t=stats[m[1].lower()]+' 강화 '+m[2]
        if m:=re.fullmatch(r'Unlocks 10 levels of (.*?) upgrades',s):t=stats[m[1].lower()]+' 강화 상한을 10레벨 높입니다'
        reason='검토한 수치·단계 반복 형식 번역'
    if t is None and (i in keep_ids or re.fullmatch(r'[\d+.,/%\s-]+k?|[IVX]+',s)):
        t=s;reason='수치·로마 숫자 단계·단위·방향 기호·색상/좌표 성분·입력 키패드 문자 또는 제작사 고유명 표기 유지'
    if t is None:missing.append((i,s));continue
    result.append(dict(id=i,source=s,target=t,classification='VISIBLE_KEEP' if t==s else 'VISIBLE_TRANSLATE',reason=reason))
save(WORK/'translation.json',result);save(WORK/'translation_missing.json',missing)
print('공식 번역',len(result),'미완료',missing)
