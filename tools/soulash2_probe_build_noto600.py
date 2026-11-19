"""원본 사본에서 Noto 600 QA 후보를 새로 구성하고 변경 허용 목록을 검사합니다."""

import copy
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/python_deps"))
import fontTools
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from soulash2_probe_build import TEXT

BASE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
PREVIOUS = ROOT / "working_private/SOULASH_2/g1_probe_01"
OUT = ROOT / "working_private/SOULASH_2/g1_probe_02"
FONT_SOURCE = ROOT / "tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf"
FONT_DIR = ROOT / "working_private/SOULASH_2/font_probe/noto600"
FONT_OUTPUT = FONT_DIR / "NotoSansKR-SemiBold.ttf"
MANIFEST_PATH = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029/baseline_manifest.json"
SETTINGS = ROOT / "working_private/SOULASH_2/qa_isolation/settings_proposed.json"
QA_SHA = "9595c0c9ce71d0538772ce8af9c5aa86b9b6e87fca79fdb0b26992cd5656093e"
SETTINGS_SHA = "13bf56b62c9651b5cf9ab26d45b2881a52c04ddd22d7f0018d2cc75b2752ba00"
VARIABLE_SHA = "194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252"
FONT_NAMES = ("romulus.ttf", "Lato-Bold.ttf", "Lato-Regular.ttf")
MESSAGES = "data/mods/core_2/messages.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_set(path):
    return {p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_file()}


def main():
    started = datetime.now(timezone.utc).isoformat()
    if OUT.exists():
        raise SystemExit("기존 QA 후보를 덮어쓰지 않습니다.")
    assert sha(FONT_SOURCE) == VARIABLE_SHA
    assert sha(PREVIOUS / "Soulash 2.exe") == QA_SHA
    assert sha(SETTINGS) == SETTINGS_SHA
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected_files = {entry["path"] for entry in manifest["files"]}
    assert file_set(BASE) == expected_files
    assert "data/user_settings.json" not in expected_files
    for relative in ["data/tutorial_values.json", "data/user.settings.json"]:
        assert not (BASE / relative).exists()

    # 이전 실행에서 생긴 파일을 가져오지 않고, 바꿀 두 파일만 사전 검증합니다.
    baseline_messages = json.loads((BASE / MESSAGES).read_text(encoding="utf-8"))
    previous_messages = json.loads((PREVIOUS / MESSAGES).read_text(encoding="utf-8"))
    restored = copy.deepcopy(previous_messages)
    applied = []
    for row in restored["main"]:
        if row["id"] in TEXT:
            source, translated = TEXT[row["id"]]
            assert row["format"] == translated
            row["format"] = source
            applied.append(row["id"])
    assert sorted(applied) == sorted(TEXT)
    assert restored == baseline_messages

    FONT_DIR.mkdir(parents=True, exist_ok=True)
    variable = TTFont(FONT_SOURCE, recalcTimestamp=False)
    assert [(axis.axisTag, axis.minValue, axis.maxValue) for axis in variable["fvar"].axes] == [("wght", 100.0, 900.0)]
    instance = instantiateVariableFont(variable, {"wght": 600}, inplace=False, updateFontNames=True)
    instance.recalcTimestamp = False
    instance.save(FONT_OUTPUT)
    instance.close()
    variable.close()
    shutil.copyfile(FONT_SOURCE.with_name("OFL.txt"), FONT_DIR / "OFL.txt")
    reopened = TTFont(FONT_OUTPUT, recalcTimestamp=False)
    cmap = reopened.getBestCmap()
    required = set("".join(target for _, target in TEXT.values()) + "Artur Śmiarowski Miłosz Ł ł")
    missing = sorted(ord(char) for char in required if not char.isspace() and ord(char) not in cmap)
    # 알려진 라틴 확장 글리프 누락은 실패로 기록하되, 요청한 글꼴 비교 후보 구성은 계속합니다.
    assert all(ord(char) in cmap for _, target in TEXT.values() for char in target if not char.isspace())
    assert "fvar" not in reopened and "gvar" not in reopened
    assert reopened["OS/2"].usWeightClass == 600
    names = {str(name_id): sorted({n.toUnicode() for n in reopened["name"].names if n.nameID == name_id})
             for name_id in [0, 1, 2, 4, 6, 13, 14, 16, 17]}
    font_details = {"path": str(FONT_OUTPUT.relative_to(ROOT)), "sha256": sha(FONT_OUTPUT),
                    "bytes": FONT_OUTPUT.stat().st_size, "weight": reopened["OS/2"].usWeightClass,
                    "variable_tables_absent": True, "cmap_count": len(cmap),
                    "hangul_syllables": sum(cp in cmap for cp in range(0xAC00, 0xD7A4)),
                    "polish_extended": {"U+0141": 0x141 in cmap, "U+0142": 0x142 in cmap,
                                        "U+015A": 0x15A in cmap, "U+015B": 0x15B in cmap},
                    "required_missing": missing, "names": names}
    reopened.close()
    print(json.dumps({"stage": "FONT_READY", "path": str(FONT_OUTPUT.relative_to(ROOT)),
                      "sha256": font_details["sha256"]}), flush=True)

    shutil.copytree(BASE, OUT)
    shutil.copyfile(PREVIOUS / "Soulash 2.exe", OUT / "Soulash 2.exe")
    shutil.copyfile(PREVIOUS / MESSAGES, OUT / MESSAGES)
    for name in FONT_NAMES:
        shutil.copyfile(FONT_OUTPUT, OUT / "data/mods/core_2/assets/fonts" / name)
    shutil.copyfile(SETTINGS, OUT / "data/user_settings.json")

    expected_changes = {"Soulash 2.exe", MESSAGES,
                        *("data/mods/core_2/assets/fonts/" + name for name in FONT_NAMES)}
    assert file_set(OUT) == expected_files | {"data/user_settings.json"}
    assert not any(p.suffix.lower() == ".lnk" for p in OUT.rglob("*"))
    differences = []
    for entry in manifest["files"]:
        # 기준선 자체도 다시 대조하며, 허용 파일 외의 복사본 바이트를 전부 검사합니다.
        assert sha(BASE / entry["path"]) == entry["sha256"], entry["path"]
        actual = sha(OUT / entry["path"])
        if actual != entry["sha256"]:
            differences.append({"path": entry["path"], "source_sha256": entry["sha256"],
                                "probe_sha256": actual})
    assert {entry["path"] for entry in differences} == expected_changes
    assert sha(OUT / "Soulash 2.exe") == QA_SHA
    assert sha(OUT / "data/user_settings.json") == SETTINGS_SHA
    assert sha(OUT / MESSAGES) == sha(PREVIOUS / MESSAGES)
    for relative in ["data/tutorial_values.json", "data/user.settings.json"]:
        assert not (OUT / relative).exists()
    settings = json.loads((OUT / "data/user_settings.json").read_text(encoding="utf-8"))
    assert settings["viewport"]["resolution"] == {"w": 1280, "h": 800}
    assert settings["sound"] == {"master": 0, "effects": 0, "music": 0}
    assert settings["viewport"]["fullscreen"] is False and settings["viewport"]["borderless"] is False
    report = {
        "game_id": "SOULASH_2", "baseline_id": BASE.name,
        "purpose": "QA_ONLY_DO_NOT_DISTRIBUTE", "started": started,
        "finished": datetime.now(timezone.utc).isoformat(),
        "script_sha256": sha(Path(__file__)), "fonttools_version": fontTools.__version__,
        "baseline_manifest_sha256": sha(MANIFEST_PATH), "baseline_file_count": len(expected_files),
        "copied_baseline_hashes": "PASS", "source_font_sha256": VARIABLE_SHA,
        "source_font_license_sha256": sha(FONT_SOURCE.with_name("OFL.txt")),
        "static_font": font_details, "required_character_coverage": "FAIL" if missing else "PASS",
        "qa_executable_sha256": QA_SHA,
        "settings_sha256": SETTINGS_SHA, "differences": differences,
        "added_files": [{"path": "data/user_settings.json", "sha256": SETTINGS_SHA}],
        "difference_allowlist": "PASS", "message_structure_and_nine_translations": "PASS",
        "previous_probe_copy_allowlist": ["Soulash 2.exe", MESSAGES],
        "migration_files_absent": "PASS", "shortcut_files_absent": "PASS",
        "runtime_files_copied_from_previous": False, "graphics_qa": "NOT_RUN",
        "font_atlas_qa": "NOT_RUN", "actual_credits_rendering": "NOT_RUN",
        "launch_responsibility": "root",
        "limitations": ["정적 cmap 확인은 실제 게임 표시나 글꼴 아틀라스 용량 검증을 대신하지 않음.",
                        "모든 QA EXE 변경은 이전 격리 manifest와 동일하며 배포 대상으로 사용하지 않음."]
    }
    report_path = ROOT / "working_private/SOULASH_2/g1_probe_02_preparation.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"stage": "COMPLETE", "target": str(OUT.relative_to(ROOT)),
                      "changed_files": len(differences), "added_files": 1,
                      "font_sha256": font_details["sha256"], "qa_sha256": QA_SHA,
                      "report_sha256": sha(report_path)}), flush=True)


if __name__ == "__main__":
    main()
