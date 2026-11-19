"""후보를 새로 열어 원본·공식 교정표·허용 필드와 독립적으로 대조합니다."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import struct
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/python_deps"))
import UnityPy
from UnityPy.streams import EndianBinaryWriter
from catalog import Catalog, bundle_crc, catalog_hash, digest
from validate_translation import validate, ko_target_rows
from dialogue_patch import FILES as DIALOGUE_FILES, OBJECTS as DIALOGUE_OBJECTS, load_inputs as load_dialogue_inputs, source_environment

SOURCE = ROOT / "source_original/ALASKA_GOLD_FEVER/25782395/game"
WORK = ROOT / "working_private/ALASKA_GOLD_FEVER"
DATA = Path("Alaska Gold Fever_Data")
AA = DATA / "StreamingAssets/aa"
BUNDLES = AA / "StandaloneWindows64"
COLLECTIONS = ("AlaskaStoryTranslations", "AlaskaTranslations", "DLCBanditsTranslations", "UtilitiesTranslations")


def filesystem_path(path):
    absolute = os.path.abspath(path)
    return Path(absolute if absolute.startswith("\\\\?\\") else "\\\\?\\" + absolute)


def file_digest(path):
    value = hashlib.sha256()
    with filesystem_path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def field_differences(before, after, path=""):
    if type(before) != type(after):
        return [path]
    if isinstance(before, dict):
        if before.keys() != after.keys():
            return [path + "/keys"]
        return [part for key in before for part in field_differences(before[key], after[key], path + "/" + key)]
    if isinstance(before, list):
        if len(before) != len(after):
            return [path + "/length"]
        return [part for i, (old, new) in enumerate(zip(before, after)) for part in field_differences(old, new, path + "/" + str(i))]
    return [] if before == after else [path]


def assets(environment):
    if hasattr(environment.file, "objects"):
        return {environment.file.name: environment.file}
    return {name: value for name, value in environment.file.files.items() if hasattr(value, "objects")}


def object_map(environment):
    result = {}
    for name, asset in assets(environment).items():
        for path_id, obj in asset.objects.items():
            key = (name, int(path_id))
            if key in result:
                raise ValueError("동일한 객체 위치가 중복되었습니다.")
            result[key] = obj
    return result


def metadata(environment):
    result = {}
    for name, asset in assets(environment).items():
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
            "version": asset.header.version, "unity_version": asset.unity_version,
            "endian": asset.header.endian, "reserved": asset.header.reserved.hex(),
            "unknown": asset.unknown, "platform": int(asset.target_platform),
            "embedded_typetree": asset._enable_type_tree,
            "types": len(asset.types), "ref_types": len(asset.ref_types or []),
            "scripts": len(asset.script_types), "externals": len(asset.externals),
            "metadata_content_sha256": digest(writer.bytes),
            "user_information": asset.userInformation,
            "object_records": [(int(obj.path_id), int(obj.type_id), int(obj.class_id)) for obj in asset.objects.values()],
        }
    return result


def verify_bundle(source_path, candidate_path, rows):
    original_bytes = source_path.read_bytes()
    candidate_bytes = candidate_path.read_bytes()
    original = UnityPy.load(original_bytes)
    candidate = UnityPy.load(candidate_bytes)
    before, after = object_map(original), object_map(candidate)
    if before.keys() != after.keys() or metadata(original) != metadata(candidate):
        raise ValueError(f"번들 객체 목록·형식·참조·순서가 바뀌었습니다: {source_path.name}")
    targets = {}
    for row in rows:
        location = row["location"]
        if location["bundle"] != source_path.name:
            continue
        if location["bundle_sha256"] != digest(original_bytes):
            raise ValueError("교정표의 원본 번들 연결이 다릅니다.")
        targets.setdefault((location["asset"], int(location["path_id"])), []).append(row)
    changed_objects, positions, changed_fields = [], [], []
    for key, obj in before.items():
        new_obj = after[key]
        original_raw, candidate_raw = obj.get_raw_data(), new_obj.get_raw_data()
        if key not in targets:
            if original_raw != candidate_raw:
                raise ValueError(f"번역 대상이 아닌 객체가 바뀌었습니다: {key}")
            continue
        old_tree, new_tree = obj.read_typetree(), new_obj.read_typetree()
        source_entries = old_tree["m_TableData"]
        candidate_entries = new_tree["m_TableData"]
        if len(source_entries) != len(candidate_entries):
            raise ValueError(f"번역 행 수가 바뀌었습니다: {key}")
        translations = {int(row["id"]): row for row in targets[key]}
        if len(translations) != len(targets[key]) or set(translations) != {int(row["m_Id"]) for row in source_entries}:
            raise ValueError(f"공식 교정표와 한국어 원본 ID가 다릅니다: {key}")
        expected = copy.deepcopy(old_tree)
        expected_changes = []
        for index, entry in enumerate(source_entries):
            row = translations[int(entry["m_Id"])]
            if row["korean_original"] != entry["m_Localized"]:
                raise ValueError(f"위치별 한국어 원본이 다릅니다: {row['collection']}/{row['id']}")
            if new_tree["m_Name"] != row["collection"] + "_ko" or new_tree["m_LocaleId"]["m_Code"] != "ko":
                raise ValueError("번역의 한국어 슬롯 또는 표 이름이 바뀌었습니다.")
            value = row["translation"]
            if entry["m_Localized"] != value:
                expected["m_TableData"][index]["m_Localized"] = value
                expected_changes.append(f"/m_TableData/{index}/m_Localized")
            if candidate_entries[index]["m_Id"] != entry["m_Id"] or candidate_entries[index]["m_Localized"] != value:
                raise ValueError(f"후보의 위치별 번역이 다릅니다: {row['collection']}/{row['id']}")
            positions.append({"collection": row["collection"], "id": row["id"], "path_id": key[1], "index": index, "expected_sha256": digest(value.encode("utf-8")), "actual_sha256": digest(candidate_entries[index]["m_Localized"].encode("utf-8"))})
        actual_changes = field_differences(old_tree, new_tree)
        if new_tree != expected or sorted(actual_changes) != sorted(expected_changes):
            raise ValueError(f"번역 문자열 이외의 필드가 변경되었습니다: {key}, {actual_changes[:10]}")
        if bool(expected_changes) != (original_raw != candidate_raw):
            raise ValueError(f"객체 바이트 변화와 기대 번역 변화가 다릅니다: {key}")
        if expected_changes:
            changed_objects.append(key[1])
        changed_fields.append({"asset": key[0], "path_id": key[1], "fields": actual_changes})
    if not targets.keys() <= before.keys():
        raise ValueError("후보에 공식 교정표의 객체가 없습니다.")
    return {"status": "PASS", "file": source_path.name, "source_sha256": digest(original_bytes), "candidate_sha256": digest(candidate_bytes), "objects": len(before), "changed_objects": changed_objects, "positions": positions, "field_changes": changed_fields, "candidate_crc": bundle_crc(candidate_bytes)}


def verify_font(source_path, candidate_path):
    from scan_assets import GameGenerator
    generator = GameGenerator("6000.0.62f1")
    generator.load_local_dll_folder(str(ROOT / "extracted_private/ALASKA_GOLD_FEVER/25782395/code/dummy"))
    original = UnityPy.load(str(source_path))
    candidate = UnityPy.load(str(candidate_path))
    original.typetree_generator = generator
    before, after = object_map(original), object_map(candidate)
    if before.keys() != after.keys() or metadata(original) != metadata(candidate):
        raise ValueError("글꼴 파일의 객체 목록·참조·형식·순서가 변경되었습니다.")
    allowed = {504: {"/m_IsReadable", "/image data", "/m_StreamData/offset", "/m_StreamData/size", "/m_StreamData/path"}, 5149: {"/m_AtlasPopulationMode", "/m_IsMultiAtlasTexturesEnabled", "/m_SourceFontFile/m_PathID"}}
    changed, observed = [], []
    pixel_evidence = None
    for key, obj in before.items():
        new_obj = after[key]
        if obj.get_raw_data() == new_obj.get_raw_data():
            continue
        if key[1] not in allowed:
            raise ValueError(f"허용되지 않은 글꼴 파일 객체 변경: {key}")
        changed.append(key[1])
        nodes = obj._get_typetree_node()
        old_tree = obj.read_typetree(nodes=nodes)
        new_tree = new_obj.read_typetree(nodes=nodes)
        expected = copy.deepcopy(old_tree)
        if key[1] == 5149:
            if old_tree["m_Name"] != "SongMyung-Regular SDF" or old_tree["m_SourceFontFile"] != {"m_FileID": 0, "m_PathID": 0}:
                raise ValueError("한국어 글꼴 원본 참조가 검증된 구조와 다릅니다.")
            expected["m_AtlasPopulationMode"] = 1
            expected["m_IsMultiAtlasTexturesEnabled"] = True
            expected["m_SourceFontFile"]["m_PathID"] = 895
        else:
            stream = old_tree["m_StreamData"]
            if old_tree["m_Name"] != "SongMyung-Regular SDF Atlas" or stream["path"] != "resources.assets.resS" or old_tree["image data"]:
                raise ValueError("아틀라스 원본 픽셀 저장 구조가 예상과 다릅니다.")
            resource = source_path.parent / stream["path"]
            with resource.open("rb") as handle:
                handle.seek(stream["offset"])
                pixels = handle.read(stream["size"])
            if len(pixels) != stream["size"] or not pixels:
                raise ValueError("원본 아틀라스 픽셀을 전부 읽지 못했습니다.")
            expected["m_IsReadable"] = True
            expected["image data"] = pixels
            expected["m_StreamData"] = {"offset": 0, "size": 0, "path": ""}
            pixel_evidence = {"source_resource": stream["path"], "source_offset": stream["offset"], "size": len(pixels), "source_pixels_sha256": digest(pixels), "candidate_pixels_sha256": digest(new_tree["image data"])}
        actual_changes = set(field_differences(old_tree, new_tree))
        if expected != new_tree or actual_changes != allowed[key[1]]:
            raise ValueError(f"허용 필드 밖의 글꼴·아틀라스 변경: {key}, {actual_changes}")
        observed.append({"path_id": key[1], "fields": sorted(actual_changes), "source_raw_sha256": digest(obj.get_raw_data()), "candidate_raw_sha256": digest(new_obj.get_raw_data())})
    if set(changed) != set(allowed):
        raise ValueError(f"필수 글꼴·아틀라스 변경이 빠졌습니다: {changed}")
    return {"status": "PASS", "object_count": len(before), "changed_objects": sorted(changed), "field_changes": observed, "pixel_evidence": pixel_evidence, "runtime_font_rendering": "NOT_RUN"}


def verify_catalog(source_data, candidate_data, bundle_files):
    original, candidate = Catalog(source_data), Catalog(candidate_data)
    if original.header != candidate.header or original.keys != candidate.keys or original.locations.keys() != candidate.locations.keys():
        raise ValueError("카탈로그의 키·위치·헤더가 변경되었습니다.")
    changes, allowed, tails = [], set(), set()
    for offset, old in original.locations.items():
        new = candidate.locations[offset]
        if {key: value for key, value in old.items() if key != "options"} != {key: value for key, value in new.items() if key != "options"}:
            raise ValueError(f"카탈로그 경로·유형·의존관계 변경: {offset}")
        if "options" not in old:
            continue
        name = old["internal"].replace("\\", "/").rsplit("/", 1)[-1]
        values = bundle_files.get(name)
        if values is None or values[0] == values[1]:
            if old["options"] != new["options"]:
                raise ValueError(f"수정되지 않은 묶음의 옵션 변경: {name}")
            continue
        source_bundle, candidate_bundle = values
        a, b = old["options"], new["options"]
        if a["size"] != len(source_bundle) or a["crc"] != bundle_crc(source_bundle):
            raise ValueError(f"원본 목록 크기·CRC와 원본 번들이 다릅니다: {name}")
        mutable = {"hash_offset", "hash_bytes", "crc", "size"}
        if {key: value for key, value in a.items() if key not in mutable} != {key: value for key, value in b.items() if key not in mutable}:
            raise ValueError(f"카탈로그의 비허용 옵션 변경: {name}")
        if b["size"] != len(candidate_bundle) or b["crc"] != bundle_crc(candidate_bundle) or b["hash_bytes"] != digest(candidate_bundle)[:32]:
            raise ValueError(f"카탈로그 후보 크기·CRC·해시 불일치: {name}")
        if b["hash_offset"] < len(source_data) or b["hash_offset"] + 16 > len(candidate_data):
            raise ValueError("새 번들 해시가 허용된 추가 구간에 없습니다.")
        tails.update(range(b["hash_offset"], b["hash_offset"] + 16))
        allowed.update(range(a["offset"], a["offset"] + 4))
        allowed.update(range(a["offset"] + 8, a["offset"] + 16))
        changes.append(name)
    expected_changed = {name for name, values in bundle_files.items() if values[0] != values[1]}
    if set(changes) != expected_changed or tails != set(range(len(source_data), len(candidate_data))):
        raise ValueError("수정 묶음 목록 또는 추가 해시 구간이 다릅니다.")
    unexpected = [i for i, (a, b) in enumerate(zip(source_data, candidate_data)) if a != b and i not in allowed]
    if unexpected:
        raise ValueError(f"카탈로그 허용 바이트 밖의 변경: {unexpected[:10]}")
    return {"status": "PASS", "keys": len(original.keys), "locations": len(original.locations), "changed_bundles": sorted(expected_changed), "unexpected_byte_changes": unexpected}


def verify_dialogue(source_path, candidate_path, relative, rows, empty_menu):
    from scan_assets import read_bounded
    original_bytes, candidate_bytes = source_path.read_bytes(), candidate_path.read_bytes()
    original = source_environment(source_path)
    candidate = UnityPy.load(str(candidate_path))
    before, after = object_map(original), object_map(candidate)
    if before.keys() != after.keys() or metadata(original) != metadata(candidate):
        raise ValueError(f'대화 파일의 객체·형식·참조가 바뀌었습니다: {relative}')
    source_hash = digest(original_bytes)
    positions, changed_objects, changed_fields = [], [], []
    preserved = 0
    masked = bytearray(original_bytes)
    masked[24:32] = candidate_bytes[24:32]
    header = original.file.header
    if candidate.file.header.file_size != len(candidate_bytes):
        raise ValueError('대화 후보 헤더의 크기가 실제 크기와 다릅니다.')

    def at(tree, pointer):
        current = tree
        for part in pointer.strip('/').split('/'):
            current = current[int(part)] if isinstance(current, list) else current[part]
        return current

    for key, obj in before.items():
        new_obj = after[key]
        old_raw, new_raw = obj.get_raw_data(), new_obj.get_raw_data()
        path_id = key[1]
        if path_id not in DIALOGUE_OBJECTS[relative]:
            if old_raw != new_raw:
                raise ValueError(f'대화 대상 밖의 객체 변경: {relative}/{path_id}')
            continue
        entries = [row for row in rows if row['file'] == relative and row['path_id'] == path_id]
        blanks = [row for row in empty_menu if row['file'] == relative and row['path_id'] == path_id]
        if len(entries) != DIALOGUE_OBJECTS[relative][path_id] or len(blanks) != len(entries):
            raise ValueError('대화 또는 비어 있는 선택지의 개수가 다릅니다.')
        nodes = obj._get_typetree_node()
        old_tree, new_tree = read_bounded(obj), new_obj.read_typetree(nodes=nodes)
        original_object_hash = digest(old_raw)
        expected = copy.deepcopy(old_tree)
        allowed = []
        for row in entries:
            if row['file_sha256'] != source_hash or row['raw_sha256'] != original_object_hash or at(old_tree, row['field']) != row['original_korean']:
                raise ValueError(f'대화 원본 위치·해시가 다릅니다: {row["id"]}')
            field = at(expected, row['field'].rsplit('/', 1)[0])
            if field['title'] != 'ko':
                raise ValueError('한국어 대사 이외의 필드를 교체하려 합니다.')
            field['value'] = row['translation']
            actual = at(new_tree, row['field'])
            if actual != row['translation']:
                raise ValueError(f'후보의 대화 위치별 번역이 다릅니다: {row["id"]}')
            if row['translation'] != row['original_korean']:
                allowed.append(row['field'])
            positions.append({'id': row['id'], 'field': row['field'], 'expected_sha256': digest(row['translation'].encode('utf-8')), 'actual_sha256': digest(actual.encode('utf-8'))})
        for row in blanks:
            if at(old_tree, row['field']) != '' or at(new_tree, row['field']) != '':
                raise ValueError(f'비어 있어야 할 선택지 문구가 바뀌었습니다: {row["id"]}')
            preserved += 1
        differences = field_differences(old_tree, new_tree)
        if new_tree != expected or sorted(differences) != sorted(allowed):
            raise ValueError(f'한국어 대사 밖의 필드 변경: {relative}/{path_id}')
        if bool(allowed) != (old_raw != new_raw):
            raise ValueError('대사 변화와 객체 바이트 변화가 일치하지 않습니다.')
        if old_raw != new_raw:
            changed_objects.append(path_id)
            needle = struct.pack('<qqIi', path_id, obj.byte_start - header.data_offset, obj.byte_size, obj.type_id)
            if original_bytes[:header.data_offset].count(needle) != 1 or new_obj.byte_start < len(original_bytes) or new_obj.byte_start % 16:
                raise ValueError('대화 수정 객체의 추가 위치가 허용 범위와 다릅니다.')
            offset = original_bytes.index(needle)
            masked[offset + 8:offset + 20] = candidate_bytes[offset + 8:offset + 20]
        changed_fields.append({'path_id': path_id, 'fields': differences})
    if bytes(masked) != candidate_bytes[:len(original_bytes)]:
        raise ValueError('대화 파일의 기존 구간이 허용된 목록 바이트 밖에서 바뀌었습니다.')
    tail_position = len(original_bytes)
    for obj in sorted((after[(original.file.name, path_id)] for path_id in changed_objects), key=lambda item: item.byte_start):
        if any(candidate_bytes[tail_position:obj.byte_start]):
            raise ValueError('추가 객체 사이에 예상하지 못한 데이터가 있습니다.')
        tail_position = obj.byte_start + obj.byte_size
    if tail_position != len(candidate_bytes):
        raise ValueError('대화 후보 끝에 예상하지 못한 데이터가 있습니다.')
    return {'status': 'PASS', 'file': relative, 'objects': len(before), 'changed_objects': changed_objects,
            'positions': positions, 'field_changes': changed_fields, 'preserved_empty_menu_fields': preserved}


def run(candidate_dir, full_baseline=True):
    if not candidate_dir.resolve().is_relative_to(ROOT / "build_candidate/ALASKA_GOLD_FEVER"):
        raise ValueError("후보 검증 출력은 지정한 후보 경계 안에 있어야 합니다.")
    report = {"game_id": "ALASKA_GOLD_FEVER", "build_id": "25782395", "check_id": "G4_CANDIDATE_INDEPENDENT",
              "status": "NOT_RUN", "started_utc": datetime.now(timezone.utc).isoformat(), "command": [sys.executable, *sys.argv],
              "tool_sha256": file_digest(Path(__file__)), "runtime_loading": "NOT_RUN", "runtime_font_rendering": "NOT_RUN", "failures": []}
    try:
        manifest_path = candidate_dir / "build_manifest.json"
        manifest = load_json(manifest_path)
        report["candidate_manifest_sha256"] = file_digest(manifest_path)
        if manifest["game_id"] != "ALASKA_GOLD_FEVER" or manifest["build_id"] != "25782395":
            raise ValueError("후보 게임 또는 빌드가 다릅니다.")
        for value in [manifest["baseline_manifest"], manifest["translation_original"], manifest["font_input"], manifest["font_report"], *manifest["translation_inputs"], *manifest['dialogue_inputs'], *manifest['dialogue_sources']]:
            if file_digest(ROOT / value["path"]) != value["sha256"]:
                raise ValueError(f"후보 입력이 변경되어 검증이 만료됐습니다: {value['path']}")
        for name, expected in manifest["tool_hashes"].items():
            if file_digest(Path(__file__).with_name(name)) != expected:
                raise ValueError(f"후보 생성 도구가 변경됐습니다: {name}")
        baseline_path = ROOT / manifest["baseline_manifest"]["path"]
        baseline = load_json(baseline_path)
        if baseline["status"] != "PASS" or baseline["build_id"] != "25782395" or baseline_path.with_suffix(".sha256").read_text(encoding="ascii").split()[0] != file_digest(baseline_path):
            raise ValueError("원본 기준선 목록을 신뢰할 수 없습니다.")
        rows = []
        for collection in COLLECTIONS:
            rows.extend(load_json(WORK / "translation" / f"{collection}.json"))
        errors = validate(load_json(ROOT / manifest["translation_original"]["path"]), rows, require_review=True)
        if errors:
            raise ValueError(f"공식 교정표 검증 실패: {errors[:3]}")
        rows = ko_target_rows(rows)
        dialogue_rows, empty_menu, dialogue_inputs, dialogue_sources = load_dialogue_inputs()
        if dialogue_inputs != manifest['dialogue_inputs'] or dialogue_sources != manifest['dialogue_sources']:
            raise ValueError('후보와 현재 대화 입력의 연결이 다릅니다.')
        names = sorted({row["location"]["bundle"] for row in rows})
        allowed_files = {*[(BUNDLES / name).as_posix() for name in names], (AA / "catalog.bin").as_posix(), (AA / "catalog.hash").as_posix(), (DATA / "resources.assets").as_posix(), *DIALOGUE_FILES}
        actual_files = {path.relative_to(candidate_dir / "overlay").as_posix() for path in (candidate_dir / "overlay").rglob("*") if path.is_file()}
        manifest_files = {row["path"]: row for row in manifest["files"]}
        if len(names) != 2 or allowed_files != actual_files or allowed_files != manifest_files.keys() or len(manifest_files) != len(manifest["files"]):
            raise ValueError("후보의 파일 목록이 허용한 7개 파일과 다릅니다.")
        baseline_files = {row["path"]: row for row in baseline["files"]}
        if full_baseline:
            source_root = filesystem_path(SOURCE)
            actual_source_files = {path.relative_to(source_root).as_posix() for path in source_root.rglob("*") if path.is_file()}
            if actual_source_files != baseline_files.keys():
                raise ValueError("원본 사본의 전체 파일 목록이 달라졌습니다.")
        checked_source = 0
        for relative, item in baseline_files.items():
            if not full_baseline and relative not in allowed_files:
                continue
            path = filesystem_path(SOURCE / relative)
            if path.stat().st_size != item["size"] or file_digest(path) != item["sha256"]:
                raise ValueError(f"원본 사본이 기준선과 다릅니다: {relative}")
            checked_source += 1
        report["source_files_checked"] = checked_source
        report["full_source_baseline"] = "PASS" if full_baseline else "NOT_RUN"
        for relative, item in manifest_files.items():
            source_item = baseline_files[relative]
            if (item["source_size"], item["source_sha256"]) != (source_item["size"], source_item["sha256"]):
                raise ValueError("후보에 연결한 원본 해시가 기준선과 다릅니다.")
            path = candidate_dir / "overlay" / relative
            if path.stat().st_size != item["candidate_size"] or file_digest(path) != item["candidate_sha256"]:
                raise ValueError(f"후보 파일이 생성 명세와 다릅니다: {relative}")
        report["bundles"] = [verify_bundle(SOURCE / BUNDLES / name, candidate_dir / "overlay" / BUNDLES / name, rows) for name in names]
        report["font"] = verify_font(SOURCE / DATA / "resources.assets", candidate_dir / "overlay" / DATA / "resources.assets")
        report['dialogues'] = [verify_dialogue(SOURCE / relative, candidate_dir / 'overlay' / relative, relative, dialogue_rows, empty_menu) for relative in DIALOGUE_FILES]
        report['dialogue_position_count'] = sum(len(item['positions']) for item in report['dialogues'])
        report['preserved_empty_menu_fields'] = sum(item['preserved_empty_menu_fields'] for item in report['dialogues'])
        if report['dialogue_position_count'] != 966 or report['preserved_empty_menu_fields'] != 966:
            raise ValueError('후보의 대사 또는 빈 선택지 대조 개수가 다릅니다.')
        source_catalog = (SOURCE / AA / "catalog.bin").read_bytes()
        candidate_catalog = (candidate_dir / "overlay" / AA / "catalog.bin").read_bytes()
        report["catalog"] = verify_catalog(source_catalog, candidate_catalog, {name: ((SOURCE / BUNDLES / name).read_bytes(), (candidate_dir / "overlay" / BUNDLES / name).read_bytes()) for name in names})
        if catalog_hash(source_catalog) != (SOURCE / AA / "catalog.hash").read_text(encoding="ascii") or catalog_hash(candidate_catalog) != (candidate_dir / "overlay" / AA / "catalog.hash").read_text(encoding="ascii"):
            raise ValueError("원본 또는 후보 카탈로그의 동반 hash가 다릅니다.")
        report["catalog_hash"] = "PASS"
        report["position_count"] = sum(len(item["positions"]) for item in report["bundles"])
        if report["position_count"] != len(rows):
            raise ValueError("후보 대조 위치 수와 공식 교정표 수가 다릅니다.")
        report["status"] = "PASS"
        report["scope"] = "수정 후보 7개 파일·표 1893행·대사 966행·빈 선택지 966개·허용 필드·참조·카탈로그 대조. 전체 원본 재검사는 full_source_baseline, 실제 실행은 runtime_loading 값을 따릅니다."
        report["exit_code"] = 0
    except Exception as error:
        report["status"] = "FAIL"
        report["failures"].append(str(error))
        report["traceback"] = traceback.format_exc()
        report["exit_code"] = 1
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (candidate_dir / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "positions": report.get("position_count"), "failures": report["failures"], "report": str(candidate_dir / "verification.json")}, ensure_ascii=False))
    return report["exit_code"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="교정 후보의 원본·위치·객체 독립 대조")
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--skip-full-baseline", action="store_true", help="수정하는 7개 파일만 기준선과 대조합니다. 전체 원본 재검사는 NOT_RUN으로 남깁니다.")
    args = parser.parse_args()
    raise SystemExit(run(args.candidate_dir.resolve(), not args.skip_full_baseline))
