"""독립 재복원 자료로 게임 동작 값·자원 연결·전체 파일 수정 경계를 대조합니다."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re

from pck_tools import read_pack
from validator import ROOT, WORK, save, sha
from validate_candidate import FIELD, script_code_tokens


ATLAS_CHANGES = {
    "assets/atlas.sprites/ui_game/purchase_land.tres": ("purchase_land", "uid://bej2m6h7m5xoh", 48),
    "assets/atlas.sprites/ui_game/icon_full.tres": ("icon_full", "uid://safhsqa37e4d", 24),
}


def leaves(value, pointer=()):
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield from leaves(child, pointer + (key,))
    elif isinstance(value, list) and value:
        for index, child in enumerate(value):
            yield from leaves(child, pointer + (index,))
    else:
        yield pointer, (type(value).__name__, value)


def containers(value, pointer=()):
    if isinstance(value, dict):
        yield pointer, ("dict", sorted(value))
        for key, child in value.items():
            yield from containers(child, pointer + (key,))
    elif isinstance(value, list):
        yield pointer, ("list", len(value))
        for index, child in enumerate(value):
            yield from containers(child, pointer + (index,))


def json_boundary(original, candidate, rows):
    errors, results = [], []
    grouped = defaultdict(list)
    for row in rows:
        if row["kind"] == "json":
            grouped[row["path"]].append(row)
    for path, expected in grouped.items():
        after = json.loads(candidate["entries"][path]["data"])
        actual_leaves = dict(leaves(after))
        permitted = {tuple(row["selector"]["pointer"]): ("str", row["target"]) for row in expected}
        before_entry = original["entries"].get(path)
        if before_entry:
            before = json.loads(before_entry["data"])
            old_leaves = dict(leaves(before))
            if set(old_leaves) != set(actual_leaves) or dict(containers(before)) != dict(containers(after)):
                errors.append({"path": path, "kind": "json_locations_or_structure"})
            unchanged = [pointer for pointer in old_leaves if pointer not in permitted]
            changed = [pointer for pointer in unchanged if old_leaves[pointer] != actual_leaves.get(pointer)]
            if changed:
                errors.append({"path": path, "kind": "json_nonvisible_values", "pointers": [list(p) for p in changed]})
            results.append({"path": path, "original_leaves": len(old_leaves), "candidate_leaves": len(actual_leaves),
                            "nonvisible_leaves": len(unchanged), "changed_nonvisible": len(changed)})
        else:
            if set(actual_leaves) != set(permitted) or any(actual_leaves[p] != permitted[p] for p in permitted if p in actual_leaves):
                errors.append({"path": path, "kind": "new_json_all_leaves"})
            results.append({"path": path, "candidate_leaves": len(actual_leaves), "new_asset": True})
    return {"status": "FAIL" if errors else "PASS", "errors": errors, "assets": results}


def resource_boundary(stage, report, assets, rows):
    restore = Path(report["restore_stage"])
    expected = defaultdict(list)
    for row in rows:
        if row["kind"] == "resource":
            expected[row["path"]].append(row)
    errors, results = [], []
    for asset in assets:
        if asset["kind"] != "resource":
            continue
        path = asset["path"]
        suffix = ".tscn" if path.endswith(".scn") else ".tres"
        relative = Path(path).with_suffix(suffix)
        before = (restore / "original/restored" / relative).read_text(encoding="utf-8-sig")
        after = (restore / "candidate/restored" / relative).read_text(encoding="utf-8-sig")
        fields = defaultdict(list)
        for match in FIELD.finditer(before):
            fields[match[1]].append(match)
        replacements = []
        for row in expected[path]:
            match = fields[row["selector"]["field"]][row["selector"]["ordinal"]]
            replacements.append((match.start(2), match.end(2), json.dumps(row["target"], ensure_ascii=False)))
        for start, end, target in sorted(replacements, reverse=True):
            before = before[:start] + target + before[end:]
        atlas = ATLAS_CHANGES.get(asset["source_path"])
        if atlas:
            name, uid, size = atlas
            original_link = 'path="res://assets/atlas.png"'
            original_uid = 'uid="uid://betknl634p02x"'
            if before.count(original_link) != 1 or before.count(original_uid) != 1:
                errors.append({"path": path, "kind": "atlas_original_link"})
            before = before.replace(original_link, 'path="res://assets/sprites/ui_game/' + name + '.png"')
            before = before.replace(original_uid, 'uid="' + uid + '"')
            before, changed = re.subn(r'^region\s*=\s*Rect2\([^\n]+\)', f"region = Rect2(0, 0, {size}, {size})", before, flags=re.M)
            if changed != 1:
                errors.append({"path": path, "kind": "atlas_original_region"})
        desired, actual = script_code_tokens(before), script_code_tokens(after)
        if desired != actual:
            different = next((index for index, pair in enumerate(zip(desired, actual)) if pair[0] != pair[1]), min(len(desired), len(actual)))
            errors.append({"path": path, "source_path": asset["source_path"], "kind": "resource_nontext_structure",
                           "first_token": different, "expected_tokens": len(desired), "actual_tokens": len(actual),
                           "expected_context": desired[max(0, different - 8):different + 12],
                           "actual_context": actual[max(0, different - 8):different + 12]})
        results.append({"path": path, "text_replacements": len(replacements), "atlas_exception": bool(atlas),
                        "status": "PASS" if desired == actual else "FAIL"})
    return {"status": "FAIL" if errors else "PASS", "resources": len(results), "errors": errors, "assets": results}


def file_boundaries(original, candidate, original_path, candidate_path, assets):
    media = json.loads((WORK / "media/final_disposition.json").read_text(encoding="utf-8"))
    approved_media = {p for row in media if row["disposition"] == "REPLACE_VECTOR" for p in row["paths"]}
    allowed = {row["path"] for row in assets} | {p for p in original["entries"] if p.endswith(".fontdata")} | approved_media
    original_names, candidate_names = set(original["entries"]), set(candidate["entries"])
    changed = {p for p in original_names & candidate_names if original["entries"][p]["data"] != candidate["entries"][p]["data"]}
    metadata_changed = {p for p in original_names & candidate_names
                        if any(original["entries"][p][field] != candidate["entries"][p][field]
                               for field in ("offset", "size", "flags", "raw", "md5"))}
    added, deleted = candidate_names - original_names, original_names - candidate_names
    errors = []
    actual_modified = changed | metadata_changed | added
    if deleted or actual_modified != allowed:
        errors.append({"kind": "pack_allowlist", "deleted": sorted(deleted), "unexpected": sorted(actual_modified - allowed), "unchanged_allowed": sorted(allowed - actual_modified)})
    prefix_ok = original["start"] == candidate["start"] and original["data"][:original["start"]] == candidate["data"][:candidate["start"]]
    if not prefix_ok:
        errors.append({"kind": "native_exe_prefix"})
    baseline_path = WORK / "baseline/source_manifest.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    expected_paths = {row["path"].replace("\\", "/") for row in baseline}
    actual_paths = {p.relative_to(candidate_path.parent).as_posix() for p in candidate_path.parent.rglob("*") if p.is_file()}
    if actual_paths != expected_paths:
        errors.append({"kind": "external_file_set", "missing": sorted(expected_paths - actual_paths), "extra": sorted(actual_paths - expected_paths)})
    unchanged_external = 0
    for row in baseline:
        path = row["path"]
        before = original_path.parent / path
        if sha(before).lower() != row["sha256"].lower() or before.stat().st_size != row["size"]:
            errors.append({"kind": "source_baseline_hash", "path": path})
        if before.resolve() == original_path.resolve():
            continue
        after = candidate_path.parent / path
        if not after.exists() or sha(after).lower() != row["sha256"].lower() or after.stat().st_size != row["size"]:
            errors.append({"kind": "external_file_hash", "path": path})
        else:
            unchanged_external += 1
    untouched = original_names - changed
    md5_equal = all(original["entries"][p]["md5"] == candidate["entries"][p]["md5"] for p in untouched)
    if not md5_equal:
        errors.append({"kind": "unmodified_md5"})
    return {"status": "FAIL" if errors else "PASS", "errors": errors, "allowed": len(allowed), "changed_existing": len(changed),
            "metadata_modified_existing": len(metadata_changed), "relocated_identical_entries": sorted(metadata_changed - changed),
            "actual_modified_including_directory": len(actual_modified),
            "added": sorted(added), "deleted": sorted(deleted), "unchanged_pack_entries": len(untouched), "unchanged_md5": md5_equal,
            "native_prefix_unchanged": prefix_ok, "external_files": len(actual_paths), "external_unchanged_except_exe": unchanged_external,
            "source_manifest_sha256": sha(baseline_path), "allowed_paths": sorted(allowed), "media_disposition_sha256": sha(WORK / "media/final_disposition.json")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-stage", required=True, type=Path)
    parser.add_argument("--validation-stage", required=True, type=Path)
    args = parser.parse_args()
    stage, validation = args.candidate_stage.resolve(), args.validation_stage.resolve()
    original_path = ROOT / "source_original/AGROMATIC_DEMO/steam_25850896/AgromaticDemo.exe"
    candidate_path = stage / "game/AgromaticDemo.exe"
    original, candidate = read_pack(original_path), read_pack(candidate_path)
    rows = json.loads((stage / "expected_locations.json").read_text(encoding="utf-8"))
    assets = json.loads((stage / "asset_expectations.json").read_text(encoding="utf-8"))
    report = json.loads((validation / "report.json").read_text(encoding="utf-8"))
    if report["status"] != "PASS" or report["candidate_sha256"] != sha(candidate_path):
        raise ValueError("성공한 위치 검증과 현재 후보 해시 연결이 필요합니다.")
    checks = {"json": json_boundary(original, candidate, rows), "resources": resource_boundary(stage, report, assets, rows),
              "files": file_boundaries(original, candidate, original_path, candidate_path, assets)}
    output = {"status": "PASS" if all(v["status"] == "PASS" for v in checks.values()) else "FAIL", "checks": checks,
              "candidate_sha256": sha(candidate_path), "original_sha256": sha(original_path), "tool_sha256": sha(Path(__file__)),
              "position_validation_sha256": sha(validation / "report.json"), "manifest_sha256": sha(stage / "expected_locations.json"),
              "asset_expectations_sha256": sha(stage / "asset_expectations.json"), "post_build_verification_tool": True}
    save(validation / "boundary_report.json", output)
    print(json.dumps({"status": output["status"], "errors": {k: len(v["errors"]) for k, v in checks.items()}}, ensure_ascii=False))
    return 0 if output["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
