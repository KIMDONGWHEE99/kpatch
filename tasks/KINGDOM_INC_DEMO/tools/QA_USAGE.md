# Kingdom Inc. Demo 검수 보조 사용

검수 전용 사본은 `working_private/KINGDOM_INC_DEMO` 아래에 둡니다. 이 보조 DLL·설정·코드 변경은 배포본에 포함하지 않습니다. 게임 실행은 주 작업자가 담당합니다.

## 새 사본 준비

한글 후보를 `working_private/KINGDOM_INC_DEMO/qa03/game` 같은 새 폴더에 복사한 다음 준비합니다. 원본 설치 폴더나 이미 준비한 사본에는 실행하지 않습니다.

```powershell
python tasks/KINGDOM_INC_DEMO/tools/prepare_qa.py --game working_private/KINGDOM_INC_DEMO/qa03/game --run-id qa03 --mode manual
```

- `--mode probe`: 첫 메뉴 → 설정 → 키 설정 → 첫 메뉴 복귀를 캡처하고 자동 종료.
- `--mode manual`: 첫 메뉴를 캡처한 뒤 파일 명령을 기다림.
- 도구 빌드가 최신이면 `--no-build`를 추가할 수 있음.
- 검수 회사명 `Korean QA Test`, 실행마다 다른 제품명 `KngQAxxxxx`.
- 변경은 회사·제품명 두 필드와 `app.info`, `SteamManager.Awake` 즉시 반환, `Bootstrap.InitializeGame`의 지원 코드 호출 한 곳으로 제한.
- `assembly-boundary.json`은 원래 후보와 모든 형식·메서드·필드·내장 자산을 대조한 결과.
- `candidate-manifest.json`은 검수 변경 전 후보, `prepared-manifest.json`은 실행할 검수 사본.

## 실행과 종료 검사

```powershell
python tasks/KINGDOM_INC_DEMO/tools/qa_session.py launch --output working_private/KINGDOM_INC_DEMO/qa03/qa_qa03
```

실행 전 원래 사용자 저장·설정·Steam 앱 폴더와 앱 목록 해시를 수집합니다. 실행 시 기본 1200×900 창·무음을 요청하고, 실제 너비는 현재 모니터 절반에서 창 테두리 여유 16픽셀을 뺀 값으로 제한합니다. Unity가 자기 창을 주 화면 `(8,32)` 위치로 옮깁니다. 게임 안의 입력 수신만 비활성화하여 사용자 마우스·키보드와 경쟁하지 않습니다.

`runtime.json` 생성 후 실제 실행 경로·PID·GPU·회사·제품·저장 경로·창 위치를 확인합니다. 검수 사본과 다른 경로라면 검수를 인정하지 않습니다.

정상 종료한 뒤:

```powershell
python tasks/KINGDOM_INC_DEMO/tools/qa_session.py finish --output working_private/KINGDOM_INC_DEMO/qa03/qa_qa03
```

이 결과의 `PASS`는 실행 경로·저장 경계·파일 무결성·기본 로그 조건에만 해당합니다. `visual_review`는 항상 `NOT_RUN`으로 남습니다. 이미지를 실제로 열어 확인한 결과를 별도로 기록해야 합니다. 오류 로그가 있으면 원본과 비교 검토할 때까지 `FAIL`로 남깁니다.

## 화면 명령

```powershell
python tasks/KINGDOM_INC_DEMO/tools/qa_session.py command --output working_private/KINGDOM_INC_DEMO/qa03/qa_qa03 --action options
```

명령 결과 이름을 출력합니다. 같은 이름의 `.result.json`이 생성될 때까지 다음 명령을 쓰지 않습니다. 성공 결과의 `CAPTURED`는 캡처 확보이며 내용 검수 완료가 아닙니다. `.png`가 실제 화면이고 같은 이름의 `.json`은 TMP 문구·글꼴·화면 영역·넘침 정보입니다.

| action | 목적·선행조건 |
|---|---|
| `capture` | 현재 화면 |
| `main_menu`, `options`, `keybindings`, `load_menu` | 첫 메뉴에서 해당 하위 화면 |
| `new_game` | 첫 메뉴에서 정상 새 게임 전환. 원본은 HUD를 숨기고 검은 배경에 제련소만 표시함 |
| `manual_craft` | `--value Forge\|complete`로 실제 제작 버튼의 공개 동작을 완료까지 호출. 정상 결과 생성과 첫 HUD 해제를 `.craft.json`에 기록. `Forge\|1`은 한 번만 실행 |
| `tutorial_close` | 원본 안내 종료 함수를 직접 호출해 HUD 표시. 정상 진행에서는 첫 수동 제련 완료가 이 함수를 호출함 |
| `buy` | 건설 메뉴. `--value Resource/Crafting/Consumption/Utility`로 분류 선택 |
| `tech` | 연구 메뉴. `--value mine`처럼 기술 ID를 주면 해당 하위 연구 |
| `focus_tech` | `--value`의 기술에 초점. 연구 메뉴가 열려 있어야 함 |
| `close_panels` | 게임판의 하위 메뉴 닫기 |
| `unlock` | `--value` 기술만 검수 저장에서 해금. 실제 게임의 `AddTech` 함수를 사용 |
| `unlock_demo` | 데모에 구현된 1~4단계 기술을 검수 저장에서 해금. 정상 진행 검증으로 취급하지 않음 |
| `resources` | 공급. 먼저 `unlock --value unlock_supply_window` |
| `war` | 전쟁. 먼저 `unlock --value war_effort` |
| `forest` | 숲 작업자. 먼저 `unlock --value forest` |
| `deco` | 장식. 먼저 `unlock --value tech_deco` |
| `pause` | 게임판의 일시정지 메뉴 |
| `save_menu`, `ingame_load`, `ingame_options`, `ingame_keys` | 일시정지 메뉴의 하위 화면 |
| `resume` | 게임판 복귀 |
| `save` | 검수 저장. 기본 이름 `한국어 검수`, `--value`로 변경 가능 |
| `return_menu` | 게임판에서 저장 후 첫 메뉴 복귀 |
| `load_latest` | 첫 메뉴에서 가장 최근 검수 저장 불러오기 |
| `alert`, `alert_close` | 실제 저장 오류 문구를 쓰는 안내창 표시·닫기 |
| `demo_end`, `demo_close` | 실제 데모 완료 안내 표시·닫기 |
| `quit` | 키 설정을 먼저 닫고 종료 |

대표 순서: 첫 화면 → 설정 → 키 설정 → 첫 화면 복귀 → 새 게임 안내 → `manual_craft Forge|complete`로 정상 첫 제련과 HUD 해제 → 건설 → 연구 → 필요한 기술 해금과 하위 메뉴 → 일시정지·저장·불러오기 → 오류 안내 → 데모 완료 안내 → 첫 메뉴 복귀 → 검수 저장 이어하기 → 종료. 첫 제련 검증에는 `tutorial_close`를 대신 사용하지 않습니다.

기술 해금이나 완료 안내 직접 호출은 해당 화면의 출력 검증입니다. 전체 회차·모든 분기·정상 전쟁 승리를 확인한 것으로 기록하지 않습니다.

## 상세 화면 접근

시설 생성과 선택창 열기는 두 명령으로 나눕니다. `node` 결과가 나온 다음 선택창 명령을 보내야 Unity가 시설의 초기화를 마칩니다. 이미 있는 시설은 재사용합니다. 생성은 검수 저장 안에서만 이루어지며, 가격 지불·정상 진행을 시험하는 기능은 아닙니다. `unlock_all`은 미구현 후반 기술까지 호출하므로 사용하지 말고 `unlock_demo`를 사용합니다.

| action | value 예 | 의미 |
|---|---|---|
| `catalog` | 생략 | 데모에 실제 등록된 시설·아이템·기술을 `access-catalog.json`으로 기록 |
| `tutorial` | `build`, `upgrade`, `input`, `tech`, `finish` | 해당 안내를 직접 표시하거나 검수용 안내 종료 |
| `node`, `node_focus` | `Mine`, `Forge`, `Forest`, `Blacksmith`, `Armory` | 시설 준비·중앙 표시 또는 기존 시설 중앙 표시 |
| `recipe` | `Forge`, `Blacksmith` | 제작법 선택창 |
| `recipe_selected` | `iron_ingot`, `iron_sword` | 열린 선택창에서 실제 제작법 선택 |
| `resource_select` | `Mine`, `SupplyDepot`, `Barracks` | 자원·공급·징집 선택창 |
| `resource_selected` | `iron_ore` | 열린 선택창에서 실제 자원 선택 |
| `forest_select` | 생략 | `Forest`의 산림 자원 선택 |
| `forest_tab` | `Forager`, `Logger`, `Hunter` | 산림 자원 분류 |
| `forest_selected` | `wood_log` | 열린 산림 선택창에서 실제 자원 선택 |
| `upgrade` | `Mine\|0` | 시설의 첫 강화 슬롯 선택창. 먼저 `mine_automation` 해금 필요 |
| `tech_list` | 생략 | 기술 목록 보기. 검수 UI 문맥으로 비활성 상위 `TechTreeUI`도 함께 켬. 기술 해금 상태는 바꾸지 않음 |
| `tech_tooltip` | `mine_automation`, `blacksmith` | 원래 `UITechNode.AddToTooltip`로 데모 1~4단계 기술 설명 표시 |
| `facility_tooltip` | `Mine` | 시설의 실제 이름·설명·구매 비용을 원래 툴팁으로 표시 |
| `node_tooltip` | `Forge` | 배치된 시설의 실제 제작·자원 컴포넌트 툴팁 표시 |
| `item_tooltip` | `iron_sword`, `soldier`, `wood_log` | 원래 아이템 설명 코드를 사용해 장비·인물·자원 설명 표시 |
| `character` | `conscript\|iron_sword` | 동일한 검수 인물을 생성해 해당 장비를 갖춘 인물 상세 표시 |
| `armory_seed` | `iron_sword,iron_dagger` | 검수 무기고 채널 0에 해당 장비 추가 |
| `armory` | `Armory` | 무기고 선택창 |
| `requisition` | 생략 | `RequisitionOffice`의 조달 계약 선택창 |
| `war_select` | 생략 | `WarEffort`의 전쟁 선택창 |
| `economy_fixture` | `initial`, `demo` | 이미 해금된 재화만 검수 잔액을 추가. 초기 금화 또는 데모 재화 HUD 표시. 실제 수입 획득 검증은 아님 |
| `currency_tooltip` | `Gold`, `Requisition`, `Medal` | 현재 활성 재화 HUD의 실제 컴포넌트로 이름·설명 표시 |
| `forest_fixture` | 생략 | 숲 전쟁 1단계 이상·세 작업반 각 최소 2명 상태로 실제 산림창 표시. 먼저 `unlock_demo` 실행 |
| `war_fixture` | `advance`, `complete`, `defense`, `lost` | 격리된 전쟁 상태 및 실제 단계 완료·방어·상실 알림 표시. 정상 승리 달성 검증은 아님 |
| `filter`, `appraiser`, `accountant`, `timer` | 생략 | 각각 `Filter`, `Appraiser`, `Accountant`, `Timer` 시설의 설정창 |
| `tooltip` | `id:12345` 또는 `title:@원문키` | 현재 활성 UI의 실제 툴팁 표시 |
| `tooltip_close` | 생략 | 검수로 연 툴팁 닫기 |
| `scroll` | `12345\|0.5` | 현재 활성 스크롤 영역의 내부 위치 변경. 1=위, 0=아래 |

매 캡처의 `.context.json`에 현재 활성 툴팁의 `id`, 경로, 제목과 스크롤의 `id`가 기록됩니다. ID는 실행마다 달라지므로 같은 실행에서 얻은 값만 사용합니다. 제목이 중복되면 임의 항목을 선택하지 않고 실패하므로 ID를 씁니다. `.json`의 `texts`는 실제 게임 TMP 문구이며 0행이면 명령을 실패로 기록합니다. Unity가 외부 DLL의 사용자 정의 배열을 누락하는 문제를 피하기 위해 각 행을 개별 직렬화합니다.

농장·던전의 시설 클래스와 전용 메뉴, 5단계 이상의 아이템은 이 데모에 없습니다. `TechNode.Add`가 대부분의 5단계 이상 기술을 숨기고 `ItemType`은 `Tier1`~`Tier4`만 등록합니다. `T7Farm`·`T8Dungeon`의 조건은 미등록 전쟁 `eastern`을 참조하므로 해당 툴팁도 호출하지 않습니다. 농장·던전 문구는 위치별 정적 검증과 전체 글리프 생성 검사로 분리합니다.

환전 클래스는 남았지만 장면 `level1/2962`의 `GameUI.CurrencyExchangePopup` 참조가 비어 있고, 전체 자산에 환전 창 컴포넌트 인스턴스가 없습니다. 환전 화면도 `NOT_APPLICABLE`이며 문구의 정적 검증을 유지합니다. 재화 설명 툴팁은 실제 HUD로 검수할 수 있습니다.

이 데모에서 정상 해금되는 재화 HUD는 금화·조달 증서·훈장입니다. 은반지는 5단계 퀘스트 게시판, 마나는 6단계 마법 부여사 해금이 필요하므로 검수 상태에서 강제로 해금하지 않습니다.

`forest_tab`은 원래 `ShowCrew`가 선택 테두리도 갱신합니다. rc3의 세 분류 캡처를 대조해 정상 이동을 확인했습니다. 작업자 화면의 `999%`는 숲 전쟁 1단계 전의 원본 차단 표시입니다. 활성 작업반 확인에는 `forest_fixture`를 씁니다.

검수 상태 명령은 `.fixture.json`에 격리 회사·제품·저장 경로, 변경 범위와 전후 상태를 남깁니다. `economy_fixture`는 `AddCurrency(...,isIncome:false)`로 잔액만 늘리고 수입 통계·해금·공급량은 직접 바꾸지 않습니다. `forest_fixture`는 전쟁 단계·진행도와 작업자 배정을, `war_fixture`는 단계·진행도·검수 병사와 원래 알림 메서드의 파생값을 다룹니다.

## 실제 문자 생성 검사

첫 메뉴에서 실행해야 첫 메뉴 글꼴 두 개도 로드된 상태로 확인할 수 있습니다.

```powershell
python tasks/KINGDOM_INC_DEMO/tools/qa_session.py command --output working_private/KINGDOM_INC_DEMO/qa03/qa_qa03 --action font_check --value "C:\Users\PC\Documents\ChatGPT\한글패치\working_private\KINGDOM_INC_DEMO\translation\required_characters.json"
```

입력은 유니코드 정수 배열 JSON 또는 필요한 실제 문자가 들어 있는 UTF-8 텍스트입니다. `pixel16`, `pixel16 NN`, `LiberationSans SDF`, `LiberationSans SDF - Fallback` 네 폰트를 필수로 검사합니다. 결과 `.fonts.json`에 입력 해시, 문자수, 동적 문자 추가 성공 여부, 직접 문자표의 누락, 폴백 포함 누락, 아틀라스 개수·크기·읽기 가능 여부, 재질 연결·쉐이더를 기록합니다. 정적 폰트에는 문자를 추가하지 않고 원래 문자표와 폴백 경로를 검사합니다. 탭·줄바꿈·BOM은 글리프 검사에서 제외하고 별도 기록합니다.

실패한 폰트가 하나라도 있으면 명령도 `FAIL`입니다. 원본 영문 비교 사본에서는 한글 글리프 검사를 생략하고, 같은 화면 명령을 실행해 공통 오류와 배치 차이를 비교합니다. 이 검사는 글리프 생성 증거이며 이미지 육안 확인을 대체하지 않습니다.

## 현재 준비 이력

- `probe/qa_probe01`: 최초 지원 코드. 키 설정 화면에서 바로 종료해 원본 게임의 객체 파괴 순서 오류가 발생했고, 글꼴 이미지 읽기 경고가 나옴. 화면 글자 배열이 Unity 직렬화에서 누락되어 해당 배열 증거는 사용할 수 없음.
- `probe02/qa_probe02`: 키 설정을 닫고 종료, 화면 글자 배열의 행별 기록, 창 위치 정보, 글꼴 이미지 읽기 경고 실패 판정 반영.
- 허용되지 않은 문구 변조를 넣은 검사기 시험: `working_private/KINGDOM_INC_DEMO/qa_verifier_negative/result.json`. 정상 거부 확인.
- probe05의 `04-main-return.json` 확인: `texts` 74행, 비어 있지 않은 문구 74행, 활성 문구 8행. 배열 누락 해결 확인.
- 상세 화면 및 글리프 검사 추가는 `KoreanQA.dll` 안에서만 이루어졌습니다. 게임 DLL에 허용한 두 메서드 변경은 그대로 유지합니다.
