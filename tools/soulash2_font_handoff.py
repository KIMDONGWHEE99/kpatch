"""글꼴 검사 범위와 의도한 외형 변경을 서로 구분해 인계한다."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "working_private/SOULASH_2/font_probe/release_20261030_v1"


def ref(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    independent = json.loads((HERE / "independent_validation.json").read_text(encoding="utf-8"))
    corpus = json.loads((HERE / "corpus_01/coverage_report.json").read_text(encoding="utf-8"))
    atlas = json.loads((HERE / "corpus_01/atlas/report.json").read_text(encoding="utf-8"))
    assert corpus["status"] == atlas["execution_status"] == "PASS"
    cases = [s for f in atlas["fonts"] for s in f["scenarios"]]
    assert all(c["all_fit_with_glyph_coverage"] and c["preload_missing_count"] == 0 for c in cases)
    ui = independent["fonts"][0]
    assert all(v for k, v in ui["checks"].items() if k != "sdl_line_advance_equal")
    assert all(s["line_equal"] for s in ui["sdl"])
    assert all(f["status"] == "PASS" for f in independent["fonts"][1:])
    paths = [HERE / "build_report.json", HERE / "independent_validation.json", HERE / "corpus_01/coverage_report.json", HERE / "corpus_01/required_codepoints.json",
             HERE / "corpus_01/atlas/report.json", HERE / "cpu_preview/comparison_26.png", HERE / "FONT_NOTICES.txt"]
    result = {"created_utc": datetime.now(timezone.utc).isoformat(), "scope": "정적 글꼴 및 지정 말뭉치의 CPU 용량 검사", "static_character_coverage": "PASS", "atlas_capacity": "PASS",
              "runtime_qa": "NOT_RUN", "whole_patch_release_ready": False, "tool": ref(Path(__file__)),
              "mapping": [{"game_file": "data/mods/core_2/assets/fonts/" + f["source"], "font": ref(HERE / "fonts" / f["output"])} for f in json.loads((HERE / "build_report.json").read_text(encoding="utf-8"))["files"]],
              "counts": {"translation_rows": corpus["rows"], "required_codepoints": corpus["required_codepoints"], "union_with_preload": atlas["requested_unique"], "atlas_cases": len(cases),
                         "atlas_failures": 0, "maximum_used_bottom_of_2048": max(s["capacity"]["used_bottom"] for s in cases), "modern_hangul_syllables_per_font": 11172},
              "intentional_ui_font_change": {"original_exact_rendering_equivalence": "FAIL", "reason": "Romulus 윤곽을 포함하지 않는 OFL 전용 Noto 글꼴로 변경해 저작물 출처를 명확히 함", "hmtx_numeric_advances_preserved": True,
                                             "sdl_line_metrics_preserved_at_all_six_sizes": True,
                                             "max_sdl_advance_pixel_difference": max(abs(x["advances"][0] - x["advances"][1]) for s in ui["sdl"] for x in s["advance_differences"]),
                                             "risk": "영문 숫자 스타일과 실제 폭이 달라져 메뉴·수치 칸의 게임 화면 재검수가 필요"},
              "cpu_preview_review": {"image": ref(HERE / "cpu_preview/comparison_26.png"), "method": "제작자가 이미지 직접 판독", "observed": "새 기본과 보조2종 모두 한글·영문·숫자 혼용 표본이 읽히며 표본의 상자 대체·잘림 없음", "scope": "CPU 표본만;게임 GPU 검수 아님"},
              "license": {"status": "OFL_ONLY_FONT_SOURCES", "romulus_outlines_copied": 0, "notices": [ref(p) for p in sorted(HERE.glob("*-OFL.txt"))] + [ref(HERE / "FONT_NOTICES.txt")],
                          "user_facing_recommendation": "기본 글꼴 표시명은 한글 기본, 보조 표시는 한글 보조 등으로 바꾸고 원본 Lato/Romulus 상품명으로 표시하지 않음"},
              "evidence": [ref(p) for p in paths], "limitations": ["보류201위치의 후속 번역이나 네이티브 추가 문구가 생기면 문자집합을 다시 확인", "대화 입력 등 사용자 임의 문자를 모두 동시에 적재하는 시험이 아님", "전체 게임 화면 및 모든 분기 검수가 아님"]}
    with (HERE / "qa_handoff.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
