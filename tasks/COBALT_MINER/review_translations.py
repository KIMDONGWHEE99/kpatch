"""별도로 읽어 교정한 결과와 형식 대조를 현재 번역 지문에 연결합니다."""
import collections
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'working_private/COBALT_MINER/translation_01'
SOURCE = ROOT / 'working_private/COBALT_MINER/investigation_20261101/classification/translation_worklist.json'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    path = OUT / 'translations.json'
    rows = json.loads(path.read_text(encoding='utf-8'))
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    assert len(rows) == len(source) == 398
    failures = []
    number_changes = []
    for index, (original, row) in enumerate(zip(source, rows)):
        if (original['source'], original['occurrences']) != (row['source'], row['occurrences']):
            failures.append({'index': index, 'kind': 'source_or_location_changed'})
        a, b = row['source'], row['translation']
        if re.findall(r'\r\n|\r|\n', a) != re.findall(r'\r\n|\r|\n', b):
            failures.append({'index': index, 'kind': 'newline_changed'})
        for pattern in [r'\[[A-Za-z]+\]', r'%(?:\d+\$)?[sdif]', r'\d+(?:\.\d+)?%', r'\$\d+(?:[.,]\d+)*(?:K)?', r'\{[^{}]*\}']:
            if collections.Counter(re.findall(pattern, a)) != collections.Counter(re.findall(pattern, b)):
                failures.append({'index': index, 'kind': 'token_changed', 'pattern': pattern})
        if '\t' in a and a.split('\t')[1:] != b.split('\t')[1:]:
            failures.append({'index': index, 'kind': 'shortcut_changed'})
        if '&' in a and '\t' in a or a.startswith('&') or a == 'Pass&word':
            old = re.findall(r'&(.)', a)
            new = re.findall(r'&(.)', b)
            if [x.lower() for x in old] != [x.lower() for x in new]:
                failures.append({'index': index, 'kind': 'mnemonic_changed'})
        old_numbers = re.findall(r'\d+(?:[.,]\d+)*(?:/\d+)?', a)
        new_numbers = re.findall(r'\d+(?:[.,]\d+)*(?:/\d+)?', b)
        if old_numbers != new_numbers:
            number_changes.append({'index': index, 'source_numbers': old_numbers, 'translation_numbers': new_numbers})
    allowed_number_changes = {99, 154, 247, 310}
    assert {x['index'] for x in number_changes} <= allowed_number_changes, number_changes
    assert not failures, failures
    report = {
        'source_worklist_sha256': sha(SOURCE), 'translation_sha256': sha(path),
        'review_date': '2026-11-01', 'reviewer': 'assistant:/root/media',
        'meaning_review_method': '398종 원문과 번역을 문맥군별로 다시 읽고 의미·부정·조건·수치를 교정. 생성기의 치환 성공 수를 교정 근거로 사용하지 않음.',
        'manual_review_sections': [
            {'indices': [0,36], 'topic': '메뉴·버튼·설정·제작진', 'status': 'PASS', 'finding': '짧은 상태어·한국어 언어명·저장/부르기/수령 동작을 구별하고 ESC 입력 표기 보존.'},
            {'indices': [37,64], 'topic': '도입 독백·자원·목표', 'status': 'PASS', 'finding': '2046년·코발트40·북/서/남 방향과 제작/장착/탑승 순서를 대조.'},
            {'indices': [65,124], 'topic': '초기 대화·도시·브레티', 'status': 'PASS', 'finding': '주인공/아나/주민의 말투 구별. $10,000/$500/$5,000 흥정과 동굴 북쪽·추가 광맥 남쪽 길 건너 조건 보존.'},
            {'indices': [125,171], 'topic': '흑연·송신탑·우주선·탈출 분기', 'status': 'PASS', 'finding': '송신탑 수리 선행조건·전체 수익 권리·MJ-1000행 약속 유지. No pickup은 무전 종료 문맥으로 통신 끝으로 해석.'},
            {'indices': [172,228], 'topic': '시설·강화·저장·수치', 'status': 'PASS', 'finding': '채굴량+1·10/15%·저장한도100/200/400/800·전력10·패널0~8/8 대조. 저장량 증가100의 모호함을 저장 한도100으로 교정. 원본 강화 설명 결함은 별도 기록.'},
            {'indices': [229,248], 'topic': '세계관 기록', 'status': 'PASS', 'finding': '2034/2041·시간당/일주일 소비 비교·부정문과 기업의 냉소적 논리를 대조. HX-9 하베스터·헬리옥스 도미니언 통일.'},
            {'indices': [249,279], 'topic': '주민 짧은 대사', 'status': 'PASS', 'finding': '물 배급·실종·더위·광맥 신고 경고의 의미 보존. 영어 감탄사를 자연스러운 한국어로 교체.'},
            {'indices': [280,308], 'topic': '채무·송신탑·사슴 조각상·상점', 'status': 'PASS', 'finding': '일반 빚과 탈출 자금 구별. +$25K 순수 수치 보존, 기회는 탈출 기회로 명확화. $2/s·$100.000·$50.000 값과 원문 형식 유지.'},
            {'indices': [309,325], 'topic': '우주선 이동·결말', 'status': 'PASS', 'finding': '15분/30분·떠난 직후 식민지 파괴·자원 고갈 뒤 자유의 인과관계를 대조. 결말별 독백 시제와 문체 통일.'},
            {'indices': [326,339], 'topic': '실행 중 버튼 문구', 'status': 'PASS', 'finding': '정적 버튼과 같은 채굴기·태양광·자원·수익·저장 용어 사용. +75% 유지.'},
            {'indices': [340,397], 'topic': '엔진 메뉴·오류·키 설정', 'status': 'PASS', 'finding': '단축키·가속키·%d·ESC와 실제 키 이름 보존. 키 명칭에는 한국어 설명을 붙이고 방향은 한글화.'},
        ],
        'glossary': {'Cobalt': '코발트', 'Lithium': '리튬', 'Graphite': '흑연', 'Battery': '배터리', 'Big Battery': '대형 배터리',
                     'Parts/Part': '부품', 'Component': '구성품', 'Electricity': '전력', 'Energy': '에너지', 'Stamina': '기력',
                     'Drill': '채굴기', 'Furnace': '용광로', 'Storage': '창고', 'Radio mast/tower': '송신탑',
                     'Ana': '아나', 'Bretty': '브레티', 'Miner 404': '광부 404', 'Heliox': '헬리옥스',
                     'Heliox Dominion': '헬리옥스 도미니언', 'HX-9 Harvester': 'HX-9 하베스터', 'CHANCE': '탈출 기회'},
        'numeric_word_renderings': [
            {'index': 99, 'source': 'A ton / Twelve', 'translation': '1톤 / 12개'},
            {'index': 154, 'source': 'zero', 'translation': '0'},
            {'index': 247, 'source': 'zero / Zero', 'translation': '0 / 0'},
            {'index': 310, 'source': 'fifteen minutes', 'translation': '15분'},
        ],
        'interpretation_notes': [
            {'index': 150, 'note': '원문 No pickup은 자연스러운 영어가 아니며, 자료 회수 완료를 알리는 무전 끝 문맥과 부모 검토에 따라 통신 끝으로 해석.'},
            {'index': 296, 'note': '관련 대화의 MJ-1000행·자유 약속을 근거로 CHANCE를 탈출 기회로 교정. 기계는 탈출 자금 납부기.'},
            {'index': 177, 'note': '원본 설명은 회복과15%를 언급하지만 원시 이벤트840/11/32/33/13상 강화는 소모만 감소. 원문 설명을 번역하며 게임 규칙은 바꾸지 않음. 원본 설명 결함은 실제 검수 보고에 남길 것.'},
        ],
        'preserved_text': [{'index':295, 'source':'+$25K', 'reason':'언어 없는 금액 표시. 수치·기호 보존.'}],
        'automatic_format_checks': {'status':'PASS', 'failures':failures, 'numeric_changes':number_changes},
        'meaning_review': 'PASS', 'runtime_review': 'NOT_RUN',
        'scope': '현재 지문 번역의 원문 대조·교정. 실제 줄맞춤·작은 글자·대화 표시 검수는 포함하지 않음.'
    }
    (OUT / 'translation_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'review_status':'PASS','translation_sha256':sha(path),'numeric_word_renderings':number_changes},ensure_ascii=False))

if __name__ == '__main__':
    main()
