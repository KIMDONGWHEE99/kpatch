"""변경 없는 저장과 시험 글꼴의 자산·필드 경계를 별도로 확인합니다."""
from common import *
from fontTools.ttLib import TTFont
from io import BytesIO

probe_name = sys.argv[1] if len(sys.argv) > 1 else "probe"
target = WORK / probe_name / "game"
spec = json.loads((WORK/probe_name/"build.json").read_text(encoding="utf-8"))
allowed = {(r["file"], r["path_id"]): r for r in spec["changes"]}
checks = []
for source in asset_files():
    original = load_asset(source)
    assert preserve_save(source, original) == source.read_bytes()
    other = load_asset(target / DATA_NAME / source.name)
    assert set(original.file.objects) == set(other.file.objects)
    assert [(x.path, x.guid) for x in original.file.externals] == [(x.path, x.guid) for x in other.file.externals]
    for obj in other.objects:
        old = original.file.objects[obj.path_id]
        key = (source.name, obj.path_id)
        if key not in allowed:
            assert old.get_raw_data() == obj.get_raw_data(), key
            continue
        if "raw_template" in allowed[key]:
            name, pid = allowed[key]["raw_template"].split("/")
            assert obj.get_raw_data() == load_asset(DATA/name).file.objects[int(pid)].get_raw_data()
            continue
        a, b = old.read_typetree(), obj.read_typetree()
        actual = {k for k in a if a[k] != b[k]}
        assert actual == set(allowed[key]["fields"]), (key, actual, allowed[key])
        if obj.type.name == "Font":
            font = TTFont(BytesIO(bytes(b["m_FontData"])))
            assert all(ord(c) in font.getBestCmap() for c in "계속하기새게임불러오기설정키종료")
        if obj.type.name == "MonoBehaviour":
            assert b["m_AtlasPopulationMode"] == 1 and b["m_IsMultiAtlasTexturesEnabled"]
    checks.append({"file":source.name, "noop":"PASS", "boundary":"PASS",
                   "source_sha256":sha(source), "probe_sha256":sha(target/DATA_NAME/source.name)})
write_json(WORK/probe_name/"static_validation.json", {"status":"PASS", "checks":checks, "changes":len(allowed)})
print(json.dumps({"status":"PASS", "files":len(checks), "modified_objects":len(allowed)}))
