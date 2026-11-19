"""번역별 실제 장면·표시 조건·글꼴 폭을 묶어 검수 순서를 만듭니다."""
from __future__ import annotations
import argparse
import importlib.util
import json
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path
from PIL import ImageFont

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('cobalt_validation', Path(__file__).with_name('validate_candidate.py'))
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)

def wrap_lines(font, text, width):
    """줄바꿈 가능 지점의 추정치입니다. 실제 Fusion 배치 판정으로 사용하지 않습니다."""
    result = []
    for explicit in re.split(r'\r\n|\r|\n', text):
        line = ''
        for token in re.findall(r'[A-Za-z0-9_]+|[^A-Za-z0-9_]', explicit):
            if line and font.getlength(line + token) > width:
                result.append(line.rstrip())
                line = token.lstrip()
            else:
                line += token
        result.append(line)
    return result

def build(candidate_id, output):
    candidate = ROOT / 'build_candidate/COBALT_MINER' / candidate_id
    dat = validation.DatFile.load(candidate / 'COBALT MINER.dat')
    package = validation.load(ROOT / 'extracted_private/COBALT_MINER/steam_24347666/nebula_01/package.json')
    plan = validation.load_plan()
    links = [json.loads(s) for s in (validation.CLASSIFICATION / 'event_links.jsonl').read_text(encoding='utf-8').splitlines()]
    by_object = defaultdict(list)
    for row in links:
        by_object[row['object_handle']].append(row)
    instances = defaultdict(list)
    for fi, frame in enumerate(package['Frames']):
        for row in frame['FrameInstances']['Instances']:
            instances[row['ObjectInfo']].append(dict(frame=fi, frame_name=frame['FrameName'], x=row['PositionX'], y=row['PositionY'], layer=row['Layer']))
    fonts = {row.handle: row.decoded for row in dat.fonts}
    cache, records = {}, []
    for row in plan.values():
        record = dict(location=row['location'], kind=row['kind'], source=row['source'], translation=row['translated'],
                      source_file_sha256=row['source_file_sha256'], source_container_sha256=row['source_container_sha256'],
                      graphics_status='NOT_RUN')
        handle = row.get('object_handle')
        if handle is None:
            record.update(screen_group='Windows 메뉴/표준 대화상자', control_context=row.get('control_context'),
                          command_id=row.get('command_id'), clipping_risk='WINDOWS_DIALOG_QA',
                          risk_reason='Windows 대화상자 단위 좌표와 시스템 글꼴/배율을 실제 창에서 확인해야 함')
            records.append(record)
            continue
        obj = package['FrameItems']['Items'][str(handle)]
        object_rows = by_object[handle]
        frame_rows = instances[handle]
        if 'frame' in row:
            frame_rows = [x for x in frame_rows if x['frame'] == row['frame']]
        related = [x for x in object_rows if 'Reappear' in x['display'] or 'Set position' in x['display'] or 'Display paragraph' in x['display']]
        if row['kind'] == 'paragraph':
            specific = [x for x in related if re.search(r' : Display paragraph ' + str(row['paragraph']) + r'$', x['display'])]
        else:
            specific = []
        record.update(object_handle=handle, object_name=obj['Name'], paragraph=row.get('paragraph'),
                      frames=sorted(set(x['frame'] for x in frame_rows)), initial_instances=frame_rows,
                      selected_paragraph_events=specific, visibility_and_position_events=related)
        if row['kind'] == 'paragraph':
            selection = [x for x in object_rows if x['type'] == 3 and x['num'] == 84 and x['kind'] == 'Actions']
            no_qualifier = all(x == -1 for x in obj['Properties']['Qualifiers'])
            if row['paragraph'] > 0 and not selection and no_qualifier:
                record['runtime_usage'] = 'SPARE_PARAGRAPH_NO_SELECTOR'
                record['runtime_usage_reason'] = '전체17장면에 해당 객체의 문단 선택 명령0, 그룹 선택자도 없음. 초기 문단0과 구분한 복제 예비 문단이며 강제 표시 검수는 일반 진행 증거와 분리'
            elif specific:
                record['runtime_usage'] = 'EXPLICIT_PARAGRAPH_SELECTOR'
            elif selection:
                record['runtime_usage'] = 'DYNAMIC_OR_INITIAL_PARAGRAPH'
            else:
                record['runtime_usage'] = 'INITIAL_PARAGRAPH'
        else:
            record['runtime_usage'] = 'BUTTON_OR_EVENT_DISPLAY'
        if record['frames']:
            record['screen_group'] = ' / '.join(package['Frames'][x]['FrameName'] for x in record['frames'])
        else:
            record['screen_group'] = '배치 인스턴스 없이 이벤트로 생성/접근하는 객체: 추가 실행 확인'
        if row['kind'] == 'paragraph':
            paragraph = obj['Properties']['ObjectParagraphs']
            width, height = paragraph['Width'], paragraph['Height']
            logfont, offset = fonts[row['font']], 12
            record['font_handle'] = row['font']
            record['paragraph_flags'] = paragraph['Paragraphs'][row['paragraph']]['ParagraphFlags']['Value']
        else:
            raw = dat.objects[handle].decoded
            blob = struct.unpack_from('<H', raw, 12)[0] + 20
            width, height = struct.unpack_from('<HH', raw, blob)
            logfont, offset = raw, blob + 36
        pixel_height = abs(struct.unpack_from('<i', logfont, offset)[0])
        weight = struct.unpack_from('<I', logfont, offset + 16)[0]
        key = weight, pixel_height
        if key not in cache:
            cache[key] = ImageFont.truetype(str(validation.FONT_DIR / f'CobaltNotoSansKR-{weight}.ttf'), pixel_height)
        font = cache[key]
        line_height = sum(font.getmetrics())
        explicit = re.split(r'\r\n|\r|\n', row['translated'])
        maximum = max(font.getlength(x) for x in explicit)
        wrapped = wrap_lines(font, row['translated'], width)
        estimated_height = len(wrapped) * line_height
        if row['kind'] in {'button_text', 'event_string'}:
            risk = 'HIGH' if maximum > width - 8 or len(explicit) * line_height > height else 'LOW_ESTIMATE'
        else:
            risk = 'HIGH' if estimated_height > height else 'MEDIUM' if estimated_height >= height * 0.85 or maximum > width else 'LOW_ESTIMATE'
        record.update(box_width=width, box_height=height, font_pixel_height=pixel_height, font_weight=weight,
                      max_explicit_line_width=round(maximum, 2), estimated_wrapped_lines=wrapped,
                      estimated_line_height=line_height, estimated_total_height=estimated_height,
                      clipping_risk=risk,
                      risk_reason='FreeType 글리프 폭/줄높이의 보수적 추정. Fusion 자동 줄바꿈·GDI 높이·실제 배율은 캡처로 최종 판정')
        records.append(record)
    groups = defaultdict(list)
    for row in records:
        groups[row['source']].append(row['location'])
    fixture_commands = []
    for frame, name in enumerate(package['Frames']):
        translated = [r['location'] for r in records if frame in r.get('frames', [])]
        if not translated and frame not in (2, 3, 4, 7):
            continue
        mode = 'menu' if frame == 2 else 'settings' if frame == 3 else 'newgame' if frame == 7 else 'frame'
        command = f'python tasks/COBALT_MINER/qa_fixture.py --input "build_candidate/COBALT_MINER/{candidate_id}/COBALT MINER.dat" --output working_private/COBALT_MINER/qa_fixtures/{candidate_id}_frame_{frame:02d} --mode {mode}'
        if mode == 'frame':
            command += f' --entry-frame {frame}'
        fixture_commands.append(dict(frame=frame, name=name['FrameName'], mode=mode, command=command,
                                     translated_locations=translated, runtime_status='NOT_RUN',
                                     limitation='정해진 장면 진입만 확인. 해당 장면의 대화 전체 분기·게임 진행 조건을 통과했다는 증거 아님'))
    result = dict(status='PASS', candidate_id=candidate_id, candidate_dat_sha256=validation.sha(dat.original),
                  translation_sha256=validation.sha(validation.TRANSLATIONS.read_bytes()),
                  tool_sha256=validation.sha(Path(__file__).read_bytes()),
                  unique_sources=len(groups), positions=len(records), risk_counts=dict(Counter(r['clipping_risk'] for r in records)),
                  fixture_commands=fixture_commands, full_graphics_review='NOT_RUN',
                  limitations=['기본 배치는 런타임 상대 위치 이동 전 좌표일 수 있음. 표시 이벤트와 조건을 함께 확인',
                               '한글 폰트 폭 추정은 실제 화면 검수를 대체하지 않음',
                               '결과 장면11~16은 두 결말의 세 장면씩이며 결과표 형식은 아님',
                               '본편 Escape event218은 저장 뒤 Main Menu로 이동. 별도 일시정지 문구는 Windows 메뉴 command1012로 제공'])
    output = output.resolve()
    if not output.is_relative_to(validation.WORK) or output.exists():
        raise ValueError('새 비공개 검수 계획 경로만 허용')
    output.mkdir(parents=True)
    for name, value in [('screen_plan.json', result), ('position_map.json', records), ('unique_source_map.json', dict(groups))]:
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    high = [r for r in records if r['clipping_risk'] == 'HIGH']
    (output / 'high_risk.json').write_text(json.dumps(high, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('positions', 'unique_sources', 'risk_counts')}, ensure_ascii=False))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-id', default='ko_candidate_01')
    parser.add_argument('--output', type=Path, default=validation.WORK / 'qa_screen_plan_01')
    args = parser.parse_args()
    build(args.candidate_id, args.output)
