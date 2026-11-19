# Nebula 비대화식 자료 추출

게임을 실행하지 않고 DAT 사본을 읽습니다. 원본 게임 폴더는 입력으로 사용하지 않고 `source_original` 또는 `working_private` 아래 사본을 지정합니다. 출력 폴더가 이미 있으면 실패하므로 과거 증거를 덮어쓰지 않습니다.

## 고정한 도구

- upstream: https://github.com/AITYunivers/NebulaFD
- commit: `a24d4d1da78c35412413faac750e07ff7d603a8a`
- .NET SDK: 8.0.418
- 소스 위치: `working_private/THE_HORDE_OF_GORAK/research/NebulaFD`
- 게임 파일 재저장에는 사용하지 않습니다. upstream의 `WriteCCN`은 대부분 미구현입니다.

## 읽기 도구 보정

`nebula_reader_fix.patch`는 게임이 아닌 추출기 소스 두 곳만 고칩니다.

1. 매개변수 26(프레임 번호)의 실제 저장 길이가 2바이트와 4바이트로 혼재합니다. 버전만 보고 4바이트로 읽던 코드를 실제 길이에 맞춰 선택합니다. 실제 게임의 24곳 중 11곳은 2바이트, 13곳은 4바이트였습니다.
2. 프레임 이동 설명을 만들 때 2바이트 형식만 받아 발생하던 형 변환 오류를 두 형식 모두 받도록 수정합니다.

이 보정 전의 `nebula_01`, 중간 `nebula_02`, 보정 후 `nebula_03`을 보존합니다. 보정 후 파싱 예외는 0건이지만 설명 변환의 미구현 항목은 906건 남았습니다. `nebula_03/unknown_description.jsonl`에 원시 이벤트 정보와 함께 보존하며, 별도 원시 이벤트 검사 결과와 연결해야 합니다. `summary.json`의 당시 `errors: 0`은 예외 수이며 전수 출처 판정 완료를 뜻하지 않습니다. 이후 도구 소스는 반환된 `[ERROR]`/`Unknown` 문구도 오류 대장에 포함하도록 수정했습니다.

## 사용 순서

프로젝트 루트에서 빌드합니다. 원본 소스 상태라면 `nebula_reader_fix.patch`를 먼저 적용합니다.

```powershell
dotnet build tasks/THE_HORDE_OF_GORAK/tools/NebulaExtract/NebulaExtract.csproj -c Release
dotnet tasks/THE_HORDE_OF_GORAK/tools/NebulaExtract/bin/Release/net8.0-windows/NebulaExtract.dll <DAT 사본> <새 비공개 출력 폴더>
```

마지막 인수로 `metadata-only`를 넣으면 PNG 변환을 생략하고 이미지 데이터의 내용 지문만 기록합니다. 실제 화면 검수가 아니며 이미지 판독 완료도 아닙니다.

## 산출물

- `input.json`: 입력 DAT 지문·도구 commit·시작 시각
- `package.json`: 객체·문단·프레임·이벤트·글꼴·이미지·음원 구조. 이진 배열은 크기와 지문으로 기록
- `frames/*.json`: 이벤트 조건·행동·매개변수·설명
- `extension_blobs/*.bin`: 확장 객체가 보관한 원문 이진 데이터
- `fonts/*.ttf`: 내장 글꼴, `fonts.json`에 지문과 논리 글꼴 목록
- `images/*.png`, `media.json`: 이미지와 원본 데이터 지문. `metadata-only`에서는 PNG 없음
- `errors.json`, `Logs/latest.log`: 예외·미지원 설명과 원시 로그

`extension_media_inventory.py`는 별도 원시 DAT 파서와 이 추출물을 대조하여 확장 문구의 정확한 바이트 위치를 기록하고 이미지 접촉판을 만듭니다. 접촉판 생성만으로 육안 검수 완료를 기록하지 않습니다.
