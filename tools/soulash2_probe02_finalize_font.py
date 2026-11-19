"""격리 후보 02의 세 글꼴만 병합본으로 교체하고 전체 파일 경계를 다시 검사합니다."""

import copy
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/python_deps"))
from fontTools.ttLib import TTFont
from soulash2_probe_build import TEXT

OUT = ROOT / "working_private/SOULASH_2/g1_probe_02"
FONT_DIR = ROOT / "working_private/SOULASH_2/font_probe/soulash_qa"
FONT = FONT_DIR / "SoulashKoreanQA-SemiBold.ttf"
FONT_SHA = "2dc2869175db8afb006233be96e937f2a081aef715dbe043fda3ebc2ac896d73"
FONT_PATHS = ["data/mods/core_2/assets/fonts/" + name
              for name in ("romulus.ttf", "Lato-Bold.ttf", "Lato-Regular.ttf")]
REPORT = OUT.with_name("g1_probe_02_preparation.json")
MANIFEST = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029/baseline_manifest.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert OUT.resolve().is_relative_to((ROOT / "working_private/SOULASH_2").resolve())
    previous = json.loads(REPORT.read_text(encoding="utf-8"))
    assert sha(FONT) == FONT_SHA
    merge = json.loads((FONT_DIR / "merge_report.json").read_text(encoding="utf-8"))
    atlas_path = FONT_DIR / "atlas_current_visible/report.json"
    atlas = json.loads(atlas_path.read_text(encoding="utf-8"))
    assert merge["status"] == "PASS" and merge["output"]["sha256"] == FONT_SHA
    assert merge["missing_required"] == []
    assert {row["codepoint"] for row in merge["additions"]} == {0x142, 0x15A}
    assert atlas["execution_status"] == "PASS" and atlas["graphics_qa"] == "NOT_RUN"
    assert all(row["font_sha256"] == FONT_SHA for row in atlas["fonts"])
    reopened = TTFont(FONT, recalcTimestamp=False)
    cmap = reopened.getBestCmap()
    required = set("".join(target for _, target in TEXT.values()) + "Artur Śmiarowski Miłosz")
    missing = sorted(ord(char) for char in required if not char.isspace() and ord(char) not in cmap)
    assert not missing
    assert "fvar" not in reopened and reopened["OS/2"].usWeightClass == 600
    font_record = {"path": str(FONT.relative_to(ROOT)), "sha256": FONT_SHA,
                   "bytes": FONT.stat().st_size, "weight": 600, "variable_tables_absent": True,
                   "cmap_count": len(cmap),
                   "hangul_syllables": sum(cp in cmap for cp in range(0xAC00, 0xD7A4)),
                   "actual_polish_credits": {"U+0142": 0x142 in cmap, "U+015A": 0x15A in cmap},
                   "required_missing": missing,
                   "names": {str(n): sorted({row.toUnicode() for row in reopened["name"].names if row.nameID == n})
                             for n in [0, 1, 2, 4, 6, 13, 14, 16, 17]}}
    reopened.close()
    assert sha(OUT / "Soulash 2.exe") == previous["qa_executable_sha256"]
    assert sha(OUT / "data/user_settings.json") == previous["settings_sha256"]
    for relative in FONT_PATHS:
        assert sha(OUT / relative) == previous["static_font"]["sha256"]

    # 이전 FAIL 상태는 이력으로 보존하며 현재 후보의 글꼴 3개만 바꿉니다.
    archive = REPORT.with_name("g1_probe_02_preparation.noto_only.json")
    assert not archive.exists()
    shutil.copyfile(REPORT, archive)
    for relative in FONT_PATHS:
        shutil.copyfile(FONT, OUT / relative)
        assert sha(OUT / relative) == FONT_SHA
    print(json.dumps({"stage": "MERGED_FONT_APPLIED", "font_sha256": FONT_SHA}), flush=True)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    baseline_paths = {entry["path"] for entry in manifest["files"]}
    added_paths = {"data/user_settings.json", "Soulash2_QA.lnk"}
    observed_paths = {path.relative_to(OUT).as_posix() for path in OUT.rglob("*") if path.is_file()}
    assert observed_paths == baseline_paths | added_paths
    assert {p.relative_to(OUT).as_posix() for p in OUT.rglob("*.lnk")} == {"Soulash2_QA.lnk"}
    differences = []
    for entry in manifest["files"]:
        actual = sha(OUT / entry["path"])
        if actual != entry["sha256"]:
            differences.append({"path": entry["path"], "source_sha256": entry["sha256"],
                                "probe_sha256": actual})
    assert {entry["path"] for entry in differences} == {"Soulash 2.exe", "data/mods/core_2/messages.json", *FONT_PATHS}
    for relative in ["data/tutorial_values.json", "data/user.settings.json"]:
        assert not (OUT / relative).exists()
    current = copy.deepcopy(previous)
    current.update({
        "font_revision": "Noto600_plus_required_Polish_glyphs",
        "font_finalized": datetime.now(timezone.utc).isoformat(),
        "font_finalizer_sha256": sha(Path(__file__)),
        "previous_preparation": {"path": str(archive.relative_to(ROOT)), "sha256": sha(archive),
                                 "status": "STALE_FOR_CURRENT_FONT"},
        "static_font": font_record,
        "required_character_coverage": "PASS",
        "coverage_scope": "소규모 번역9개·현재 영어 표시95자·크레딧 이름. 전체 번역 필요문자 완성 판정 아님.",
        "font_merge_evidence": {"path": str((FONT_DIR / "merge_report.json").relative_to(ROOT)),
                                "sha256": sha(FONT_DIR / "merge_report.json")},
        "font_atlas_cpu_evidence": {"path": str(atlas_path.relative_to(ROOT)), "sha256": sha(atlas_path)},
        "differences": differences,
        "added_files": [{"path": path, "sha256": sha(OUT / path),
                         "role": "QA_LAUNCHER_ONLY_EXCLUDED_FROM_DISTRIBUTION" if path.endswith(".lnk") else "QA_SETTINGS"}
                        for path in sorted(added_paths)],
        "difference_allowlist": "PASS", "shortcut_files_absent": "NOT_APPLICABLE",
        "shortcut_exception": "root가 probe02 target/cwd로 만든 Soulash2_QA.lnk 하나만 허용. 이전 실행 사본에서 복사한 파일이 아님.",
        "graphics_qa": "NOT_RUN", "font_atlas_qa": "NOT_RUN", "actual_credits_rendering": "NOT_RUN",
        "runtime_isolation": "NOT_RUN", "release_ready": False,
    })
    REPORT.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"stage": "COMPLETE", "font_sha256": FONT_SHA,
                      "qa_sha256": current["qa_executable_sha256"], "changed_files": len(differences),
                      "added_files": len(added_paths), "report_sha256": sha(REPORT)}), flush=True)


if __name__ == "__main__":
    main()
