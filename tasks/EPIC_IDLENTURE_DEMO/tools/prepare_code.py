"""실행 중 표시 문구를 위치별로 번역하고 저장 식별자와 분리합니다."""
from common import *
import re
code=json.loads((EXTRACT/'code_strings.json').read_text(encoding='utf8'))
translations={73:'<nobr>피해 <color=red>',76:'명',77:'명',78:', <nobr>공격 대상 <color=yellow>{0}{1}</color></nobr>',79:', <nobr>대기시간 <color=yellow>{0}</color></nobr>',80:', <nobr>사거리 <color=yellow>{0}</color></nobr>',85:'계산식: ',86:'피해 {1}의 {0}%',165:'정지',166:'자동',187:'반격',188:'추가 공격',189:'반사: ',190:'+턴',202:'사망',203:'회피',204:'막기',205:'치명타: ',337:'피해 ???',338:'위력 ???%.',339:'{0} {1}레벨',340:'위력 {0}%.',342:' </size><size=24>피해',344:'{0} {1}/{2}레벨',346:'최대',348:'{0} {1}레벨',349:'최대',358:'몬스터',453:'레벨 {0}',516:'소켓 ',520:'\n<color=grey>더블 클릭하거나 빈 칸으로 끌어다 놓으면 장착합니다.\n오른쪽 클릭하면 판매합니다.</color>',521:'{0}레벨',529:'{0}등급 - {1} {2}/{3}',530:'목걸이',531:'갑옷',532:'장화',533:'장갑',534:'망토',535:'목걸이',536:'반지',540:'특성',541:'대장간',542:'연구',543:'기술 도감',544:'알 수 없음',603:'설정을 유지하려면 적용을 누르세요 ({0})',646:'+보석',647:'소지품 가득 참',648:'+장비',652:'{0} 해금!',705:' {0}턴',706:'화상: ',707:'빙결: ',762:'구매',763:'구매',764:'최대',765:'보유',766:'구매',767:'구매',768:'강화',769:'강화'}
save(WORK/'code_translation.json',[dict(code[i],target=t) for i,t in translations.items()])
catalog=json.loads((WORK/'translation.json').read_text(encoding='utf8'));lookup={r['source']:r['target'] for r in catalog}
labels={s:lookup[s] for s in ['Charge','Bash','Cleave','Fireball','Magic Missiles','Potion','Caltrops','Hook','Whirlwind']}
labels.update({'None':'없음','Hero':'영웅','Death':'죽음','Jelly':'젤리','JellyKing':'젤리 왕','Unknown':'알 수 없음','Stun':'기절','Burning':'화상','CantMove':'이동 불가','ExtraAttack':'추가 공격','Frozen':'빙결','HP':'체력','DMG':'피해'})
enums={int(v):k for k,v in re.findall(r'^\s*(\w+)\s*=\s*(-?\d+)',(EXTRACT/'code/UnlockableType.cs').read_text(encoding='utf8'),re.M)}
occurrences=json.loads((WORK/'translation_occurrences.json').read_text(encoding='utf8'))
row=next(r for r in occurrences if r['field']=='/Unlocks/_serializedList/0/Value/DisplayName')
t=json.loads((EXTRACT/'trees'/f"{row['file']}_{row['path_id']}.json").read_text(encoding='utf8'))
for entry in t['Unlocks']['_serializedList']:
    key=enums[entry['Key']];labels[key]=lookup[entry['Value']['DisplayName']]
save(WORK/'runtime_labels.json',labels)
print('코드 번역',len(translations),'표시 이름',len(labels))
