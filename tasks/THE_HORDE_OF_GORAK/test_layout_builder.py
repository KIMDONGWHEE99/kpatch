"""별도 Nebula 재추출 및 전체 원시 바이트 비교로 배치 수정 경계를 검증한다."""
from __future__ import annotations
import copy
import json
import struct
from pathlib import Path

from dat_container import DatFile, sha
from validate_candidate import differences, runtime_checksum

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "working_private/THE_HORDE_OF_GORAK"


def main():
    before_path = ROOT / "build_candidate/THE_HORDE_OF_GORAK/ko_candidate_01/THOG.dat"
    after_path = WORK / "layout_smoke_01/THOG.dat"
    before, after = DatFile.load(before_path), DatFile.load(after_path)
    checks = []

    def check(label, truth):
        checks.append({"check": label, "status": "PASS" if truth else "FAIL"})

    old_package = json.loads((WORK / "validation_01/nebula_candidate/package.json").read_text(encoding="utf-8"))
    new_package = json.loads((WORK / "layout_smoke_01/nebula/package.json").read_text(encoding="utf-8"))
    expected = copy.deepcopy(old_package)
    check("original_candidate_identity", sha(before.original) == "4854dc417f63aa69ef5ee7ed59bfe0b6d49d6eae091e3adaa7fc864f2b66e348")
    for old, new in zip(before.objects, after.objects):
        want = bytearray(old.decoded)
        if old.index == 514:
            struct.pack_into("<H", want, 136, 5)
            expected["FrameItems"]["Items"]["514"]["Properties"]["ObjectParagraphs"]["Paragraphs"][0]["FontHandle"] = 6
        if old.index in (510, 1000):
            height = {510: 300, 1000: 144}[old.index]
            struct.pack_into("<I", want, 124, height)
            expected["FrameItems"]["Items"][str(old.index)]["Properties"]["ObjectParagraphs"]["Height"] = height
        check(f"object_{old.index}_exact_bytes", bytes(want) == new.decoded)
    for old, new in zip(before.fonts, after.fonts):
        want = bytearray(old.decoded)
        if old.handle == 21:
            struct.pack_into("<i", want, 12, -20)
        check(f"font_{old.handle}_exact_bytes", old.handle == new.handle and bytes(want) == new.decoded)
    expected["FontBank"]["Fonts"]["21"]["Height"] = -20
    want = bytearray(before.one(0x2258).decoded)
    struct.pack_into("<i", want, 1344, -20)
    check("embedded_mapping_exact_bytes", bytes(want) == after.one(0x2258).decoded)
    allowed = {0x2256, 0x2257, 0x2258, 0x6667, 0x5556, 0x2242}
    for name, old in before.by_location.items():
        new = after.by_location[name]
        if not old.children and old.chunk_id not in allowed:
            check("unchanged_chunk_" + name, old.raw == new.raw)
    check("same_chunk_identities", set(before.by_location) == set(after.by_location))
    check("same_header", before.header == after.header)
    offsets = list(struct.unpack("<" + "I" * (len(after.one(0x5556).decoded) // 4), after.one(0x5556).decoded))
    check("font_offsets", all(offsets[b.handle - 1] == b.offset + 260 for b in after.fonts))
    expected["FontOffsets"].update(Offsets=offsets, SortedOffsets=sorted(x for x in offsets if x))
    expected["FontBank"]["ChunkSize"] = len(after.one(0x6667).raw)
    expected["FontOffsets"]["ChunkSize"] = len(after.one(0x5556).raw)
    expected["Protection"] = {"byte_length": 4, "sha256": sha(after.one(0x2242).decoded)}
    diff = list(differences(expected, new_package))
    check("independent_full_semantic_tree", not diff)
    start, end = [len(after.header) + after.one(x).offset for x in (0x222F, 0x2242)]
    check("runtime_integrity", runtime_checksum(after.original[start:end]) == struct.unpack("<I", after.one(0x2242).decoded)[0])
    errors = [x for x in checks if x["status"] != "PASS"]
    report = {"status": "PASS" if not errors else "FAIL", "before_sha256": sha(before.original),
              "after_sha256": sha(after.original), "checks": checks, "errors": errors, "semantic_differences": diff,
              "method": "빌더 보고서 미사용. 독립 Nebula 의미 트리 전체와 원시 필드별 정확 바이트 비교",
              "runtime_qa": "NOT_RUN"}
    (WORK / "layout_smoke_01/independent_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks), "errors": errors, "semantic_differences": diff}, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
