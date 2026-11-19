"""한글 원본 글꼴과 두 가지 화면 배율용 동적 글꼴을 준비합니다."""
from common import *
import copy
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

def prepare_font():
    path = WORK / "fonts/NotoSansKR-Regular.ttf"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        font = instantiateVariableFont(TTFont(ROOT / "tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf"), {"wght": 400}, inplace=True)
        font.save(path)
    return path

def apply_fonts(target):
    font_path = prepare_font()
    raw = font_path.read_bytes()
    ft = TTFont(font_path)
    units = ft["head"].unitsPerEm
    changes = []
    templates = load_asset(DATA / "resources.assets")
    material_template = templates.file.objects[6].read_typetree()
    font_template = templates.file.objects[2058].read_typetree()
    shader_template = templates.file.objects[20].get_raw_data()
    for name in ("resources.assets", "sharedassets0.assets"):
        source = DATA / name
        env = load_asset(source)
        for obj in env.objects:
            if name == "sharedassets0.assets" and obj.path_id in (2, 3):
                before = obj.read_typetree()
                tree = copy.deepcopy(material_template)
                tree["m_Name"] = before["m_Name"]
                tree["m_Shader"] = {"m_FileID":0, "m_PathID":32}
                for pair in tree["m_SavedProperties"]["m_TexEnvs"]:
                    if pair[0] == "_MainTex":
                        pair[1]["m_Texture"] = {"m_FileID":0, "m_PathID":6 if obj.path_id == 2 else 7}
                tree["m_SavedProperties"]["m_Floats"] = [
                    (key, 1024.0 if key in ("_TextureWidth", "_TextureHeight") else value)
                    for key, value in tree["m_SavedProperties"]["m_Floats"]
                ]
                obj.save_typetree(tree)
                changes.append({"file":name, "path_id":obj.path_id, "fields":[k for k in tree if before[k] != tree[k]]})
            elif name == "sharedassets0.assets" and obj.path_id == 32:
                obj.set_raw_data(shader_template)
                changes.append({"file":name, "path_id":obj.path_id, "raw_template":"resources.assets/20"})
            elif obj.type.name == "Font":
                tree = obj.read_typetree()
                tree["m_FontData"] = list(raw)
                tree["m_FontNames"] = ["Noto Sans KR"]
                obj.save_typetree(tree)
                changes.append({"file": name, "path_id": obj.path_id, "fields": ["m_FontData", "m_FontNames"]})
            elif name == "sharedassets0.assets" and obj.path_id in (88, 89):
                before = obj.read_typetree()
                tree = copy.deepcopy(font_template)
                tree["m_Name"] = before["m_Name"]
                tree["m_SourceFontFile"] = {"m_FileID":0, "m_PathID":34}
                tree["m_Material"] = {"m_FileID":0, "m_PathID":2 if obj.path_id == 88 else 3}
                tree["m_AtlasTextures"] = [{"m_FileID":0, "m_PathID":6 if obj.path_id == 88 else 7}]
                size = 64
                scale = size / units
                face = tree["m_FaceInfo"]
                face.update(m_FamilyName="Noto Sans KR", m_StyleName="Regular", m_PointSize=float(size),
                            m_UnitsPerEM=units, m_LineHeight=ft["hhea"].ascent*scale-ft["hhea"].descent*scale+ft["hhea"].lineGap*scale,
                            m_AscentLine=ft["hhea"].ascent*scale, m_DescentLine=ft["hhea"].descent*scale,
                            m_CapLine=ft["OS/2"].sCapHeight*scale, m_MeanLine=ft["OS/2"].sxHeight*scale)
                tree["m_GlyphTable"] = []
                tree["m_CharacterTable"] = []
                tree["m_UsedGlyphRects"] = []
                tree["m_FreeGlyphRects"] = [{"m_X":0, "m_Y":0, "m_Width":1023, "m_Height":1023}]
                tree["m_AtlasWidth"] = tree["m_AtlasHeight"] = 1024
                tree["m_AtlasPopulationMode"] = 1
                tree["m_IsMultiAtlasTexturesEnabled"] = True
                tree["m_AtlasTextureIndex"] = 0
                obj.save_typetree(tree)
                changes.append({"file": name, "path_id": obj.path_id, "fields": [k for k in tree if before[k] != tree[k]]})
            elif name == "sharedassets0.assets" and obj.path_id in (6, 7):
                tree = obj.read_typetree()
                before = copy.deepcopy(tree)
                tree["m_Width"] = tree["m_Height"] = 1024
                tree["m_CompleteImageSize"] = 1024 * 1024
                tree["m_MipCount"] = 1
                tree["m_TextureFormat"] = 1
                tree["m_IsReadable"] = True
                tree["m_TextureSettings"]["m_FilterMode"] = 1
                tree["m_StreamData"] = {"offset":0, "size":0, "path":""}
                tree["image data"] = bytes(1024 * 1024)
                obj.save_typetree(tree)
                changes.append({"file": name, "path_id": obj.path_id, "fields": [k for k in tree if before[k] != tree[k]]})
        out = target / DATA_NAME / name
        out.write_bytes(preserve_save(source, env))
    return changes
