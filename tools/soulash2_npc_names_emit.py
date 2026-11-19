"""검토한 인명 음역을 원본 위치와 연결하며 UTF-8 이름 파일을 별도 생성한다."""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
INVENTORY = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029/effective_inventory/v4/translation_work_v2.jsonl"
TARGETS = ROOT / "working_private/SOULASH_2/translations/npc_names_reviewed_targets.json"
OUTPUT = ROOT / "working_private/SOULASH_2/translations/npc_names_20261030"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    targets = json.loads(TARGETS.read_text(encoding="utf-8"))
    grouped = defaultdict(list)
    for line in INVENTORY.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("axis") == "text_line" and "/npc/names/" in row["file"] and row["file"].endswith(".txt"):
            grouped[row["file"]].append(row)
    if set(targets) != {Path(f).stem for f in grouped}:
        raise ValueError("인명 파일 범위가 목록과 다름")
    OUTPUT.mkdir(parents=True, exist_ok=False)
    results, emitted = [], []
    for relative, rows in sorted(grouped.items()):
        source = SOURCE / relative
        digest = sha(source)
        original_lines = source.read_bytes().decode("utf-8").splitlines(keepends=True)
        translated = targets[source.stem].split("|")
        if len(rows) != len(original_lines) or len(rows) != len(translated):
            raise ValueError("행 수가 원본과 다름: " + relative)
        chunks = []
        for index, (row, original_line, target) in enumerate(zip(rows, original_lines, translated), 1):
            ending = "\r\n" if original_line.endswith("\r\n") else "\n" if original_line.endswith("\n") else "\r" if original_line.endswith("\r") else ""
            original = original_line[:-len(ending)] if ending else original_line
            assert row["source_file_sha256"] == digest
            assert row["line"] == index and row["source"] == original
            assert row["source_value_sha256"] == hashlib.sha256(original.encode("utf-8")).hexdigest()
            assert row["location_id"] == relative + "#line/" + str(index)
            if not re.fullmatch(r"[가-힣]+(?: [가-힣]+)*", target):
                raise ValueError("검토되지 않은 문자 또는 빈 이름: " + row["location_id"])
            new_row = dict(row)
            new_row["target"] = target
            new_row["translation_status"] = "REVIEWED"
            new_row["translation_review"] = {"method": "원본 순서의 이름 전체를 직접 읽고 종족별 발음에 맞춰 한글 음역", "target_source": TARGETS.relative_to(ROOT).as_posix(), "target_source_sha256": sha(TARGETS)}
            emitted.append(new_row)
            chunks.append(target + ending)
        destination = OUTPUT / "payload" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes("".join(chunks).encode("utf-8"))
        results.append({"path": relative, "source_sha256": digest, "target_sha256": sha(destination), "rows": len(rows)})
    batch = OUTPUT / "npc_names_001.jsonl"
    batch.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in emitted), encoding="utf-8")
    manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "status": "TRANSLATED_REQUIRES_INDEPENDENT_VALIDATION", "rows": len(emitted), "files": results,
                "inputs": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)} for p in [INVENTORY, TARGETS, Path(__file__)]],
                "batch": {"path": batch.relative_to(ROOT).as_posix(), "sha256": sha(batch)}, "notes": ["35개 인명 파일의 모든2422행 음역", "중복 인명과 원본 순서·줄끝·최종 개행을 보존", "게임 실행 검수는 별도"]}
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(emitted), "files": len(results), "batch": str(batch.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
