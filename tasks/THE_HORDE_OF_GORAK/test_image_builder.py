"""원본 PNG와 무변경·4픽셀 변경·오류 입력으로 이미지 작성기를 검증한다."""
import json
from pathlib import Path

from PIL import Image

from dat_container import DatFile, sha
from image_builder import ALLOWED_HANDLES, ImageBank, verify_replacement

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311/THOG.dat"
PNGS = ROOT / "extracted_private/THE_HORDE_OF_GORAK/steam_26336311/nebula_01/images"
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/image_builder_test_01"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = DatFile.load(SOURCE)
    dat = DatFile.load(SOURCE)
    bank = ImageBank(dat)
    checks = []

    def record(name, condition):
        assert condition, name
        checks.append({"id": name, "status": "PASS"})

    record("image_count_2031", len(bank.records) == 2031)
    for handle in sorted(ALLOWED_HANDLES):
        png = PNGS / f"{handle:05d}.png"
        with Image.open(png) as image:
            rgba = image.convert("RGBA").tobytes()
        record(f"nebula_png_match_{handle}", bank.by_handle[handle].rgba() == rgba)
        record(f"same_pixels_no_change_{handle}", bank.replace_png(handle, png)["changed_pixels"] == 0)
    bank.apply()
    record("unchanged_dat_exact", dat.serialize() == source.original)

    expected, plan = {}, {}
    for handle in sorted(ALLOWED_HANDLES):
        value = bytearray(bank.by_handle[handle].rgba())
        first = next(i for i in range(0, len(value), 4) if value[i + 3] == 255)
        value[first] ^= 255
        png = OUT / f"probe_{handle}.png"
        Image.frombytes("RGBA", bank.by_handle[handle].dimensions, bytes(value)).save(png)
        expected[handle] = bytes(value)
        plan[str(handle)] = str(png)
        record(f"one_pixel_changed_{handle}", bank.replace_png(handle, png)["changed_pixels"] == 1)
    bank.apply()
    data = dat.serialize()
    reread = DatFile(data)
    changed = verify_replacement(source, reread, expected)
    record("only_four_images_changed", set(changed) == ALLOWED_HANDLES)
    record("rebuilt_dat_roundtrip", reread.serialize() == data)
    decoded = ImageBank(reread)
    for handle in sorted(ALLOWED_HANDLES):
        Image.frombytes("RGBA", decoded.by_handle[handle].dimensions, decoded.by_handle[handle].rgba()).save(OUT / f"reread_{handle}.png")
        record(f"encoded_png_pixels_match_{handle}", decoded.by_handle[handle].rgba() == expected[handle])
    rejected = False
    try:
        bank.replace_png(4, PNGS / "00004.png")
    except ValueError:
        rejected = True
    record("unapproved_handle_rejected", rejected)
    invalid = OUT / "invalid_size.png"
    Image.new("RGBA", (1, 1), (255, 0, 0, 255)).save(invalid)
    rejected = False
    try:
        bank.replace_png(215, invalid)
    except ValueError:
        rejected = True
    record("wrong_dimensions_rejected", rejected)
    (OUT / "THOG.dat").write_bytes(data)
    (OUT / "probe_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"source_sha256": sha(source.original), "candidate_sha256": sha(data), "checks": checks,
              "tool_sha256": sha((Path(__file__).parent / "image_builder.py").read_bytes()),
              "changed_handles": changed, "runtime_qa": "NOT_RUN", "scope": "정상 번역 이미지가 아닌 위치별 한 픽셀만 바꾼 재조립 시험"}
    (OUT / "test_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"checks": len(checks), "sha256": sha(data), "status": "PASS"}))


if __name__ == "__main__":
    main()
