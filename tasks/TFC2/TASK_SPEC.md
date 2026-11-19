# TFC2 완전 한글화 작업 명세

아래는 빌드 25097525 작업의 대상·허용 범위 기록이다. 신규 수정판의 공통 절차와 게이트는 [핵심 지침서](../../docs/KOREAN_PATCH_PLAYBOOK.md)를 적용한다. 새 기준 통합 재검증과 코드 보완은 [현재 상태](../../PROJECT_STATUS.md)에서 구분한다.

## 대상 기준선

- 게임: TFC2: The Fertile Crescent 2 - Collapse of the Bronze Age
- Steam 앱 ID: `4158610`
- Steam 빌드 ID: `25097525`
- Unity: `6000.2.9f1`
- 실행 방식: `IL2CPP`
- Addressables: `2.7.4`
- 원본 설치 경로: `D:\steam\steamapps\common\The Fertile Crescent 2`
- 작업 기준선: `source_original/TFC2_BUILD_25097525`

## 목표

게임 자체에서 표시되는 영어 문구를 자연스러운 한국어로 번역하고, 한글 글꼴을 안전하게 표시하며, 원본 파일을 포함하지 않는 차이 패치 설치본을 만든다.

## 조사 범위

1. Localization StringTable 전체
2. 장면·프리팹의 TMP/Text 직접 문구
3. `resources.assets`, `sharedassets*.assets`, `level*` 직렬화 문자열
4. IL2CPP `global-metadata.dat` 문자열과 실제 사용 메서드
5. 화면에 표시되는 enum 이름과 런타임 조합 문구
6. 개발·예비·접근성 화면
7. Texture2D, Sprite, VideoClip 등 미디어 삽입 문구
8. 실제 사용 TMP FontAsset, Source Font, Atlas, Material, Fallback 의존 관계

모든 조사 항목은 `VISIBLE_TRANSLATE`, `VISIBLE_KEEP`, `INTERNAL`, `MEDIA`, `UNKNOWN` 중 하나로 분류한다. `UNKNOWN`이 남으면 릴리스하지 않는다.

## 변경 허용 경계

- 번역된 StringTable과 직접 표시 문자열
- 한국어 표시에 필요한 글꼴·TMP FontAsset·폴백 설정
- 수정된 Addressables 묶음을 로드하기 위한 카탈로그 정보
- 런타임 조합 문구를 번역하거나 폴백 글꼴을 초기화하는 데 꼭 필요한 코드/메타데이터
- 실제 화면에 영어가 픽셀로 포함된 이미지·영상

게임 규칙, 수치, 저장 데이터 형식, 네트워크 동작, 도전 과제 조건은 변경하지 않는다.

## 검증 게이트

- 원본과 작업 기준선 130개 Windows 파일의 크기·SHA-256 일치
- No-op round-trip 및 수정 자산 재열기 성공
- 번역 대상 누락·원문 잔존·제어 토큰 차이 각 0건
- `UNKNOWN` 0건
- IL2CPP를 수정하면 Cpp2IL 또는 동급 도구 재분석 성공
- 전체 한국어 말뭉치의 필요한 글리프 0건 누락
- 실제 사용 동적 TMP 글꼴의 Source Font·다중 아틀라스·폴백 유효성 확인
- xdelta 정방향·역방향 해시 일치
- 원본·변조·중복 설치·제거·이전 패치 조건을 격리 복사본에서 시험
- 후보 복사본을 그래픽 모드로 실행하고 첫 화면, 설정, HUD, 대화, 결과·종료 화면 확인
- 실행 프로세스 경로가 후보 복사본인지 확인
- Player.log의 한글 글리프 누락과 패치 고유 로딩 오류 각 0건
- 사용자 저장 데이터 실행 전후 무결성 확인

## 현재 상태

2026-09-04 기준 1.0.0 정적·설치·대표 흐름 실행 검증 기록이 있다. [당시 최종 보고](../../validation/TFC2/final_release_validation.json)와 [실행 범위](../../validation/TFC2/runtime_qa_report.json)를 참조한다. 전체 캠페인·분기 검증이나 2026-09-05 공통 기준의 통합 재검증 완료를 뜻하지 않는다.
