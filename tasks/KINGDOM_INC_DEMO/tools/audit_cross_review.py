"""네 번역표를 읽기 전용으로 교차 검토하고 수정 권고를 별도 기록합니다."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / "working_private" / "KINGDOM_INC_DEMO"
TRANSLATION = WORK / "translation"
PARTS = [TRANSLATION / f"part_{a}_{b}.json" for a, b in
         [(0, 399), (400, 799), (800, 1199), (1200, 1555)]]
SOURCE = WORK / "language_source.json"
CODE = ROOT / "extracted_private" / "KINGDOM_INC_DEMO" / "inspection" / "decompiled"
OUTPUT = WORK / "audit" / "cross_review.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


rows = [row for path in PARTS for row in read(path)]
by_index = {row["index"]: row for row in rows}
original = {row["index"]: row for row in read(SOURCE)}
assert sorted(by_index) == list(range(1556))
assert len(rows) == len(by_index)
findings = []


def add(issue_id, category, priority, reason, replacements, evidence, optional=False):
    findings.append({
        "id": issue_id,
        "category": category,
        "priority": priority,
        "status": "NOT_APPLIED",
        "optional": optional,
        "reason": reason,
        "evidence": evidence,
        "changes": [{
            "index": i, "key": by_index[i]["key"], "source": by_index[i]["source"],
            "current": by_index[i]["target"], "recommended": target,
        } for i, target in replacements.items()],
    })


quest_indices = [407, 542, 546, 550, 554, 558, 562, 568, 572, 575]
add("C01", "같은 기능 명칭", "medium",
    "의뢰 게시판과 의뢰 화면은 모두 의뢰를 사용하지만, 직업 조건과 전리품 설명은 퀘스트로 표시되어 연결이 흐려집니다.",
    {i: by_index[i]["target"].replace("퀘스트", "의뢰") for i in quest_indices},
    {"reference_indices": [255, 256, 1135, 1328, 1329, 1358, 1363]})
add("C02", "해금 조건의 지명", "medium",
    "선행 거점의 이름이 실제 전쟁 목록·던전 목록과 다릅니다. 목록의 명칭으로 맞춥니다.",
    {356: "전쟁 진행 필요: 아를링겐 유적",
     419: "필요 전쟁 진행도: 왕성 구역",
     427: "필요 전쟁 진행도: 정상 유적"},
    {"reference_indices": [1226, 1248, 1264, 1474]})
add("C03", "인물 고유명사", "low",
    "동일한 성인의 명칭을 성 일로니아로 통일합니다.",
    {1068: "성 일로니아의 유물"},
    {"reference_indices": [410, 1244, 1245]})
add("C04", "자원 명칭", "medium",
    "아이템 이름 수지와 해당 채집 기술의 송진을 맞춥니다. 원문 설명도 소나무 진액이므로 송진이 구체적으로 맞습니다.",
    {518: "송진"}, {"reference_indices": [519, 818, 819]})
add("C05", "자원 명칭", "medium",
    "벌목 해금 설명에서 통나무와 고대 통나무로 부르던 자원을 실제 아이템 이름인 연목 원목·고대목 원목에 맞춥니다.",
    {812: "연목 벌목",
     813: "벌목꾼에게 나무를 베어 연목 원목을 공급하는 법을 가르칩니다.",
     828: "고대목 벌목",
     829: "벌목꾼에게 숲에서 가장 큰 나무를 알아보고 베어 고대목 원목을 얻는 법을 가르칩니다."},
    {"reference_indices": [484, 622, 624]})
add("C06", "화면 기능 명칭", "medium",
    "복제 도구가 선택하는 대상은 작업장의 공간입니다. 생산 과정이라는 설명은 작업장 복사 동작과의 연결을 약하게 만듭니다.",
    {809: "#[C]#를 눌러 작업장의 일부를 선택하고 복사합니다."},
    {"reference_indices": [31, 125, 131, 1449, 1451, 1453]})
add("C07", "화면 기능 명칭", "low",
    "같은 Decorations 기능의 메뉴·기술·옵션 이름을 꾸미기로 통일합니다.",
    {792: "꾸미기", 1091: "꾸미기 설정"},
    {"reference_indices": [30, 124]})
add("C08", "화면 기능 명칭", "low",
    "같은 Area Move 기능의 단축키·도구 이름과 기술 이름을 영역 이동으로 통일합니다.",
    {806: "영역 이동"}, {"reference_indices": [35, 128]})
add("C09", "방어구 등급 명칭", "medium",
    "직업 조건에서 경갑·중형 방어구·중갑을 요구하지만 아이템 툴팁은 경량·중형·중량 방어구를 표시합니다. 등급과 조합 틀을 함께 바꾸어 중복 접미사를 피합니다.",
    {1128: "{0} - #{1}#", 1174: "경갑", 1175: "중형 방어구", 1176: "중갑"},
    {"reference_indices": [530, 533, 536, 731, 735, 738, 739],
     "code": [
         {"path": str(CODE / "Assets.Source.Items.Type" / "EquipmentItemType.cs"),
          "line": 145, "observation": "ArmorLine에 ArmorType.GetDisplayName()과 장비 슬롯명을 넘겨 툴팁을 조합합니다."},
         {"path": str(CODE / "Assets.Source.Items" / "ArmorTypeExtensions.cs"),
          "line": 5, "observation": "ArmorLight/Medium/Heavy의 표시 키를 반환합니다. 확인된 소비처는 위 조합 틀입니다."}]})
add("C10", "장비 슬롯 명칭", "low",
    "같은 장비 슬롯의 명칭을 주손·보조손으로 통일합니다. 보조손에는 방패도 들어가므로 보조 무기보다 슬롯명이 정확합니다.",
    {1289: "주손 #(비어 있음)#", 1290: "보조손 (비어 있음)"},
    {"reference_indices": [1166, 1167, 530, 543]})
add("C11", "환전 비용 명칭", "low",
    "환전 업그레이드는 수수료라고 설명하지만 거래 창은 환전세라고 표시합니다. 같은 비용을 가리키므로 통일합니다.",
    {1548: "환전 수수료: #{0}#."},
    {"reference_indices": [401, 403]})
add("C12", "기능 설명의 직역", "medium",
    "quota는 이 게임에서 초당 자원 공급 한도입니다. 할당량 비용이라는 표현을 실제 구매 기능에 맞춰 구체화합니다.",
    {1379: "철광석 공급 한도 확장 비용 #-50%#",
     1380: "철광석 공급 한도 확장 비용 #-5%#"},
    {"reference_indices": [123, 183],
     "code": [
         {"path": str(CODE / "Assets.Behaviour.UI.Resources" / "ResourceQuotaRow.cs"),
          "line": 60, "observation": "버튼은 GetResourceUpgrade의 비용을 지불하고 AddResource로 공급 한도를 늘립니다."},
         {"path": str(CODE / "Assets.Source.Player" / "GamePlayer.cs"),
          "line": 333, "observation": "철광석 의뢰 보상이 공급 한도 추가 구매 비용에 0.5 및 반복당 0.95 배수를 적용합니다."}]})
add("C13", "조건의 과도한 구체화", "medium",
    "원문의 full heavy armor를 머리와 몸통 모두라고 풀어 썼지만, 실제 HasArmorType은 둘 중 하나만 중갑이어도 허용합니다. 슬롯 양쪽 필수라는 추가 제한을 삭제합니다.",
    {530: by_index[530]["target"].replace(
        "머리와 몸통에 모두 중갑을 착용하고 방패를 든 채 훈련하면",
        "중갑과 방패를 갖추고 훈련하면")},
    {"code": [
        {"path": str(CODE / "Assets.Source.Items.Data" / "HumanItemData.cs"),
         "line": 255, "observation": "전사 계열에 방패와 HasArmorType(Heavy) 조건으로 Tank 특성을 부여합니다."},
        {"path": str(CODE / "Assets.Source.Items.Data" / "HumanItemData.cs"),
         "line": 332, "observation": "머리·몸통 모두 없을 때만 실패하고, 둘 중 하나가 지정 등급이면 성공할 수 있습니다."}]})
add("C14", "아이템 이름 참조", "low",
    "발명 공방 기술 Widgets?에서 아이템 이름을 실제 기계 장치에 맞춥니다.",
    {1055: "기계 장치?"}, {"reference_indices": [706, 707]})
add("C15", "자연스러운 인원 명칭", "low",
    "crew를 작업대로 번역하면 작업용 받침대로 읽힐 수 있습니다. 사람들의 집단임이 분명한 산림 작업반을 권합니다.",
    {134: "산림 작업반"}, {"reference_indices": [135, 1294, 1295, 1297]}, optional=True)
add("C16", "같은 해금 조건 안내", "low",
    "같은 선행 전쟁 조건 안내의 어순을 기존 다수 항목의 전쟁 진행 필요로 통일합니다.",
    {i: by_index[i]["target"].replace("필요 전쟁 진행도:", "전쟁 진행 필요:")
     .replace("필요한 전쟁 진행:", "전쟁 진행 필요:")
     .replace("필요한 전쟁 진척:", "전쟁 진행 필요:")
     .replace("성곽 지구", "왕성 구역").replace("정상의 폐허", "정상 유적")
     for i in [410, 419, 422, 427, 842, 1288]},
    {"reference_indices": [225, 226, 252, 311, 356, 371, 380, 395]}, optional=True)
add("C17", "던전 이름 표기", "low",
    "옌스부르크 지하묘지의 띄어쓰기를 목록 이름과 안내에서 동일하게 유지합니다.",
    {1250: by_index[1250]["target"].replace("지하 묘지", "지하묘지"),
     1251: by_index[1251]["target"].replace("지하 묘지", "지하묘지")},
    {"reference_indices": [417]}, optional=True)

mechanical = []
for row in rows:
    source = row["source"]
    target = row["target"]
    index = row["index"]
    checks = {
        "original_source_and_key": (source == original[index]["source"] and
                                    row["key"] == original[index]["key"]),
        "placeholder_inventory": Counter(re.findall(r"\{[^{}]+\}", source)) ==
                                 Counter(re.findall(r"\{[^{}]+\}", target)),
        "highlight_delimiters": source.count("#") == target.count("#") and target.count("#") % 2 == 0,
        "tag_order": re.findall(r"<[^>]+>", source) == re.findall(r"<[^>]+>", target),
        "escaped_break_count": source.count("\\n") == target.count("\\n"),
        "real_break_count": source.count("\n") == target.count("\n"),
        "empty_source_preservation": bool(source) == bool(target),
    }
    if not all(checks.values()):
        mechanical.append({"index": index, "key": row["key"], "checks": checks})

groups = defaultdict(list)
for row in rows:
    groups[row["source"]].append(row)
different_duplicates = []
accepted = {
    "Mine": "버튼 동작은 채굴, 시설·획득처는 광산으로 문맥이 다릅니다.",
    "Butcher": "버튼 동작은 도축, 시설·제작처는 정육점으로 문맥이 다릅니다.",
    "#Click# to choose a new material to extract.": "숲·농장의 같은 선택 기능이며 번역의 의미는 같습니다.",
    "Hunters": "ForestCrewForager2의 원문 오기이며 소비 코드가 Forager인 근거가 별도 검토에 있습니다.",
    "Available items:": "숲의 획득 목록과 농장의 재배 목록으로 문맥이 달라 각각 구체화했습니다.",
}
for source, group in groups.items():
    if len({r["target"] for r in group}) > 1:
        different_duplicates.append({
            "source": source,
            "rows": [{"index": r["index"], "key": r["key"], "target": r["target"]} for r in group],
            "decision": "ACCEPT_CONTEXT" if source in accepted else "FIX_RECOMMENDED",
            "reason": accepted.get(source, "C07 또는 C08의 수정 권고에 포함됩니다."),
        })

report = {
    "status": "FAIL",
    "review_complete": True,
    "reason": "원문 의미와 수치는 대체로 정확하지만, 같은 기능·자원·거점의 명칭 및 한 곳의 과도한 조건 구체화가 남아 있습니다.",
    "scope": "원문과 네 part의 1556개 전체 정독·중복·시설명·조건 교차 검토. 실제 게임 화면 검수는 포함하지 않습니다.",
    "input_files": [{"path": str(path), "sha256": digest(path), "rows": len(read(path))} for path in PARTS],
    "source_sha256": digest(SOURCE),
    "latest_root_text_sha256": digest(TRANSLATION / "root_0_399.txt"),
    "part_files_modified": False,
    "mechanical_check": {"status": "PASS" if not mechanical else "FAIL", "errors": mechanical},
    "semantic_checks": [
        {"status": "PASS", "indices": [848, 851, 852, 854, 856, 857, 858, 865, 866, 867, 868, 870, 872, 874, 906],
         "checked": "증가·감소 방향, 최대치 up to, 장착품 절반 효과, 강화 미적용, 아이템·모집 인원당 추가 비용을 보존했습니다."},
        {"status": "PASS", "indices": [1023, 1024, 1026, 1027, 1032, 1033],
         "checked": "음식 품질 120% 초과 조건과 수입 최대 50%, 크라운 10%, 휴식 구간 중 낮은 확률을 정확히 표현했습니다."},
        {"status": "PASS", "indices": [1120, 1122, 1123, 1124, 1125],
         "checked": "기력 고갈 은퇴·반복 기력 소모·가장 높은 능력치와 비율 관계가 맞습니다. 1124/1125의 위치 인수 순서 변경은 한국어 어순이며 인수 번호가 보존되었습니다."},
        {"status": "PASS", "indices": [1329, 1369, 1370, 1379, 1380, 1381, 1382, 1386, 1388, 1390, 1396, 1398, 1400, 1402, 1404, 1406],
         "checked": "게시판당 다섯 명·반복 보상/기력·권장 전투력·최초/반복 할인 50%/5%·전사 도적 마법사 50%·성직자 75% 난이도 감소를 보존했습니다. quota 명칭은 C12에서 개선을 권고합니다."},
        {"status": "PASS", "indices": [1424, 1425, 1427, 1430, 1462, 1465],
         "checked": "위쪽/아래쪽 출력, 조건 충족 시 통과, 다섯 명 파티, 전멸 초기화, 던전 교체 시 진행 소멸을 보존했습니다."},
        {"status": "PASS", "indices": [1306, 1489, 1521],
         "checked": "Forager 복수형의 원문 Hunters 오기와 Arlingen 문맥의 Arlington 오기를 바로잡은 근거가 타당합니다. 다섯 단어 대사는 '숄라스를 절대 깨우지 말아야 한다'로 5어절을 유지합니다."},
        {"status": "PASS", "indices": [0, 2, 1392, 1394],
         "checked": "locale의 en-US 유지와 원문부터 비어 있는 세 항목은 번역 누락으로 세지 않았습니다. 실제 원본 빈 설명의 런타임 처리는 별도 범위입니다."},
    ],
    "generated_names": {
        "status": "UNCHANGED",
        "evidence_path": str(WORK / "audit" / "name_classification.json"),
        "reason": "인명 생성용 라틴 음절의 결합·모음 축약과 저장 시드 연동에 관한 기존 고유인명 유지 근거를 변경하지 않았습니다.",
    },
    "duplicate_source_review": different_duplicates,
    "findings": findings,
    "finding_count": len(findings),
    "blocking_recommendation_groups": sum(not f["optional"] for f in findings),
    "optional_recommendation_groups": sum(f["optional"] for f in findings),
    "application_note": "아직 적용하지 않았습니다. C02와 C16은 같은 행에 걸치므로 적용 시 C16의 최종 문장을 우선하며, 적용 후 part·canonical·문자표·검증 결과를 다시 생성해야 합니다.",
}
OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": report["status"], "mechanical": report["mechanical_check"]["status"],
                  "rows": len(rows), "findings": len(findings),
                  "mechanical_errors": mechanical}, ensure_ascii=False))
