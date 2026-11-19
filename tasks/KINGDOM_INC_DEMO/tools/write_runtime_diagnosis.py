"""rc3 실행에서 확인한 접근 결함과 수정 근거를 비공개 감사 기록으로 남깁니다."""
import json
from pathlib import Path
from common import ROOT, WORK, EXTRACT, DATA, sha, write_json

code = ROOT / "extracted_private/KINGDOM_INC_DEMO/inspection/decompiled"
session = WORK / "full_rc3/qa_full_rc3"
inventory = json.loads((EXTRACT / "objects.json").read_text(encoding="utf-8"))
objects = {row["id"]: row for row in inventory}


def evidence(path):
    path = Path(path)
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def source(name):
    return evidence(code / name)


def capture(prefix):
    matches = list(session.glob(prefix + "*.png"))
    if len(matches) != 1:
        raise ValueError((prefix, matches))
    return evidence(matches[0])


card_ids = [
    "mine", "forge", "shop", "blacksmith", "supply_depot", "requisition_office",
    "tailor", "carpenter", "leatherworker", "barracks", "war_effort", "engraver", "forest", "campfire",
]
report = {
    "build": "25631786",
    "scope": "rc3 실행 결함의 읽기 전용 진단과 다음 검수 지원 코드 준비. 후보 게임 자산 수정·게임 실행은 주 작업자 담당.",
    "status": "PASS",
    "runtime_after_support_fix": "NOT_RUN",
    "original_assembly": evidence(DATA / "Managed/Assembly-CSharp.dll"),
    "session": evidence(session / "session-check.json"),
    "session_result_preserved": json.loads((session / "session-check.json").read_text(encoding="utf-8")),
    "tech_card_layout": {
        "finding": "공용 큰 기술 카드의 설명 영역이 오른쪽 그림 아래까지 뻗음. 그림 너비만 SetTech에서 변경되고 설명 폭은 조정되지 않음.",
        "image": capture("225651_"),
        "objects": [objects[f"sharedassets1.assets/{n}"] for n in [971, 1022, 806, 678, 816, 1362, 860]],
        "code": source("Assets.Behaviour.UI.TechTree/UIElementTechNode.cs"),
        "before": {
            "card_size": [360, 180], "description_parent_size": [344, 72],
            "description_size": [328, 56], "font_size": 12, "autosize": False,
            "word_wrapping_mode": 1, "line_spacing": 20, "overflow_mode": 0,
        },
        "proposed_minimum_scalar_changes": [
            {"object": "sharedassets1.assets/806", "field": "m_SizeDelta/x", "before": -16, "after": -120},
            {"object": "sharedassets1.assets/678", "field": "m_SizeDelta/y", "before": 72, "after": 96},
            {"object": "sharedassets1.assets/1022", "field": "m_lineSpacing", "before": 20, "after": 0},
        ],
        "geometry": "기존 왼쪽 고정 위치를 유지하면 설명 224×80, 카드 기준 오른쪽 끝240. 최대 그림 폭96에서 왼쪽248이므로 간격8 확보.",
        "max_sprite_width": 48,
        "image_scale": 2,
        "detail_sprite_count": 14,
        "prior_count_correction": "처음 13개로 전달한 수를 바로잡음. sharedassets1.assets/87 Anvil을 쓰는 blacksmith 포함 총14개.",
        "required_focus_tech": card_ids,
        "runtime_validation": "NOT_RUN",
    },
    "tech_list": {
        "finding": "목록 자식 GO213만 켜면 상위 GO169 TechTreeUI가 꺼져 있어 RefreshList 코루틴 실패.",
        "evidence": [objects["level1/3128"], objects["level1/3172"],
                     source("Assets.Behaviour.UI.TechTree/TechTreeMenu.cs"),
                     source("Assets.Behaviour.UI.TechTree/TechTreeListView.cs"),
                     evidence(session / "messages.jsonl")],
        "support_fix": "TechTreeMenu._uiLabel 상위 UI를 검수 문맥으로 켠 후 정확한 _listView를 활성화. isActiveAndEnabled 확인. 기술·원본 메서드는 변경하지 않음.",
    },
    "node_tooltip": {
        "finding": "자식 TooltipSource의 첫 항목은 제작법이 아닌 입출력 자원이 될 수 있음.",
        "support_fix": "시설 본체의 ITooltipTitleSource/ITooltipCustomSource를 PreviewTooltipSource.SetSource로 연결. WorldFlowRecipe의 실제 설명 코드 사용.",
        "evidence": source("Assets.Behaviour.Flow.Elements/WorldFlowRecipe.cs"),
    },
    "forest_tabs": {
        "finding": "세 캡처 대조 결과 밝은 테두리와 선택 위치가 올바르게 이동함. ShowCrew가 SetSelected를 호출하므로 추가 수정 불필요.",
        "images": [capture("225916_"), capture("225917_"), capture("225919_")],
        "status": "PASS",
    },
    "forest_blocked": {
        "finding": "999%는 숲 전쟁 1단계 전의 원본 차단 상태. 기술만 해금해서는 활성 작업반이 되지 않음.",
        "code": source("Assets.Source.Player/ForestSettings.cs"),
        "preview_fixture": "forest_fixture는 검수 저장의 숲 전쟁1단계·작업반 각2명을 준비. 실제 해금·전쟁 승리 검증이 아님.",
    },
    "not_applicable": [
        {
            "screen": "환전 창",
            "reason": "level1/2962 GameUI CurrencyExchangePopup 참조 {m_FileID:0,m_PathID:0}; 전체 MonoBehaviour 인스턴스0.",
            "instance_count": sum("Assets.Behaviour.UI.CurrencyExchange.CurrencyExchangePopup" in str(row)
                                  and row["type"] == "MonoBehaviour" for row in inventory),
            "evidence": [objects["level1/2962"], evidence(EXTRACT / "objects.json")],
        },
        {
            "screen": "농장·던전·후반 인물",
            "reason": "5단계 이상 대부분 숨김, 아이템은 Tier1~4 등록. 농장/던전 조건의 eastern 전쟁이 미등록. 잔존 문구 정적 검증과 전체 문자 검사는 유지.",
            "evidence": [source("Assets.Source.Player.Tech/T7Farm.cs"),
                         source("Assets.Source.Player.Tech/T8Dungeon.cs"),
                         source("Assets.Source.Adventure/WarType.cs"),
                         source("Assets.Source.Player/TechNode.cs"),
                         source("Assets.Source.Items/ItemType.cs")],
        },
    ],
    "normal_first_craft": {
        "action": "manual_craft", "value": "Forge|complete",
        "method": "WorldFlowElement.ClickCraft를 실제 CanManualCraft 조건하에 반복. 정상 Update가 결과 생산·HUD 해제. 직접 상태 대입 없음.",
        "assertions": "새 게임 검정 화면이었던 경우, 3초 뒤 blackout=false와 결과 아이템 증가 필수. .craft.json 전후 기록.",
        "evidence": [source("Assets.Behaviour.Flow/WorldFlowElement.cs"),
                     source("Assets.Source.Flow.Elements/RecipeElement.cs"),
                     source("Assets.Source.Player/GamePlayer.cs")],
    },
    "economy_preview": {
        "action": "economy_fixture", "values": ["initial", "demo"],
        "reason": "원본 CurrencyDisplay는 잔액0인 재화를 표시하지 않음. 초기 제작은 주괴를 생산하지만 재화를 벌지 않으므로 이전 빈 HUD는 정상.",
        "boundary": "이미 해금된 통화만 AddCurrency(...,false)로 추가. 정상 수입 통계와 해금·공급량 직접 변경 없음. .fixture.json 기록.",
        "demo_currency": ["Gold", "Requisition", "Medal"],
        "evidence": [source("Assets.Behaviour.UI.HUD/CurrencyPane.cs"),
                     source("Assets.Behaviour.UI.Shared/CurrencyDisplay.cs"),
                     source("Assets.Source.Player/CurrencyExtensions.cs")],
    },
    "support": {
        "dll": evidence(WORK / "toolchain/KoreanQA/KoreanQA.dll"),
        "build": {"status": "PASS", "warnings": 0, "errors": 0},
        "sources": [evidence(ROOT / "tasks/KINGDOM_INC_DEMO/tools/KoreanQA" / name)
                    for name in ["Driver.cs", "UiAccess.cs", "Scenario.cs", "FontCheck.cs"]],
        "game_dll_boundary": "SteamManager.Awake와 Bootstrap.InitializeGame 두 메서드의 기존 검수 변경만 유지. prepare_qa의 독립 경계 검사 결과가 별도로 필요.",
    },
    "runtime_plan": evidence(WORK / "audit/runtime_plan.json"),
}
write_json(WORK / "audit/runtime_access_diagnosis_rc3.json", report)
print(json.dumps({"status": report["status"], "support_runtime": report["runtime_after_support_fix"],
                  "cards": len(card_ids), "path": "audit/runtime_access_diagnosis_rc3.json"}, ensure_ascii=False))
