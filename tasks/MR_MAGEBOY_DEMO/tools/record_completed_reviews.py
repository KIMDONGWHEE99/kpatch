"""이미 끝낸 c06 판독 결과만 기록한다. 화면·게임·새 덤프를 조사하지 않는다."""
import hashlib
import json
from pathlib import Path

from pck_tools import WORK


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


stage = WORK / 'ko_1.0.0_c06'
events = {event['id']: event for event in read(stage / 'screens.json')}
info = read(stage / 'runtime_info.json')
boundary = read(stage / 'independent_boundary.json')
prior = {row['id']: row for row in read(WORK / 'ko_1.0.0_c04/visual_review_skills.json')['entries']}
sheets = read(stage / 'review_sheets/skills/index.json')
sheet_by_id = {row['id']: sheet for sheet in sheets for row in sheet['source_captures']}

# 이 60개는 기록 작성 전에 새 검수판 11페이지에서 모두 육안으로 읽었다.
reviewed = '''001 002 003 004 007 008 012 013 016 017 018 026 027 032 055 059 063 077 081 085
089 090 092 093 095 101 102 103 111 112 118 121 147 148 156 157 158 159 160 169 173
189 198 199 208 211 212 213 215 216 218 220 244 245 247 248 249 250 251 252'''.split()
reopened = {'013', '032', '089', '090', '118', '212', '220', '245', '249'}
previously_obscured = {'032', '089', '090', '118'}
numeric_notes = {'092', '093', '199', '216'}
entries = []
for number in reviewed:
    ident = 'skill_' + number
    event = events[ident]
    sheet = sheet_by_id[ident]
    tip_texts = {Path(row['path']).name: row['text'] for row in event['texts'] if '/ToolTip/' in row['path']}
    labels = {'title': tip_texts['Title'], 'description': tip_texts['Description'], 'upgrade': tip_texts['UpgradeValue']}
    reason = '새 c06 검수판에서 제목·본문의 한글 획, 숫자, 색상 구간, 문장 끝을 모두 읽었다. 태그 노출·본문 잘림·제목 가림은 없다.'
    if number in previously_obscured:
        reason = '새 c06 검수판과 원본 PNG를 모두 읽었다. 이전 상태창에 가렸던 제목 전체가 선명하게 보이고, 본문·숫자·색상 구간도 잘리지 않는다.'
    elif number in {'013', '212', '220'}:
        reason = '검수판의 자동 잘라내기가 일부 문구를 덜 보여 원본 PNG를 추가로 읽었다. 실제 화면에서는 전체 문장과 수치가 완전하게 보인다.'
    elif number in {'245', '249'}:
        reason = '긴 설명의 새 검수판과 원본 PNG를 모두 읽었다. 상태창보다 설명창이 앞에 보이며 제목·조건문·문장 끝이 가려지지 않는다.'
    content_note = '설명과 강화 수치의 차이는 원본 설명/계산 배열에서도 존재한다. 원문 숫자와 계산을 유지한 별도 기록에 연결한다.' if number in numeric_notes else ''
    entries.append({
        'id': ident, 'status': 'PASS', 'reason': reason, 'content_note': content_note,
        'labels': labels, 'image': event['image'], 'image_sha256': event['sha256'],
        'event_sha256': hashlib.sha256(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'review_sheet': sheet['path'], 'review_sheet_sha256': sheet['sha256'],
        'review_sheet_source_sha256': next(row['sha256'] for row in sheet['source_captures'] if row['id'] == ident),
        'original_png_reopened': number in reopened,
        'original_source_positions': prior[ident]['original_source_positions'],
        'layout': event['detail']['tooltip_layout'],
        'checks': dict.fromkeys(['glyphs', 'raw_tag_exposure', 'description_clipping', 'title_readability', 'conditions_context', 'viewport_margin'], 'PASS')
    })

# 기존 중복 사건은 지우지 않고 마지막 60개 사건의 검토용 복사본만 만든다.
snapshot = stage / 'independent_reviews/visual_skills_events.json'
save(snapshot, [events['skill_' + number] for number in reviewed])
report = {
    'status': 'PASS', 'candidate': 'ko_1.0.0_c06',
    'scope': '새 c06 실제 GPU 기술 툴팁 60개를 검수판 11페이지에서 전수 육안 판독했고, 제목 가림 또는 자동 잘라내기 의심 9개는 원본 PNG도 추가 판독했다. 이전 c04 판정을 재사용하지 않았다.',
    'candidate_pck_sha256': boundary['candidate_pck_sha256'], 'qa_pck_sha256': info['qa_pack'],
    'runtime': info, 'runtime_info_sha256': sha(stage / 'runtime_info.json'),
    'event_snapshot': str(snapshot), 'event_snapshot_sha256': sha(snapshot),
    'event_policy': 'screens.json의 id별 마지막 사건 사용. 각 캡처 SHA와 해당 사건 SHA를 기록한다.',
    'source_reference_policy': '원문 위치·원본 자산 해시는 동일 고정 원본의 참조 자료이며, 육안 판정은 전부 새 c06 화면으로 수행했다.',
    'source_captures': 60, 'review_sheet_pages': 11, 'original_png_reopened': 9, 'pass': 60, 'fail': 0,
    'geometry': {'status': 'PASS', 'viewport': [0, 0, 480, 240], 'margin': 4, 'allowed_height': 232, 'observed_max_height': 144, 'outside_margin': 0, 'z_index': 100},
    'numeric_source_notes': str(stage / 'independent_reviews/source_runtime_notes.json'),
    'limitations': '60개 표시 설명을 판독한 범위이며 전체 회차나 모든 실제 플레이 조건을 실행 검증했다는 뜻은 아니다.',
    'entries': entries,
}
save(stage / 'visual_review_skills.json', report)

notes_path = stage / 'independent_reviews/source_runtime_notes.json'
notes = read(notes_path)
notes['scope'] = '원본 규칙 자체 설명/계산 표시 차이 4종의 보존 근거. 고정 후보 입력은 수정하지 않는다.'
if not any(row['id'] == 'skill_093' for row in notes['entries']):
    source_positions = [row for row in prior['skill_093']['original_source_positions'] if row['id'].endswith('string191')]
    block = '''id.MOVEMENT_SPEED_II: {
type.NAME: "Speed Buff II", type.DESCRIPTION: "Increases your {yellow}movement speed{yellow} by {green}15%{green}", type.TEXTURE: Rect2(1920, 960, 32, 32), 
type.REQUIRMENTS: {id.MOVEMENT_SPEED_I: 1}, type.UPGRADE_GROUP: upgrade_group.MOVEMENT_SPEED, type.UPGRADE_TYPE: upgrade_type.PERCENT, type.CURRENCY: cost_type.MONSTER_CORE_I, type.COST: [1000, 2000, 3000], type.UPGRADE_VALUE: [20, 25, 30]}, 
'''
    notes['entries'].append({
        'id': 'skill_093', 'source_entry': 'id.MOVEMENT_SPEED_II',
        'source_file': notes['entries'][0]['source_file'], 'source_file_sha256': notes['entries'][0]['source_file_sha256'],
        'source_line': 455, 'original_block': block,
        'source_description': 'Increases your {yellow}movement speed{yellow} by {green}15%{green}',
        'upgrade_value_first': 20, 'classification': 'ORIGINAL_DESCRIPTION_VALUE_DISAGREEMENT',
        'original_source_positions': source_positions,
        'decision': '원본 설명의 숫자와 원본 계산 배열을 모두 유지한다. 어느 쪽도 임의로 고치지 않는다.'
    })
for row in notes['entries']:
    event = events[row['id']]
    row['c06_image'] = event['image']
    row['c06_image_sha256'] = event['sha256']
    row['c06_labels'] = next(entry['labels'] for entry in entries if entry['id'] == row['id'])
notes['c06_visual_review'] = str(stage / 'visual_review_skills.json')
notes['c06_visual_review_sha256'] = sha(stage / 'visual_review_skills.json')
save(notes_path, notes)

# 입력 153개 대조는 이미 실행한 결과만 사용한다. 새 색상 덤프와 이미지는 열지 않는다.
native_path = stage / 'independent_native_check.json'
native = read(native_path)
save(stage / 'independent_reviews/native_check_before_stop.json', native)
native['status'] = 'NOT_RUN'
native['completion_policy'] = '사용자가 추가 검수를 중단하도록 지시하여, 기존 입력 153개 대조 결과만 반영하고 새 색상 덤프·이미지 판독·기본 OK 실행을 수행하지 않았다.'
native['input_summary'] = {'status': 'PASS', 'positions': 153, 'failures': 0, 'scope': '실제4.7.2 논리키·물리키·수식키 조합144개 및 마우스9개. 컨트롤러 전체 실제 입력 프로브는 포함하지 않는다.'}
native['color_picker_completion'] = {'status': 'NOT_RUN', 'existing_dump': str(stage / 'screens/native_color_native.json'), 'native_popup_pixels_review': 'NOT_RUN', 'new_dump_comparison': 'NOT_RUN'}
native['default_dialog_completion'] = {'status': 'NOT_RUN', 'reason': '기본 확인 버튼 명령·실제 화면은 실행하지 않았다.'}
native['missing_commands'] = ['loading_dialog']
native['pending_checks'] = ['color_picker_native_positions', 'color_picker_native_popup_pixels', 'default_ok_runtime_and_pixels']
save(native_path, native)
print(json.dumps({'skills': 'PASS', 'count': 60, 'native_input': 'PASS', 'native_remaining': 'NOT_RUN', 'source_rule_notes': 4}, ensure_ascii=False))
