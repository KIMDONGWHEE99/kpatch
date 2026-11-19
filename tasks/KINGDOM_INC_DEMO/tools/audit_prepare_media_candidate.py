"""이미지 생성 도구의 한글 아이콘을 원본 알파 경계에 맞춰 축소합니다."""
from common import *
from PIL import Image
import shutil

GENERATED = Path(r"C:\Users\PC\.codex\generated_images\01a1596c-4884-78d1-b21c-c090e847b45c\exec-a5752706-4f94-485b-a996-81d5ac12ef46.png")


def main():
    folder = WORK / "media"
    folder.mkdir(parents=True, exist_ok=True)
    original = EXTRACT / "textures/sharedassets1.assets_27.png"
    preserved = folder / "IconDecoLabel_imagegen_original.png"
    shutil.copy2(GENERATED, preserved)
    before = Image.open(original).convert("RGBA")
    generated = Image.open(preserved).convert("RGBA")
    bbox = before.getchannel("A").getbbox()
    generated_bbox = generated.getchannel("A").getbbox()
    scaled = generated.crop(generated_bbox).resize((bbox[2]-bbox[0], bbox[3]-bbox[1]), Image.Resampling.NEAREST)
    after = Image.new("RGBA", before.size, (0, 0, 0, 0))
    after.paste(scaled, bbox[:2])
    expected = folder / "IconDecoLabel_ko_32.png"
    after.save(expected)
    preview = folder / "IconDecoLabel_ko_32_preview.png"
    after.resize((512, 512), Image.Resampling.NEAREST).save(preview)
    evidence = {
        "game_id": GAME_ID, "build_id": BUILD,
        "texture_id": "sharedassets1.assets/27", "sprite_id": "sharedassets1.assets/105",
        "original_png": str(original), "original_sha256": sha(original),
        "generated_png": str(preserved), "generated_sha256": sha(preserved),
        "expected_png": str(expected), "expected_sha256": sha(expected),
        "expected_rgba_sha256": hashlib.sha256(after.tobytes()).hexdigest(),
        "original_alpha_bbox": list(bbox), "generated_alpha_bbox": list(generated_bbox),
        "size": list(after.size), "resample": "NEAREST",
        "operations": ["이미지 생성 도구 결과를 비공개 작업 영역으로 복사",
                       "생성 이미지의 알파 경계로 자르기",
                       "원본 알파 경계 크기로 최근접 축소",
                       "원본 32×32 크기의 투명 캔버스에서 동일 좌표에 배치"],
        "visual_review": "NOT_RUN",
    }
    write_json(folder / "IconDecoLabel_evidence.json", evidence)
    print(evidence)


if __name__ == "__main__":
    main()
