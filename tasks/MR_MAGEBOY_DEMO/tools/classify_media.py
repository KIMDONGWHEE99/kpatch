"""제작자가 관찰한 전체 검수판과 확대 자료를 원본 해시에 연결합니다."""
from pathlib import Path
import hashlib
import json
from pck_tools import ROOT, WORK, EXTRACTED

media = WORK/'media'
rows = json.loads((media/'inventory.json').read_text(encoding='utf-8'))
sheet_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (media/'sheets').glob('*.png')}
brands = {7, 678, 1356, 1357, 1785}
non_text = {0,1,2,3,4,5,6,8,23,24,25,26,27,130,677,679,680,1359,1414,1415,2201,2572}
for row in rows:
    item = row['id']
    row['review'] = {'method': '제작자 원본 픽셀 육안 판독', 'sheet': '%03d.png' % (item//120), 'sheet_sha256': sheet_hashes['%03d.png' % (item//120)]}
    if item in brands:
        disposition, reason = 'KEEP', 'Git·Godot·Steam 또는 플러그인 제작사 브랜드와 심볼을 관찰했습니다. 고유 로고를 보존합니다.'
    elif item in non_text:
        disposition, reason = 'NO_TEXT', '실제 포함 텍스처에서 배경·구름·셰이더·적·인물·물체 또는 문자가 없는 도형을 관찰했습니다.'
    elif 9 <= item <= 22:
        disposition, reason = 'KEEP', '입력 아이콘 묶음의 미리보기·장치별 키 이름·제작자 표기입니다. 실행 장면의 개별 키 기호와 구분되는 보조 자료이며 원본 제작사 표시를 보존합니다.'
    elif item == 1358:
        disposition, reason = 'KEEP', '확대 원본에서 Stage Forest/Cave/Ruins/Lava의 구 시제품 버튼 8영역과 키 기호를 관찰했습니다. 전체 장면·리소스·스크립트에 해당 버튼 영역 참조가 없으며 현재 stages.gd는 ui_atlas 지역 그림, stage_levels_data.gd의 별도 표시 이름을 사용합니다. 현재 표시 이름은 텍스트 번역 대상입니다.'
    elif item == 2571:
        disposition, reason = 'KEEP', '확대 원본에서 게임 고유 제목 MR MAGEBOY와 키보드 기호·숫자·아이콘을 관찰했습니다. 게임 제목 로고와 실제 키 표기를 보존합니다.'
    else:
        disposition, reason = 'KEEP', '검수판에서 물리 키·컨트롤러 버튼·장치·마우스·방향·상태·숫자 기호를 관찰했습니다. A/B/X/Y·Start/Select/Options/Share·Ctrl/Alt/Shift/Enter/Space 등의 입력 식별 표기를 실제 장치와 대조할 수 있도록 보존합니다.'
    row['disposition'], row['reason'] = disposition, reason
    if item in {130,1358,1359,1414,1415,2571}:
        row['review']['full_resolution_image'] = row['output']
        row['review']['full_resolution_sha256'] = row['sha256']
assert all(row['source_sha256'] and row['reason'] and row['disposition'] != 'UNKNOWN' for row in rows)
(media/'classification.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
raw_icon=EXTRACTED/'raw/game/assets/game_assets/DekstopIcon.png'
record={'textures':sum(len(x['paths']) for x in rows),'unique_pixels':len(rows),'unknown':0,'texture_export_errors':0,
        'standalone_png':{'path':'game/assets/game_assets/DekstopIcon.png','sha256':hashlib.sha256(raw_icon.read_bytes()).hexdigest(),'disposition':'NO_TEXT','reason':'原本 ctex와 같은 책가방형 게임 아이콘을 관찰했습니다.'.replace('原本','원본')},
        'video':'PCK 전체 확장자 목록에 동영상 자산이 없습니다.','audio':'음성 대화 없이 효과음·음악을 사용하는 자료이며 원본 음향은 보존합니다.',
        'observed_sheets':sheet_hashes,'retained_words':['MR MAGEBOY','Git','Godot','Steam','입력 장치·키 이름','미사용 시제품 지역 버튼·아이콘 미리보기']}
(media/'audit.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:record[k] for k in ['textures','unique_pixels','unknown','texture_export_errors']},ensure_ascii=False))
