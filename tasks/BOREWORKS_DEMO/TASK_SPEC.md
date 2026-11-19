# Boreworks Demo 한국어 패치 작업 명세

작성일: 2026-09-12 · 원본: Steam 23942533 · 앱: 4829140

사용자 요청은 지정된 Steam 설치본의 한글패치 제작과 적용입니다. 검증을 통과한 뒤 해당 설치본에 적용하며 외부 공개는 요청 범위에 없습니다.

공통 절차는 [핵심 지침서](../../docs/KOREAN_PATCH_PLAYBOOK.md)와 [실행 검수 참조](../../docs/KOREAN_PATCH_RUNTIME_QA_REFERENCE.md)를 따릅니다.

- 실행 구조: Windows x64, Godot 4.6.3, .NET 8/C#, PCK v3. Unity 전용 검사 항목은 해당하지 않으며 PCK 목록·C# 메서드·Godot 글꼴 검사를 수행합니다.
- 기준선: `source_original/BOREWORKS_DEMO/steam_23942533`, 192개, 509,809,608바이트. 목록은 `working_private/BOREWORKS_DEMO/baseline.json`에 보관합니다.
- 기준선 목록 SHA-256: `0d73f059aba35c021e9d59bb0f698d55d4ba41932c7a16d94d4060184ffae532`.
- 추출: `extracted_private/BOREWORKS_DEMO/steam_23942533`. PCK 1,014개 파일의 MD5를 대조했습니다.
- 작업·번역·원시 검수 증거: `working_private/BOREWORKS_DEMO`. 후보는 `build_candidate/BOREWORKS_DEMO/<고유 후보 ID>`.
- 조사 범위: 영어 Translation, 장면의 직접 문구, 모든 게임 C# 어셈블리의 문자열·enum·런타임 조합, 개발/오류/접근성 화면, 이미지와 글꼴. 미확인 항목은 UNKNOWN으로 기록합니다.
- 허용 변경: 표시 문구, 언어 설정, 한글 글꼴과 필요한 연결. 게임 규칙·수치·저장 형식·업적 조건은 변경하지 않습니다.
- 소규모 시험: PCK 무변경 재구성과 변경 경계 검사, 영어 표의 소수 문구를 한국어로 넣어 글꼴·실제 로딩 확인. 통과 전 대량 번역을 진행하지 않습니다.
- 실행 검수: 저장 경로와 Steam 연결을 코드에서 확인하여 사본의 저장·로그·클라우드 쓰기를 격리하고 실제 프로세스 경로와 전후 저장 해시를 기록합니다. 시작·설정·새 게임·HUD·도움말·일시정지·결과·종료를 확인하며 미도달 화면은 미검증으로 남깁니다.
- 정적 검수: 후보에서 다시 추출한 위치별 번역, 태그 순서·중첩·자리표시자·줄바꿈, 전체 한글 문자 지원, 미허용 코드·자산 변경을 검사합니다.
- 설치: 원본 백업, 버전·해시 거부, 중간 실패 복구를 지원하는 차이 패치. 최종 ZIP에서 추출한 설치기로 정상·중복·제거·변조·부분 설치·중단 복구·한글 공백 경로를 시험합니다.
- 원본과 파생 자산은 비공개 4개 영역 밖에 두지 않습니다. 공유 보고서는 검토한 요약만 포함합니다.

| 단계 | 상태 | 근거 |
|---|---|---|
| G0 | PASS | 결과 보고서 및 EVIDENCE_INDEX.json |
| G1 | PASS | 결과 보고서 및 EVIDENCE_INDEX.json |
| G2 | PASS | 결과 보고서 및 EVIDENCE_INDEX.json |
| G3 | PASS | 결과 보고서 및 EVIDENCE_INDEX.json |
| G4 | PASS | 결과 보고서 및 EVIDENCE_INDEX.json |
| G5 | PASS | 결과 보고서 및 EVIDENCE_INDEX.json |
| G6 | PASS | 결과 보고서 및 EVIDENCE_INDEX.json |
| G7 | PASS | 결과 보고서 및 EVIDENCE_INDEX.json |
| G8 | PASS | 결과 보고서 및 EVIDENCE_INDEX.json |
