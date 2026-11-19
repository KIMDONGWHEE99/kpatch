"""한국어 번들 재저장·소규모 변경·목록 갱신을 비공개 사본에서 검사합니다."""
from __future__ import annotations

import argparse
import copy
import json
import platform
import struct
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/python_deps"))
import UnityPy
from UnityPy.streams import EndianBinaryReader, EndianBinaryWriter
from UnityPy.files.SerializedFile import SerializedType
from catalog import Catalog, bundle_crc, catalog_hash, digest, update_catalog


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def object_inventory(environment):
    result = {}
    for obj in environment.objects:
        key = f"{obj.assets_file.name}|{obj.path_id}|{obj.type.name}"
        if key in result:
            raise ValueError(f"중복된 객체 위치: {key}")
        result[key] = digest(obj.get_raw_data())
    return result


def save_preserving_layout(environment):
    """Unity 6의 원본 16바이트 객체 정렬과 메타데이터를 보존합니다."""
    replacements = {}
    for name, asset in environment.file.files.items():
        if not hasattr(asset, "objects"):
            continue
        if asset.header.version != 22:
            raise ValueError(f"검증하지 않은 직렬화 버전: {asset.header.version}")
        source = asset.reader.bytes
        reader = EndianBinaryReader(source, endian=asset.header.endian)
        reader.Position = 48
        if reader.read_string_to_null() != asset.unity_version:
            raise ValueError("메타데이터 Unity 버전이 일치하지 않습니다.")
        if reader.read_int() != asset._m_target_platform or reader.read_boolean() != asset._enable_type_tree:
            raise ValueError("플랫폼 또는 형식 정보가 일치하지 않습니다.")
        if reader.read_int() != len(asset.types):
            raise ValueError("객체 형식 수가 일치하지 않습니다.")
        for _ in asset.types:
            SerializedType(reader, asset, False)
        if reader.read_int() != len(asset.objects):
            raise ValueError("객체 수가 일치하지 않습니다.")
        positions = {}
        for _ in asset.objects:
            reader.align_stream(4)
            position = reader.Position
            path_id, offset, size, type_id = reader.read_long(), reader.read_long(), reader.read_u_int(), reader.read_int()
            obj = asset.objects[path_id]
            if (offset + asset.header.data_offset, size, type_id) != (obj.byte_start, obj.byte_size, obj.type_id):
                raise ValueError("객체 표와 원본 객체 위치가 다릅니다.")
            positions[path_id] = position
        output = bytearray(source[:asset.header.data_offset])
        previous_end = asset.header.data_offset
        for obj in sorted(asset.objects.values(), key=lambda item: item.byte_start):
            if obj.byte_start != (previous_end + 15) // 16 * 16 or any(source[previous_end:obj.byte_start]):
                raise ValueError("원본 객체 간 간격이 검증한 16바이트 정렬과 다릅니다.")
            while len(output) % 16:
                output.append(0)
            data = obj.data if obj.data is not None else obj.get_raw_data()
            struct.pack_into(asset.header.endian + "QI", output, positions[obj.path_id] + 8, len(output) - asset.header.data_offset, len(data))
            output.extend(data)
            previous_end = obj.byte_start + obj.byte_size
        if previous_end != len(source):
            raise ValueError("원본 파일 마지막에 알 수 없는 데이터가 있습니다.")
        struct.pack_into(">Q", output, 24, len(output))
        replacement = EndianBinaryReader(bytes(output))
        replacement.flags = asset.flags
        replacements[name] = replacement
    originals = dict(environment.file.files)
    try:
        environment.file.files.update(replacements)
        return environment.file.save(packer="original")
    finally:
        environment.file.files = originals


def structure_inventory(environment):
    result = {}
    for name, asset in environment.file.files.items():
        if not hasattr(asset, "objects"):
            result[name] = {"raw_sha256": digest(asset.bytes)}
            continue
        writer = EndianBinaryWriter(endian=asset.header.endian)
        for item in asset.types:
            item.write(asset, writer, False)
        for item in asset.ref_types or []:
            item.write(asset, writer, True)
        for item in asset.externals:
            item.write(asset.header, writer)
        for item in asset.script_types:
            item.write(asset.header, writer)
        result[name] = {
            "unity_version": asset.unity_version,
            "format_version": asset.header.version,
            "platform": int(asset.target_platform),
            "type_tree_enabled": asset._enable_type_tree,
            "types": len(asset.types), "reference_types": len(asset.ref_types or []),
            "externals": len(asset.externals), "scripts": len(asset.script_types),
            "schema_and_reference_sha256": digest(writer.bytes),
            "object_order": [int(key) for key in asset.objects],
            "user_information": asset.userInformation,
        }
    return result


def differences(before, after, path=""):
    if type(before) != type(after):
        return [path]
    if isinstance(before, dict):
        if before.keys() != after.keys():
            return [path + ".keys"]
        return [p for key in before for p in differences(before[key], after[key], f"{path}.{key}")]
    if isinstance(before, list):
        if len(before) != len(after):
            return [path + ".length"]
        return [p for i, (old, new) in enumerate(zip(before, after)) for p in differences(old, new, f"{path}[{i}]")]
    return [] if before == after else [path.lstrip(".")]


def sample_indices(rows):
    selected = {next(i for i, row in enumerate(rows) if row["m_Localized"])}
    for token in ("<", "{", "\n"):
        found = next((i for i, row in enumerate(rows) if token in row["m_Localized"]), None)
        if found is not None:
            selected.add(found)
    return sorted(selected)


def check_bundle(source: Path, output: Path):
    original_data = source.read_bytes()
    original = UnityPy.load(original_data)
    source_objects = object_inventory(original)
    source_structure = structure_inventory(original)
    result = {"file": source.name, "source_size": len(original_data), "source_sha256": digest(original_data), "source_crc": bundle_crc(original_data), "object_count": len(source_objects), "stages": {}}
    sample_changes = []
    candidate_data = None
    for stage in ("container_roundtrip", "typetree_roundtrip", "localized_probe"):
        environment = UnityPy.load(original_data)
        expected_trees, expected_fields = {}, {}
        for obj in environment.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            tree = obj.read_typetree()
            if "m_TableData" not in tree:
                continue
            old_tree = copy.deepcopy(tree)
            key = f"{obj.assets_file.name}|{obj.path_id}|{obj.type.name}"
            expected_fields[key] = []
            if stage == "localized_probe":
                for i in sample_indices(tree["m_TableData"]):
                    item = tree["m_TableData"][i]
                    before = item["m_Localized"]
                    item["m_Localized"] = before + " · 한국어 번역 검증"
                    sample_changes.append({"file": source.name, "asset": obj.assets_file.name, "path_id": obj.path_id, "table": tree["m_Name"], "entry_id": item["m_Id"], "field": f"m_TableData[{i}].m_Localized", "before": before, "after": item["m_Localized"]})
                    expected_fields[key].append(f"m_TableData[{i}].m_Localized")
            expected_trees[key] = tree
            if stage != "container_roundtrip":
                obj.save_typetree(tree)
            if sorted(differences(old_tree, tree)) != sorted(expected_fields[key]):
                raise ValueError(f"시험 번역 외의 필드가 변경되었습니다: {key}")
        output_data = save_preserving_layout(environment)
        target = output / stage / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(output_data)
        reopened = UnityPy.load(str(target))
        output_objects = object_inventory(reopened)
        if source_objects.keys() != output_objects.keys():
            raise ValueError(f"객체 목록이 변경되었습니다: {stage}, {source.name}")
        if source_structure != structure_inventory(reopened):
            raise ValueError(f"스키마·참조·객체 순서가 변경되었습니다: {stage}, {source.name}")
        if stage != "localized_probe":
            for name, asset in original.file.files.items():
                if asset.reader.bytes != reopened.file.files[name].reader.bytes:
                    raise ValueError(f"무변경 저장의 압축 전 원본 바이트가 바뀌었습니다: {stage}, {source.name}")
        changed = [key for key in source_objects if source_objects[key] != output_objects[key]]
        expected_changed = [key for key, fields in expected_fields.items() if fields]
        if sorted(changed) != sorted(expected_changed):
            raise ValueError(f"예상 밖 객체 바이트 변경: {stage}, {source.name}, {changed}")
        for obj in reopened.objects:
            key = f"{obj.assets_file.name}|{obj.path_id}|{obj.type.name}"
            if key in expected_trees:
                tree = obj.read_typetree()
                if tree != expected_trees[key]:
                    raise ValueError(f"재추출 결과가 기대 필드와 다릅니다: {stage}, {key}")
        result["stages"][stage] = {
            "status": "PASS", "output": str(target.relative_to(ROOT)),
            "output_size": len(output_data), "output_sha256": digest(output_data),
            "output_crc": bundle_crc(output_data), "byte_identical": original_data == output_data,
            "changed_objects": changed, "expected_field_changes": expected_fields,
            "schema_and_references_preserved": True,
            "uncompressed_byte_identical": stage != "localized_probe",
            "object_alignment": 16,
            "object_inventory": output_objects,
        }
        if stage == "localized_probe":
            candidate_data = output_data
    return result, sample_changes, candidate_data


def run(source: Path, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    aa = source / "Alaska Gold Fever_Data/StreamingAssets/aa"
    catalog_data = (aa / "catalog.bin").read_bytes()
    parsed = Catalog(catalog_data)
    settings = json.loads((aa / "settings.json").read_text(encoding="utf-8"))
    bundle_paths = sorted((aa / "StandaloneWindows64").glob("*korean*.bundle"))
    if len(bundle_paths) != 2:
        raise ValueError(f"예상 한국어 묶음 2개와 다릅니다: {len(bundle_paths)}")
    report = {
        "game_id": "ALASKA_GOLD_FEVER", "build_id": "25782395", "check_id": "G1_STATIC_RISK_PROBE",
        "started_utc": datetime.now(timezone.utc).isoformat(), "status": "NOT_RUN",
        "command": [sys.executable, *sys.argv], "python_version": platform.python_version(),
        "unitypy_version": UnityPy.__version__, "addressables_version": settings.get("m_AddressablesVersion"),
        "tools": {p.name: digest(p.read_bytes()) for p in (Path(__file__), Path(__file__).with_name("catalog.py"))},
        "files": [], "probe_changes": [],
        "runtime_loading": "NOT_RUN", "runtime_font_rendering": "NOT_RUN", "G1_overall": "NOT_RUN",
    }
    changes = []
    try:
        for path in bundle_paths:
            row, samples, candidate_data = check_bundle(path, output)
            for item in parsed.bundles()[path.name]:
                if item["options"]["crc"] != row["source_crc"] or item["options"]["size"] != row["source_size"]:
                    raise ValueError(f"원본 CRC 또는 크기가 목록과 다릅니다: {path.name}")
            row["source_catalog_crc_matches"] = True
            report["files"].append(row)
            report["probe_changes"].extend(samples)
            changes.append({"name": path.name, "source_size": row["source_size"], "candidate_bytes": candidate_data, "candidate_crc": bundle_crc(candidate_data)})
        updated, catalog_report = update_catalog(catalog_data, changes)
        (output / "localized_probe/catalog.bin").write_bytes(updated)
        source_hash = (aa / "catalog.hash").read_text(encoding="ascii")
        if catalog_hash(catalog_data) != source_hash:
            raise ValueError("원본 카탈로그 hash 파일과 계산값이 다릅니다.")
        candidate_hash = catalog_hash(updated)
        (output / "localized_probe/catalog.hash").write_text(candidate_hash, encoding="ascii")
        report["catalog"] = catalog_report
        report["catalog_hash"] = {
            "source": source_hash, "candidate": candidate_hash,
            "algorithm": "SpookyHash V2, zero seeds, little endian raw 128-bit bytes",
            "source_recalculation_matches": True,
            "settings_catalog_dependency_count": [len(item.get("m_Dependencies", [])) for item in settings["m_CatalogLocations"]],
            "status": "PASS", "note": "로컬 목록의 hash 의존성은 없지만 원본 빌드 도구와 동일한 규칙으로 동반 파일을 갱신합니다.",
        }
        report["references"] = [
            "https://docs.unity3d.com/6000.0/Documentation/ScriptReference/AssetBundle.LoadFromFile.html",
            "https://docs.unity3d.com/Packages/com.unity.addressables@2.7/api/UnityEngine.AddressableAssets.ResourceLocators.ContentCatalogData.html",
            "https://raw.githubusercontent.com/needle-mirror/com.unity.addressables/2.7.4/Editor/Build/DataBuilders/BuildScriptPackedMode.cs",
            "https://raw.githubusercontent.com/needle-mirror/com.unity.scriptablebuildpipeline/2.4.1/Editor/Utilities/HashingMethods.cs",
            "https://burtleburtle.net/bob/c/SpookyV2.h",
            "https://burtleburtle.net/bob/c/SpookyV2.cpp",
        ]
        report["status"] = "PASS"
        report["scope"] = "재저장·번역 필드·원본 CRC 일치·목록 변경 경계 정적 검사만 통과"
        report["exit_code"] = 0
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        report["exit_code"] = 1
        raise
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(output / "report.json", report)
    print(json.dumps({"status": report["status"], "bundle_count": len(report["files"]), "sample_fields": len(report["probe_changes"]), "runtime_loading": report["runtime_loading"], "report": str(output / "report.json")}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="한국어 자산 소규모 정적 위험 검사")
    parser.add_argument("--source", type=Path, default=ROOT / "source_original/ALASKA_GOLD_FEVER/25782395/game")
    parser.add_argument("--output", type=Path, default=ROOT / "working_private/ALASKA_GOLD_FEVER/risk_probe")
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT / "working_private/ALASKA_GOLD_FEVER/risk_probe"):
        raise ValueError("위험 검사 출력은 지정한 비공개 경계 안에 있어야 합니다.")
    run(args.source, args.output)
