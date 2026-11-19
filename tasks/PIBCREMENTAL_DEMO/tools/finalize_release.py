"""모든 검증 결과가 통과했을 때만 배포 보고서와 검증된 ZIP을 만듭니다."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VALIDATION = ROOT / "validation/PIBCREMENTAL_DEMO"
RELEASE = ROOT / "release_output/PIBCREMENTAL_DEMO_KOREAN_PATCH_1.0.0"
ARCHIVE = ROOT / "release_output/Pibcremental_Demo_Korean_Patch_v1.0.0.zip"


def load(name: str) -> dict:
    return json.loads((VALIDATION / name).read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> None:
    static = load("candidate_static_validation.json")["summary"]
    audit = load("final_audit_summary.json")["summary"]
    runtime = load("graphical_qa_report.json")
    delta = load("release_xdelta_validation.json")
    installer = load("installer_test_report.json")
    if not static["all_static_gates_passed"] or audit["unknown"] != 0:
        raise RuntimeError("정적 검사 또는 문자열 분류가 통과하지 못했습니다.")
    if not runtime["representative_graphical_qa_passed"]:
        raise RuntimeError("대표 화면 그래픽 검증이 통과하지 못했습니다.")
    if not delta["passed"] or not installer["passed"] or installer["tests"] != 12:
        raise RuntimeError("차이 패치 또는 설치기 12종 검증이 통과하지 못했습니다.")
    if ARCHIVE.exists():
        raise RuntimeError(f"배포 ZIP이 이미 있습니다: {ARCHIVE}")

    report = f"""Pibcremental Demo 한국어 패치 1.0.0 검증보고서
검증일: 2026-09-02

대상 빌드
- Steam 앱: 4780080 / 빌드: 25008003 / 표시 버전: 27.08.01
- Unity 6000.4.0f1 / Mono 실행 방식 / Addressables 2.9.1
- 원본 212개 파일, 총 132,505,966바이트를 격리 복사하고 크기·SHA-256 기록
- 원본 복사본 변경 0건 / 후보 변경 파일 7개 / 그 외 205개 파일 동일

문자열·정적 검사
- Localization 원문 1,183종 번역, 영어·독일어 테이블 각각 2,093개 값 확인
- 직접 표시 문구 {static['direct_unique']}종, {static['direct_target_occurrences']}개 위치 적용
- 코드 문구 36종, 39개 위치 적용
- 문자열·미디어 분류 {audit['records']:,}개 기록 / 번역 대상 위치 {audit['classification_counts']['VISIBLE_TRANSLATE']:,}건
- 미분류 0건 / 번역 대상 원문 잔존 0건 / 태그·토큰·자리표시자·줄바꿈 차이 0건
- 수정 자산과 코드 다시 열기 통과 / 변경된 현지화 묶음 3개의 카탈로그 검증 통과
- 이미지 24개 접촉 시트 검수: 번역할 일반 픽셀 영문 없음
  게임명·제작사 로고와 장식 낙서는 고유 표기로 유지

글꼴 검사
- 기존 TMP 글꼴 자산 12개를 보존하고 Noto Sans KR 한글 폴백을 실행 중 추가
- 전체 번역에 필요한 문자 {static['required_glyphs']}자, 누락 0자
- 동적 글자 생성과 다중 아틀라스(글자를 담는 이미지) 활성화
- 실제 실행 로그 3개에서 한글 글리프 누락·아틀라스 오류·예외·카탈로그 로딩 오류 0건

실제 그래픽 검증
- 첫 화면, 버전 표기, 설정, 창 모드·무제한 FPS, 언어 표시, 인트로,
  HUD·튜토리얼 대화, 피블 바위, 게임 내 종료 메뉴, 데모 완료·감사 표시 확인
- 최종 후보의 추가 번역은 첫 화면·설정·HUD·데모 감사 표시에서 재확인
- 실제 실행 경로가 격리된 검수 복사본임을 프로세스 경로로 확인
- 검수 제품명과 저장 경로 분리. 데모 완료 화면은 검수 저장의 나무 레벨 7과
  완료 요구 수 0을 사용해 접근했으며, 최종 화면 검수에서 Steam 통계 전송 비활성화
- 이러한 검수 전용 변경은 정식 후보·배포 차이 패치에 포함되지 않음
- 기존 진행·설정·자동 저장 메타데이터 변경 0건
- 초기 실행에서 기본 Player.log 갱신 및 Player-prev.log 생성만 발생
  이후에는 실행 로그도 작업 폴더로 분리
- Event System 중복, GraphicRaycaster 미설정, DontDestroyOnLoad 관련
  비치명적 경고는 관찰되었으나 한글 출력·현지화 로딩 오류는 없었음

배포·설치기 검사
- 7개 파일의 정방향·역방향 VCDIFF를 즉시 복원해 총 14번 해시 일치 확인
- 격리 복사본 설치기 시험 12종 통과:
  원본 설치, 중복 설치, 제거, 부분 설치 재개, 재개 후 제거, 부분 설치 제거,
  변조 파일 거부, 중복 제거, 다른 빌드 파일 거부, 잘못 지정한 폴더 거부,
  손상된 차이 패치 거부, 원본 게임 파일 미포함
- 거부 시험에서는 게임 파일을 바꾸지 않은 것까지 확인
- 최초 공개판이므로 이전 공개 패치에서의 갱신 시험은 해당 없음
- 배포에는 설치·제거기, 차이 패치, 문서, 라이선스만 포함

유지 표기와 검증 범위
- Pibcremental, Arcane Cabinet, Grab The Games, Discord, 제작진 인명·닉네임,
  곡명, URL, Cmaj13, CU3, S.N.A.F.U, FPS·XP·PP, 숫자 단위·조작 키 등 유지
- Steam 자체 상점·도전 과제 팝업처럼 게임 파일 밖의 문구는 대상이 아님
- 독일어 테이블은 전 항목 한국어로 정적 검증했지만 실제 언어 슬롯 전환은 미확인
- 모든 회차·분기의 전체 플레이 검증이나 이미지 로고 한글화 완료를 뜻하지 않음
"""
    (RELEASE / "검증보고서.txt").write_text(report, encoding="utf-8-sig")

    paths = sorted(path for path in RELEASE.rglob("*") if path.is_file())
    forbidden = {".dll", ".assets", ".unity3d", ".bundle", ".ttf", ".otf"}
    if any(path.suffix.lower() in forbidden for path in paths):
        raise RuntimeError("배포에 게임 자산 또는 원본 글꼴 파일이 들어 있습니다.")
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in paths:
            archive.write(path, path.relative_to(RELEASE).as_posix())
    with zipfile.ZipFile(ARCHIVE) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP의 CRC 검증에 실패했습니다.")
        for path in paths:
            relative = path.relative_to(RELEASE).as_posix()
            actual_hash = hashlib.sha256(archive.read(relative)).hexdigest().upper()
            if actual_hash != sha256(path):
                raise RuntimeError(f"ZIP 내용 해시가 다릅니다: {relative}")
    package_report = {
        "schema_version": 1,
        "passed": True,
        "archive": str(ARCHIVE),
        "archive_bytes": ARCHIVE.stat().st_size,
        "archive_sha256": sha256(ARCHIVE),
        "files": len(paths),
        "zip_contents_verified": True,
        "forbidden_game_payloads": [],
    }
    (VALIDATION / "release_package_report.json").write_text(
        json.dumps(package_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (ARCHIVE.parent / f"{ARCHIVE.name}.sha256.txt").write_text(
        f"{package_report['archive_sha256']}  {ARCHIVE.name}\n", encoding="ascii"
    )
    print(json.dumps(package_report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
