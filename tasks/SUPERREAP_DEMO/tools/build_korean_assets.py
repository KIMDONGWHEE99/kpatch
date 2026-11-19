#!/usr/bin/env python3
"""SuperReap Demo의 Unity 텍스트 자산과 글꼴 참조를 작업 복사본에 패치한다."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import ntpath
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


TOKEN_PATTERN = re.compile(r"%[A-Za-z0-9_.]+%?|{[^{}]+}|<[^>]+>|\[br /]")
FUSION_CAB = "CAB-3eae3cf36f9df4de0dafc1377add32c2"
FUSION_BUNDLE_RELATIVE = "StreamingAssets/yoo/DefaultPackage/259fdfc53ba5156c92dd3a5f15a71078.bundle"
FUSION_BUNDLE_PATH_ID = 3642251582287177650
FUSION_SHARED_PATH_ID = 1014
FUSION_BUNDLE_FONT_PATH_ID = 3368284683069913546
FUSION_SHARED_FONT_PATH_ID = 385
FUSION_RAW_FONT = "fusion-pixel-10px-monospaced-zh_hans_385.font"
YARN_LOCALIZATION_COPIES_PER_LOCALE = 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--managed-dir", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--translation-data", type=Path, required=True)
    parser.add_argument("--translations-dir", type=Path, required=True)
    parser.add_argument("--font-inventory", type=Path, required=True)
    parser.add_argument("--font-raw-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--unity-version", default="2022.3.62f3")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def token_signature(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text)


def check_tokens(source: str, target: str, label: str) -> None:
    if token_signature(source) != token_signature(target):
        raise RuntimeError(f"태그·토큰 불일치: {label}: {source!r} -> {target!r}")


def script_class(obj: Any) -> str:
    try:
        head = obj.parse_monobehaviour_head()
        script = head.m_Script.deref_parse_as_object()
        return str(script.m_ClassName)
    except Exception:
        return ""


def aligned_string_blob(text: str) -> bytes:
    encoded = text.encode("utf-8")
    padding = b"\x00" * ((4 - (len(encoded) % 4)) % 4)
    return struct.pack("<I", len(encoded)) + encoded + padding


def replace_serialized_string(obj: Any, source: str, target: str) -> None:
    """MonoBehaviour 전체를 다시 쓰지 않고 직렬화 문자열 한 필드만 교체한다."""
    raw = obj.get_raw_data()
    old = aligned_string_blob(source)
    new = aligned_string_blob(target)
    occurrences = raw.count(old)
    if occurrences != 1:
        raise RuntimeError(f"직렬화 문자열 위치 수가 1이 아님: {occurrences}: {source!r}")
    obj.set_raw_data(raw.replace(old, new, 1))


def read_aligned_string(data: bytes, offset: int) -> tuple[str, int]:
    if offset + 4 > len(data):
        raise RuntimeError("직렬화 문자열 길이를 읽을 수 없습니다.")
    size = struct.unpack_from("<I", data, offset)[0]
    end = offset + 4 + size
    aligned_end = (end + 3) & ~3
    if aligned_end > len(data):
        raise RuntimeError("직렬화 문자열이 객체 범위를 벗어났습니다.")
    return data[offset + 4:end].decode("utf-8"), aligned_end


def parse_yarn_localization(data: bytes) -> tuple[str, list[str], list[dict[str, Any]]]:
    """Yarn Localization의 키 배열과 값 문자열 위치를 안전하게 읽는다."""
    # ScriptableObject 공통 머리말: GameObject PPtr, enabled, Script PPtr = 28바이트.
    name, offset = read_aligned_string(data, 28)
    key_count = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    keys: list[str] = []
    for _ in range(key_count):
        key, offset = read_aligned_string(data, offset)
        keys.append(key)

    value_count = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    if value_count != key_count:
        raise RuntimeError(f"Yarn 키/값 수 불일치: {key_count}/{value_count}")
    values: list[dict[str, Any]] = []
    for key in keys:
        start = offset
        text, offset = read_aligned_string(data, offset)
        values.append({"key": key, "text": text, "start": start, "end": offset})
        # localizedAsset PPtr(12바이트)와 AssetReference 문자열 3개를 건너뛴다.
        offset += 12
        for _ in range(3):
            _, offset = read_aligned_string(data, offset)
    if len(data) - offset != 8:
        raise RuntimeError(f"Yarn Localization 꼬리 크기가 예상과 다릅니다: {len(data) - offset}")
    return name, keys, values


def patch_yarn_localization(obj: Any, translations: dict[str, str]) -> tuple[str, int]:
    raw = obj.get_raw_data()
    name, keys, values = parse_yarn_localization(raw)
    if set(keys) != set(translations) or len(keys) != len(translations):
        missing = sorted(set(translations) - set(keys))
        extra = sorted(set(keys) - set(translations))
        raise RuntimeError(f"Yarn 대사 ID 불일치 {name}: 누락 {missing[:3]}, 추가 {extra[:3]}")
    patched = bytearray(raw)
    for value in reversed(values):
        key = str(value["key"])
        source = str(value["text"])
        target = translations[key]
        check_tokens(source, target, f"Yarn:{name}:{key}")
        patched[int(value["start"]):int(value["end"])] = aligned_string_blob(target)
    obj.set_raw_data(bytes(patched))
    return name, len(values)


def locale_code(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("m_Code", ""))
    return str(value)


def table_collection(name: str) -> str:
    for suffix in ("_zh-CN", "_zh-Hant", "_en"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def pptr(file_id: int, path_id: int) -> dict[str, int]:
    return {"m_FileID": int(file_id), "m_PathID": int(path_id)}


def external_basename(path: str) -> str:
    normalized = path.replace("\\", "/").rstrip("/")
    return normalized.rsplit("/", 1)[-1]


def fusion_pptr(obj: Any) -> dict[str, int] | None:
    assets_file = obj.assets_file
    name = str(getattr(assets_file, "name", ""))
    if name == "sharedassets0.assets":
        return pptr(0, FUSION_SHARED_PATH_ID)
    if name == FUSION_CAB:
        return pptr(0, FUSION_BUNDLE_PATH_ID)
    for index, external in enumerate(getattr(assets_file, "externals", []), 1):
        base = external_basename(str(external.path))
        if base == "sharedassets0.assets":
            return pptr(index, FUSION_SHARED_PATH_ID)
        if base == FUSION_CAB:
            return pptr(index, FUSION_BUNDLE_PATH_ID)
    return None


def is_fusion_font_asset(obj: Any) -> bool:
    assets_file = obj.assets_file
    name = str(getattr(assets_file, "name", ""))
    path_id = int(obj.path_id)
    return (name == "sharedassets0.assets" and path_id == FUSION_SHARED_PATH_ID) or (
        name == FUSION_CAB and path_id == FUSION_BUNDLE_PATH_ID
    )


def parse_dialogue(text: str) -> tuple[list[str], list[list[str]]]:
    lines = text.lstrip("\ufeff").splitlines()
    if not lines:
        raise RuntimeError("Dialogue.en이 비어 있습니다.")
    header = next(csv.reader([lines[0]]))
    rows: list[list[str]] = []
    for line_number, line in enumerate(lines[1:], 2):
        if not line:
            continue
        first = line.split(",", 2)
        if len(first) != 3:
            raise RuntimeError(f"대사 CSV 앞부분 해석 실패: {line_number}")
        language, item_id, remainder = first
        tail = remainder.rsplit(",", 5)
        if len(tail) != 6:
            raise RuntimeError(f"대사 CSV 뒷부분 해석 실패: {line_number}")
        text_field, file_name, node, yarn_line, lock, comment = tail
        # 원본의 일부 행은 쉼표가 든 본문을 따옴표로 감싸지 않았다.
        # 오른쪽 메타데이터 5칸을 먼저 분리했으므로, 따옴표가 있을 때만 CSV 해제를 한다.
        if len(text_field) >= 2 and text_field.startswith('"') and text_field.endswith('"'):
            parsed_text = next(csv.reader([text_field]))
            if len(parsed_text) != 1:
                raise RuntimeError(f"대사 본문 해석 실패: {line_number}")
            dialogue_text = parsed_text[0]
        else:
            dialogue_text = text_field
        rows.append([language, item_id, dialogue_text, file_name, node, yarn_line, lock, comment])
    return header, rows


def build_dialogue(text: str, translations: dict[str, str]) -> tuple[str, int]:
    header, rows = parse_dialogue(text)
    seen: set[str] = set()
    for row in rows:
        item_id = row[1]
        if item_id not in translations:
            raise RuntimeError(f"대사 번역 누락: {item_id}")
        check_tokens(row[2], translations[item_id], item_id)
        row[2] = translations[item_id]
        seen.add(item_id)
    extra = set(translations) - seen
    if extra:
        raise RuntimeError(f"원본에 없는 대사 번역 ID: {sorted(extra)[:5]}")
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(rows)
    return "\ufeff" + stream.getvalue(), len(rows)


def decode_text_asset(value: Any) -> tuple[str, bool]:
    raw = bytes(value) if isinstance(value, (bytes, bytearray)) else str(value).encode("utf-8")
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig"), has_bom


def encode_text_asset(text: str, has_bom: bool) -> str:
    # 이 Unity 버전의 TextAsset m_Script는 바이트 배열이 아니라 직렬화 문자열이다.
    return ("\ufeff" if has_bom else "") + text.lstrip("\ufeff")


def save_environment(env: Any) -> bytes:
    return env.file.save(packer="original")


def main() -> None:
    args = parse_args()
    inventory = load_json(args.inventory)
    localization_rows = load_json(args.translation_data / "localization_entries.json")
    direct_rows = load_json(args.translation_data / "direct_text_entries.json")
    config_audit = load_json(args.translation_data / "config_localization_audit.json")
    localization_map: dict[str, str] = load_json(args.translations_dir / "localization_ko.json")
    direct_map: dict[str, str] = load_json(args.translations_dir / "direct_ko.json")
    dialogue_map: dict[str, str] = load_json(args.translations_dir / "dialogue_ko.json")
    font_inventory = load_json(args.font_inventory)

    merged_text_map = dict(localization_map)
    merged_text_map.update(direct_map)
    key_to_korean: dict[str, str] = {}
    table_id_to_korean: dict[tuple[str, int], str] = {}
    for row in localization_rows:
        source = str(row["source"])
        if source not in localization_map:
            raise RuntimeError(f"StringTable 번역 누락: {row['key']}")
        target = localization_map[source]
        check_tokens(source, target, str(row["key"]))
        key_to_korean[str(row["key"])] = target
        table_id_to_korean[(str(row["table"]), int(row["id"]))] = target

    direct_targets: dict[tuple[str, int], dict[tuple[str, str], str]] = defaultdict(dict)
    expected_direct = 0
    for row in direct_rows:
        if row["classification"] != "VISIBLE_TRANSLATE":
            continue
        source = str(row["source"])
        if source not in merged_text_map:
            raise RuntimeError(f"TMP/Text 직접 문구 번역 누락: {source!r}")
        target = merged_text_map[source]
        check_tokens(source, target, f"{row['file']}:{row['path_id']}")
        direct_targets[(str(row["file"]), int(row["path_id"]))][
            (str(row["class"]), source)
        ] = target
        expected_direct += 1

    config_targets: dict[str, dict[tuple[int, str], str]] = defaultdict(dict)
    for row in config_audit["config_fields"]:
        if row["classification"] != "VISIBLE_TRANSLATE" or row["field"] == "comnent":
            continue
        target = ""
        for key in row["present_localization_keys"]:
            target = key_to_korean.get(str(key), "")
            if target:
                break
        if not target and row["asset"] == "tbfarmcfg" and row["field"] == "name":
            target = key_to_korean.get(f"farm.crop.{row['id']}.name", "")
        if not target:
            target = merged_text_map.get(str(row["source"]), "")
        if not target:
            raise RuntimeError(
                f"설정 표시 필드 번역 누락: {row['asset']} {row['id']} {row['field']} {row['source']!r}"
            )
        check_tokens(str(row["source"]), target, f"{row['asset']}:{row['id']}:{row['field']}")
        config_targets[str(row["asset"])][(int(row["record_index"]), str(row["field"]))] = target

    font_files = {str(row["file"]) for row in font_inventory["tmp_text_usages"]}
    target_files: set[str] = set(font_files)
    target_files.update(file for file, _ in direct_targets)
    target_files.update(
        str(file_row["relative_path"])
        for file_row in inventory["files"]
        if file_row["localization_tables"]
        or any(item["name"] == "Dialogue.en" or item["name"] in config_targets for item in file_row["text_assets"])
    )
    target_files.add("resources.assets")
    target_files.add("sharedassets0.assets")
    target_files.add(FUSION_BUNDLE_RELATIVE)

    generator = TypeTreeGenerator(args.unity_version)
    generator.load_local_dll_folder(str(args.managed_dir))
    fusion_font_data = (args.font_raw_dir / FUSION_RAW_FONT).read_bytes()
    report_rows: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()

    for relative in sorted(target_files, key=str.casefold):
        source = args.data_root / Path(relative)
        if not source.is_file():
            raise FileNotFoundError(source)
        env = UnityPy.load(str(source))
        env.typetree_generator = generator
        counts: Counter[str] = Counter()
        errors: list[str] = []
        for obj in env.objects:
            object_type = obj.type.name
            class_name = script_class(obj) if object_type == "MonoBehaviour" else ""
            object_key = (relative, int(obj.path_id))

            if object_type == "MonoBehaviour" and class_name in {"TextMeshPro", "TextMeshProUGUI"}:
                try:
                    tree = obj.read_typetree()
                    changed = False
                    source_text = str(tree.get("m_text", ""))
                    target_text = direct_targets.get(object_key, {}).get((class_name, source_text))
                    if target_text is not None:
                        check_tokens(source_text, target_text, f"{relative}:{obj.path_id}")
                        tree["m_text"] = target_text
                        counts["direct_text"] += 1
                        changed = True
                    font_ref = fusion_pptr(obj)
                    if font_ref is None:
                        raise RuntimeError("Fusion 글꼴 외부 참조를 찾지 못했습니다.")
                    if tree.get("m_fontAsset") != font_ref:
                        tree["m_fontAsset"] = font_ref
                        counts["tmp_font_refs"] += 1
                        changed = True
                    if changed:
                        obj.save_typetree(tree)
                except Exception as exc:
                    errors.append(f"{obj.path_id} {class_name}: {type(exc).__name__}: {exc}")
                continue

            if object_type == "MonoBehaviour" and class_name == "Localization":
                try:
                    locale_name, changed_rows = patch_yarn_localization(obj, dialogue_map)
                    counts[f"yarn_localization_{locale_name}"] += changed_rows
                except Exception as exc:
                    errors.append(f"{obj.path_id} Yarn Localization: {type(exc).__name__}: {exc}")
                continue

            if object_type == "MonoBehaviour" and class_name == "TMP_FontAsset":
                if not is_fusion_font_asset(obj):
                    continue
                try:
                    tree = obj.read_typetree()
                    changed = False
                    if int(tree.get("m_AtlasPopulationMode", -1)) != 1:
                        tree["m_AtlasPopulationMode"] = 1
                        changed = True
                    # 원본 4096x4096 아틀라스가 이미 거의 가득 차 있어 한글 동적 추가가
                    # 모두 실패한다. 두 번째 아틀라스를 만들 수 있게 해야 실제 실행에서
                    # 한글 글리프가 생성된다.
                    if int(tree.get("m_IsMultiAtlasTexturesEnabled", 0)) != 1:
                        tree["m_IsMultiAtlasTexturesEnabled"] = 1
                        changed = True
                    if changed:
                        obj.save_typetree(tree)
                    counts["tmp_fusion_multi_atlas"] += 1
                except Exception as exc:
                    errors.append(f"{obj.path_id} TMP_FontAsset: {type(exc).__name__}: {exc}")
                continue

            if object_type == "MonoBehaviour" and class_name == "Text":
                try:
                    tree = obj.read_typetree()
                    source_text = str(tree.get("m_Text", ""))
                    target_text = direct_targets.get(object_key, {}).get((class_name, source_text))
                    if target_text is not None:
                        check_tokens(source_text, target_text, f"{relative}:{obj.path_id}")
                        replace_serialized_string(obj, source_text, target_text)
                        counts["direct_text"] += 1
                except Exception as exc:
                    errors.append(f"{obj.path_id} Text: {type(exc).__name__}: {exc}")
                continue

            if object_type == "MonoBehaviour":
                if class_name == "TMP_Settings" or class_name == "StringTable":
                    try:
                        tree = obj.read_typetree()
                    except Exception as exc:
                        errors.append(f"{obj.path_id} {class_name}: {type(exc).__name__}: {exc}")
                        continue
                    changed = False
                    if class_name == "StringTable":
                        collection = table_collection(str(tree.get("m_Name", "")))
                        for entry in tree.get("m_TableData", []):
                            key = (collection, int(entry.get("m_Id", 0)))
                            if key not in table_id_to_korean:
                                continue
                            source_text = str(entry.get("m_Localized", ""))
                            target_text = table_id_to_korean[key]
                            entry["m_Localized"] = target_text
                            counts[f"string_table_{locale_code(tree.get('m_LocaleId')) or 'unknown'}"] += 1
                            changed = True
                    if class_name == "TMP_Settings":
                        font_ref = fusion_pptr(obj)
                        if font_ref is not None:
                            tree["m_defaultFontAsset"] = font_ref
                            tree["m_fallbackFontAssets"] = [font_ref]
                            counts["tmp_settings"] += 1
                            changed = True
                    if changed:
                        obj.save_typetree(tree)
                continue

            if object_type == "TextAsset":
                value = obj.read()
                name = str(getattr(value, "m_Name", ""))
                if name != "Dialogue.en" and name not in config_targets:
                    continue
                source_text, has_bom = decode_text_asset(getattr(value, "m_Script", b""))
                if name == "Dialogue.en":
                    target_text, changed_rows = build_dialogue(source_text, dialogue_map)
                    counts["dialogue_rows"] += changed_rows
                    value.m_Script = encode_text_asset(target_text, True)
                else:
                    records = json.loads(source_text.lstrip("\ufeff"))
                    wrapped = isinstance(records, dict)
                    record_list = [records] if wrapped else records
                    for (record_index, field), target_text in config_targets[name].items():
                        source_value = str(record_list[record_index][field])
                        check_tokens(source_value, target_text, f"{name}:{record_index}:{field}")
                        record_list[record_index][field] = target_text
                        counts["config_fields"] += 1
                    output_value: Any = record_list[0] if wrapped else record_list
                    target_text = json.dumps(output_value, ensure_ascii=False, separators=(",", ":"))
                    value.m_Script = encode_text_asset(target_text, has_bom)
                value.save()
                continue

            if object_type == "Font" and relative == "resources.assets" and int(obj.path_id) in {100, 101, 102, 103, 104}:
                tree = obj.read_typetree()
                tree["m_FontData"] = fusion_font_data
                obj.save_typetree(tree)
                counts["legacy_font_data"] += 1

        if errors:
            raise RuntimeError(f"{relative} 패치 오류:\n" + "\n".join(errors[:20]))
        if not counts:
            continue
        output = args.output_root / Path(relative)
        output.parent.mkdir(parents=True, exist_ok=True)
        output_bytes = save_environment(env)
        output.write_bytes(output_bytes)
        row = {
            "file": relative,
            "source_size": source.stat().st_size,
            "source_sha256": sha256_bytes(source.read_bytes()),
            "output_size": len(output_bytes),
            "output_sha256": sha256_bytes(output_bytes),
            "changes": dict(counts),
        }
        report_rows.append(row)
        totals.update(counts)

    if totals["direct_text"] != expected_direct:
        raise RuntimeError(f"직접 문구 적용 수 불일치: {totals['direct_text']} / {expected_direct}")
    expected_config = sum(len(rows) for rows in config_targets.values())
    if totals["config_fields"] != expected_config:
        raise RuntimeError(f"설정 필드 적용 수 불일치: {totals['config_fields']} / {expected_config}")
    if totals["dialogue_rows"] != len(dialogue_map):
        raise RuntimeError(f"대사 적용 수 불일치: {totals['dialogue_rows']} / {len(dialogue_map)}")
    if totals["tmp_fusion_multi_atlas"] != 2:
        raise RuntimeError(
            f"Fusion TMP 다중 아틀라스 적용 수 불일치: "
            f"{totals['tmp_fusion_multi_atlas']} / 2"
        )
    for locale in ("en", "zh-Hans", "zh-Hant"):
        expected_yarn_rows = len(dialogue_map) * YARN_LOCALIZATION_COPIES_PER_LOCALE
        if totals[f"yarn_localization_{locale}"] != expected_yarn_rows:
            raise RuntimeError(
                f"Yarn {locale} 대사 적용 수 불일치: "
                f"{totals[f'yarn_localization_{locale}']} / {expected_yarn_rows}"
            )
    for locale in ("en", "zh-CN", "zh-Hant"):
        if totals[f"string_table_{locale}"] != len(localization_rows):
            raise RuntimeError(
                f"{locale} StringTable 적용 수 불일치: {totals[f'string_table_{locale}']} / {len(localization_rows)}"
            )

    report = {
        "schema_version": 1,
        "files": report_rows,
        "summary": {
            "modified_files": len(report_rows),
            **dict(totals),
            "expected_direct_text": expected_direct,
            "expected_config_fields": expected_config,
            "expected_dialogue_rows": len(dialogue_map),
            "expected_string_table_rows_per_locale": len(localization_rows),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
