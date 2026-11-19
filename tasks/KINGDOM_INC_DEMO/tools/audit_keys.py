"""직접 번역 키와 열거형·입력 액션에서 조합되는 키의 원본 존재 여부를 조사합니다."""
from common import *
from collections import Counter
import re

AUDIT = WORK / "audit"
DECOMPILED = EXTRACT.parent / "inspection/decompiled"


def enum_values(path):
    text = path.read_text(encoding="utf-8")
    body = text.split("{", 1)[1].rsplit("}", 1)[0]
    return [part.strip().split("=")[0].strip() for part in body.split(",") if part.strip()]


def main():
    original = EXTRACT/"textassets/resources.assets_21_en-US.txt"
    keys = {}
    for lineno, line in enumerate(original.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith(";"):
            continue
        match = re.match(r"\s*(.+?)\s*=(.*)", line)
        if match:
            keys[match[1].strip()] = {"line": lineno, "source": match[2].strip()}
    checks = []
    prefixes = {"@", "@Currency", "@ForestCrew", "@Stat", "@Armor", "@Slot", "@ElementCategory", "@ResourceTag", "@RecipeTag", "@KB"}
    code = json.loads((EXTRACT.parent/"inspection/code_strings.json").read_text(encoding="utf-8"))
    for row in code:
        if row["source"].startswith("@") and row["source"] not in prefixes:
            checks.append({"origin": "code", "method": row["method"], "offset": row["offset"], "key": row["source"][1:]})
    for row in json.loads((EXTRACT/"strings.json").read_text(encoding="utf-8")):
        if row["source"].startswith("@"):
            checks.append({"origin": "asset", "id": row["id"], "key": row["source"][1:]})
    groups = [
        ("Assets.Source.Player/Currency.cs", "Currency", ["", "Desc"]),
        ("Assets.Source.Player/ForestWorker.cs", "ForestCrew", ["", "2", "Desc"]),
        ("Assets.Source.Items/AppraiserStat.cs", "Stat", [""]),
        ("Assets.Source.Items/EquipStat.cs", "Stat", [""]),
        ("Assets.Source.Items/ArmorType.cs", "Armor", [""]),
        ("Assets.Source.Items/EquipmentSlot.cs", "Slot", [""]),
        ("Assets.Source.Flow/ElementCategory.cs", "ElementCategory", [""]),
        ("Assets.Source.Items/ResourceTag.cs", "ResourceTag", [""]),
        ("Assets.Source.Items/RecipeTag.cs", "RecipeTag", [""]),
    ]
    for relative, prefix, suffixes in groups:
        path = DECOMPILED/relative
        for name in enum_values(path):
            for suffix in suffixes:
                checks.append({"origin": "enum", "code_file": relative, "enum": name,
                               "key": prefix+name+suffix, "evidence_sha256": sha(path)})
    player_input = DECOMPILED/"Assets.Behaviour.Input/PlayerInput.cs"
    body = re.search(r"RebindableKeys = new List<InputAction>\s*\{(.*?)\};", player_input.read_text(encoding="utf-8"), re.S)[1]
    for name in re.findall(r"_inputInstance\.UI\.(\w+)", body):
        checks.append({"origin": "input", "code_file": str(player_input.relative_to(DECOMPILED)),
                       "key": "KB"+name, "evidence_sha256": sha(player_input)})
    for row in checks:
        row["status"] = "PASS" if row["key"] in keys else "FAIL"
        row["source_translation"] = keys.get(row["key"])
    write_json(AUDIT/"key_coverage_original.json", checks)
    summary = {"game_id": GAME_ID, "build_id": BUILD, "source_sha256": sha(original),
               "tool_sha256": sha(__file__), "keys": len(keys),
               "checks": len(checks), "origins": dict(Counter(r["origin"] for r in checks)),
               "missing": [r for r in checks if r["status"] == "FAIL"]}
    write_json(AUDIT/"key_coverage_original_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
