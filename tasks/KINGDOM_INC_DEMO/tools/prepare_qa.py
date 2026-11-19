"""별도 사본에만 화면 검수 보조를 붙이고 허용한 변경 경계를 다시 검사합니다."""
import argparse
import copy
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from common import ROOT, WORK, SOURCE, DATA_NAME, load_asset, read_tree, sha, write_json


def manifest(root):
    return {p.relative_to(root).as_posix(): {"size": p.stat().st_size, "sha256": sha(p)}
            for p in sorted(root.rglob("*")) if p.is_file()}


def run(command):
    subprocess.run([str(x) for x in command], check=True, cwd=ROOT)


def prepare(game, run_id, mode, build=True):
    game = Path(game).resolve()
    game.relative_to(WORK.resolve())
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", run_id):
        raise ValueError("검수 이름에는 영문·숫자·밑줄·붙임표만 사용할 수 있습니다.")
    data = game / DATA_NAME
    assert (game / "KingdomInc.exe").is_file()
    assert not (game / "korean-qa.json").exists(), "이미 검수용으로 준비된 사본입니다."
    output = game.parent / ("qa_" + run_id)
    assert not output.exists(), "같은 검수 기록을 덮어쓰지 않습니다."
    output.mkdir(parents=True)
    before = manifest(game)
    write_json(output / "candidate-manifest.json", before)
    tools = ROOT / "tasks/KINGDOM_INC_DEMO/tools"
    toolchain = WORK / "toolchain"
    if build:
        run(["dotnet", "build", tools / "KoreanQA/KoreanQA.csproj", "-c", "Release", "-o",
             toolchain / "KoreanQA", f"-p:GameManaged={SOURCE / DATA_NAME / 'Managed'}", "--nologo", "-v", "quiet"])
        run(["dotnet", "build", tools / "AssemblyTool/AssemblyTool.csproj", "-c", "Release",
             "-o", toolchain / "AssemblyTool", "--nologo", "-v", "quiet"])
    support = toolchain / "KoreanQA/KoreanQA.dll"
    patcher = toolchain / "AssemblyTool/AssemblyTool.dll"
    assert support.is_file() and patcher.is_file()
    backup = output / "candidate_inputs"
    backup.mkdir()
    assembly = data / "Managed/Assembly-CSharp.dll"
    settings = data / "globalgamemanagers"
    appinfo = data / "app.info"
    for source in [assembly, settings, appinfo]:
        shutil.copy2(source, backup / source.name)
    run(["dotnet", patcher, "qa", backup / assembly.name, assembly, support])
    run(["dotnet", patcher, "verify-qa", backup / assembly.name, assembly, output / "assembly-boundary.json"])
    shutil.copy2(support, data / "Managed/KoreanQA.dll")

    # 고정 길이 두 필드의 실제 바이트만 바꾸므로 Unity 설정의 다른 값과 꼬리값은 보존됩니다.
    source_settings = backup / "globalgamemanagers"
    original_env = load_asset(source_settings)
    settings_object = next(o for o in original_env.objects if o.type.name == "PlayerSettings")
    before_tree = read_tree(settings_object)
    assert before_tree["companyName"] == "Leaping Turtle" and before_tree["productName"] == "KingdomInc"
    company = "Korean QA Test"
    product = "KngQA" + hashlib.sha256(run_id.encode()).hexdigest()[:5]
    raw = source_settings.read_bytes()
    payload = settings_object.get_raw_data()
    result = bytearray(raw)
    changes = []
    for field, new_value in [("companyName", company), ("productName", product)]:
        old = before_tree[field].encode()
        new = new_value.encode()
        assert len(old) == len(new) and payload.count(old) == 1
        start = settings_object.byte_start + payload.index(old)
        assert raw[start:start + len(old)] == old
        result[start:start + len(old)] = new
        changes.append({"object": settings_object.path_id, "field": field, "start": start, "length": len(old),
                        "before": before_tree[field], "after": new_value})
    settings.write_bytes(result)
    actual_env = load_asset(settings)
    assert set(original_env.file.objects) == set(actual_env.file.objects)
    for old_obj in original_env.objects:
        actual_obj = actual_env.file.objects[old_obj.path_id]
        if old_obj.path_id == settings_object.path_id:
            actual_tree = read_tree(actual_obj)
            expected_tree = copy.deepcopy(before_tree)
            expected_tree.update(companyName=company, productName=product)
            assert actual_tree == expected_tree
        else:
            assert old_obj.get_raw_data() == actual_obj.get_raw_data(), old_obj.path_id
    allowed = {i for c in changes for i in range(c["start"], c["start"] + c["length"])}
    assert len(raw) == len(result)
    assert all(a == b or i in allowed for i, (a, b) in enumerate(zip(raw, result)))
    appinfo.write_text(company + "\n" + product + "\n", encoding="utf-8")
    config = {"output": str(output), "mode": mode, "width": 1200, "height": 900}
    write_json(game / "korean-qa.json", config)
    after = manifest(game)
    changed = {name for name in before if before[name] != after[name]}
    added = set(after) - set(before)
    assert set(before) <= set(after)
    expected_changed = {f"{DATA_NAME}/Managed/Assembly-CSharp.dll", f"{DATA_NAME}/globalgamemanagers", f"{DATA_NAME}/app.info"}
    assert changed == expected_changed, changed
    assert added == {"korean-qa.json", f"{DATA_NAME}/Managed/KoreanQA.dll"}, added
    write_json(output / "prepared-manifest.json", after)
    write_json(output / "preparation.json", {
        "status": "PASS", "game": str(game), "output": str(output), "run_id": run_id,
        "company": company, "product": product, "mode": mode, "settings_changes": changes,
        "changed_files": sorted(changed), "added_files": sorted(added),
        "assembly_tool_sha256": sha(patcher), "support_sha256": sha(support),
        "candidate_manifest_sha256": sha(output / "candidate-manifest.json"),
        "prepared_manifest_sha256": sha(output / "prepared-manifest.json"),
        "note": "검수 사본 변경 경계만 검사했으며 실제 화면 검수는 아직 하지 않았습니다."
    })
    print(json.dumps({"game": str(game), "output": str(output), "product": product}, ensure_ascii=False))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mode", choices=["probe", "manual"], default="manual")
    parser.add_argument("--no-build", action="store_true")
    args = parser.parse_args()
    prepare(args.game, args.run_id, args.mode, not args.no_build)
