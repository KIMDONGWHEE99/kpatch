from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
from pathlib import Path

import UnityPy


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def aligned_string(text: str) -> bytes:
    encoded = text.encode("utf-8")
    return struct.pack("<I", len(encoded)) + encoded + b"\x00" * ((-len(encoded)) % 4)


def save_environment(environment: object) -> bytes:
    try:
        return environment.file.save(packer="original")
    except TypeError:
        return environment.file.save()


def main() -> None:
    parser = argparse.ArgumentParser(description="저장 데이터가 분리된 그래픽 QA 복사본을 준비합니다.")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--product-name", default="Pibcremental Korean QA")
    args = parser.parse_args()

    candidate = args.candidate.resolve()
    output = args.output.resolve()
    if output.exists():
        raise RuntimeError(f"QA 출력 폴더가 이미 있습니다: {output}")
    shutil.copytree(candidate, output)

    relative_data = Path("Pibcremental_Data/data.unity3d")
    candidate_data = candidate / relative_data
    qa_data = output / relative_data
    environment = UnityPy.load(str(qa_data))
    player_settings = [obj for obj in environment.objects if obj.type.name == "PlayerSettings"]
    if len(player_settings) != 1:
        raise RuntimeError(f"PlayerSettings 수가 예상과 다릅니다: {len(player_settings)}")

    obj = player_settings[0]
    raw = obj.get_raw_data()
    source_blob = aligned_string("Pibcremental")
    target_blob = aligned_string(args.product_name)
    if raw.count(source_blob) != 1:
        raise RuntimeError("제품명 원문을 정확히 한 번 찾지 못했습니다.")
    obj.set_raw_data(raw.replace(source_blob, target_blob, 1))
    qa_data.write_bytes(save_environment(environment))

    reopened = UnityPy.load(str(qa_data))
    reopened_settings = [obj for obj in reopened.objects if obj.type.name == "PlayerSettings"]
    reopened_raw = reopened_settings[0].get_raw_data()
    if target_blob not in reopened_raw or source_blob in reopened_raw:
        raise RuntimeError("QA 제품명 재검증에 실패했습니다.")

    differing_files: list[str] = []
    for candidate_file in sorted(path for path in candidate.rglob("*") if path.is_file()):
        relative = candidate_file.relative_to(candidate)
        qa_file = output / relative
        if sha256(candidate_file) != sha256(qa_file):
            differing_files.append(relative.as_posix())
    if differing_files != [relative_data.as_posix()]:
        raise RuntimeError(f"QA 복사본의 예상 밖 차이: {differing_files}")

    report = {
        "candidate": str(candidate),
        "qa_root": str(output),
        "isolated_product_name": args.product_name,
        "isolated_save_path": str(
            Path.home() / "AppData/LocalLow/Arcane Cabinet UG" / args.product_name
        ),
        "candidate_file_count": sum(1 for path in candidate.rglob("*") if path.is_file()),
        "qa_file_count": sum(1 for path in output.rglob("*") if path.is_file()),
        "differing_files": differing_files,
        "candidate_data_sha256": sha256(candidate_data),
        "qa_data_sha256": sha256(qa_data),
        "reopened": True,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
