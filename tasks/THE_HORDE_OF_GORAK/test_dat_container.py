"""실제 원본과 오류 주입으로 DAT 재조립 경계를 확인한다."""
import json
import struct
from pathlib import Path

from dat_container import Chunk, DatFile, sha, utf16z

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311/THOG.dat"
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/container_tests/integrity_01"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    dat = DatFile.load(SOURCE)
    checks = []

    def record(name, value):
        assert value, name
        checks.append({"id": name, "status": "PASS"})

    record("unchanged_roundtrip_exact", dat.serialize() == SOURCE.read_bytes())
    record("source_runtime_integrity", dat.integrity_summary()["status"] == "PASS")
    # 검증 청크만 손상시킨 입력을 탐지하고 원래 값으로 복구하는지 확인한다.
    damaged = bytearray(dat.original)
    damaged[len(dat.header) + dat.one(0x2242).offset + 8] ^= 1
    damaged_dat = DatFile(bytes(damaged))
    record("corrupted_runtime_integrity_detected", damaged_dat.integrity_summary()["status"] == "FAIL")
    record("corrupted_runtime_integrity_repaired", damaged_dat.serialize() == dat.original)
    for label, action in [
        ("wrong_source_rejected", lambda: dat.patch_utf16("object:32", 148, "OTHER", "그래픽")),
        ("longer_text_rejected", lambda: dat.patch_utf16("object:32", 148, "GRAPHICS", "슬롯보다훨씬긴한국어문구")),
        ("unequal_binary_size_rejected", lambda: dat.patch("object:32", 0, b"a", b"bb")),
    ]:
        rejected = False
        try:
            action()
        except ValueError:
            rejected = True
        record(label, rejected)

    plan = [
        {"target": "object:32", "offset": 148, "source": "GRAPHICS", "translated": "그래픽"},
        {"target": "font:16", "offset": 40, "source": "Trebuchet MS", "translated": "Malgun Gothic", "slot_bytes": 64},
    ]
    for change in plan:
        dat.patch_utf16(**change)
    candidate = dat.serialize()
    reread = DatFile(candidate)
    record("candidate_roundtrip_exact", reread.serialize() == candidate)
    record("candidate_runtime_integrity", reread.integrity_summary()["status"] == "PASS")
    for change in plan:
        _, value = reread.get_target(change["target"])
        record("expected_value_" + change["target"], utf16z(value, change["offset"])[0] == change["translated"])
    original = DatFile.load(SOURCE)
    changed_chunks = []
    for before, after in zip(original.chunks, reread.chunks):
        record("chunk_identity_" + before.location, (before.chunk_id, before.flag) == (after.chunk_id, after.flag))
        if before.decoded != after.decoded:
            changed_chunks.append(f"0x{before.chunk_id:04x}")
    record("only_expected_top_chunks_changed", set(changed_chunks) == {"0x2256", "0x2257", "0x2242", "0x6667", "0x5556"})
    record("only_one_object_changed", [a.index for a, b in zip(original.objects, reread.objects) if a.decoded != b.decoded] == [32])
    record("only_one_font_changed", [a.handle for a, b in zip(original.fonts, reread.fonts) if a.decoded != b.decoded] == [16])

    # 수정 시 사용하는 네 가지 저장 방식 모두 독립적인 청크 파서로 복원한다.
    from dat_container import parse_chunks
    for flag in range(4):
        template = next(c for c in original.by_location.values() if c.flag == flag and c.cipher and c.decoded)
        probe = Chunk(template.chunk_id, flag, template.raw, template.decoded, "probe", 0, template.cipher)
        probe.replacement = bytes((template.decoded[0] ^ 1,)) + template.decoded[1:]
        rebuilt = parse_chunks(probe.serialize(), "probe", template.cipher)[0]
        record(f"modified_encoding_flag_{flag}", rebuilt.decoded == probe.replacement)

    target = OUT / "korean_smoke" / "THOG.dat"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(candidate)
    (OUT / "smoke_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"source_sha256": sha(original.original), "candidate_sha256": sha(candidate),
              "candidate_path": str(target), "checks": checks, "changes": plan,
              "changed_chunks": changed_chunks, "graphics_qa": "NOT_RUN",
              "font_offset_note": "원본 28개 항목의 handle-1 및 블록 시작+260 관계를 유지했으며 실제 로딩 검증은 아직 안 함"}
    (OUT / "container_test_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"checks": len(checks), "candidate_sha256": sha(candidate), "graphics_qa": "NOT_RUN"}))


if __name__ == "__main__":
    main()
