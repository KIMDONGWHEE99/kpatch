"""기존 조사 원행을 보존하면서 모든 축의 근거 있는 판정을 새 후보에 통합한다."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029"
SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
DEFAULT_BASE = BASE / "effective_inventory/v4/effective_classification_ledger.jsonl"
CLASSES = {"UNKNOWN", "INTERNAL", "VISIBLE_TRANSLATE", "VISIBLE_KEEP", "MEDIA"}
AXES = {"json_value", "json_key", "text_line", "map_name", "media", "native_string", "map_body_string"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(data)
    return value.hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def rows(path):
    with path.open("rb") as stream:
        for number, raw in enumerate(stream, 1):
            yield number, json.loads(raw), sha(raw)


@lru_cache(maxsize=None)
def safe(base, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative or PurePosixPath(relative).is_absolute() or str(PurePosixPath(relative)) != relative or any(x in (".", "..") for x in relative.split("/")):
        raise ValueError("정규 상대 경로가 아님")
    path = (base / relative).resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError("경로 경계 이탈")
    return path


def infer_axis(row):
    axis = row.get("axis")
    if axis:
        if axis not in AXES:
            raise ValueError("미지원 축")
        return axis
    loc = row.get("location_id", "")
    if "#key/" in loc:
        return "json_key"
    if "#body/string/" in loc:
        return "map_body_string"
    if "#line/" in loc:
        return "text_line"
    if "#header/" in loc:
        return "map_name"
    if "#/" in loc:
        return "json_value"
    if "@" in loc and ":" in loc:
        return "native_string"
    if row.get("classification") == "MEDIA":
        return "media"
    raise ValueError("판정의 조사 축을 식별할 수 없음")


class Pairs(list):
    pass


class SourceCheck:
    def __init__(self, record, baseline):
        self.record = record
        self.baseline = baseline
        self.checked = {}
        self.cache_file = None
        self.cache_data = None
        self.cache_obj = None

    def file(self, relative, expected):
        if relative not in self.checked:
            path = safe(SOURCE, relative)
            actual = self.record(path)["sha256"]
            if relative not in self.baseline or actual != self.baseline[relative]:
                raise ValueError("원본 기준 지문 불일치: " + relative)
            self.checked[relative] = actual
        if expected != self.checked[relative]:
            raise ValueError("위치 원본 파일 지문 불일치: " + relative)

    def data(self, relative):
        if self.cache_file != relative:
            self.cache_file = relative
            self.cache_data = safe(SOURCE, relative).read_bytes()
            self.cache_obj = None
        return self.cache_data

    def value(self, axis, original):
        relative = original.get("file", "Soulash 2.exe")
        data = self.data(relative)
        if axis in ("json_value", "json_key"):
            if self.cache_obj is None:
                self.cache_obj = json.loads(data.decode("utf-8-sig"), object_pairs_hook=Pairs)
            cursor = self.cache_obj
            steps = original.get("occurrence_path")
            if steps:
                for index, step in enumerate(steps):
                    if "index" in step:
                        if type(cursor) is not list:
                            raise ValueError("배열 등장 위치 오류")
                        cursor = cursor[step["index"]]
                    else:
                        ordinal = step["pair_ordinal"]
                        if not isinstance(cursor, Pairs) or cursor[ordinal][0] != step["key"] or sum(k == step["key"] for k, _ in cursor[:ordinal + 1]) != step["occurrence"]:
                            raise ValueError("객체 등장 위치 오류")
                        if axis == "json_key" and index == len(steps) - 1:
                            return cursor[ordinal][0]
                        cursor = cursor[ordinal][1]
            else:
                pointer = original["parent_path"] if axis == "json_key" else original["field_path"]
                for part in pointer.split("/")[1:] if pointer else []:
                    key = part.replace("~1", "/").replace("~0", "~")
                    if isinstance(cursor, Pairs):
                        values = [v for k, v in cursor if k == key]
                        if len(values) != 1:
                            raise ValueError("중복 객체에 등장 위치가 없음")
                        cursor = values[0]
                    else:
                        cursor = cursor[int(key)]
                if axis == "json_key":
                    if not isinstance(cursor, Pairs) or sum(k == original["key"] for k, _ in cursor) != 1:
                        raise ValueError("키 위치 오류")
                    return original["key"]
            return cursor
        if axis == "text_line":
            return data.decode("utf-8-sig").splitlines()[original["line"] - 1]
        if axis == "map_name":
            return data.decode("utf-8-sig").split("|", 2)[1]
        if axis == "native_string":
            raw = data[original["file_offset"]:original["file_offset"] + original["byte_length"]]
            if sha(raw) != original["source_sha256"]:
                raise ValueError("네이티브 문자열 바이트 지문 불일치")
            return raw.decode(original["encoding"])
        if axis == "map_body_string":
            if self.cache_obj is None:
                body = data.decode("utf-8-sig").split("|", 2)[2]
                self.cache_obj = [(m.start(), m.group()) for m in re.finditer(r"[A-Za-z_][A-Za-z0-9_-]*", body)]
            index = int(original["location_id"].rsplit("/", 1)[1])
            offset, value = self.cache_obj[index]
            if offset != original["body_character_offset"]:
                raise ValueError("지도 본문 문자 위치 불일치")
            return value
        return None


def merge(output, base=DEFAULT_BASE, overlays=(), additions=()):
    output, base = output.resolve(), base.resolve()
    if not output.is_relative_to(ROOT / "working_private/SOULASH_2"):
        raise ValueError("새 분류 후보 출력 경계 오류")
    output.mkdir(parents=True, exist_ok=False)
    inputs, evidence_paths = {}, set()

    def record(path):
        if path in inputs:
            return inputs[path]
        path = path.resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError("입력 파일 경계 오류")
        if path not in inputs:
            inputs[path] = {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path), "size": path.stat().st_size}
        return inputs[path]

    record(Path(__file__))
    base_record = record(base)
    base_summary_path = base.parent / "effective_inventory_summary.json"
    base_summary = json.loads(base_summary_path.read_text(encoding="utf-8"))
    record(base_summary_path)
    if base_summary["outputs"][base.name] != base_record["sha256"]:
        raise ValueError("기존 통합 목록 지문 불일치")
    prior_validation_path = base.parent / "independent_merge_validation.json"
    prior_validation = json.loads(prior_validation_path.read_text(encoding="utf-8"))
    record(prior_validation_path)
    if prior_validation["status"] != "PASS" or prior_validation["summary_sha256"] != record(base_summary_path)["sha256"]:
        raise ValueError("기존 통합 독립검사 연결 불일치")
    for name in ("source_json_coverage.jsonl", "extraction_errors_preserved.jsonl", "extraction_recovery_diagnostics.json", "evidence_artifacts.json", "root_evidence_artifacts.json"):
        if record(base.parent / name)["sha256"] != base_summary["outputs"][name]:
            raise ValueError("기존 조사 보조 근거 지문 불일치")
    for relative, item in json.loads((base.parent / "evidence_artifacts.json").read_text(encoding="utf-8")).items():
        if record(safe(BASE, relative))["sha256"] != item["sha256"]:
            raise ValueError("기존 추출·분류 입력 지문 변경")
    for relative, expected in json.loads((base.parent / "root_evidence_artifacts.json").read_text(encoding="utf-8")).items():
        if record(safe(ROOT, relative))["sha256"] != expected:
            raise ValueError("기존 외부 분류 근거 지문 변경")
    baseline_path = BASE / "baseline_manifest.json"
    record(baseline_path)
    baseline = {row["path"]: row["sha256"] for row in json.loads(baseline_path.read_text(encoding="utf-8"))["files"]}
    source_check = SourceCheck(record, baseline)

    def evidence(row):
        found = set()

        def reference(relative, expected, source=False):
            if not isinstance(relative, str) or not re.fullmatch(r"[a-f0-9]{64}", str(expected)):
                raise ValueError("근거 경로·지문 형식 오류")
            root = SOURCE if source else ROOT
            path = safe(root, relative)
            if not source and not path.is_file() and not relative.startswith(("working_private/", "extracted_private/", "source_original/", "tools/")):
                path = safe(BASE, relative)
            if record(path)["sha256"] != expected:
                raise ValueError("판정 근거 지문 변경: " + relative)
            evidence_paths.add(path)
            found.add(path)

        def visit(value):
            if isinstance(value, dict):
                if "artifact" in value and ("artifact_sha256" in value or "sha256" in value):
                    reference(value["artifact"], value.get("artifact_sha256", value.get("sha256")))
                for path_key, hash_key in (("evidence_path", "evidence_sha256"), ("evidence_artifact", "evidence_artifact_sha256")):
                    if path_key in value:
                        reference(value[path_key], value.get(hash_key))
                if "file" in value and "line_start" in value and ("file_sha256" in value or "source_sha256" in value):
                    reference(value["file"], value.get("file_sha256", value.get("source_sha256")), True)
                for key, child in value.items():
                    if key not in ("original_record", "inventory_origin", "original_inventory", "translation_origin", "override_history"):
                        visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(row)
        unresolved_media = row.get("classification") == "MEDIA" and row.get("treatment") == "UNKNOWN"
        if row.get("classification") != "UNKNOWN" and not unresolved_media and not found:
            raise ValueError("파일 지문이 연결된 판정 근거 없음")
        return [{"path": p.relative_to(ROOT).as_posix(), "sha256": inputs[p]["sha256"]} for p in sorted(found)]

    proposals, overlay_inputs = defaultdict(list), []
    errors, dispositions, overlay_count = [], Counter(), Counter()
    for path in overlays:
        path = path.resolve()
        rec = record(path)
        if any(item["path"] == rec["path"] for item in overlay_inputs):
            raise ValueError("중복 보강 파일")
        overlay_inputs.append(rec)
        local = set()
        for number, row, row_sha in rows(path):
            axis = infer_axis(row)
            key = axis + ":" + row["location_id"]
            if key in local:
                raise ValueError("동일 파일의 중복 판정 위치")
            local.add(key)
            issue = None
            try:
                refs = evidence(row)
            except (OSError, ValueError, KeyError) as error:
                issue, refs = str(error), []
            proposals[key].append({"record": row, "artifact": rec["path"], "artifact_sha256": rec["sha256"], "row_number": number, "row_sha256": row_sha, "evidence": refs, "evidence_error": issue})
            overlay_count[rec["path"]] += 1

    axis_rows, classifications, treatments = Counter(), defaultdict(Counter), Counter()
    before_classes, seen, used, unresolved_samples = defaultdict(Counter), set(), set(), defaultdict(list)
    ledger_path = output / "effective_classification_ledger.jsonl"
    applications_path = output / "overlay_application_ledger.jsonl"
    translated_path = output / "translation_work.jsonl"
    additions_records = []

    def write(stream, row):
        stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    with ledger_path.open("x", encoding="utf-8", newline="\n") as ledger, applications_path.open("x", encoding="utf-8", newline="\n") as applications, translated_path.open("x", encoding="utf-8", newline="\n") as work:
        def process(base_row, row_sha):
            axis, loc = base_row["axis"], base_row["location_id"]
            key = axis + ":" + loc
            if key in seen:
                raise ValueError("기존·추가 조사 위치 중복")
            seen.add(key)
            original = base_row["original_record"]
            relative = original.get("file", "Soulash 2.exe")
            source_check.file(relative, base_row["source_file_sha256"])
            value = original.get("key") if axis == "json_key" else original.get("source")
            if isinstance(value, str) and sha(value.encode("utf-8")) != base_row["source_value_sha256"]:
                raise ValueError("기존 조사 문자열 지문 오류")
            current = base_row["classification"]
            before_classes[axis][current] += 1
            treatment = base_row.get("treatment")
            history, rejected = [], False
            if proposals.get(key) or axis == "map_body_string":
                if source_check.value(axis, original) != value:
                    raise ValueError("실제 원본 위치 값 불일치: " + key)
            for item in proposals.get(key, []):
                used.add((item["artifact"], item["row_number"]))
                patch = item["record"]
                proposed = patch.get("classification")
                mismatch = []
                if patch.get("source_file_sha256") != base_row["source_file_sha256"]:
                    mismatch.append("source_file_sha256")
                if axis != "media" and patch.get("source_value_sha256") != base_row["source_value_sha256"]:
                    mismatch.append("source_value_sha256")
                for name in ("file", "field_path", "parent_path", "key", "line", "occurrence_path", "body_character_offset"):
                    if name in patch and patch[name] != original.get(name, relative if name == "file" else None):
                        mismatch.append(name)
                if "source" in patch and patch["source"] != value:
                    mismatch.append("source")
                if item["evidence_error"]:
                    state = "REJECTED_EVIDENCE"
                elif mismatch or proposed not in CLASSES:
                    state = "REJECTED_IDENTITY"
                elif current != proposed and current != patch.get("previous_classification", patch.get("original_classification", "UNKNOWN")):
                    state = "REJECTED_CLASSIFICATION_CONFLICT"
                elif axis == "media" and patch.get("treatment") not in ("UNKNOWN", "KEEP", "TRANSLATE", "REPLACE", "NO_TEXT", "INTERNAL"):
                    state = "REJECTED_MEDIA_TREATMENT"
                elif axis == "media" and treatment != patch.get("treatment") and treatment != patch.get("previous_treatment", "UNKNOWN"):
                    state = "REJECTED_MEDIA_CONFLICT"
                else:
                    state = "APPLIED" if current != proposed or (axis == "media" and treatment != patch.get("treatment")) else "CORROBORATES_OR_RETAINS"
                    current = proposed
                    if axis == "media":
                        treatment = patch["treatment"]
                applied = {k: item[k] for k in ("artifact", "artifact_sha256", "row_number", "row_sha256", "evidence")}
                applied.update({"record_id": key, "disposition": state, "classification": proposed, "mismatched_fields": mismatch, "evidence_error": item["evidence_error"]})
                if "treatment" in patch:
                    applied["treatment"] = patch["treatment"]
                history.append(applied)
                write(applications, applied)
                dispositions[state] += 1
                if state.startswith("REJECTED"):
                    rejected = True
                    errors.append(applied)
            if rejected:
                current = "UNKNOWN"
                if axis == "media":
                    treatment = "UNKNOWN"
            result = {**base_row, "base_classification": base_row["classification"], "base_row_sha256": row_sha, "classification": current, "classification_status": "CONFLICT" if rejected else base_row.get("classification_status", "PASS"), "finish_overlay_history": history}
            if axis == "media":
                result["treatment"] = treatment
                treatments[treatment] += 1
            write(ledger, result)
            axis_rows[axis] += 1
            classifications[axis][current] += 1
            if current == "UNKNOWN" or (axis == "media" and treatment == "UNKNOWN"):
                if len(unresolved_samples[axis]) < 30:
                    unresolved_samples[axis].append({"location_id": loc, "source": value, "file": relative})
            if current == "VISIBLE_TRANSLATE":
                write(work, {**original, "axis": axis, "record_id": key, "location_id": loc, "source_file_sha256": base_row["source_file_sha256"], "source_value_sha256": base_row["source_value_sha256"], "classification": current, "inventory_origin": base_row["inventory_origin"], "target": None})

        for _, row, row_sha in rows(base):
            process(row, row_sha)
        for axis, path in additions:
            if axis not in AXES:
                raise ValueError("새 조사 축 오류")
            rec = record(path.resolve())
            additions_records.append({"axis": axis, **rec})
            for number, row, row_sha in rows(path):
                if row.get("classification") != "UNKNOWN":
                    raise ValueError("새 조사 항목은 UNKNOWN으로 등록한 뒤 별도 판정해야 함")
                normalized = {"axis": axis, "record_id": axis + ":" + row["location_id"], "location_id": row["location_id"], "source_file_sha256": row["source_file_sha256"], "source_value_sha256": row.get("source_value_sha256"), "classification": "UNKNOWN", "classification_status": "PASS", "inventory_origin": {"artifact": rec["path"], "artifact_sha256": rec["sha256"], "row_number": number, "row_sha256": row_sha}, "original_record": row, "overlay_history": []}
                process(normalized, row_sha)

    orphan = []
    for entries in proposals.values():
        for item in entries:
            if (item["artifact"], item["row_number"]) not in used:
                orphan.append({"artifact": item["artifact"], "row_number": item["row_number"], "location_id": item["record"]["location_id"]})
    changed = [item["path"] for path, item in inputs.items() if digest(path) != item["sha256"]]
    missing_evidence = sum(item["evidence_error"] is not None for items in proposals.values() for item in items)
    unknown = sum(counts["UNKNOWN"] for counts in classifications.values())
    unresolved_media = treatments["UNKNOWN"]
    historical_errors = base_summary.get("unresolved_extraction_failures", 0)
    result = {"schema_version": 1, "game_id": "SOULASH_2", "steam_build": "25967323", "status": "FAIL" if errors or orphan or changed else "PASS", "g2_status": "FAIL" if unknown or unresolved_media or errors or orphan or changed or historical_errors else "PASS", "scope": "DECLARED_AXES_AND_EXPLICIT_OVERLAYS", "release_ready": False, "generated_at": datetime.now(timezone.utc).isoformat(),
              "base": base_record, "overlays": overlay_inputs, "additions": additions_records, "axis_rows": dict(axis_rows), "axis_classifications": {a: dict(c) for a, c in classifications.items()}, "before_classifications": {a: dict(c) for a, c in before_classes.items()}, "media_treatments": dict(treatments), "overlay_rows": dict(overlay_count), "overlay_dispositions": dict(dispositions), "conflicts": len(errors), "orphans": len(orphan), "missing_evidence": missing_evidence, "unresolved_classification": unknown, "unresolved_media_treatments": unresolved_media, "unresolved_total": unknown + unresolved_media, "unresolved_extraction_failures": historical_errors, "checked_source_files": len(source_check.checked), "checked_evidence_files": len(evidence_paths), "changed_inputs": changed, "unresolved_samples": dict(unresolved_samples), "inputs": [inputs[p] for p in sorted(inputs)], "outputs": {p.name: digest(p) for p in (ledger_path, applications_path, translated_path)}, "limitations": ["전체 분류 미확정은 별도 G2 FAIL로 유지", "이미지·음성 판정은 연결된 기존 검수 범위만 재사용", "기존 원행 구조 검사는 지문이 같은 v4 독립검사 근거를 보존하고 새 판정 위치를 실제 원본에서 재확인"]}
    (output / "conflicts.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in errors), encoding="utf-8")
    (output / "orphans.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in orphan), encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--overlay", type=Path, action="append", default=[])
    parser.add_argument("--add", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    additions = [(value.split("=", 1)[0], Path(value.split("=", 1)[1])) for value in args.add]
    result = merge(args.output, args.base, args.overlay, additions)
    print(json.dumps({k: result[k] for k in ("status", "g2_status", "axis_rows", "axis_classifications", "conflicts", "orphans", "missing_evidence", "unresolved_total")}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
