"""직접 표시 문구와 미디어 검수판을 준비합니다. 원본은 읽기만 합니다."""
from common import *
from collections import Counter
import re

AUDIT = WORK / "audit"
MEDIA_REVIEW = EXTRACT / "media_review"


def prepare():
    rows = json.loads((EXTRACT / "strings.json").read_text(encoding="utf-8"))
    code = json.loads((EXTRACT.parent / "inspection/code_strings.json").read_text(encoding="utf-8"))
    fields = {"m_text", "m_Text", "m_Options", "_bodyText", "_title", "_baseText"}
    direct = [r for r in rows if r["type"] == "MonoBehaviour" and
              r["field"].split("/")[1] in fields and not r["source"].startswith("@")]
    write_json(AUDIT / "direct_source.json", direct)
    write_json(AUDIT / "direct_unique.json", sorted({r["source"] for r in direct}))
    code_review = []
    for r in code:
        s, m = r["source"], r["method"]
        if (not s or s.startswith("@") or "Assets.Source.Name." in m or
                "Assets.Behaviour.Input.InputActions" in m or
                "LightJson" in m or "::ToJson(" in m or "::FromJson(" in m):
            continue
        if re.fullmatch(r"[\W\d_]+", s):
            continue
        code_review.append(r)
    write_json(AUDIT / "code_review.json", code_review)
    groups = {}
    for r in code_review:
        groups.setdefault(r["method"], []).append(f'{r["offset"]}: {r["source"]!r}')
    (AUDIT / "code_review.txt").write_text("\n\n".join(
        k + "\n" + "\n".join(v) for k, v in groups.items()), encoding="utf-8")
    print({"direct": len(direct), "direct_unique": len({r["source"] for r in direct}),
           "code_review": len(code_review)})


def sheets():
    from PIL import Image, ImageDraw, ImageFont
    media = json.loads((EXTRACT / "media.json").read_text(encoding="utf-8"))
    rows = [r for r in media if r["type"] == "Texture2D"]
    font = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 16)
    cells = []
    index = []
    for idx, row in enumerate(rows):
        path = EXTRACT / "textures" / f'{row["file"]}_{row["path_id"]}.png'
        if not path.exists():
            index.append({**row, "index": idx, "image": None})
            continue
        image = Image.open(path).convert("RGBA")
        cell = Image.new("RGB", (320, 280), "#d0d0d0")
        thumb = image.copy()
        thumb.thumbnail((310, 224))
        bg = Image.new("RGBA", thumb.size, "#444444")
        bg.alpha_composite(thumb)
        cell.paste(bg.convert("RGB"), ((320-thumb.width)//2, 2))
        draw = ImageDraw.Draw(cell)
        draw.text((5, 228), f"{idx:03} {row['file']}/{row['path_id']}", font=font, fill="#000000")
        draw.text((5, 247), f"{row['name'][:29]} {image.width}x{image.height}", font=font, fill="#000000")
        index.append({**row, "index": idx, "image": str(path),
                      "image_sha256": sha(path), "size": list(image.size),
                      "sheet": len(cells)//20})
        cells.append(cell)
    MEDIA_REVIEW.mkdir(parents=True, exist_ok=True)
    for start in range(0, len(cells), 20):
        batch = cells[start:start+20]
        sheet = Image.new("RGB", (1600, 280*((len(batch)+4)//5)), "#d0d0d0")
        for j, cell in enumerate(batch):
            sheet.paste(cell, ((j%5)*320, (j//5)*280))
        sheet.save(MEDIA_REVIEW / f"sheet_{start//20:02}.jpg", quality=95)
    write_json(MEDIA_REVIEW / "texture_index.json", index)
    print({"media_types": dict(Counter(r["type"] for r in media)),
           "texture_count": len(rows), "images": len(cells), "sheets": (len(cells)+19)//20})


if __name__ == "__main__":
    prepare()
    sheets()
