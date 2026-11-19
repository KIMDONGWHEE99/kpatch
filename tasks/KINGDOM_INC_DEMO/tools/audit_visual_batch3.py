"""직접 확인한 납품·아이템·인물·무기고 캡처 5장의 판독을 기록합니다."""
from common import WORK, sha, write_json
from datetime import datetime, timezone
from PIL import Image
import json

QA = WORK / "full_rc3" / "qa_full_rc3"
reviewed = {
    "230019_5668300_requisition": {
        "screen": "납품 가능한 계약",
        "observations": [
            "창 제목 납품 가능한 계약과 철 단검·거친 조끼·의장용 갑옷 세 아이템 이름을 직접 판독했습니다.",
            "아이템과 납품 증서 아이콘 사이의 등호, 보상 0.47·0.37·1.19가 각각의 행에서 구분되어 보입니다.",
            "긴 제목과 세 아이템 이름 모두 테두리 안에 들어가며 아이콘·주사위 버튼과 겹치지 않습니다.",
            "한글 네모 글리프, 잘린 자모, 영문 메뉴 잔존을 찾지 못했습니다. 하단의 빈 행은 텍스트가 표시된 항목으로 세지 않았습니다.",
        ],
    },
    "230054_9696700_item_tooltip": {
        "screen": "철검 아이템 도움말",
        "observations": [
            "도움말의 철검, 무기 - 주손·보조손 겸용, 설명 전체, 획득처: 대장간, 판매가와 재화 수치 6·39를 직접 판독했습니다.",
            "설명은 견습 기사나 초보 모험가에게 알맞은 평범한 철검입니다.로 끝까지 보이며 선행 번역과 문맥이 맞습니다.",
            "제목·장비 슬롯·설명·획득처·판매가가 서로 다른 줄에 배치되어 겹치지 않습니다.",
            "하단 판매가까지 도움말 테두리 안에서 확인됩니다. 배경의 대장간·숲·전쟁 지원·납품 사무소 및 제작·채취·교환 버튼도 한글로 표시됩니다.",
        ],
    },
    "230057_4617200_item_tooltip": {
        "screen": "병사 아이템 도움말",
        "observations": [
            "병사, 체력, 전투력, 주손 (비어 있음), 보조손 (비어 있음), 머리 (비어 있음), 몸통 (비어 있음), 음식 (비어 있음)을 직접 판독했습니다.",
            "주손의 비어 있음은 빨간색으로, 나머지 빈 슬롯은 회색으로 표시되며 각 아이콘 옆에 맞게 배치됩니다.",
            "마지막 음식 슬롯도 화면 하단과 도움말 테두리 안에 보이고 글자가 잘리지 않습니다.",
            "체력과 전투력에 표시된 0은 판독할 수 있습니다. 이 캡처만으로 검수용 인물의 능력치 생성·전투 계산이 정상인지 판정하지 않았습니다.",
        ],
    },
    "230100_7148700_character": {
        "screen": "인물 상세 정보",
        "observations": [
            "인물 상세 정보, 레벨 1 징집병, 체력 102/102, 전투력·힘·민첩·방어력·마력·지혜를 직접 판독했습니다.",
            "철검과 빈 장비 슬롯의 보조손·머리·몸통·음식·반지·목걸이·장신구·물약 이름이 각 아이콘 옆에 표시됩니다.",
            "특성: (없음), 전문화 경로:까지 창 안에서 보이며 한글·수치·아이콘이 겹치지 않습니다.",
            "상단의 Sigen von Bergheim은 사전 감사에서 유지하기로 한 생성형 고유인명입니다. 일반 UI 문구의 번역 누락으로 분류하지 않습니다.",
            "이름과 직업 줄, 체력 막대, 능력치 표, 장비 칸은 각 구역에 수용되어 잘림이나 깨진 글리프가 보이지 않습니다.",
        ],
        "visible_keep": [{
            "text": "Sigen von Bergheim",
            "classification": "VISIBLE_KEEP",
            "reason": "기존 이름 생성 음절·결합·저장 시드 연동에 따른 고유인명 유지 결정",
            "evidence": str(WORK / "audit" / "name_classification.json"),
        }],
    },
    "230105_0696400_armory": {
        "screen": "무기고 설정",
        "observations": [
            "무기고 설정, 출력 아이템:, (입력용으로 사용), 철검, 철 단검과 각 수량 x1을 직접 판독했습니다.",
            "무기고를 입력용으로 쓸지 출력할 아이템을 고를지 구분되는 문맥이며, 선택지 이름이 자연스럽습니다.",
            "창 제목과 선택지 텍스트가 테두리 안에 들어가고, 왼쪽 아이콘·오른쪽 수량과 겹치지 않습니다.",
            "x1은 수량 표현으로 유지된 기호입니다. 일반 영문 UI 단어는 보이지 않습니다.",
            "한글 네모 글리프·잘린 자모·배치 겹침을 찾지 못했습니다. 표시되지 않은 다른 무기고 옵션은 검수 범위에 포함하지 않습니다.",
        ],
    },
}
records = []
for stem, review in reviewed.items():
    image_path = QA / (stem + ".png")
    text_path = QA / (stem + ".json")
    context_path = QA / (stem + ".context.json")
    with Image.open(image_path) as image:
        dimensions = list(image.size)
    data = json.loads(text_path.read_text(encoding="utf-8"))
    overflows = [row for row in data["texts"] if row.get("active")
                 and row.get("onScreen") and row.get("overflow")]
    records.append({
        "filename": image_path.name, "path": str(image_path), "sha256": sha(image_path),
        "dimensions": dimensions, "status": "PASS",
        "viewed_with": "functions.view_image(detail=original)", "visually_opened": True,
        "checks": {key: "PASS" for key in
                   ("korean_readability", "clipping", "overlap", "context", "missing_translation")},
        **review,
        "supplementary_evidence": {
            "capture_json": {"path": str(text_path), "sha256": sha(text_path)},
            "context_json": {"path": str(context_path), "sha256": sha(context_path)},
            "active_on_screen_overflow_count": len(overflows),
            "active_on_screen_overflows": overflows,
            "interpretation": (
                "판정은 실제 PNG를 직접 읽은 결과입니다. 철검 도움말 7개와 병사 도움말 4개의 overflow 표시는 "
                "화면 판독으로 별도 확인했습니다. 숫자와 모든 해당 문구가 보이므로 이 표시만으로 시각 잘림 판정을 내리지 않았습니다. "
                "병사 체력 막대의 0 또한 화면에서 확인됩니다."
            ),
        },
    })
report = {
    "status": "PASS",
    "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
    "reviewer": "source_audit", "candidate": "full_rc3",
    "scope": "요청한 5장 PNG를 직접 열어 번역·글리프·잘림·겹침·문맥을 판독했습니다. 게임 조작은 하지 않았습니다.",
    "images_opened": 5, "pass_count": 5, "fail_count": 0,
    "records": records, "defects": [],
    "not_claimed": ["전체 아이템·인물 분기 검수", "전투 계산 검증", "모든 저장소 설정 검수",
                    "후보 전체 시각 검수 완료", "배포 가능"],
}
write_json(WORK / "audit" / "visual_batch3.json", report)
print(json.dumps({"status": report["status"], "images_opened": 5, "pass": 5, "fail": 0}))
