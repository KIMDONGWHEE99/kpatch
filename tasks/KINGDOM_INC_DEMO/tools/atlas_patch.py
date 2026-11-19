"""검수한 생성 아이콘의 글자 영역을 그대로 잘라 작은 아이콘 칸에 넣습니다."""
from common import DATA, WORK, load_asset, read_tree, sha, write_json
from PIL import Image
import hashlib


TEXTURE_PAIR = ("sharedassets0.assets", 11)
TEXTURE_SHA256 = "2413dbd04a30f74d2f159673a0486dbc3334e5733bfe594b5656bff8e08ff5c9"
SPRITE_SHA256 = "a5df78766419f0c8f7218fb5ace99d4af7fb59ffd8fca135cdd32c4d3905b13e"
CELL = (35, 205, 16, 16)


def prepare_icon():
    original = WORK / "media/IconDecoLabel_ko_32.png"
    output = WORK / "media/Icons32_ko_16_v2.png"
    image = Image.open(original).convert("RGBA")
    assert image.size == (32, 32)
    cropped = image.crop((8, 6, 24, 22))
    cropped.save(output)
    cropped.resize((512, 512), Image.Resampling.NEAREST).save(WORK / "media/Icons32_ko_16_v2_preview.png")
    sprite = load_asset(DATA / "resources.assets").file.objects[82]
    assert hashlib.sha256(sprite.get_raw_data()).hexdigest() == SPRITE_SHA256
    evidence = {
        "source_png": str(original), "source_png_sha256": sha(original),
        "expected_png": str(output), "expected_png_sha256": sha(output),
        "expected_rgba_sha256": hashlib.sha256(cropped.tobytes()).hexdigest(),
        "source_texture": "sharedassets0.assets/11", "source_texture_object_sha256": TEXTURE_SHA256,
        "source_sprite": "resources.assets/82", "source_sprite_object_sha256": SPRITE_SHA256,
        "unity_cell": list(CELL), "png_cell": [35, 35, 16, 16], "texture_size": [256, 256],
        "operation": "이미 생성·검수된 32×32 이미지에서 (8,6)-(24,22) 영역을 16×16 그대로 자름. 새 그림·문자·크기변환 없음.",
        "crop_box": [8, 6, 24, 22], "resample": "NONE", "visual_runtime_qa": "NOT_RUN",
        "source_crop_visual_review": "PASS", "source_crop_review": "root와 tooling_audit가 v2 미리보기를 실제 열어 글 자획 보존을 확인함.",
    }
    texture = load_asset(DATA / "sharedassets0.assets").file.objects[11]
    assert hashlib.sha256(texture.get_raw_data()).hexdigest() == TEXTURE_SHA256
    original_pixels = texture.read().image.convert("RGBA")
    expected_atlas = original_pixels.copy()
    expected_atlas.paste(cropped, (35, 35))
    before, after = original_pixels.tobytes(), expected_atlas.tobytes()
    outside_changes = sum(before[p:p+4] != after[p:p+4] for p in range(0, len(before), 4)
                          if not (35 <= (p // 4) % 256 < 51 and 35 <= (p // 4) // 256 < 51))
    assert outside_changes == 0
    expected_atlas.save(WORK / "media/Icons_atlas_expected_rc5.png")
    evidence.update(expected_atlas_png_sha256=sha(WORK / "media/Icons_atlas_expected_rc5.png"),
                    outside_changed_pixels=outside_changes, prepared_boundary="PASS", candidate_reextraction="NOT_RUN")
    write_json(WORK / "media/Icons32_ko_evidence_v2.json", evidence)
    return output


def apply_atlas(name, obj):
    if (name, obj.path_id) != TEXTURE_PAIR:
        return None
    assert hashlib.sha256(obj.get_raw_data()).hexdigest() == TEXTURE_SHA256
    tree = read_tree(obj)
    assert tree["m_Name"] == "Icons" and tree["m_TextureFormat"] == 4
    assert (tree["m_Width"], tree["m_Height"], tree["m_MipCount"]) == (256, 256, 1)
    assert tree["m_StreamData"] == {"offset": 0, "size": 0, "path": ""}
    before = bytes(tree["image data"])
    assert len(before) == 256 * 256 * 4
    icon = Image.open(WORK / "media/Icons32_ko_16_v2.png").convert("RGBA")
    assert icon.size == (16, 16)
    # Unity RGBA32 원시 행은 아래에서 위로 저장됩니다. 해당 16행의 16픽셀만 교체합니다.
    block = icon.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()
    after = bytearray(before)
    x, y, width, height = CELL
    for row in range(height):
        offset = ((y + row) * 256 + x) * 4
        after[offset:offset + width * 4] = block[row * width * 4:(row + 1) * width * 4]
    tree["image data"] = bytes(after)
    obj.save_typetree(tree)
    return {"file": name, "path_id": obj.path_id, "fields": ["image data"],
            "unity_cell": list(CELL), "image_sha256": sha(WORK / "media/Icons32_ko_16_v2.png")}
