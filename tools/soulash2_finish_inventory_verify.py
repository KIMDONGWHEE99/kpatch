"""완료용 전축 목록을 생성 코드에 의존하지 않고 다시 대조한다."""
import argparse
import collections
import hashlib
import itertools
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
EXTRACTED = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029"
HEX = re.compile(r"[a-f0-9]{64}\Z")


class ObjectPairs(list):
    """JSON 객체의 중복 키와 순서를 보존한다."""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def read_rows(path):
    with path.open("rb") as stream:
        for number, raw in enumerate(stream, 1):
            yield number, raw, json.loads(raw)


def resolve_pointer(value, pointer):
    for component in pointer.split("/")[1:]:
        component = component.replace("~1", "/").replace("~0", "~")
        value = value[int(component)] if isinstance(value, list) else value[component]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", required=True)
    args = parser.parse_args()
    folder = (ROOT / args.folder).resolve()
    summary_path = folder / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    errors = []
    hash_cache = {}
    parsed_sources = {}
    source_bytes = {}
    source_text = {}
    map_matches = {}
    pair_sources = {}
    checked_evidence = set()
    resolved_paths = {}
    actual_checked = collections.Counter()

    def check(condition, code, **detail):
        if not condition:
            errors.append({"code": code, **detail})

    def locate(name, relative=None):
        cache_key = (name, str(relative) if relative is not None else None)
        if cache_key in resolved_paths:
            return resolved_paths[cache_key]
        path = Path(name)
        candidates = [path] if path.is_absolute() else [ROOT / path, SOURCE / path, EXTRACTED / path]
        if relative is not None:
            candidates.insert(0, relative / path)
        found = [p.resolve() for p in candidates if p.is_file()]
        if not found:
            raise FileNotFoundError(name)
        resolved_paths[cache_key] = found[0]
        return found[0]

    def verify_hash(name, expected, relative=None):
        try:
            path = locate(name, relative)
            key = str(path)
            if key not in hash_cache:
                with path.open("rb") as stream:
                    hasher = hashlib.sha256()
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        hasher.update(chunk)
                    digest = hasher.hexdigest()
                hash_cache[key] = digest
            check(hash_cache[key] == expected, "ARTIFACT_HASH", path=str(path), expected=expected, actual=hash_cache[key])
            return path
        except (OSError, ValueError) as exc:
            errors.append({"code": "ARTIFACT_MISSING", "path": name, "error": str(exc)})
            return None

    def references(node, relative=None, recurse=False):
        """필드 이름과 지문이 함께 있는 근거를 직접 다시 연다."""
        refs = []
        if isinstance(node, list):
            for child in node:
                refs.extend(references(child, relative, recurse))
        elif isinstance(node, dict):
            name = next((node[k] for k in ("artifact", "path", "file") if isinstance(node.get(k), str)), None)
            fingerprint = next((node[k] for k in ("artifact_sha256", "file_sha256", "sha256", "source_file_sha256") if isinstance(node.get(k), str) and HEX.fullmatch(node[k])), None)
            if name and fingerprint:
                path = verify_hash(name, fingerprint, relative)
                if path:
                    refs.append((str(path), fingerprint))
                    if recurse and path.suffix == ".json" and str(path) not in checked_evidence:
                        checked_evidence.add(str(path))
                        child = json.loads(path.read_text(encoding="utf-8-sig"))
                        refs.extend(references(child, path.parent, True))
            for child in node.values():
                if isinstance(child, (dict, list)):
                    refs.extend(references(child, relative, recurse))
        return refs

    # 입력 지문과 기초 목록의 기존 검증 증거도 다시 확인한다.
    for item in summary["inputs"]:
        verify_hash(item["path"], item["sha256"])
    for name, fingerprint in summary["outputs"].items():
        verify_hash(name, fingerprint, folder)
    base_path = verify_hash(summary["base"]["path"], summary["base"]["sha256"])
    if base_path is None:
        raise ValueError("기초 목록을 읽을 수 없습니다")
    base_dir = base_path.parent
    for filename in ("effective_inventory_summary.json", "independent_merge_validation.json", "evidence_artifacts.json", "root_evidence_artifacts.json"):
        path = base_dir / filename
        check(path.is_file(), "BASE_EVIDENCE_MISSING", file=filename)
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            references(data, base_dir, True)
            if filename == "effective_inventory_summary.json":
                for name, value in data.get("outputs", {}).items():
                    if isinstance(value, str) and HEX.fullmatch(value):
                        verify_hash(name, value, base_dir)

    # 각 덧씌우기 파일은 행 순서·원행 지문을 별도로 색인한다.
    overlays = {}
    overlay_total = collections.Counter()
    for record in summary["overlays"]:
        path = verify_hash(record["path"], record["sha256"])
        if path is None:
            continue
        rows = []
        for number, raw, row in read_rows(path):
            refs = references(row, None, True)
            rows.append((sha(raw), row, refs))
        overlays[str(path)] = rows
        overlay_total[record["path"]] = len(rows)
    check(dict(overlay_total) == summary["overlay_rows"], "OVERLAY_COUNTS")

    def originals():
        for number, raw, row in read_rows(base_path):
            yield row, sha(raw), "base"
        for addition in summary["additions"]:
            path = verify_hash(addition["path"], addition["sha256"])
            if path is None:
                continue
            for number, raw, original in read_rows(path):
                axis = addition["axis"]
                row = {"axis": axis, "record_id": axis + ":" + original["location_id"], "location_id": original["location_id"], "source_file_sha256": original["source_file_sha256"], "source_value_sha256": original["source_value_sha256"], "classification": "UNKNOWN", "classification_status": "PASS", "original_record": original, "overlay_history": []}
                yield row, sha(raw), "addition"

    def actual_value(row):
        original = row["original_record"]
        axis = row["axis"]
        file = original.get("file")
        if not file:
            file = row["location_id"].split("@", 1)[0] if axis == "native_string" else row["location_id"].split("#", 1)[0]
        path = verify_hash(file, row["source_file_sha256"])
        if path is None:
            return
        try:
            if axis in ("json_value", "json_key"):
                if file not in parsed_sources:
                    parsed_sources[file] = json.loads(path.read_text(encoding="utf-8-sig"))
                content = parsed_sources[file]
                if axis == "json_value":
                    value = resolve_pointer(content, original["field_path"])
                    check(value == original["source"], "ACTUAL_JSON_VALUE", record_id=row["record_id"])
                else:
                    if original.get("occurrence_path"):
                        if file not in pair_sources:
                            pair_sources[file] = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=ObjectPairs)
                        item = pair_sources[file]
                        parts = []
                        last_key = None
                        for step in original["occurrence_path"]:
                            if "index" in step:
                                assert isinstance(item, list) and not isinstance(item, ObjectPairs)
                                item = item[step["index"]]
                                parts.append(str(step["index"]))
                            else:
                                assert isinstance(item, ObjectPairs)
                                ordinal = step["pair_ordinal"]
                                key, child = item[ordinal]
                                assert key == step["key"]
                                assert sum(k == key for k, _ in item[:ordinal + 1]) == step["occurrence"]
                                item = child
                                parts.append(key.replace("~", "~0").replace("/", "~1"))
                                last_key = key
                        check(last_key == original["key"], "ACTUAL_JSON_OCCURRENCE_KEY", record_id=row["record_id"])
                        check("/".join([""] + parts[:-1]) == original["parent_path"], "ACTUAL_JSON_OCCURRENCE_PARENT", record_id=row["record_id"])
                    else:
                        parent = resolve_pointer(content, original["parent_path"])
                        check(isinstance(parent, dict) and original["key"] in parent, "ACTUAL_JSON_KEY", record_id=row["record_id"])
                    value = original["key"]
            elif axis == "map_body_string":
                if file not in source_text:
                    source_text[file] = path.read_text(encoding="utf-8-sig")
                body = source_text[file].split("|", 2)[2]
                if file not in map_matches:
                    map_matches[file] = list(re.finditer(r"[A-Za-z_][A-Za-z0-9_-]*", body))
                matches = map_matches[file]
                index = int(row["location_id"].rsplit("/", 1)[1])
                match = matches[index]
                value = match.group()
                check(match.start() == original["body_character_offset"] and value == original["source"], "ACTUAL_MAP_BODY", record_id=row["record_id"])
            elif axis == "map_name":
                if file not in source_text:
                    source_text[file] = path.read_text(encoding="utf-8-sig")
                value = source_text[file].split("|", 2)[1]
                check(value == original["source"], "ACTUAL_MAP_HEADER", record_id=row["record_id"])
            elif axis == "text_line":
                if file not in source_text:
                    source_text[file] = path.read_text(encoding="utf-8-sig")
                value = source_text[file].splitlines()[original["line"] - 1]
                check(value == original["source"], "ACTUAL_TEXT_LINE", record_id=row["record_id"])
            elif axis == "native_string":
                if file not in source_bytes:
                    source_bytes[file] = path.read_bytes()
                raw = source_bytes[file][original["file_offset"]:original["file_offset"] + original["byte_length"]]
                encoding = original["encoding"].replace("utf16le", "utf-16-le")
                value = raw.decode(encoding)
                check(value == original["source"], "ACTUAL_NATIVE_STRING", record_id=row["record_id"])
            else:
                value = None
            if isinstance(value, str):
                check(sha(value.encode()) == row["source_value_sha256"], "ACTUAL_VALUE_HASH", record_id=row["record_id"])
            actual_checked[axis] += 1
        except (KeyError, IndexError, ValueError, UnicodeError, AssertionError) as exc:
            errors.append({"code": "ACTUAL_READ_ERROR", "record_id": row["record_id"], "error": str(exc)})

    axes = collections.Counter()
    classes = collections.defaultdict(collections.Counter)
    before = collections.defaultdict(collections.Counter)
    media = collections.Counter()
    dispositions = collections.Counter()
    seen_ids = set()
    used_overlay_rows = set()
    mutable = {"classification", "classification_status", "treatment", "base_classification", "base_row_sha256", "finish_overlay_history"}
    accepted = {"APPLIED", "CORROBORATES_OR_RETAINS"}
    for expected, actual in itertools.zip_longest(originals(), read_rows(folder / "effective_classification_ledger.jsonl")):
        if expected is None or actual is None:
            check(False, "ROW_COUNT_OR_ORDER")
            break
        old, raw_hash, kind = expected
        number, raw, row = actual
        rid = row.get("record_id")
        check(rid == old["record_id"] and rid not in seen_ids, "IDENTITY_ORDER_OR_DUPLICATE", line=number, record_id=rid)
        seen_ids.add(rid)
        for key, value in old.items():
            if key not in mutable:
                check(row.get(key) == value, "PRESERVED_FIELD", line=number, key=key)
        if kind == "base":
            check(row.get("base_row_sha256") == raw_hash, "BASE_RAW_HASH", record_id=rid)
        check(row.get("base_classification") == old["classification"], "BASE_CLASSIFICATION", record_id=rid)
        state = old["classification"]
        treatment = old.get("treatment")
        any_applied = False
        for history in row.get("finish_overlay_history", []):
            path = locate(history["artifact"])
            overlay_key = str(path)
            index = history["row_number"] - 1
            check(overlay_key in overlays and 0 <= index < len(overlays.get(overlay_key, [])), "OVERLAY_REFERENCE", record_id=rid)
            if overlay_key not in overlays or not 0 <= index < len(overlays[overlay_key]):
                continue
            expected_hash, patch, refs = overlays[overlay_key][index]
            used_overlay_rows.add((overlay_key, index))
            check(history["row_sha256"] == expected_hash, "OVERLAY_RAW_HASH", record_id=rid)
            verify_hash(history["artifact"], history["artifact_sha256"])
            references(history.get("evidence", []), None, True)
            disposition = history["disposition"]
            dispositions[disposition] += 1
            if disposition in accepted:
                any_applied = True
                check(bool(refs), "ACCEPTED_WITHOUT_EVIDENCE", record_id=rid)
                target_id = patch.get("record_id")
                if target_id:
                    check(target_id == rid, "OVERLAY_IDENTITY", record_id=rid)
                if patch.get("location_id"):
                    check(patch["location_id"] == row["location_id"], "OVERLAY_LOCATION", record_id=rid)
                for field in ("source_file_sha256", "source_value_sha256"):
                    if patch.get(field):
                        check(patch[field] == row[field], "OVERLAY_SOURCE_HASH", field=field, record_id=rid)
                if "source" in patch:
                    check(patch["source"] == old["original_record"].get("source", old["original_record"].get("key")), "OVERLAY_SOURCE", record_id=rid)
                new = patch["classification"]
                check(new in {"UNKNOWN", "INTERNAL", "VISIBLE_KEEP", "VISIBLE_TRANSLATE", "MEDIA"}, "CLASSIFICATION_ENUM", record_id=rid)
                check(state in ("UNKNOWN", new), "CLASSIFICATION_CONFLICT_ACCEPTED", record_id=rid, before=state, after=new)
                if disposition == "APPLIED":
                    check(state != new or patch.get("treatment") != treatment, "FALSE_APPLIED", record_id=rid)
                state = new
                if "treatment" in patch:
                    check(treatment in (None, "UNKNOWN", patch["treatment"]), "MEDIA_CONFLICT_ACCEPTED", record_id=rid)
                    treatment = patch["treatment"]
                check(not history.get("mismatched_fields") and not history.get("evidence_error"), "ACCEPTED_ERROR", record_id=rid)
        check(row["classification"] == state, "FINAL_CLASSIFICATION", record_id=rid)
        if old["axis"] == "media":
            check(row.get("treatment") == treatment, "FINAL_MEDIA_TREATMENT", record_id=rid)
            media[row.get("treatment", "UNKNOWN")] += 1
        if any_applied or kind == "addition":
            actual_value(row)
        else:
            original = row["original_record"]
            file = original.get("file", row["location_id"].split("@", 1)[0].split("#", 1)[0])
            verify_hash(file, row["source_file_sha256"])
        axes[row["axis"]] += 1
        classes[row["axis"]][row["classification"]] += 1
        before[row["axis"]][old["classification"]] += 1
    check(dict(axes) == summary["axis_rows"], "AXIS_TOTAL")
    check({k: dict(v) for k, v in classes.items()} == summary["axis_classifications"], "CLASSIFICATION_TOTAL")
    check({k: dict(v) for k, v in before.items()} == summary["before_classifications"], "BEFORE_TOTAL")
    check(dict(media) == summary["media_treatments"], "MEDIA_TOTAL")
    check(dict(dispositions) == summary["overlay_dispositions"], "DISPOSITION_TOTAL")
    unresolved = sum(v.get("UNKNOWN", 0) for v in classes.values())
    unresolved_media = media.get("UNKNOWN", 0)
    check(unresolved == summary["unresolved_classification"], "UNRESOLVED_TOTAL")
    check(unresolved_media == summary["unresolved_media_treatments"], "UNRESOLVED_MEDIA_TOTAL")
    check(unresolved + unresolved_media == summary["unresolved_total"], "UNRESOLVED_COMBINED_TOTAL")
    if unresolved + unresolved_media + summary.get("unresolved_extraction_failures", 0):
        check(summary["g2_status"] == "FAIL", "G2_FALSE_PASS")
    orphan_count = sum(len(rows) for rows in overlays.values()) - len(used_overlay_rows)
    check(orphan_count == summary["orphans"], "ORPHAN_COUNT", calculated=orphan_count)
    report = {"status": "PASS" if not errors else "FAIL", "scope": "생성 코드 미사용. 기초 전행과 순서·원문·보존필드, 덧씌우기 원행·근거·분류전이, 원본 파일 및 적용 위치 실제값 대조", "generator_summary_sha256": sha(summary_path.read_bytes()), "tool_sha256": sha(Path(__file__).read_bytes()), "base_rows_plus_additions": sum(axes.values()), "axis_rows": axes, "actual_location_checks": actual_checked, "checked_artifact_count": len(hash_cache), "checked_nested_evidence_json": len(checked_evidence), "used_overlay_rows": len(used_overlay_rows), "errors": errors, "error_count": len(errors), "g2_status": summary["g2_status"], "unresolved_total": unresolved + unresolved_media}
    (folder / "independent_verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "errors"}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
