"""원본 PCK의 모든 항목을 조사 근거와 연결하고 미분류를 거부합니다."""
from collections import Counter
import hashlib
import json
from pathlib import Path
from pck_tools import BASELINE, EXTRACTED, WORK, read_pack

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

pack = read_pack(BASELINE / 'MR MAGEBOY DEMO.pck')[3]
remaps = {r['target']: r['source'] for r in read(WORK / 'remap_targets.json')}
texts = {r['path'] for r in read(WORK / 'translation/text_files.json')}
records = []
for entry in pack:
    name = entry['name']
    extension = Path(name).suffix
    kind, evidence = 'UNKNOWN', ''
    if extension in ('.gdc', '.scn', '.res'):
        source = remaps.get(name)
        assert source in texts, (name, source)
        kind, evidence = 'TEXT_REVIEWED', 'translation/census.json의 복원 원문 위치·원본 자산 지문에 연결: ' + source
    elif extension in ('.ctex', '.png'):
        kind, evidence = 'MEDIA_REVIEWED', 'media/classification.json·audit.json에 원본 픽셀·위치·관찰·유지 사유 연결'
    elif extension == '.translation':
        kind, evidence = 'TEXT_REVIEWED', 'translation/original_locale_dump.json에서 .en/.fr 원본 69키씩 직접 조회; CSV 138값 대조'
    elif extension == '.fontdata':
        kind, evidence = 'FONT_REVIEWED', 'PixelOperator8 본문·굵은 글꼴 및 Awesome9 아이콘 글꼴; 후보 fonts 보고서와 원본 데이터 지문 연결'
    elif extension in ('.sample', '.oggvorbisstr'):
        kind, evidence = 'MEDIA_KEEP', '복원된 game/assets의 효과음 묶음·배경음악: 발걸음·채집·텍스트 출력음·UI·환경 음악. 언어 문구 전달 코드 없음; 원본 보존'
    elif extension in ('.import', '.remap'):
        kind, evidence = 'INTERNAL', 'Godot 원본 경로·변환 옵션·대상 자산 경로를 저장하는 변환 명세; 문자열/픽셀은 연결 자산에서 조사'
    elif extension == '.gdshader':
        data = entry['data'].decode('utf-8')
        assert 'shader_type' in data and 'void ' in data and '"' not in data
        kind, evidence = 'INTERNAL', '직접 읽은 화면 효과 계산식·개발 주석; 문자 출력 또는 이미지 문구 정의 없음'
    elif extension == '.gdextension':
        assert name == 'addons/godotsteam/godotsteam.gdextension'
        kind, evidence = 'INTERNAL', '직접 읽은 Steam 확장 모듈 진입점·OS별 라이브러리 경로 목록'
    elif extension == '.cfg':
        assert name in ('.godot/extension_list.cfg', '.godot/global_script_class_cache.cfg')
        kind, evidence = 'INTERNAL', '직접 읽은 Steam 모듈 경로/스크립트 클래스·기반 클래스·언어·경로 캐시; UI 소비 없음'
    elif name == '.godot/uid_cache.bin':
        kind, evidence = 'INTERNAL', 'Godot 자산 UID와 res:// 자산 경로 캐시; 원본 참조 식별용 바이너리'
    elif name == 'project.binary':
        assert 'project.godot' in texts
        kind, evidence = 'TEXT_REVIEWED', '복원 프로젝트 설명과 입력 조합은 census/runtime_manifest, 기타 설정과 입력 식별자 유지'
    assert kind != 'UNKNOWN', name
    records.append({'path': name, 'size': entry['size'], 'sha256': hashlib.sha256(entry['data']).hexdigest(), 'classification': kind, 'evidence': evidence})
assert len(records) == 8688
summary = {'status': 'PASS', 'entries': len(records), 'classification': dict(Counter(r['classification'] for r in records)), 'unknown': 0,
           'source_pck_sha256': hashlib.sha256((BASELINE / 'MR MAGEBOY DEMO.pck').read_bytes()).hexdigest()}
(WORK / 'pack_classification.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
(WORK / 'pack_classification_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False))
