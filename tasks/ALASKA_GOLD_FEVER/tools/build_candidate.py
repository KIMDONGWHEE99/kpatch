"""검토가 끝난 공식 번역표에서 덮어쓰지 않는 한국어 수정 후보를 만듭니다."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/python_deps"))
import UnityPy
from catalog import Catalog, bundle_crc, catalog_hash, digest, update_catalog
from risk_probe import save_preserving_layout
from validate_translation import validate, ko_target_rows
from dialogue_patch import FILES as DIALOGUE_FILES, load_inputs as load_dialogue_inputs, build_file as build_dialogue_file

SOURCE = ROOT / "source_original/ALASKA_GOLD_FEVER/25782395/game"
WORK = ROOT / "working_private/ALASKA_GOLD_FEVER"
DATA = Path("Alaska Gold Fever_Data")
AA = DATA / "StreamingAssets/aa"
BUNDLES = AA / "StandaloneWindows64"
BASELINE = ROOT / "extracted_private/ALASKA_GOLD_FEVER/25782395/baseline_manifest.json"
COLLECTIONS = ("AlaskaStoryTranslations", "AlaskaTranslations", "DLCBanditsTranslations", "UtilitiesTranslations")


def file_digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(candidate_id, font_overlay, font_report):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", candidate_id) or candidate_id.upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(10)], *[f"LPT{i}" for i in range(10)]}:
        raise ValueError("후보 ID에는 영문·숫자·밑줄·하이픈만 사용할 수 있습니다.")
    target = ROOT / "build_candidate/ALASKA_GOLD_FEVER" / candidate_id
    if target.exists():
        raise FileExistsError("기존 후보 ID는 덮어쓸 수 없습니다. 새 ID를 사용하세요.")
    baseline = load_json(BASELINE)
    if baseline.get("status") != "PASS" or baseline.get("build_id") != "25782395":
        raise ValueError("검증된 기준선이 없습니다.")
    baseline_digest = file_digest(BASELINE)
    if BASELINE.with_suffix(".sha256").read_text(encoding="ascii").split()[0] != baseline_digest:
        raise ValueError("기준선 목록 자체의 해시가 다릅니다.")
    original_path = WORK / "translation/inventory_original.json"
    original = load_json(original_path)
    reviewed, inputs = [], []
    for collection in COLLECTIONS:
        path = WORK / "translation" / f"{collection}.json"
        rows = load_json(path)
        if any(row["collection"] != collection for row in rows):
            raise ValueError(f"다른 표의 행이 섞였습니다: {collection}")
        reviewed.extend(rows)
        inputs.append({"path": str(path.relative_to(ROOT)), "sha256": file_digest(path), "rows": len(rows)})
    errors = validate(original, reviewed, require_review=True)
    if errors:
        raise ValueError(f"번역 검토·제어 정보 검사 실패 {len(errors)}건: {errors[:3]}")
    reviewed = ko_target_rows(reviewed)
    dialogue_rows, empty_menu, dialogue_inputs, dialogue_sources = load_dialogue_inputs()
    if any(row.get("location") is None for row in reviewed):
        raise ValueError("원본 한국어 위치가 없는 항목은 별도 처리 명세가 필요합니다.")
    font_evidence = load_json(font_report)
    if font_evidence.get("status") != "PASS" or font_evidence.get("probe_sha256") != file_digest(font_overlay):
        raise ValueError("글꼴 후보와 정적 검증 보고서가 일치하지 않습니다.")
    records = {row["path"]: row for row in baseline["files"]}
    bundle_names = sorted({row["location"]["bundle"] for row in reviewed})
    if len(bundle_names) != 2:
        raise ValueError("한국어 원본 묶음 수가 예상한 2개와 다릅니다.")
    required = [*[BUNDLES / name for name in bundle_names], AA / "catalog.bin", AA / "catalog.hash", DATA / "resources.assets", *map(Path, DIALOGUE_FILES)]
    for relative in required:
        path = SOURCE / relative
        expected = records[relative.as_posix()]
        if path.stat().st_size != expected["size"] or file_digest(path) != expected["sha256"]:
            raise ValueError(f"수정에 사용할 원본이 기준선과 다릅니다: {relative}")
    if font_evidence.get("source_sha256") != records[(DATA / "resources.assets").as_posix()]["sha256"]:
        raise ValueError("글꼴 후보의 원본 빌드가 다릅니다.")
    outputs, table_records, changes = {}, [], []
    for name in bundle_names:
        relative = BUNDLES / name
        source_data = (SOURCE / relative).read_bytes()
        source_hash = digest(source_data)
        environment = UnityPy.load(source_data)
        groups = {}
        for row in reviewed:
            location = row["location"]
            if location["bundle"] != name:
                continue
            if location["bundle_sha256"] != source_hash:
                raise ValueError(f"번역표에 연결된 원본 묶음 해시가 다릅니다: {name}")
            key = (location["asset"], int(location["path_id"]))
            groups.setdefault(key, {})[int(row["id"])] = row
        consumed, changed_count = set(), 0
        for obj in environment.objects:
            key = (obj.assets_file.name, int(obj.path_id))
            if key not in groups:
                continue
            rows = groups[key]
            tree = obj.read_typetree()
            if set(rows) != {int(item["m_Id"]) for item in tree["m_TableData"]} or len(rows) != len(tree["m_TableData"]):
                raise ValueError(f"번역표와 원본 한국어의 ID 목록·개수가 다릅니다: {key}")
            consumed.add(key)
            changed = 0
            for item in tree["m_TableData"]:
                row = rows[int(item["m_Id"])]
                if tree["m_Name"] != row["collection"] + "_ko" or tree["m_LocaleId"]["m_Code"] != "ko":
                    raise ValueError("표 이름 또는 언어 슬롯이 한국어 위치와 다릅니다.")
                if item["m_Localized"] != row["korean_original"] or digest(item["m_Localized"].encode("utf-8")) != row["korean_sha256"]:
                    raise ValueError(f"위치별 원본 문구가 다릅니다: {row['collection']}/{row['id']}")
                if item["m_Localized"] != row["translation"]:
                    item["m_Localized"] = row["translation"]
                    changed += 1
            if changed:
                obj.save_typetree(tree)
            changed_count += changed
            table_records.append({"bundle": name, "asset": key[0], "path_id": key[1], "table": tree["m_Name"], "rows": len(rows), "changed": changed})
        if consumed != groups.keys():
            raise ValueError("번역표가 지정한 객체 중 찾지 못한 위치가 있습니다.")
        candidate_data = save_preserving_layout(environment) if changed_count else source_data
        outputs[relative.as_posix()] = candidate_data
        if source_data != candidate_data:
            changes.append({"name": name, "source_size": len(source_data), "candidate_bytes": candidate_data, "candidate_crc": bundle_crc(candidate_data)})
    source_catalog = (SOURCE / AA / "catalog.bin").read_bytes()
    source_catalog_hash = (SOURCE / AA / "catalog.hash").read_text(encoding="ascii")
    if catalog_hash(source_catalog) != source_catalog_hash:
        raise ValueError("원본 카탈로그와 동반 해시가 다릅니다.")
    updated_catalog, catalog_report = update_catalog(source_catalog, changes)
    outputs[(AA / "catalog.bin").as_posix()] = updated_catalog
    outputs[(AA / "catalog.hash").as_posix()] = catalog_hash(updated_catalog).encode("ascii")
    outputs[(DATA / "resources.assets").as_posix()] = font_overlay.read_bytes()
    dialogue_records = []
    for relative in DIALOGUE_FILES:
        outputs[relative], records_for_file = build_dialogue_file(SOURCE / relative, relative, dialogue_rows)
        dialogue_records.extend(records_for_file)
    # 입력이 도중에 바뀌면 후보를 남기지 않고 중단합니다.
    for item in [*inputs, *dialogue_inputs, *dialogue_sources]:
        if file_digest(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("번역 입력이 후보 생성 도중 변경되었습니다.")
    target.mkdir(parents=True)
    manifest = {
        "game_id": "ALASKA_GOLD_FEVER", "build_id": "25782395", "candidate_id": candidate_id,
        "status": "NOT_RUN", "build_status": "PASS", "independent_verification": "NOT_RUN", "runtime_status": "NOT_RUN",
        "created_utc": datetime.now(timezone.utc).isoformat(), "command": [sys.executable, *sys.argv],
        "baseline_manifest": {"path": str(BASELINE.relative_to(ROOT)), "sha256": baseline_digest},
        "translation_original": {"path": str(original_path.relative_to(ROOT)), "sha256": file_digest(original_path)},
        "translation_inputs": inputs,
        "dialogue_inputs": dialogue_inputs, "dialogue_sources": dialogue_sources,
        "dialogues": dialogue_records, "preserved_empty_menu_fields": len(empty_menu),
        "excluded_english_orphan": {"collection": "AlaskaStoryTranslations", "id": "56888088429502464", "reason": "한국어 행·공유 키가 없는 영어 원문만의 고아행"},
        "font_input": {"path": str(font_overlay.relative_to(ROOT)), "sha256": file_digest(font_overlay)},
        "font_report": {"path": str(font_report.relative_to(ROOT)), "sha256": file_digest(font_report)},
        "tool_hashes": {name: file_digest(Path(__file__).with_name(name)) for name in ("build_candidate.py", "catalog.py", "risk_probe.py", "validate_translation.py", "dialogue_patch.py", "scan_assets.py")},
        "tables": table_records, "catalog": catalog_report, "files": [],
        "scope": "한국어 표 1893행·대화 966행과 한국어 글꼴. 빈 선택지 966개 보존. 실제 화면 및 전체 출처 검수는 별도입니다.",
    }
    for relative, data in sorted(outputs.items()):
        path = target / "overlay" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if file_digest(path) != digest(data):
            raise ValueError(f"기록 후 파일 재검사 실패: {relative}")
        manifest["files"].append({"path": relative, "source_size": records[relative]["size"], "source_sha256": records[relative]["sha256"], "candidate_size": len(data), "candidate_sha256": digest(data)})
    write_json(target / "build_manifest.json", manifest)
    print(json.dumps({"candidate": str(target), "files": len(outputs), "translated_rows": sum(row["rows"] for row in table_records), "edited_rows": sum(row["changed"] for row in table_records), "dialogue_rows": len(dialogue_rows), "edited_dialogues": sum(row["changed"] for row in dialogue_records), "independent_verification": "NOT_RUN"}, ensure_ascii=False))
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="검토 완료한 한국어 교정 후보 생성")
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--font-overlay", type=Path, default=WORK / "font_audit/probe_v3/resources.assets")
    parser.add_argument("--font-report", type=Path, default=WORK / "font_audit/font_probe_v3_report.json")
    args = parser.parse_args()
    build(args.candidate_id, args.font_overlay.resolve(), args.font_report.resolve())
