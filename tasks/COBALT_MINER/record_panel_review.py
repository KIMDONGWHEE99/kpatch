"""수동 시각 판독 결정을 실제 캡처·픽셀·번역 위치 지문에 연결합니다. 판독 자체를 자동 추정하지 않습니다."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT/'working_private/COBALT_MINER'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def pixels(path, rect=None):
    with Image.open(path) as image:
        if rect:
            x,y,w,h = rect
            image = image.crop((x,y,x+w,y+h))
        return image.convert('RGB').tobytes()


def record(source, decision_path):
    source, decision_path = source.resolve(), decision_path.resolve()
    assert source.is_relative_to(PRIVATE) and decision_path.is_relative_to(PRIVATE)
    evidence = source/'evidence'
    contact = source/'contact_complete_01'
    decisions = load(decision_path)
    manifest = load(evidence/'cycle_manifest.json')
    contacts = load(contact/'contacts.json')
    translation_path = PRIVATE/'translation_01/translations.json'
    expected = {o['location']: t for t in load(translation_path) for o in t['occurrences']}
    manifest_rows = {Path(r['output']).name:r for r in manifest['records']}
    for name, entry in manifest_rows.items():
        assert sha(evidence/name) == entry['sha256']
        with Image.open(evidence/name) as image:
            assert image.size == (1920,1080)
    panel_by_id = {p['panel']:p for p in contacts['panels']}
    decision_by_id = {p['panel']:p for p in decisions['panels']}
    assert len(decision_by_id) == len(decisions['panels'])
    rows, representative_pixels = [], {}
    for panel_id, decision in decision_by_id.items():
        panel = panel_by_id[panel_id]
        source_path, panel_path = evidence/panel['first_capture'], contact/panel['file']
        assert sha(source_path) == panel['source_sha256'] == manifest_rows[source_path.name]['sha256']
        assert sha(panel_path) == panel['display_sha256']
        assert pixels(source_path,panel['display_rect']) == pixels(panel_path)
        representative_pixels[panel_id] = pixels(source_path,panel['rect'])
        location = f"object:{decisions['object_handle']}/paragraph:{decision['paragraph']}"
        entry = expected[location]
        assert decision['observed_anchor'] in entry['translation'].replace('\n',' ')
        assert decision['status'] in ['PASS','FAIL','NOT_RUN']
        rows.append(dict(**decision,location=location,source=entry['source'],expected_translation=entry['translation'],
                         capture=panel['first_capture'],source_bmp_sha256=panel['source_sha256'],
                         panel_path=str(panel_path),panel_sha256=panel['display_sha256']))
    mapping = []
    for item in contacts['mapping']:
        if item['panel'] not in decision_by_id:
            continue
        path = evidence/item['capture']
        assert pixels(path,contacts['rect']) == representative_pixels[item['panel']]
        mapping.append(dict(capture=path.name,source_bmp_sha256=manifest_rows[path.name]['sha256'],
                            paragraph=decision_by_id[item['panel']]['paragraph'],
                            status=decision_by_id[item['panel']]['status'],basis='실제 판독한 대표 패널과 자막 영역 전체 RGB 픽셀 동일'))
    required = set(decisions['expected_paragraphs'])
    passed = {r['paragraph'] for r in rows if r['status']=='PASS'}
    observed = {r['paragraph'] for r in rows}
    missing = sorted(required-observed)
    not_passed = sorted(required-passed)
    pre = load(evidence/'prelaunch.json')
    assert sha(source/'game/COBALT MINER.dat') == pre['qa_dat_sha256']
    full_views = []
    for view in decisions.get('full_frame_reviews',[]):
        path = source/view['path']
        assert pixels(path) == pixels(evidence/view['capture'])
        full_views.append(dict(**view,sha256=sha(path),bmp_sha256=manifest_rows[view['capture']]['sha256']))
    review_status = 'FAIL' if any(r['status']=='FAIL' for r in rows) else 'PASS' if not not_passed else 'NOT_RUN'
    report = dict(status=review_status,scope=decisions['scope'],
                  review_method='비교판을 직접 열어 실제 문장을 판독한 수동 결정을 입력. 문단 번호는 실제 내용으로 연결하고 시간으로 추정하지 않음',
                  source=str(source),candidate_dat_sha256=pre['game_source_hashes']['COBALT MINER.dat'],qa_dat_sha256=pre['qa_dat_sha256'],
                  translation_sha256=sha(translation_path),decisions_sha256=sha(decision_path),
                  manifest_sha256=sha(evidence/'cycle_manifest.json'),contacts_sha256=sha(contact/'contacts.json'),
                  guard_sha256=sha(source/'qa_guard.js'),
                  evidence={name:sha(evidence/name) for name in ['prelaunch.json','rea_runtime.json','post_integrity.json'] if (evidence/name).exists()},
                  post_integrity_status=load(evidence/'post_integrity.json')['status'] if (evidence/'post_integrity.json').exists() else 'NOT_RUN',
                  capture_identity={k:manifest[k] for k in ['pid','hwnd','first_window_utc','stopped_utc']},
                  capture_count=manifest['captures'],matched_capture_count=len(mapping),
                  inspected_paragraphs=sorted(observed),passed_paragraphs=sorted(passed),missing_paragraphs=missing,
                  not_passed_paragraphs=not_passed,paragraphs=rows,captures=mapping,
                  excluded_captures=sorted(set(manifest_rows)-{m['capture'] for m in mapping}),
                  full_frame_reviews=full_views,comparison_boards={p.name:sha(p) for p in contact.glob('contact_*.png')},
                  limits=['이 문단 구간의 실제 표시 검수이며 다른 구간의 통과를 대신하지 않음',
                          '검수 전용 표시 순환이므로 원래 모든 퀘스트 분기 통과와 구별',
                          '캡처 파일 존재·경과 시간·API 성공값만으로 표시 PASS를 만들지 않음'])
    output=decision_path.parent/'screen_review.json'
    if output.exists():raise ValueError('기존 검수 보고서 덮어쓰기 금지')
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(status=report['status'],passed=len(passed),missing=missing,sha256=sha(output))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--decisions',type=Path,required=True)
    args=parser.parse_args()
    record(args.source,args.decisions)
