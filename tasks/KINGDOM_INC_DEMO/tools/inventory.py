"""자산과 문구·글꼴·이미지를 위치별로 조사하고 읽기 실패를 보존합니다."""
from common import *
from collections import Counter

def walk(value, field=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk(item, field + "/" + key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk(item, field + "/" + str(index))
    elif isinstance(value, str) and value:
        yield field, value

if __name__ == "__main__":
    objects, strings, errors, media, fonts = [], [], [], [], []
    versions = {}
    for path in asset_files():
        env = load_asset(path)
        file_sha256 = sha(path)
        versions[path.name] = env.file.unity_version
        counts = Counter()
        for obj in env.objects:
            counts[obj.type.name] += 1
            row = {"id": f"{path.name}/{obj.path_id}", "file": path.name,
                   "file_sha256": file_sha256, "path_id": obj.path_id, "type": obj.type.name,
                   "object_sha256": hashlib.sha256(obj.get_raw_data()).hexdigest()}
            try:
                tree = obj.read_typetree()
                row["name"] = tree.get("m_Name", "")
                if obj.type.name == "MonoBehaviour":
                    script = obj.parse_monobehaviour_head().m_Script.deref_parse_as_object()
                    row["script"] = f"{script.m_AssemblyName}:{script.m_Namespace}.{script.m_ClassName}"
                for field, value in walk(tree):
                    strings.append({**row, "id": row["id"] + field, "field": field,
                                    "source": value, "classification": "UNKNOWN"})
                if obj.type.name in ("MonoBehaviour", "PlayerSettings", "ResourceManager", "TextAsset"):
                    write_json(EXTRACT / "trees" / path.name / f"{obj.path_id}.json", tree)
                if obj.type.name == "Font" or "m_CharacterTable" in tree:
                    write_json(EXTRACT / "fonts" / f"{path.name}_{obj.path_id}.json", tree)
                    fonts.append(row)
                if obj.type.name == "TextAsset":
                    out = EXTRACT / "textassets" / f"{path.name}_{obj.path_id}_{tree['m_Name']}.txt"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(tree["m_Script"], encoding="utf-8")
                if obj.type.name in ("Texture2D", "Sprite", "VideoClip"):
                    media.append({**row, "classification": "MEDIA", "treatment": "UNKNOWN"})
                if obj.type.name == "Texture2D":
                    out = EXTRACT / "textures" / f"{path.name}_{obj.path_id}.png"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    obj.read().image.save(out)
            except Exception as exc:
                errors.append({**row, "classification": "UNKNOWN", "error": str(exc)})
            objects.append(row)
        print(path.name, dict(counts), flush=True)
    for name, value in (("objects", objects), ("strings", strings), ("errors", errors),
                        ("media", media), ("fonts", fonts), ("versions", versions)):
        write_json(EXTRACT / (name + ".json"), value)
    print(json.dumps({"objects": len(objects), "strings": len(strings), "errors": len(errors),
                      "media": len(media), "fonts": len(fonts)}))
