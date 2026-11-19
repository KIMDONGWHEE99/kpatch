"""동결 DAT02와 native03을 새 검수 후보로 조립하고 G3/G4 근거를 연결한다."""
from __future__ import annotations
import hashlib
import json
import shutil
from pathlib import Path

import assemble_candidate

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "working_private/THE_HORDE_OF_GORAK"
BASE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311"
PREVIOUS = ROOT / "build_candidate/THE_HORDE_OF_GORAK/ko_candidate_02"
TARGET = ROOT / "build_candidate/THE_HORDE_OF_GORAK/ko_candidate_03"
NATIVE = WORK / "native_candidate_03"
OUT = WORK / "final_validation_03"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    return sha(path.read_bytes())


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def snapshot(root):
    return {p.relative_to(root).as_posix(): digest(p) for p in root.rglob("*") if p.is_file()}


def outside_ranges_equal(before, after, ranges):
    # 조립기의 범위 검증 함수를 재호출하지 않고 바깥 구간을 독립 대조한다.
    if len(before) != len(after):
        return False
    position = 0
    for start, end in sorted(ranges):
        if not 0 <= start <= end <= len(before):
            return False
        if start > position and before[position:start] != after[position:start]:
            return False
        position = max(position, end)
    return before[position:] == after[position:]


def main():
    if TARGET.exists() or OUT.exists():
        raise ValueError("기존03후보/검증폴더를 덮어쓰지 않음")
    checks, inputs, dependency_checks = [], {}, []

    def check(name, condition, **detail):
        row = {"check": name, "status": "PASS" if condition else "FAIL", **detail}
        checks.append(row)
        if not condition:
            raise ValueError(name)

    def evidence(path):
        inputs[str(path)] = digest(path)
        return {"path": str(path), "sha256": inputs[str(path)]}

    def verify_dependencies(path, label):
        value = load(path)
        collection = value["inputs"]
        entries = collection.items() if isinstance(collection, dict) else ((r["path"], r["sha256"]) for r in collection)
        count = 0
        for name, expected in entries:
            file = Path(name)
            if not file.is_absolute():
                file = ROOT / file
            actual = digest(file)
            check(label + ":" + name, actual == expected)
            inputs[str(file)] = actual
            dependency_checks.append({"group": label, "path": str(file), "sha256": actual, "status": "PASS"})
            count += 1
        evidence(path)
        return count

    frozen02 = snapshot(PREVIOUS)
    frozen_native03 = snapshot(NATIVE)
    audit_path = NATIVE / "native_patch_audit.json"
    audit = load(audit_path)
    check("native03_frozen_audit", digest(audit_path) == "01beedeff860b5d2f5e6d05df396f5ce6b3f77e435bab5ed758b09451660303f")
    check("native03_fields_files", len(audit["translations"]) == 176 and len(audit["files"]) == 6
          and sum(len(r["paths"]) for r in audit["files"]) == 11)
    dat_report = load(PREVIOUS / "build_report.json")
    check("dat02_identity", digest(PREVIOUS / "THOG.dat") == dat_report["candidate_sha256"]
          == "ead9003686811357da03b1f0e6c36f2fb05a3d6cd9aa4a060bc5b629fb6c9b6c")
    dat_g4_count = verify_dependencies(WORK / "validation_02/validation_dependencies.json", "DAT_G4_reuse")
    native_review_count = verify_dependencies(WORK / "native_review_03/dependencies.json", "native03_review_reuse")
    dat_build_count = verify_dependencies(PREVIOUS / "build_report.json", "DAT_build_reuse")
    g4 = load(WORK / "validation_02/g4_summary.json")
    native_review = load(WORK / "native_review_03/g3_native03_preparation.json")
    native_proof = load(WORK / "native_review_03/independent_proofread.json")
    dat_proof = load(WORK / "translation_02/proofread_summary.json")
    dat_audit = load(WORK / "translation_02/audit_summary.json")
    windows = load(NATIVE / "windows_resource_validation.json")
    check("component_report_identities", g4["status"] == native_review["status"] == native_proof["status"] == "PASS"
          and g4["candidate_sha256"] == dat_report["candidate_sha256"]
          and native_review["native_audit_sha256"] == native_proof["audit_sha256"] == digest(audit_path))
    check("dat_proofread_and_tokens", dat_proof["parent_review"]["status"] == dat_audit["status"] == "PASS"
          and dat_proof["translations_sha256"] == dat_audit["translations_sha256"] == digest(WORK / "translation_02/translations.json"))
    check("native_windows_resource_reads", windows["status"] == "PASS" and len(windows["records"]) == 50
          and all(r["status"] == "PASS" and r["expected"] == r["actual"] for r in windows["records"]))
    base_g3_evidence = [WORK / "translation_02/translations.json", WORK / "translation_02/proofread_summary.json",
                       WORK / "translation_02/parent_review_completion.json", WORK / "translation_02/audit_summary.json",
                       WORK / "native_review_03/independent_proofread.json", WORK / "native_review_03/g3_native03_preparation.json",
                       WORK / "native_review_03/required_characters.json", WORK / "native_review_03/embedded_extended_union.json",
                       WORK / "native_review_03/gdi_font_routes.json", WORK / "native_review_03/native_dialog_fonts.json",
                       WORK / "alignment_investigation_02/after_layout_summary.json"]
    base_g4_evidence = [WORK / "validation_02/g4_summary.json", WORK / "validation_02/validation_dependencies.json",
                       WORK / "native_review_03/review_checks.json", WORK / "native_review_03/dependencies.json",
                       NATIVE / "native_patch_audit.json", NATIVE / "rea_candidate_resources_evidence.json",
                       NATIVE / "windows_resource_validation.json"]
    refs_g3, refs_g4 = [evidence(p) for p in base_g3_evidence], [evidence(p) for p in base_g4_evidence]
    evidence(Path(__file__))
    evidence(ROOT / "tasks/THE_HORDE_OF_GORAK/assemble_candidate.py")

    TARGET.mkdir()
    OUT.mkdir()
    # 기존 DAT의 바이트와 빌드 기록을 그대로 재사용하며 새 빌드가 있었다고 기록하지 않는다.
    shutil.copyfile(PREVIOUS / "THOG.dat", TARGET / "THOG.dat")
    shutil.copyfile(PREVIOUS / "build_report.json", TARGET / "build_report.json")
    assemble_candidate.build(TARGET, NATIVE)
    manifest_path = TARGET / "assembly_manifest.json"
    manifest = load(manifest_path)
    baseline_path = WORK / "investigation_20261031/baseline_manifest.json"
    baseline = {r["path"]: r for r in load(baseline_path)["files"]}
    actual_paths = {p.relative_to(TARGET / "game").as_posix(): p for p in (TARGET / "game").rglob("*") if p.is_file()}
    native_replacements = {path: row for row in audit["files"] for path in row["paths"]}
    check("assembled_exact_32_paths", set(actual_paths) == set(baseline) and len(actual_paths) == 32)
    compared_files = []
    for relative, path in sorted(actual_paths.items()):
        before, after = (BASE / relative).read_bytes(), path.read_bytes()
        if relative == "THOG.dat":
            expected = dat_report["candidate_sha256"]
            check("assembled_DAT_identical_to_independently_extracted_02", sha(after) == expected
                  and after == (PREVIOUS / "THOG.dat").read_bytes())
        elif relative in native_replacements:
            row = native_replacements[relative]
            expected = row["candidate_sha256"]
            check("assembled_native_exact_input_" + relative, sha(after) == expected and after == (NATIVE / relative).read_bytes())
            check("native_allowed_change_boundary_" + relative, outside_ranges_equal(before, after, row["allowed_ranges"]))
        else:
            expected = baseline[relative]["sha256"]
            check("unchanged_original_" + relative, after == before and sha(after) == expected)
        check("baseline_source_identity_" + relative, sha(before) == baseline[relative]["sha256"])
        compared_files.append({"path": relative, "bytes": len(after), "sha256": sha(after),
                               "changed_from_original": sha(before) != sha(after),
                               "changed_from_02": digest(PREVIOUS / "game" / relative) != sha(after)})
    # 파일 집합 지문은 경로·크기·해시의 정규 JSON을 SHA256으로 계산한다.
    identity_rows = [{"path": r["path"], "bytes": r["bytes"], "sha256": r["sha256"]} for r in compared_files]
    game_digest = sha(json.dumps(identity_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    check("assembled_native_11_paths", len(native_replacements) == 11)
    check("expected_changed_file_counts", sum(r["changed_from_original"] for r in compared_files) == 12
          and sum(r["changed_from_02"] for r in compared_files) == 4)
    check("frozen02_unchanged", snapshot(PREVIOUS) == frozen02)
    check("frozen_native03_unchanged", snapshot(NATIVE) == frozen_native03)
    for path, expected in inputs.items():
        check("evidence_still_identical_" + path, digest(Path(path)) == expected)

    manifest.update({"game_file_set_sha256": game_digest,
                     "file_set_hash_format": "sorted path records {path,bytes,sha256}; json sort_keys=True,separators=(',',':'),UTF8",
                     "dat_provenance": {"origin": str(PREVIOUS / "THOG.dat"), "sha256": dat_report["candidate_sha256"],
                                        "rebuild_performed": False, "copied_build_report_sha256": digest(PREVIOUS / "build_report.json")},
                     "changed_from_02": [r["path"] for r in compared_files if r["changed_from_02"]],
                     "verification": {
                         "G3": {"status": "PASS", "scope": "동결 대상의 번역 교정·문자/글꼴 준비 정적 근거 연결", "report_path": str(OUT / "g3_summary.json"), "source_evidence": refs_g3},
                         "G4": {"status": "PASS", "scope": "DAT동일성 재사용+native03 독립재추출+조립 전체파일/변경경계 확인", "report_path": str(OUT / "g4_summary.json"), "source_evidence": refs_g4},
                         "G2": {"status": "NOT_RUN", "reason": "REA 네이티브 전수 분류 조사 진행 중. 이 조립은 G2 완료를 선언하지 않음"},
                         "G5": {"status": "NOT_RUN", "reason": "이 새 조립본의 실제 UI QA는 부모 담당"}},
                     "deployment": {"allowed": False, "reason": "G2 및 새 조립본 G5 판정 미완료. 검수 후보 전용"}})
    save(manifest_path, manifest)
    manifest_hash = digest(manifest_path)
    common = {"status": "PASS", "assembly_manifest_sha256": manifest_hash, "game_file_set_sha256": game_digest,
              "game_path": str(TARGET / "game"), "dat_sha256": dat_report["candidate_sha256"], "native_audit_sha256": digest(audit_path),
              "graphics_qa": "NOT_RUN", "G2": "NOT_RUN", "deployment_allowed": False}
    g3_bound = {**common, "gate": "G3", "scope": "동결된 조립 구성요소의 번역·글꼴 준비 근거 연결",
                "dat_translation_groups": 590, "dat_translation_locations": 855, "native_translation_fields": 176,
                "known_required_union_count": native_review["known_union_count"], "embedded_font_missing": 0,
                "game_font_routes": {"logical": 28, "embedded": 5, "mapping": 22, "buttons": 81, "dat_dialogs": 4},
                "native_explicit_dialogs": 20, "final_layout_field_changes": 5, "independent_proofread": "PASS",
                "source_evidence": refs_g3, "caller_font_scope": native_review["caller_font_scope"],
                "scope_limit": "native G2가 조사 중이므로 알려진 동결 번역 대상만의 준비 검증. 실제 UI 폴백/잘림·추가 표시 출처 없음의 증명은 별도"}
    g4_bound = {**common, "gate": "G4", "scope": "새 조립본32파일에 대한 정적 검증",
                "files": compared_files, "files_total": 32, "changed_from_original": 12, "changed_from_02": 4,
                "reused_DAT_independent_checks": g4["checks"], "dat_reuse_dependency_checks": dat_g4_count,
                "native_review_dependency_checks": native_review_count, "dat_build_dependency_checks": dat_build_count,
                "native_review_checks": native_review["checks"], "native_resource_LoadString_reads": 50,
                "native_fields_independently_read": 176, "source_evidence": refs_g4,
                "reuse_basis": "DAT바이트 전체 및28입력 동일성, native03바이너리·20교정입력 동일성을 확인하고 새game파일을다시읽어원본/검증입력과정확대조",
                "fresh_assembly_checks": len(checks), "errors": []}
    save(OUT / "g3_summary.json", g3_bound)
    save(OUT / "g4_summary.json", g4_bound)
    save(OUT / "assembly_checks.json", checks)
    save(OUT / "dependency_revalidation.json", {"status": "PASS", "assembly_manifest_sha256": manifest_hash,
         "records": dependency_checks, "frozen02_unchanged": True, "frozen_native03_unchanged": True,
         "source_reports_modified": False, "reuse_scope": "기존 실행 보고서는 수정하지 않고 동일 입력의 정적검사만새후보에연결"})
    save(OUT / "verification_index.json", {"status": "PASS", "assembly_manifest": {"path": str(manifest_path), "sha256": manifest_hash},
         "game_file_set_sha256": game_digest, "reports": [evidence(OUT / name) for name in ("g3_summary.json", "g4_summary.json", "assembly_checks.json", "dependency_revalidation.json")],
         "G2": "NOT_RUN", "G5": "NOT_RUN", "deployment_allowed": False})
    save(OUT / "dependencies.json", {"status": "PASS", "assembly_manifest_sha256": manifest_hash, "inputs": inputs,
         "rule": "고정 입력·파일·새조립manifest변경시관련결과STALE. G2/G5미완료를PASS로승격하지않음"})
    print(json.dumps({"candidate": str(TARGET), "files": 32, "changed_from_original": 12, "changed_from_02": 4,
                      "assembly_manifest_sha256": manifest_hash, "game_file_set_sha256": game_digest,
                      "checks": len(checks), "G2": "NOT_RUN", "G5": "NOT_RUN", "deployment_allowed": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
