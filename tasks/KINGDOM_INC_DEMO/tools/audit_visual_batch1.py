"""직접 연 이미지 5장의 육안 판정과 보조 자료 지문을 기록합니다."""
from common import WORK, sha, write_json
from datetime import datetime, timezone
from PIL import Image
import json

QA = WORK / "full_rc3" / "qa_full_rc3"
findings = {
    "225651_1160000_tech": {
        "status": "FAIL",
        "observed_screen": "기술 계통도",
        "translation": "PASS",
        "glyphs": "PASS",
        "clipping": "PASS",
        "overlap": "FAIL",
        "coverage": "PASS",
        "observations": [
            "중앙 아이템 상점·제련소 카드의 제목과 설명, 무료!, 새 업그레이드 가능!을 직접 판독했습니다.",
            "아이템 상점 설명의 끝부분이 오른쪽 상점 그림의 왼쪽 부분과 겹칩니다. 대략 x702~730, y314~326 영역입니다.",
            "제련소 설명은 그림 왼쪽에서 끝나 겹치지 않습니다. 한글 네모·빈 글리프·깨진 자모는 보이지 않습니다.",
            "좌우 가장자리의 인접 카드는 기술 계통도 화면 밖으로 이어지는 상태입니다. 그 부분을 해당 카드 내부의 글자 잘림으로 판정하지 않았습니다.",
        ],
        "defect_ids": ["V01"],
    },
    "225653_1729700_tech_list": {
        "status": "FAIL",
        "observed_screen": "기술 계통도",
        "translation": "PASS",
        "glyphs": "PASS",
        "clipping": "PASS",
        "overlap": "FAIL",
        "coverage": "FAIL",
        "observations": [
            "파일 이름은 tech_list이지만, 실제 픽셀에는 노드들이 선으로 연결된 기술 계통도가 보입니다. 목록 형태의 기술 창은 없습니다.",
            "아이템 상점과 제련소 설명을 판독했으며, 앞 캡처와 같은 상점 설명·그림 겹침이 보입니다.",
            "이 캡처는 기술 목록 화면을 실제 확인했다는 근거로 사용할 수 없습니다.",
        ],
        "defect_ids": ["V01", "V02"],
    },
    "225654_4891700_tech_tooltip": {
        "status": "FAIL",
        "observed_screen": "기술 계통도와 대장간 도움말",
        "translation": "PASS",
        "glyphs": "PASS",
        "clipping": "PASS",
        "overlap": "FAIL",
        "coverage": "PASS",
        "observations": [
            "왼쪽 아래 도움말의 대장간, 주로 금속을 사용하는 다양한 아이템을 제작합니다., 비용:, 재화 8·70을 직접 판독했습니다.",
            "도움말 자체의 글자는 선명하고 테두리 안에 들어갑니다. 설명과 비용 행 사이에 간격이 있으며 서로 겹치지 않습니다.",
            "도움말의 아래 테두리가 화면 하단 가까이 있으나 가격 아이콘·숫자·테두리를 모두 확인할 수 있습니다.",
            "배경의 아이템 상점 카드에는 V01의 설명·그림 겹침이 그대로 남아 있어 화면 전체 판정은 FAIL입니다. 도움말 자체의 시각 판정은 PASS입니다.",
        ],
        "tooltip_only_status": "PASS",
        "defect_ids": ["V01"],
    },
    "225657_2490800_node": {
        "status": "PASS",
        "observed_screen": "작업장에 배치된 제련소·광산",
        "translation": "PASS",
        "glyphs": "PASS",
        "clipping": "PASS",
        "overlap": "PASS",
        "coverage": "PASS",
        "observations": [
            "제련소·광산 이름표와 제련 버튼을 직접 판독했습니다.",
            "이름표와 버튼의 한글은 테두리 안에서 표시되며 아이콘과 겹치지 않습니다.",
            "네모 글리프, 잘린 자모, 영문 잔존은 보이지 않습니다.",
            "이 판정은 화면에 보이는 두 시설과 버튼에 한정합니다.",
        ],
        "defect_ids": [],
    },
    "225659_9866700_resource_select": {
        "status": "PASS",
        "observed_screen": "자원 선택 창",
        "translation": "PASS",
        "glyphs": "PASS",
        "clipping": "PASS",
        "overlap": "PASS",
        "coverage": "PASS",
        "observations": [
            "자원 선택, 철광석, 공급량: 초당 1.0 | 전체 수요: 초당 0.0을 직접 판독했습니다.",
            "제목·자원 이름·수치가 각각의 영역 안에 들어가고, 강조된 수치도 선명합니다.",
            "네모 글리프·한글 잘림·텍스트 겹침은 보이지 않습니다.",
            "하단에는 빈 장식 행들이 보이며 이 화면에 나타나지 않은 다른 자원은 확인한 것으로 처리하지 않습니다.",
        ],
        "defect_ids": [],
    },
}

records = []
for stem, finding in findings.items():
    image_path = QA / (stem + ".png")
    text_path = QA / (stem + ".json")
    context_path = QA / (stem + ".context.json")
    with Image.open(image_path) as image:
        dimensions = list(image.size)
    data = json.loads(text_path.read_text(encoding="utf-8"))
    overflows = [row for row in data["texts"]
                 if row.get("active") and row.get("onScreen") and row.get("overflow")]
    shop = [row for row in data["texts"] if row.get("active") and row.get("onScreen")
            and "대부분의 아이템을 시장에서 적정 가격에 판매합니다." == row.get("text")]
    records.append({
        "filename": image_path.name, "path": str(image_path), "sha256": sha(image_path),
        "dimensions": dimensions,
        "viewed_with": "functions.view_image(detail=original)",
        "visually_opened": True,
        **finding,
        "supplementary_evidence": {
            "text_capture": {"path": str(text_path), "sha256": sha(text_path)},
            "context_capture": {"path": str(context_path), "sha256": sha(context_path)},
            "active_on_screen_overflow_count": len(overflows),
            "active_on_screen_overflows": overflows,
            "shop_description_object": shop,
            "interpretation": (
                "텍스트 배열은 육안 판독의 보조 근거입니다. 상점 설명은 overflow=false여도 그림과 겹칩니다. "
                "도움말의 overflow=true 3개는 높이 1인 텍스트 영역에서 보고되지만 실제 이미지의 도움말은 읽히며 잘리지 않습니다. "
                "visibleCharacters의 공백 제외 가능성을 고려하여 차이를 곧바로 누락 글자로 보지 않았습니다."
            ),
        },
    })
report = {
    "status": "FAIL",
    "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
    "reviewer": "source_audit",
    "candidate": "full_rc3",
    "scope": "지정된 원본 PNG 5장을 실제로 열어 판독한 결과입니다. 게임을 조작하지 않았으며 다른 화면의 완료를 주장하지 않습니다.",
    "images_opened": 5, "pass_count": 2, "fail_count": 3,
    "records": records,
    "defects": [
        {"id": "V01", "status": "FAIL", "category": "텍스트·그림 겹침",
         "screens": list(findings)[:3],
         "source_key": "shop_desc",
         "source_text": "Sells most items on the open market for a fair price.",
         "current_translation": "대부분의 아이템을 시장에서 적정 가격에 판매합니다.",
         "observation": "기술 카드 오른쪽 그림 위로 설명 끝부분이 올라옵니다.",
         "suggested_action": "의미를 유지하는 짧은 문장으로 다듬거나 그림을 피하도록 설명 영역을 조정하고, 같은 종류의 기술 카드 전체를 재검토하세요."},
        {"id": "V02", "status": "FAIL", "category": "필수 화면 확보 실패",
         "screens": ["225653_1729700_tech_list"],
         "observation": "목록 화면이 아니라 기술 계통도만 보입니다.",
         "suggested_action": "기술 목록 보기가 실제로 열린 상태를 새로 캡처하여 육안 검토해야 합니다."},
    ],
    "not_claimed": ["기술 목록 확인 완료", "모든 기술 카드 검수", "후보 전체 시각 검수 완료", "배포 가능"],
}
write_json(WORK / "audit" / "visual_batch1.json", report)
print(json.dumps({"status": report["status"], "images_opened": 5,
                  "pass": 2, "fail": 3, "defects": ["V01", "V02"]}))
