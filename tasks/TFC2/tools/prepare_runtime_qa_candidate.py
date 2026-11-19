from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any


def aligned_string(text: str) -> bytes:
    encoded = text.encode("utf-8")
    return struct.pack("<I", len(encoded)) + encoded + b"\0" * ((-len(encoded)) % 4)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_environment(env: Any) -> bytes:
    try:
        return env.file.save(packer="original")
    except TypeError:
        return env.file.save()


def main() -> None:
    parser = argparse.ArgumentParser(description="TFC2 그래픽 QA용 저장 데이터 격리 이름 적용")
    parser.add_argument("--qa-root", type=Path, required=True)
    parser.add_argument("--unitypy-root", type=Path, required=True)
    parser.add_argument("--product-name", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.unitypy_root.resolve()))
    import UnityPy  # type: ignore

    path = args.qa_root / "TFC2_Data/globalgamemanagers"
    original = path.read_bytes()
    env = UnityPy.load(str(path))
    targets = [obj for obj in env.objects if obj.type.name == "PlayerSettings"]
    if len(targets) != 1:
        raise RuntimeError(f"PlayerSettings 객체 수가 예상과 다릅니다: {len(targets)}")
    obj = targets[0]
    raw = obj.get_raw_data()
    old = aligned_string("TFC2")
    new = aligned_string(args.product_name)
    if raw.count(old) != 1:
        raise RuntimeError(f"PlayerSettings 제품 이름 위치 수가 예상과 다릅니다: {raw.count(old)}")
    obj.set_raw_data(raw.replace(old, new, 1))
    output = save_environment(env)
    path.write_bytes(output)

    reopened = UnityPy.load(str(path))
    verify_obj = next(obj for obj in reopened.objects if obj.type.name == "PlayerSettings")
    verify_raw = verify_obj.get_raw_data()
    if verify_raw.count(new) != 1 or verify_raw.count(old) != 0:
        raise RuntimeError("QA 제품 이름 재개방 검증에 실패했습니다.")
    report = {
        "schema_version": 1,
        "passed": True,
        "qa_root": str(args.qa_root.resolve()),
        "company_name": "Wield Interactive",
        "original_product_name": "TFC2",
        "qa_product_name": args.product_name,
        "persistent_data_relative": f"AppData/LocalLow/Wield Interactive/{args.product_name}",
        "source_size": len(original),
        "output_size": len(output),
        "source_sha256": sha256(original),
        "output_sha256": sha256(output),
        "reopened": True,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
