# SuperReap Demo 한국어 패치 자료

보유 패치 기준은 1.0.1이다. 글꼴 아틀라스 문제 수정, 정적·목록·설치 시험, 실제 첫 화면 그래픽 검증 기록이 있다. 현재 공통 절차는 [핵심 지침서](../../docs/KOREAN_PATCH_PLAYBOOK.md), 통합 상태는 [PROJECT_STATUS](../../PROJECT_STATUS.md)를 따른다.

- [글꼴 문제와 재발 방지 사례](../../docs/KOREAN_PATCH_RUNTIME_QA_REFERENCE.md)
- [당시 최종 게이트](../../working_private/SUPERREAP_DEMO/validation/final_gate.json)
- [원본과 배치 실행 비교](../../working_private/SUPERREAP_DEMO/validation/runtime_smoke_comparison.json)
- [1.0.1 설치기 시험](../../working_private/SUPERREAP_DEMO/validation/installer_validation_1.0.1.json)
- [첫 화면 캡처](../../working_private/SUPERREAP_DEMO/validation/candidate_font_fix_first_screen.png)

최종 게이트의 그래픽 증거는 첫 화면 중심이다. 배치 실행 통과를 HUD·대화·결과 등 대표 흐름 전체의 그래픽 검증으로 확대하지 않는다. 새 수정판에서는 실제 게임 빌드·기준선·도구 버전을 다시 확인하고 새 게이트에 맞는 증거를 확보한다.

도구 소스는 `tools`, 설치기 원형은 `release_template`에 있다. 기존 자료는 예전 폴더 체계를 사용하므로 이동 전에 스크립트와 보고서 참조를 확인한다. 위 비공개 증거 링크는 로컬 작업용이며 공개 패키지에 해당 자산을 포함하지 않는다.
