"""KcBoxA 버튼 후미 확장의 독립 길이·범위·객체 보존 검사."""
import json
from pathlib import Path

from button_builder import inspect_button, patch_button_text
from dat_container import DatFile, sha

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311/THOG.dat"
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/button_builder_test_01"


def main():
    dat = DatFile.load(SOURCE)
    original = DatFile.load(SOURCE)
    rows = [json.loads(line) for line in (ROOT / "extracted_private/THE_HORDE_OF_GORAK/steam_26336311/media_review_01/extension_inventory.jsonl").read_text(encoding="utf-8").splitlines()]
    buttons = [row["object_handle"] for row in rows if row["kind"] == "button_text"]
    assert len(buttons) == 81
    for handle in buttons:
        inspect_button(dat, handle)
    change = patch_button_text(dat, 68, "NO", "아니요")
    output = dat.serialize()
    reread = DatFile(output)
    after = inspect_button(reread, 68)
    assert after["source"] == "아니요" and len(after["data"]) == 364 and after["text_size"] == 8
    assert [a.index for a, b in zip(original.objects, reread.objects) if a.decoded != b.decoded] == [68]
    assert {a.chunk_id for a, b in zip(original.chunks, reread.chunks) if a.decoded != b.decoded} == {0x2256, 0x2257, 0x2242}
    assert reread.integrity_summary()["status"] == "PASS"
    assert reread.serialize() == output
    # 긴 문구를 다시 줄인 뒤 원래 객체 내용과 올바른 파일 검증값을 확인한다.
    patch_button_text(reread, 68, "아니요", "NO")
    restored = reread.serialize()
    assert DatFile(restored).objects[68].decoded == original.objects[68].decoded
    assert DatFile(restored).integrity_summary()["status"] == "PASS"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "THOG.dat").write_bytes(output)
    report = {"status": "PASS", "buttons_structurally_checked": len(buttons), "change": change,
              "source_sha256": sha(original.original), "candidate_sha256": sha(output), "runtime_qa": "NOT_RUN",
              "scope": "버튼 끝의 문구와 보존된 8바이트 후미만 이동. 다른 섹션 위치는 전부 문구보다 앞에 있음"}
    (OUT / "test_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
