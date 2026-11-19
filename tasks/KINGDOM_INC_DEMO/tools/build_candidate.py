"""원본 사본에서 고정한 번역·글꼴·아이콘만 적용하여 후보를 만듭니다."""
from common import *
from font_patch import apply_fonts, prepare_font
from layout_patch import LAYOUT_EDITS, apply_layout
from atlas_patch import prepare_icon, apply_atlas
from translation_checks import controls
from collections import defaultdict
import copy
import shutil
import subprocess
from PIL import Image

def get_field(tree, path):
    for key in path.strip("/").split("/"):
        tree = tree[int(key)] if isinstance(tree, list) else tree[key]
    return tree

def set_field(tree, path, value):
    parts = path.strip("/").split("/")
    for key in parts[:-1]:
        tree = tree[int(key)] if isinstance(tree, list) else tree[key]
    key = parts[-1]
    tree[int(key) if isinstance(tree, list) else key] = value

if __name__ == "__main__":
    build_id = sys.argv[1]
    candidate = ROOT/"build_candidate"/GAME_ID/build_id/"game"
    out = WORK/build_id
    assert not candidate.exists(), "후보는 덮어쓰지 않습니다."
    font_path = prepare_font()
    atlas_icon = prepare_icon()
    tool = WORK/"toolchain/TextPatch/TextPatch.dll"
    translations = WORK/"audit/code_direct_translations.json"
    image_path = WORK/"media/IconDecoLabel_ko_32.png"
    inputs = [WORK/"translation/canonical.json",WORK/"translation/language_ko.txt",WORK/"translation/required_characters.json",
              WORK/"audit/direct_translations.json",translations,image_path,ROOT/"tasks/KINGDOM_INC_DEMO/tools/font_patch.py",
              ROOT/"tasks/KINGDOM_INC_DEMO/tools/build_candidate.py",tool,
              ROOT/"tasks/KINGDOM_INC_DEMO/tools/common.py",ROOT/"tasks/KINGDOM_INC_DEMO/tools/layout_patch.py",
              ROOT/"tasks/KINGDOM_INC_DEMO/tools/translation_checks.py",font_path,
              ROOT/"tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf",
              EXTRACT/"baseline.json",EXTRACT/"trees/resources.assets/21.json",WORK/"language_source.json",
              ROOT/"tasks/KINGDOM_INC_DEMO/tools/TextPatch/Program.cs",
              ROOT/"tasks/KINGDOM_INC_DEMO/tools/atlas_patch.py",atlas_icon,WORK/"media/Icons32_ko_evidence_v2.json",
              WORK/"audit/media_classification.json",WORK/"audit/media_reclassification_icons32.json",
              WORK/"audit/media_resolution_icons32.json"]
    input_records = [{"path":str(p),"sha256":sha(p)} for p in inputs]
    source_manifest = json.loads((EXTRACT/"baseline.json").read_text(encoding="utf-8"))
    for row in source_manifest["files"]:
        assert sha(SOURCE/row["path"]) == row["sha256"]
    shutil.copytree(SOURCE, candidate)
    changes = apply_fonts(candidate)
    direct = json.loads((WORK/"audit/direct_translations.json").read_text(encoding="utf-8"))
    language = (WORK/"translation/language_ko.txt").read_text(encoding="utf-8")
    grouped = defaultdict(lambda: defaultdict(list))
    for row in direct:
        controls(row["source"], row["expected"])
        grouped[row["file"]][row["path_id"]].append(row)
    original_language = json.loads((EXTRACT/"trees/resources.assets/21.json").read_text(encoding="utf-8"))["m_Script"]
    grouped["resources.assets"][21].append({"field":"/m_Script","source":original_language,"expected":language})
    for name in sorted(set(grouped) | {key[0] for key in LAYOUT_EDITS} | {"sharedassets1.assets"}):
        path = candidate/DATA_NAME/name
        env = load_asset(path)
        for obj in env.objects:
            atlas_change = apply_atlas(name,obj)
            if atlas_change:
                changes.append(atlas_change)
            rows = grouped[name].get(obj.path_id, [])
            if rows or (name,obj.path_id) in LAYOUT_EDITS:
                tree = read_tree(obj)
                before = copy.deepcopy(tree)
                for row in rows:
                    assert get_field(tree,row["field"]) == row["source"], (name,obj.path_id,row["field"])
                    set_field(tree,row["field"],row["expected"])
                apply_layout(name,obj,tree)
                obj.save_typetree(tree)
                changes.append({"file":name,"path_id":obj.path_id,
                                "fields":[k for k in tree if tree[k]!=before[k]]})
            if name == "sharedassets1.assets" and obj.path_id == 27:
                before = obj.read_typetree()
                texture = obj.read()
                texture.image = Image.open(image_path).convert("RGBA")
                texture.save()
                after = obj.read_typetree()
                changes.append({"file":name,"path_id":27,"fields":[k for k in after if after[k]!=before[k]],
                                "image_expected":str(image_path),"image_sha256":sha(image_path)})
        path.write_bytes(preserve_save(path, env))
        print(name,"번역 위치",sum(len(r) for r in grouped[name].values()),flush=True)
    dll = Path(DATA_NAME)/"Managed/Assembly-CSharp.dll"
    subprocess.run(["dotnet",str(tool),"patch",str(SOURCE/dll),str(candidate/dll),str(translations)],check=True)
    result = subprocess.run(["dotnet",str(tool),"verify",str(SOURCE/dll),str(candidate/dll),str(translations)],
                            check=True,capture_output=True,text=True,encoding="utf-8")
    write_json(out/"code_verification.json",json.loads(result.stdout.strip()))
    files = [{"path":p.relative_to(candidate).as_posix(),"size":p.stat().st_size,"sha256":sha(p)}
             for p in sorted(candidate.rglob("*")) if p.is_file()]
    for record in input_records:
        assert sha(record["path"]) == record["sha256"], f"제작 중 입력 변경: {record['path']}"
    write_json(out/"build.json",{"game_id":GAME_ID,"build_id":build_id,"candidate":str(candidate),
               "baseline_manifest_sha256":sha(EXTRACT/"baseline.json"),"files":files,"edits":changes,
               "expected":direct,"language_sha256":sha(WORK/"translation/language_ko.txt"),
               "layout_expected":[{"file":name,"path_id":pid,**spec} for (name,pid),spec in LAYOUT_EDITS.items()],
               "inputs":input_records})
    print(json.dumps({"candidate":str(candidate),"files":len(files),"modified_objects":len(changes)}))
