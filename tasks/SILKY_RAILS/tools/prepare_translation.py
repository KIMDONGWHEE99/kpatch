"""원문 서식과 줄바꿈을 보존하고 추가 표시 문구를 연결합니다."""
from baseline import *
import re
rows=json.loads((WORK/'table_rows.json').read_text(encoding='utf-8'));ko=json.loads((WORK/'ko.json').read_text(encoding='utf-8'))
fix={
'sys.event.select_cart':'차량\n선택','ui.campfire.repair':'파손\n차량\n수리','ui.campfire.scrap':'분해\n부품\n획득','ui.reward.repair_dead':'파손\n차량\n수리','ui.sultan.gift':'술탄에게\n차량 선물','ui.sultan.grant':'피해량\n+{0} 부여','ui.event.swap':'교환\n차량 {0}','ui.s.build':'편성 후\n출발','ui.s.repair_cart':'차량\n수리',
'cart.cart_cactus.desc':'360도 방향으로 가시를 발사합니다.\n성장 완료: 가시가 적 1명을 추가로 관통합니다.\n개화: 즉시 가시를 원형으로 발사합니다.',
'cart.cart_sunflower.desc':'라운드 종료 시 금화 +{4/6/8}.\n개화: 이번 라운드 수입에 금화 +{2/3/5} (최대 3중첩).\n성장 완료: 기본 수입이 금화 +{8/15/25}로 증가합니다.',
'cart.sapphirecart.desc':'얼음 칼날 {V0/V1/V2}개를 던져 피해를 주고 3초 동안 적을 둔화시킵니다.\n인접한 차량의 판매 가격 1금화당 재사용 대기시간 -{0.4/0.6/0.75}%.',
'tut.exclamation':'차량 위의 느낌표는 다가오는 적 무리의 공격 대상이라는 뜻입니다.\n\n차량을 끌어 위치를 바꾸세요.',
'event.snowevent_the_ghoststation.c1':'유령의 거래 수락\n유령의 저주 유물을 얻습니다.',
'event.snowevent_the_ghoststation.c2':'기적을 울리고 출발\n유령을 무시하고 계속 갑니다.',
'event.desertevent_clockstation.c2':'흩어진 톱니바퀴 줍기\n6금화를 얻습니다.',
'event.desertevent_golemhead.c2':'빛나는 조각 긁어 모으기\n8금화를 얻습니다.',
'relic.emergencyboiler.desc_b':'<color=#4A4D50><b>[파손됨]</b></color>\n보일러가 더 이상 비상 보호를 제공하지 않습니다.',
'relic.fieldengineerkit.desc':'파손된 군사 차량을 자동 수리하여 <color=#0E4A14><b>체력을 전부 회복</b></color>합니다. 소요 시간: <color=#5A3E00><b>{0}라운드</b></color>.\n<color=#3A3D40><i>파손된 군사 차량을 기다리는 중...</i></color>',
'relic.fieldengineerkit.desc_b':'파손된 군사 차량 1대를 자동 수리해 <color=#0E4A14><b>체력을 전부 회복</b></color>합니다. 주기: <color=#5A3E00><b>{0}라운드</b></color>.\n현재 수리 중: <color=#0B2545><b>{1}</b></color>, <color=#5A3E00><b>{2}번 칸</b></color> (<color=#0E4A14><b>{3}라운드 남음</b></color>).',
'relic.gildedcaboose.desc':'보유한 <color=#5A3E00><b>{0}금화</b></color>마다 마지막 차량의 <color=#0B2545><b>기본 피해량 +1</b></color>.\n현재 효과: <color=#5A3E00><b>기본 피해량 +{1}</b></color>.',
'tut.level_end':'구간이 끝나면 금화를 모으고\n\n다음 역으로 이동합니다.\n\n',
 'tut.move_camera':'[WASD], 화면 가장자리의 마우스,\n또는 [오른쪽 클릭 후 끌기]로 화면을 이동하세요.',
 'tut.use_abilities':'아래쪽 능력 아이콘을 클릭하거나\n[1, 2, 3, 4]를 눌러 능력을 사용하세요.'}
ko.update(fix)
for r in rows:
 s=r['source'];k=r['key'];t=ko[k]
 if s.endswith('\n') and not t.endswith('\n'):t+='\n'
 if '\n<size=' in s:t=t.replace('<size=','\n<size=',1) if '\n<size=' not in t else t
 if s.count('\n')>t.count('\n'):
  n=s.count('\n')-t.count('\n')
  if k=='relic.heavyordnanceoverhaul.desc':t=t.replace(' • ','\n• ')
  elif '\n<color=' in s:t=t.replace('<color=#F59E0B>','\n<color=#F59E0B>').replace('<color=#3A3D40>','\n<color=#3A3D40>').replace('<color=#4A4D50>','\n<color=#4A4D50>').replace('<color=#8A1C14>','\n<color=#8A1C14>')
  elif '. ' in t:t=t.replace('. ','.\n',n)
  elif '! ' in t:t=t.replace('! ','!\n',n)
 ko[k]=t
 assert s.count('\n')==t.count('\n'),(k,s.count('\n'),t.count('\n'))
 assert s.count('\\n')==t.count('\\n'),k
 assert re.findall(r'<[^>]+>',s)==re.findall(r'<[^>]+>',t),k
 # 레벨별 선택 문구는 분기 수를 유지하며 숫자·이름 자리표시자는 그대로 보존합니다.
 a=re.findall(r'\{[^{}]*\}',s);b=re.findall(r'\{[^{}]*\}',t)
 assert collections.Counter(x for x in a if '/' not in x)==collections.Counter(x for x in b if '/' not in x),k
 assert [x.count('/') for x in a if '/' in x]==[x.count('/') for x in b if '/' in x],k
save(WORK/'ko.json',ko)
def norm(s):return re.sub(r'\s+','',s.replace('\\n','\n'))
source_map={norm(r['source']):ko[r['key']].replace('\\n','\n') for r in rows}
extra={'Repaire a broken Cart':'파손된 차량 수리','TESLA':'테슬라','Tesla':'테슬라','Option A':'선택 A','Seed : 123456789':'시드: 123456789','(Copy)':'(복사)','BUILD\n&  GO':'편성 후\n출발','Unlock all':'모두 해금','Stats':'능력치','Repair \nCart':'차량\n수리','station 123':'123번 역','New Text':'새 텍스트','Panel Title':'패널 제목','Button':'버튼','Reset':'초기화','Message text\n':'메시지\n','Color\n':'색상\n','Foldout':'펼치기','Foldout\n':'펼치기\n','Enum':'목록','TEST':'시험','End of story.\nRestart?':'이야기가 끝났습니다.\n다시 시작할까요?','Current buff: ':'현재 강화: ',' <color=#ffb74d>(changes next round)</color>':' <color=#ffb74d>(다음 라운드에 변경)</color>',
'Enemies have <color=#B91C1C><b>+{0}% Max HP</b></color>.\n':'적 <color=#B91C1C><b>최대 체력 +{0}%</b></color>.\n',
'Survive <color=#D97706><b>{0} {1}</b></color> to break the curse and grant all carts <color=#15803D><b>+1 Damage, +1 Target, and +1 Heal Power</b></color>.':'<color=#D97706><b>{0}{1}</b></color> 생존하면 저주가 풀리고 모든 차량의 <color=#15803D><b>피해량 +1, 대상 수 +1, 회복력 +1</b></color>.',
'{0}\n<color=#60A5FA><b>Broken Carts:</b></color> <color=#FBBF24><b>{1} / {2}</b></color>':'{0}\n<color=#60A5FA><b>파괴한 차량:</b></color> <color=#FBBF24><b>{1} / {2}</b></color>',
'Reduces your train size by <color=#B91C1C><b>-{0} Slot</b></color>.\n':'최대 차량 수 <color=#B91C1C><b>-{0}칸</b></color>.\n',
'Survive <color=#D97706><b>{0} {1}</b></color> to permanently gain <color=#15803D><b>+1 Slot</b></color>.':'<color=#D97706><b>{0}{1}</b></color> 생존하면 최대 차량 수가 영구적으로 <color=#15803D><b>+1칸</b></color> 증가합니다.',
'Gain <color=#5A3E00><b>+{0} Gold</b></color> upon entering the shop for each active trait synergy on your train.\nCurrently yielding: <color=#5A3E00><b>+{1} Gold</b></color>.':'상점 입장 시 열차의 활성화된 특성 하나당 <color=#5A3E00><b>금화 +{0}</b></color> 획득.\n현재 수입: <color=#5A3E00><b>금화 +{1}</b></color>.'}
source_map.update({norm(k):v for k,v in extra.items()});save(WORK/'source_map.json',source_map)
assets=json.loads((EXTRACT/'strings.json').read_text());direct=[]
for r in assets:
 if r['field'] not in ['/m_text','/m_Text']:continue
 target=source_map.get(norm(r['source']))
 if target and target!=r['source']:direct.append(dict(r,target=target))
save(WORK/'direct_translation.json',direct)
code=[]
for r in json.loads((EXTRACT/'code_strings.json').read_text()):
 s=r['source'];m=r['method'];t=None
 if 'GameLanguageMeta::.cctor' in m:t={'pt-BR':'ko','Brazilian Portuguese':'Korean','Português (BR)':'한국어'}.get(s)
 elif 'LocalizationManager::LoadSavedCode' in m or 'SettingsPlayerData/SettingsDataObject::.ctor' in m:
  if s=='en':t='ko'
 elif any(z in m for z in ['GetDynamicDescription','GetCustomTooltipText','BasicInkExample::RefreshView']):t=source_map.get(norm(s))
 elif any(z in c for c in r['context'] for z in ['Loc::','TMP_Text::set_text']):
  if s in extra:t=extra[s]
 if t and t!=s:code.append(dict(method=m,offset=r['offset'],source=s,target=t))
save(WORK/'code_translation.json',code)
print('표',len(ko),'직접 표시',len(direct),'코드',len(code))
