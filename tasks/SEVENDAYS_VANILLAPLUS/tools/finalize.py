import hashlib
import json
from pathlib import Path
import sys

from build import BASE, CANDIDATE, ROOT, WORK, GAME


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    out = ROOT / 'validation' / GAME / 'ko_0.1.0'
    static = json.loads((out / 'static_checks.json').read_text(encoding='utf-8'))
    tests = json.loads((out / 'package_checks.json').read_text(encoding='utf-8'))
    package = json.loads((WORK / 'package_info.json').read_text(encoding='utf-8'))
    assert static['status'] == tests['status'] == 'PASS'
    data = (CANDIDATE / 'VanillaPlus/Config/Localization.csv').read_bytes()
    assert sha(data) == static['candidate_sha256'] == tests['candidate_sha256']
    assert sha(Path(package['path']).read_bytes()) == package['sha256'] == tests['zip_sha256']
    frozen = CANDIDATE.parent / ('ko_0.1.0_final_' + sha(data)[:8]) / 'VanillaPlus/Config/Localization.csv'
    frozen.parent.mkdir(parents=True, exist_ok=True)
    if frozen.exists():
        assert frozen.read_bytes() == data
    else:
        frozen.write_bytes(data)
    inputs = [BASE / 'manifest.json', BASE / 'base_game_Localization.csv', BASE / 'base_XUi_InGame_windows.xml',
        WORK / 'canonical_translation.json', WORK / 'units.json', WORK / 'decor_unique.txt', WORK / 'ko_decor.tsv']
    inputs += sorted(WORK.glob('ko_units_*.tsv'))
    inputs += sorted(Path(__file__).parent.glob('*.py')) + [Path(__file__).with_name('Patch.ps1')]
    manifest = {'game_id': GAME, 'build_id': 'ko_0.1.0_final_' + sha(data)[:8],
        'files': [{'path': str(p.relative_to(ROOT)).replace('\\', '/'), 'sha256': sha(p.read_bytes()), 'size': p.stat().st_size} for p in inputs + [frozen, Path(package['path'])]],
        'static_checks_sha256': sha((out / 'static_checks.json').read_bytes()),
        'package_checks_sha256': sha((out / 'package_checks.json').read_bytes()),
        'runtime_status': 'NOT_RUN', 'runtime_reason': '사용자가 직접 실제 플레이 테스트를 수행하도록 요청함'}
    (out / 'final_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    report = f'''# Vanilla Plus 1.6.0 한국어 번역 0.1.0 결과

작성일: 2026-09-06 · 용도: 사용자 플레이 테스트용 로컬 번역본

**번역표 4,235개 항목 작성, 정적 검사, 최종 ZIP 설치·복구 시험 {tests['count']}건을 완료했습니다. 실제 게임 실행은 하지 않았습니다.** 사용자가 직접 플레이 테스트하겠다고 요청한 범위를 따랐습니다. 일반 공개 업로드와 실제 모드 설치는 수행하지 않았습니다.

## 파일과 사용 방법

- 패키지: release_output/VanillaPlus_1.6.0_Korean_0.1.0.zip ({tests['zip_size']:,}바이트)
- ZIP SHA-256: `{tests['zip_sha256']}`
- 고정 번역표: `{str(frozen.relative_to(ROOT)).replace(chr(92), '/')}`
- [사용 안내](../../../release_output/SEVENDAYS_VANILLAPLUS/ko_0.1.0/사용방법.txt)

ZIP을 모두 풀고 적용.cmd를 실행해 **설치한 VanillaPlus 모드의 Config/Localization.csv**를 선택합니다. 게임 언어는 한국어로 사용합니다. 제거.cmd는 같은 파일을 원문으로 복구합니다. 별도 Python 설치는 필요하지 않습니다.

## 변경 범위

아이템 556개, item_modifiers 분류 12개, 블록·장식 3,279개, 상태 효과 5개, 특성·제작 안내 378개, 차량 분류 5개로 총 4,235개입니다.

기본 게임과 영어가 같은 3,041개 항목에 공식 한국어를 연결하고, 모드 고유 항목 1,194개를 따로 번역했습니다. 공식 번역을 참고한 102개는 화면용 약어 등을 다듬었습니다. 무기 모델명만으로 된 6개 항목은 식별 표기를 유지했습니다.

모드 Localization.csv의 koreana 열만 수정했습니다. 나머지 19개 열의 80,465개 값과 행 순서·내부 키를 보존했습니다. XML·제작법·능력치 설정·DLL·글꼴·이미지·실제 게임 설치본·사용자 저장·설정에는 쓰지 않았습니다.

## 검증

| 항목 | 결과 |
|---|---|
| 원본 | ZIP CRC, 모드 파일 19개 크기·SHA-256 고정·대조 PASS |
| 재추출 | 독립 CSV 파서로 4,235행 × 20열 재열기 PASS |
| 위치별 번역 | 기대값 전부 일치, 빈 값·누락·중복·위치 교환 0 |
| 형식 | 색상 태그 순서·중첩, 숫자·부호·퍼센트, 제어 줄바꿈·자리표시자 오류 0 |
| XML | 18개 해석 성공, 명시적 번역 참조 1,231곳 누락 0 |
| 동적 슬롯 | 기본 UI 사용 위치 5개·번역 키 2개와 한국어 값 확인 |
| 검사기 | 빈 값·위치 교환·다른 열·행 삭제·중복·태그·숫자 결함 7종 검출 |
| 패키지 | 허용 파일 7개·개별 해시 확인, 원본 게임 자산·검수 코드 미포함 |
| 설치·복구 | 최종 ZIP에서 꺼낸 실제 설치기로 {tests['count']}건 PASS |
| 실제 게임·글꼴 출력 | NOT_RUN — 사용자 직접 테스트 요청 |

근거: [정적 검사](static_checks.json), [최종 ZIP 시험](package_checks.json), [최종 파일 목록](final_manifest.json).

설치 시험은 정상 설치·중복 설치·제거·중복 제거·재설치·백업 없는 제거·변조 거부·부분 적용 거부·다른 버전 거부·차이 파일 손상 거부·다른 백업 거부·파일 잠금 교체 실패·실패 후 재시도·교체 전/후 중단 상태·부분 임시 파일 보관 후 재시도·부분 백업 복구·적용 CMD·제거 CMD입니다. 한글·공백 경로의 격리 사본에서 수행했고 주변의 무관한 시험 파일도 보존했습니다.

중단은 해당 파일 상태를 만들어 재현했으며 실제 프로세스 강제 종료 시험으로 주장하지 않습니다. 파일 선택 대화상자의 UI는 미검증이며 동일 설치기의 직접 경로 지정과 CMD 실행기는 시험했습니다.

## 유지 표기와 미검증

SMG5·AK47·M60, R 키, 단위·규격, A/B/C·T 구분, LED·OSB·TFP 및 일부 상표·로고 이름은 유지했습니다. XML의 Vanilla + 브랜드, ModInfo의 원본 영어 소개·저자 정보도 유지했습니다. SMELTING·TOOLS·Empty는 기존 한국어 키를 참조하는 구조를 확인했습니다.

기본 게임 이미지에 그려진 간판·로고의 영문은 수정하지 않았습니다. 모드 ZIP에는 독립 이미지·영상·DLL이 없습니다. 전체 게임 코드나 이미지 픽셀까지 한글화한 결과로 확대하지 않습니다.

필요 문자 {static['required_characters']}종을 기록했습니다. 별도 글꼴 묶음을 읽었지만 해당 묶음만으로 실제 UI 전체의 글꼴 연결·문자 생성·출력을 입증하지 못하므로 글꼴 검사 전체 통과로 기록하지 않습니다. 게임 로딩·글자 깨짐·긴 이름 잘림·다른 모드와의 조합·멀티플레이는 미검증입니다.

## 기준선과 재현

- 원본 ZIP: `0ecd9323c633fe75648c0a0dd606951b3860af4c80a15b2330172a38a2fe91bd`
- 원문 CSV: `{static['source_sha256']}`
- 번역 CSV: `{static['candidate_sha256']}`
- 참고 게임: Steam build 24994517. 적용 지원은 제공된 VanillaPlus 1.6.0 파일 해시에 한정합니다.
- 도구 순서: prepare.py → build.py → validate.py → package.py → test_package.py → finalize.py.
- 번역 원본과 검토 목록은 working_private/SEVENDAYS_VANILLAPLUS/ko_0.1.0에 보관합니다.

이번 사용자 요청의 번역본 제작과 파일 검사를 완료했습니다. G0~G8 전체 완료판은 아니며 소규모 게임 로딩, 전체 글꼴 출력, G5와 공개 배포 판정은 NOT_RUN입니다.
'''
    (out / 'RESULT_REPORT.md').write_text(report, encoding='utf-8')
    status = ROOT / 'PROJECT_STATUS.md'
    text = status.read_text(encoding='utf-8')
    text = text.replace('갱신일: 2026-09-05 · 현재 작업: 공통 프로세스·문서 정비', '갱신일: 2026-09-06 · 현재 작업: Vanilla Plus 1.6.0 한국어 번역 0.1.0')
    old = '**핵심 지침서와 작성 양식 정비 완료. 검증 도구의 결함 수정과 기존 패치의 새 기준 재검증은 미완료.** 초기화만 된 프로젝트가 아니라 4개 게임의 작업·검증·배포 자료를 보유한 작업 공간입니다.'
    text = text.replace(old, '**Vanilla Plus 번역표 4,235개 항목과 파일 검사, 최종 ZIP 설치·복구 시험 19건 완료. 실제 플레이는 사용자 요청에 따라 사용자가 직접 테스트합니다.** 기존 공통 도구의 결함 수정과 기존 4개 게임의 새 기준 재검증은 별도 미완료 상태입니다.')
    text = text.replace('| 이번 작업의 실제 게임 실행·배포 수정 |', '| 2026-09-05 문서 작업의 실제 게임 실행·배포 수정 |')
    heading = '| 게임·패치 | 보유 검증 범위 | 알려진 미검증·제한 | 안내 |\n|---|---|---|---|'
    row = '| 7 Days to Die / Vanilla Plus 1.6.0 · 한국어 0.1.0 | 번역표 4,235개·참조 1,231곳 정적 검사, 최종 ZIP 설치·복구 19건 | 사용자 직접 플레이 테스트 예정. 실제 화면·로딩·글꼴 출력 미검증 | [게임 README](tasks/SEVENDAYS_VANILLAPLUS/README.md), [제작 결과](validation/SEVENDAYS_VANILLAPLUS/ko_0.1.0/RESULT_REPORT.md) |'
    if row not in text:
        text = text.replace(heading, heading + '\n' + row)
    status.write_text(text, encoding='utf-8')
    log = ROOT / 'WORK_LOG.md'
    text = log.read_text(encoding='utf-8')
    if 'SEVENDAYS-VANILLAPLUS-KO-001' not in text:
        text += '\n\n## 2026-09-06 — SEVENDAYS-VANILLAPLUS-KO-001\n\n- 사용자 제공 Vanilla Plus 1.6.0 번역표 4,235개 한국어 칸 제작. 실제 플레이 테스트는 사용자 요청에 따라 사용자가 수행.\n- 원본 ZIP·개별 파일 해시 고정, 기본 한국어 용어 연결, 모드 고유 설명 교정. 숫자·태그·위치·행 구조 검사 PASS.\n- 최종 ZIP 설치·복구 19종 PASS. 임시 쓰기 중단·부분 백업은 보관 후 복구, 미지원 입력은 거부. 게임 설치본·저장·설정·공개 업로드 변경 없음.\n- 결과: [제작 보고서](validation/SEVENDAYS_VANILLAPLUS/ko_0.1.0/RESULT_REPORT.md). 실제 게임 로딩·글꼴·레이아웃 NOT_RUN.\n'
        log.write_text(text, encoding='utf-8')
    print('고정 파일:', str(frozen))
    print('최종 ZIP:', package['sha256'])
    print('정적 검사 PASS / 패키지 검사', tests['count'], 'PASS / 실제 실행 NOT_RUN')


if __name__ == '__main__':
    main()
