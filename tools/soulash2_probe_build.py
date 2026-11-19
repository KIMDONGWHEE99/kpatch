"""소규모 한국어 로딩 시험 사본을 준비한다. 실행은 별도 격리 검증 뒤 수행한다."""
import copy
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
OUT = ROOT / "working_private/SOULASH_2/g1_probe_01"
TEXT = {189: ("Options", "설정"), 190: ("Exit Game", "게임 종료"),
        191: ("Resume", "계속하기"), 193: ("Exit to Main Menu", "메인 메뉴로"),
        197: ("Sound", "소리"), 292: ("Credits", "제작진"),
        427: ("Continue", "계속하기"), 752: ("Language", "언어"), 783: ("Quit", "종료")}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    if OUT.exists():
        raise SystemExit("기존 시험 사본을 덮어쓰지 않습니다.")
    started = datetime.now(timezone.utc).isoformat()
    manifest_path = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029/baseline_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    shutil.copytree(BASE, OUT)
    messages_path = OUT / "data/mods/core_2/messages.json"
    messages = json.loads(messages_path.read_text(encoding="utf-8"))
    no_op = json.loads(json.dumps(messages, ensure_ascii=False, indent=4))
    assert no_op == messages
    changed = copy.deepcopy(messages)
    applied = []
    for row in changed["main"]:
        if row["id"] in TEXT:
            source, translated = TEXT[row["id"]]
            assert row["format"] == source
            row["format"] = translated
            applied.append(row["id"])
    assert sorted(applied) == sorted(TEXT)
    messages_path.write_text(json.dumps(changed, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    reread = json.loads(messages_path.read_text(encoding="utf-8"))
    for row in reread["main"]:
        if row["id"] in TEXT:
            assert row["format"] == TEXT[row["id"]][1]
            row["format"] = TEXT[row["id"]][0]
    assert reread == messages
    font = ROOT / "tasks/MR_MAGEBOY_DEMO/third_party/Galmuri/Galmuri11-Bold.ttf"
    for name in ["romulus.ttf", "Lato-Bold.ttf", "Lato-Regular.ttf"]:
        shutil.copyfile(font, OUT / "data/mods/core_2/assets/fonts" / name)
    differences = []
    for entry in manifest["files"]:
        file = OUT / entry["path"]
        actual = sha(file)
        if actual != entry["sha256"]:
            differences.append({"path": entry["path"], "source_sha256": entry["sha256"], "probe_sha256": actual})
    expected = {"data/mods/core_2/messages.json", *["data/mods/core_2/assets/fonts/" + n for n in ["romulus.ttf", "Lato-Bold.ttf", "Lato-Regular.ttf"]]}
    assert {x["path"] for x in differences} == expected
    report = {"game_id": "SOULASH_2", "baseline_id": BASE.name, "check_id": "G1_PROBE_PREPARATION",
              "started": started, "finished": datetime.now(timezone.utc).isoformat(), "command": sys.argv,
              "baseline_manifest_sha256": sha(manifest_path), "script_sha256": sha(Path(__file__)),
              "no_op_structure": "PASS", "probe_json_reopen": "PASS", "boundary": "PASS",
              "graphics_qa": "NOT_RUN", "isolation": "NOT_RUN", "differences": differences,
              "translations": {str(k): {"source": v[0], "target": v[1]} for k,v in TEXT.items()}}
    target = ROOT / "working_private/SOULASH_2/g1_probe_01_preparation.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"differences": len(differences), "translations": len(applied), "graphics_qa": "NOT_RUN"}))

if __name__ == "__main__":
    main()
