# Soulash 2 배포 도구 사용 계약

이 폴더의 설치기는 Steam 앱2399160·빌드25967323·게임0.10.4.0.1 전용입니다. 공개 패키지는 설치·제거 도구, 라이선스, 해시 목록, 정·역방향 차이 파일만 포함합니다. 게임 원본·수정 완성 자산·검수 저장·검수 코드는 포함하지 않습니다.

## 현재 구현 범위

`tools/soulash2_release_package.py`는 원본·후보 전 파일을 대조하고 차이 파일을 생성하자마자 정·역방향으로 복원합니다. ZIP을 고정하고 별도 폴더에 추출한 뒤 지문을 대조합니다. 후보 경로는 `build_candidate/SOULASH_2` 안으로, 중간 복원 파일은 `working_private/SOULASH_2` 안으로 제한합니다.

`Patch.ps1`은 실제 게임이 실행 중인 경우, 미지원 빌드·변조·누락 파일, 손상된 차이 도구·파일을 거부합니다. 교체 전 전 파일을 준비하고, 원자적 교체(파일이 반만 기록되는 일을 줄이는 교체 방식)와 거래 기록으로 실패·강제 중단 뒤 복구합니다. 백업이 없어도 역방향 차이 파일로 원본을 복원할 수 있습니다. 사용자가 추가한 저장·무관한 파일은 변경하지 않습니다.

`tools/soulash2_release_installer_test.py`는 ZIP에서 꺼낸 설치기를 검수 사본에만 실행합니다. `LOCALAPPDATA`를 시험 폴더로 지정하여 사용자 백업·설정에 쓰지 않습니다. 실제 게임 프로세스나 사용자 설치본을 실행·수정하지 않습니다. 실행 중 거부 시험은 Windows 명령 처리기를 이름만 바꾼 합성 대기 프로세스입니다.

## 후보 고정과 완료 증거

실제 후보 패키징에는 `--release-gate`가 필수입니다. 보고서가 같은 후보 전체 목록과 연결되고 `G4`·`G5`가 모두 유효해야 합니다. `PASS` 문구만 적힌 임의 보고서를 만들지 않습니다. 실제 검수 결과를 아래 계약으로 연결합니다.

후보 목록에는 `game_id`, `steam_build`, `candidate_id`, `files` 배열을 기록합니다. 각 파일은 `path`, `size`, `sha256`을 가져야 합니다. G4·G5 보고서는 `status`와 동일한 `candidate_manifest_sha256`을 포함합니다.

```json
{
  "game_id": "SOULASH_2",
  "steam_build": "25967323",
  "status": "PASS",
  "candidate_id": "최종_고유_후보_ID",
  "candidate_manifest": {"path": "working_private/SOULASH_2/최종목록.json", "sha256": "실제_지문"},
  "allowed_changes": ["data/mods/core_2/messages.json"],
  "checks": {
    "G4": {"status": "PASS", "path": "working_private/SOULASH_2/정적검사.json", "sha256": "실제_지문"},
    "G5": {"status": "PASS", "path": "working_private/SOULASH_2/화면검수.json", "sha256": "실제_지문"}
  },
  "dependencies": [
    {"path": "extracted_private/SOULASH_2/0.10.4.0.1_20261029/baseline_manifest.json", "sha256": "실제_지문"},
    {"path": "working_private/SOULASH_2/최종번역원본.jsonl", "sha256": "실제_지문"}
  ]
}
```

`dependencies`에는 원본 목록·공식 번역 원본·생성 및 검증 도구·글꼴 등 실제 보고서가 의존하는 입력을 모두 넣습니다. 위 배열은 형식 예시이며 완전한 입력 목록이 아닙니다. `allowed_changes`는 실제 검수한 변경 경계 전체를 명시해야 합니다.

```powershell
python tools/soulash2_release_package.py --candidate build_candidate/SOULASH_2/최종후보 --baseline-manifest extracted_private/SOULASH_2/0.10.4.0.1_20261029/baseline_manifest.json --release-gate working_private/SOULASH_2/완료증거.json --version 1.0.0 --revision r1 --readme tasks/SOULASH_2/release_template/README.txt
python tools/soulash2_release_installer_test.py --package-report working_private/SOULASH_2/package_1.0.0_r1/package.json
python tools/soulash2_release_audit.py --package-report working_private/SOULASH_2/package_1.0.0_r1/package.json --candidate build_candidate/SOULASH_2/최종후보
```

최종 README는 제작용 문구를 제거하고 실제 변경·검수 범위로 완성합니다. 사용자 저장·설정 등 신규 파일이 후보에 있으면 무조건 배포하지 말고 경계를 다시 확인합니다. 정상적인 신규 패치 파일만 `--allow-added`로 하나씩 명시할 수 있습니다.

## 합성 시험

```powershell
python tools/soulash2_release_selftest.py --revision 새_시험_ID
python tools/soulash2_release_gate_test.py
```

합성 시험의 ZIP과 모든 자료는 `working_private/SOULASH_2/release_preparation` 안에만 생성됩니다. 합성 시험 통과는 설치기 기능의 근거이며 실제 후보의 G6·G7 완료가 아닙니다. 최종 후보 ZIP에서 같은 시험과 독립 감사를 다시 실행해야 합니다. 이전 공개 패치가 생기면 해당 버전의 업데이트 시나리오를 추가해야 합니다.
