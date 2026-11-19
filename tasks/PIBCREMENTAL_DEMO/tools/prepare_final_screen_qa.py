#!/usr/bin/env python3
"""검수 복사본에서 데모 완료 화면에 빠르게 도달할 수 있도록 조건을 낮춥니다."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def script_class(obj: Any) -> str:
    try:
        head = obj.parse_monobehaviour_head()
        return str(head.m_Script.deref_parse_as_object().m_ClassName)
    except Exception:
        return ""


def save_environment(environment: Any) -> bytes:
    try:
        return environment.file.save(packer="original")
    except TypeError:
        return environment.file.save()


def main() -> None:
    parser = argparse.ArgumentParser(description="Pibcremental 데모 완료 화면용 QA 상태 준비")
    parser.add_argument("--qa-root", type=Path, required=True)
    parser.add_argument("--qa-save", type=Path, required=True)
    parser.add_argument("--save-backup", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--unity-version", default="6000.4.0f1")
    args = parser.parse_args()

    qa_root = args.qa_root.resolve()
    qa_data = qa_root / "Pibcremental_Data/data.unity3d"
    managed_dir = qa_root / "Pibcremental_Data/Managed"
    qa_save = args.qa_save.resolve()
    save_backup = args.save_backup.resolve()

    if not qa_data.is_file() or not managed_dir.is_dir():
        raise RuntimeError(f"검수 복사본 구성이 올바르지 않습니다: {qa_root}")
    if not qa_save.is_file():
        raise RuntimeError(f"검수용 저장 파일을 찾을 수 없습니다: {qa_save}")
    if save_backup.exists():
        raise RuntimeError(f"저장 백업이 이미 있습니다: {save_backup}")

    save_before = qa_save.read_bytes()
    save_backup.parent.mkdir(parents=True, exist_ok=True)
    save_backup.write_bytes(save_before)
    save_document = json.loads(save_before.decode("utf-8-sig"))
    level_before = int(save_document["building"]["currentLevel"])
    save_document["building"]["currentLevel"] = 7
    qa_save.write_text(
        json.dumps(save_document, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    data_before_hash = sha256(qa_data)
    generator = TypeTreeGenerator(args.unity_version)
    generator.load_local_dll_folder(str(managed_dir))
    environment = UnityPy.load(str(qa_data))
    environment.typetree_generator = generator

    matches = [
        obj
        for obj in environment.objects
        if obj.type.name == "MonoBehaviour" and script_class(obj) == "CS_FinalQuestPanel"
    ]
    if len(matches) != 1:
        raise RuntimeError(f"CS_FinalQuestPanel 수가 예상과 다릅니다: {len(matches)}")

    target = matches[0]
    tree = target.read_typetree()
    required_pibs_before = int(tree["requiredPibsPerBuilding"])
    required_costumes_before = int(tree["requiredCostumesPerBuilding"])
    if required_pibs_before != 10 or required_costumes_before != 10:
        raise RuntimeError(
            "원본 데모 완료 조건이 예상과 다릅니다: "
            f"피블={required_pibs_before}, 의상={required_costumes_before}"
        )
    tree["requiredPibsPerBuilding"] = 0
    tree["requiredCostumesPerBuilding"] = 0
    target.save_typetree(tree)
    qa_data.write_bytes(save_environment(environment))

    reopened = UnityPy.load(str(qa_data))
    reopened.typetree_generator = generator
    reopened_matches = [
        obj
        for obj in reopened.objects
        if obj.type.name == "MonoBehaviour" and script_class(obj) == "CS_FinalQuestPanel"
    ]
    if len(reopened_matches) != 1:
        raise RuntimeError("수정한 완료 조건을 다시 열지 못했습니다.")
    reopened_tree = reopened_matches[0].read_typetree()
    if (
        int(reopened_tree["requiredPibsPerBuilding"]) != 0
        or int(reopened_tree["requiredCostumesPerBuilding"]) != 0
    ):
        raise RuntimeError("수정한 데모 완료 조건의 재검증에 실패했습니다.")

    report = {
        "schema_version": 1,
        "qa_only": True,
        "distributed_candidate_modified": False,
        "qa_root": str(qa_root),
        "qa_save": str(qa_save),
        "save_backup": str(save_backup),
        "save_sha256_before": hashlib.sha256(save_before).hexdigest().upper(),
        "save_sha256_after": sha256(qa_save),
        "tree_level_before": level_before,
        "tree_level_after": 7,
        "data_sha256_before": data_before_hash,
        "data_sha256_after": sha256(qa_data),
        "final_quest_path_id": int(target.path_id),
        "required_pibs_before": required_pibs_before,
        "required_pibs_after": 0,
        "required_costumes_before": required_costumes_before,
        "required_costumes_after": 0,
        "reopened": True,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
