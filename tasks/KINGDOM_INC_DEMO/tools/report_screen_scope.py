"""화면 존재·부재의 코드/장면 근거와 추가 검수 코드의 한정된 변경을 기록합니다."""
import difflib
import json
from datetime import datetime, timezone
from common import ROOT, WORK, EXTRACT, DATA, load_asset, read_tree, sha, write_json

CODE = ROOT / "extracted_private/KINGDOM_INC_DEMO/inspection/decompiled"
TOOLS = ROOT / "tasks/KINGDOM_INC_DEMO/tools"


def ev(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def source(name, patterns):
    path = CODE / name
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    return {**ev(path), "matches": [{"line": i, "text": line.strip()} for i, line in enumerate(lines, 1)
                                  if any(pattern in line for pattern in patterns)]}


objects = read(EXTRACT / "objects.json")
by_id = {row["id"]: row for row in objects}
types = read(CODE.parent / "code_strings.json.types.json")
trees = list((EXTRACT / "trees").rglob("*.json"))
calls = []


def walk(value, location):
    if isinstance(value, dict):
        if value.get("m_MethodName"):
            calls.append({"tree": location, "method": value["m_MethodName"],
                          "target_type": value.get("m_TargetAssemblyTypeName")})
        for child in value.values():
            walk(child, location)
    elif isinstance(value, list):
        for child in value:
            walk(child, location)


for tree_path in trees:
    walk(read(tree_path), str(tree_path.relative_to(ROOT)))

scene_env = load_asset(DATA / "globalgamemanagers")
build_settings = read_tree(next(obj for obj in scene_env.objects if obj.path_id == 11))
script_env = load_asset(DATA / "globalgamemanagers.assets")
dialog_script = read_tree(next(obj for obj in script_env.objects if obj.path_id == 2002))
code_files = list(CODE.rglob("*.cs"))
searches = {}
for name, needles in {
    "query_callers": ["UIAlertWindow.Query("],
    "locale_change_callers": ["Translation.UpdateLocale(", "Translation.All"],
    "dialogue_routes": ["Dialogue", "Conversation", "GameOver", "DeathScreen", "Accessibility", "Colorblind", "Subtitle"],
}.items():
    matches = []
    for path in code_files:
        for n, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if any(needle in line for needle in needles):
                matches.append({"path": str(path.relative_to(ROOT)), "line": n, "text": line.strip()})
    searches[name] = {"needles": needles, "matches": matches}
searches["dialogue_routes"]["match_review"] = "검색된 NewGameOverlay/HideNewGameOverlay 4곳은 새 게임 첫 제련 전 배경 덮개이며 GameOver 문자열의 부분 일치다. 별도 게임 오버 화면을 뜻하지 않는다."

relevant_ids = ["globalgamemanagers/11", "globalgamemanagers.assets/2002", "level0/426", "level0/513",
                "level1/2962", "level1/3056", "level1/3082", "level1/3344", "level2/121", "resources.assets/21"]
asset_evidence = []
for object_id in relevant_ids:
    row = dict(by_id[object_id])
    tree_path = EXTRACT / "trees" / row["file"] / f'{row["path_id"]}.json'
    if tree_path.exists():
        row["tree"] = ev(tree_path)
        row["fields"] = read(tree_path)
    asset_evidence.append(row)

evidence = {
    "object_inventory": ev(EXTRACT / "objects.json"),
    "object_count": len(objects),
    "type_inventory": ev(CODE.parent / "code_strings.json.types.json"),
    "type_count": len(types), "decompiled_code_files": len(code_files),
    "serialized_tree_count": len(trees),
    "serialized_event_call_count": len(calls),
    "relevant_event_calls": [row for row in calls if any(term in row["method"].lower()
        for term in ["query", "locale", "language", "dialog", "death", "gameover", "accessib", "subtitle"])],
    "scenes": build_settings["scenes"],
    "dialog_script": {k: dialog_script[k] for k in ["m_Name", "m_ClassName", "m_Namespace", "m_AssemblyName"]},
    "dialog_script_instance_count": sum(row.get("script") == "Unity.InputSystem:UnityEngine.InputSystem.Editor.Dialog" for row in objects),
    "searches": searches, "assets": asset_evidence,
    "code": [
        source("Assets.Behaviour.UI/GameUIType.cs", ["\t"]),
        source("Assets.Behaviour.UI/GameUI.cs", ["ShowCharacterDetails", "DemoThanks", "SceneManager.LoadScene"]),
        source("Assets.Behaviour.UI.MainMenu/MainMenuUI.cs", ["_mainMenuContent", "_loadGameContent", "_optionsContent", "_keybindContent", "UIAlertWindow.Show", "SceneManager.LoadScene"]),
        source("Assets.Behaviour.UI.MainMenu/InGameMenuUI.cs", ["_mainContent", "_loadGameContent", "_saveGameContent", "_optionsContent", "_keybindContent", "UIAlertWindow.Show", "SceneManager.LoadScene"]),
        source("Assets.Behaviour.UI.MainMenu/OptionsUI.cs", ["private TMP_", "private Slider", "private Toggle", "PlayerPrefs.", "ShowKeyBindings"]),
        source("Assets.Source.Util/Translation.cs", ["Resources.LoadAll", "DefaultLanguage", 'FileInfo("language.ini")', 'PlayerPrefs.GetString("Locale")', "UpdateLocale", '_languages[key].Apply']),
        source("Assets.Behaviour.UI/UIAlertWindow.cs", ["public static void Query", '"@Dialog', "ShowAlert", "buttons.Length", "_onClick?.Invoke"]),
        source("Assets.Behaviour.UI.Human/HumanDetailsPopup.cs", ["SetItem(", "CurrentHealth > 0", "HumanDetailsDead", "_healthText.color"]),
        source("Assets.Source.Adventure/WarProgress.cs", ["TakeDamage(", "Soldiers.RemoveAt", "SoldierDied", "AddProgress(-1)"]),
        source("Assets.Source.Items.Data/CombatantItemData.cs", ["Dead =>", "TakeDamage(", "CurrentHealth <= 0"]),
    ],
    "language_rows": [row for row in read(WORK / "language_source.json") if row["key"] in
        ["OptionsLanguage", "OptionsLanguageChanged", "OptionsLanguageChangedDesc", "DialogOkay", "DialogYes", "DialogNo", "HumanDetailsDead"]],
}

report = {
    "status": "PASS",
    "scope": "이 Steam 데모 빌드의 장면·UI 연결·전체 게임 코드와 직렬화된 이벤트를 근거로 추가 화면의 존재를 분류한다. PASS는 조사 완료이며 아래 NOT_RUN 화면을 실행 통과로 바꾸지 않는다.",
    "utc": datetime.now(timezone.utc).isoformat(),
    "build": "25631786", "source_assembly": ev(DATA / "Managed/Assembly-CSharp.dll"),
    "evidence": evidence,
    "screens": [
        {"id": "narrative_dialogue", "status": "NOT_APPLICABLE", "scope": "인물 간 대화 전용 화면",
         "reason": "등록 장면은 MainMenu/Game/Bootstrap 3개이고 실제 메뉴·팝업 연결은 GameUI/MainMenuUI/InGameMenuUI 필드에 모두 열거된다. 대화 노드·대화 화자·대화 진행용 게임 형식/코드/연결이 없다. 이름 Dialog인 유일 스크립트는 Unity 입력 시스템 Editor 형식이며 장면 인스턴스가 0개다. 일반 알림창은 별도로 존재한다."},
        {"id": "branching_story_choices", "status": "NOT_APPLICABLE", "scope": "스토리 분기 선택지",
         "reason": "대화/이야기 분기 시스템과 데이터가 없으며 현재 게임 코드에서 UIAlertWindow.Query 호출자는 0개, 직렬화된 Query 이벤트 연결도 0개다. 그러나 공용 예/아니요 창 구현은 존재하므로 해당 표시를 N/A로 제외하지 않고 아래 별도 검수한다."},
        {"id": "generic_yes_no_dialog", "status": "NOT_RUN", "exists": True,
         "reason": "Bootstrap이 level2/121 UIAlertWindow를 초기화하고 Query가 DialogYes/DialogNo 버튼 2개를 생성한다. 현재 데모의 일반 플레이 호출 경로는 없지만 구현·언어 키·실제 UI 자산이 모두 존재한다.",
         "action": "alert_query", "value": "", "close_action": "alert_close",
         "runtime_scope": "LGError/LGErrorCorrupt 원본 문구와 원본 Query의 버튼 표시만. 선택 결과 콜백은 없다."},
        {"id": "language_switch_screen", "status": "NOT_APPLICABLE",
         "reason": "OptionsUI 코드의 전체 저장/적용 필드와 level0/513, level1/3344 옵션 인스턴스에는 해상도·창 모드·음악·효과음·FPS·자동 저장·UI 크기만 연결되어 있다. 언어 선택 필드·버튼이 없으며 Translation.UpdateLocale/All의 게임 호출자와 이벤트 연결도 0개다. 언어 변경 함수·미사용 언어 문구 키는 있지만 실행 가능한 언어 전환 화면은 아니다. 시작 시 en-US/기존 Locale/외부 language.ini를 읽는 로딩 경로와 구분한다."},
        {"id": "dedicated_accessibility_screen", "status": "NOT_APPLICABLE",
         "reason": "주 메뉴·일시정지 메뉴의 연결 화면은 메인/저장/불러오기/설정/키 설정으로 한정되어 있고, 실제 OptionsUI 필드와 게임 형식에 별도 접근성·자막·색각 설정 UI가 없다. UI 크기와 키 설정은 존재하므로 접근성 관련 기능 전체를 N/A로 표시하지 않는다.",
         "existing_related_controls": ["설정의 UI 크기", "키 설정", "음량 설정"],
         "existing_controls_review": ev(WORK / "audit/visual_rc4_batch1.json")},
        {"id": "player_death_gameover_screen", "status": "NOT_APPLICABLE", "scope": "플레이어 사망/게임 오버 전용 화면",
         "reason": "전쟁 사망은 WarProgress.UpdateWar에서 병사를 Soldiers 목록에서 제거하고 시설에 SoldierDied를 알리는 구조다. 해당 경로에서 게임 오버 장면·팝업으로 전환하지 않으며 등록 장면/메뉴 연결에 플레이어 사망 화면도 없다. 인물 상세창의 사망 표시와 병사 사망 애니메이션은 존재하므로 아래 별도 구분한다."},
        {"id": "human_dead_state", "status": "NOT_RUN", "exists": True,
         "reason": "GameUI.CharacterPopup은 level1/3056으로 연결된다. HumanDetailsPopup.SetItem은 CurrentHealth<=0이면 level1/2828 텍스트에 @HumanDetailsDead를 빨간색으로 표시한다.",
         "action": "human_dead", "value": "soldier",
         "runtime_scope": "새 독립 인물 미리보기의 Health01만 0으로 변경. 실제 병력이나 저장 인물을 죽이지 않으며 정상 전투의 사망 과정 검증을 주장하지 않는다."},
    ],
}
write_json(WORK / "audit/na_screens.json", report)

before_dir = WORK / "toolchain/support_extension_before"
before_text = (before_dir / "UiAccess.cs").read_text(encoding="utf-8")
after_text = (TOOLS / "KoreanQA/UiAccess.cs").read_text(encoding="utf-8")
insert = '            if (c.action == "alert_query" || c.action == "human_dead") return ActScreenExtension(c);\n'
assert after_text.replace(insert, "", 1) == before_text
boundary = read(WORK / "audit/support_extension_boundary.json")
assert boundary["status"] == "PASS"
assert len(boundary["changedExistingMethods"]) == 1
assert boundary["changedExistingMethods"][0]["originalInstructionsUnchangedOutsideInsertion"]
extension = {
    "status": "PASS", "scope": "새 검수 명령 2개만 추가한 지원 DLL의 정적 빌드·변경 경계 검사. 게임 실행 결과는 각 추가 세션에 따로 기록한다.",
    "utc": datetime.now(timezone.utc).isoformat(),
    "before_dll": ev(before_dir / "KoreanQA.dll"),
    "after_dll": ev(WORK / "toolchain/KoreanQA/KoreanQA.dll"),
    "boundary": ev(WORK / "audit/support_extension_boundary.json"),
    "boundary_summary": {"unchanged_existing_methods": boundary["unchangedExistingMethods"],
                         "existing_method_change": boundary["changedExistingMethods"]},
    "source_changes": {
        "UiAccess": {"before": ev(before_dir / "UiAccess.cs"), "after": ev(TOOLS / "KoreanQA/UiAccess.cs"),
                     "exact_change": insert.strip(), "rest_identical": True,
                     "diff": "".join(difflib.unified_diff(before_text.splitlines(True), after_text.splitlines(True), "before/UiAccess.cs", "after/UiAccess.cs"))},
        "added": ev(TOOLS / "KoreanQA/ZScreenExtension.cs"),
    },
    "new_types": boundary["newTypes"], "new_methods": boundary["newMethods"],
    "build": {"status": "PASS", "warnings": 0, "errors": 0},
    "commands": [
        {"action": "alert_query", "value": "", "scope": "원본 Query의 예/아니요 표시. 콜백 없음", "close": "alert_close"},
        {"action": "human_dead", "value": "soldier", "scope": "독립 새 인물의 Health01=0으로 원본 사망 문구 표시. 실제 병력·저장 무변경", "close": "close_panels"},
    ],
    "recommended_sequence": [
        {"action": "alert_query", "value": ""}, {"action": "alert_close", "value": ""},
        {"action": "new_game", "value": ""}, {"action": "manual_craft", "value": "Forge|complete"},
        {"action": "human_dead", "value": "soldier"}, {"action": "close_panels", "value": ""},
        {"action": "quit", "value": ""},
    ],
    "game_boundary": "후보 게임·원본 게임 DLL·자산은 변경하지 않는다. prepare_qa가 별도 검수 사본에 두 메서드만 변경했는지 기존 독립 경계 검사를 계속 수행한다.",
    "failed_checks_preserved": [
        {"evidence": ev(WORK / "audit/support_extension_boundary_first_fail.json"),
         "resolution": "새 소스 파일의 컴파일 순서가 기존 람다 내부 이름을 밀어낸 차이를 발견해 파일을 마지막 ZScreenExtension.cs로 옮겼다. 최종 검사에서 기존 123개 메서드가 동일하다."},
        {"evidence": ev(WORK / "audit/support_extension_boundary_second_fail.json"),
         "resolution": "검사기가 새 분기를 메서드 맨 앞의 접두부로만 가정했으나 컴파일러가 기존 클로저 초기화 5개 명령 뒤에 삽입했다. 임의 한 구간 삽입을 제거한 나머지 명령·분기 목적지가 정확히 같은지 검사하도록 수정했고 최종 PASS했다."},
    ],
    "runtime": "NOT_RUN",
}
write_json(WORK / "audit/support_extension_change.json", extension)
print(json.dumps({"status": "PASS", "na_screens": len(report["screens"]), "extension_boundary": boundary["status"]}))
