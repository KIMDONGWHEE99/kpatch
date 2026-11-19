# 세븐데이즈투다이 Vanilla Plus 한국어 번역

대상: Vanilla Plus 1.6.0 · 한국어 패치 0.1.0 · 작성일: 2026-09-06

현재 제공 방식은 **한국어가 미리 적용된 모드 통합본**입니다. 사용자가 모드만 설치하면 되도록 요청하여 원본 19개 파일 중 번역표 하나를 검증된 한국어 파일로 교체했습니다. ZIP의 VanillaPlus 폴더를 Mods에 넣으면 되며, 게임 언어는 한국어로 사용합니다.

- 통합 ZIP: `build_candidate/SEVENDAYS_VANILLAPLUS/integrated_0.1.0_28a6c1cb/VanillaPlus_1.6.0_Korean_Integrated.zip`
- [통합본 검증 결과](../../validation/SEVENDAYS_VANILLAPLUS/integrated_0.1.0_28a6c1cb/RESULT_REPORT.md)
- 기존 차이 패치 ZIP은 이력으로 보존합니다. 통합본에는 별도 적용기 실행이 필요하지 않습니다.

사용자 제공 ZIP의 번역표 4,235개 항목을 한국어로 제작합니다. 기본 게임과 원문이 같은 항목은 설치된 게임의 공식 한국어를 참고하며, 모드 고유 이름·효과 설명은 별도로 번역합니다.

사용자의 현재 지시인 **“번역본 제작 해주시고 실제 플레이테스트는 제가 직접하겠습니다”**에 따라 실제 게임 실행은 제작 범위에서 제외합니다. 정적 검사(게임을 실행하지 않고 파일과 문구를 대조하는 검사) 결과와 실제 화면 미검증을 구분합니다. 공개 배포·게임 설치·저장 변경은 요청받지 않았습니다.

- [작업 명세](TASK_SPEC.md)
- [설정](GAME_CONFIG.yaml)
- 도구: `tools/prepare.py`, `tools/build.py`, `tools/validate.py`, `tools/package.py`
- 비공개 번역 원본: `working_private/SEVENDAYS_VANILLAPLUS/ko_0.1.0`
- 원본: `source_original/SEVENDAYS_VANILLAPLUS/1.6.0`
- 후보: `build_candidate/SEVENDAYS_VANILLAPLUS/ko_0.1.0`

번역 대상은 모드가 제공하는 언어 표입니다. 기본 게임 이미지의 간판·로고 픽셀은 이 패치의 수정 대상이 아닙니다. 모드에는 새 이미지·영상·DLL이 포함되어 있지 않습니다.
