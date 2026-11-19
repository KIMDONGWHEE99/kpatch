"""검수된 imagegen 글 표식의 셀 규격 준비를 확인하고 미디어 처리 분류를 확정합니다."""
import hashlib
import json
from datetime import datetime, timezone

from common import DATA, WORK, load_asset, sha, write_json
from PIL import Image


def main():
    audit = WORK / "audit"
    media = WORK / "media"
    ledger_path = audit / "media_classification.json"
    unresolved_path = audit / "media_classification_icons32_unresolved.json"
    if not unresolved_path.exists():
        unresolved_path.write_bytes(ledger_path.read_bytes())
    unresolved = json.loads(unresolved_path.read_text(encoding="utf-8"))
    affected = {"sharedassets0.assets/11", "resources.assets/82"}
    assert {r["id"] for r in unresolved if r.get("treatment") == "UNKNOWN"} == affected
    evidence_path = media / "Icons32_ko_evidence_v2.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    approved_path = media / "IconDecoLabel_ko_32.png"
    expected_path = media / "Icons32_ko_16_v2.png"
    atlas_path = media / "Icons_atlas_expected_rc5.png"
    assert sha(approved_path) == evidence["source_png_sha256"]
    assert sha(expected_path) == evidence["expected_png_sha256"]
    assert sha(atlas_path) == evidence["expected_atlas_png_sha256"]
    approved = Image.open(approved_path).convert("RGBA")
    expected = Image.open(expected_path).convert("RGBA")
    atlas = Image.open(atlas_path).convert("RGBA")
    assert expected.size == (16, 16) and atlas.size == (256, 256)
    assert approved.crop((8, 6, 24, 22)).tobytes() == expected.tobytes()
    assert hashlib.sha256(expected.tobytes()).hexdigest() == evidence["expected_rgba_sha256"]
    source_tex = load_asset(DATA / "sharedassets0.assets").file.objects[11]
    assert hashlib.sha256(source_tex.get_raw_data()).hexdigest() == evidence["source_texture_object_sha256"]
    original = source_tex.read().image.convert("RGBA")
    changed = [
        (x, y) for y in range(256) for x in range(256)
        if original.getpixel((x, y)) != atlas.getpixel((x, y))
    ]
    outside = [(x, y) for x, y in changed if not (35 <= x < 51 and 35 <= y < 51)]
    assert changed and not outside
    assert atlas.crop((35, 35, 51, 51)).tobytes() == expected.tobytes()

    rows = json.loads(ledger_path.read_text(encoding="utf-8"))
    for row in rows:
        if row["id"] not in affected:
            continue
        row["treatment"] = "TRANSLATE"
        row["review_status"] = "PASS"
        row["patch_status"] = "NOT_RUN"
        row["runtime_retest_status"] = "NOT_RUN"
        row["resolution_evidence"] = str(audit / "media_resolution_icons32.json")
        row.pop("expected_treatment_after_resolution", None)
        row["evidence"] = "rc4 실제 기술 목록과 원본 재추출에서 글상자 Icons_32의 영문 L/후속 잘린 글자 모양을 확인. 동일 imagegen 완성 '글' 이미지의 16×16 영역을 추출하여 교체할 픽셀을 확정했다. 위치별 원본 해시·소비 코드·출력 계보·셀 밖 불변은 media_reclassification_icons32 및 media_resolution_icons32에 연결한다."
        if row["type"] == "Texture2D":
            row["region_treatments"] = [
                {"rect_unity_xywh": [35, 205, 16, 16], "treatment": "TRANSLATE", "sprite_id": "resources.assets/82"},
                {"region": "나머지 모든 픽셀", "treatment": "KEEP", "reason": "기존 기호·물품 아이콘의 판독을 유지하며 준비한 atlas에서 셀 밖 변경 0픽셀을 독립 대조했다."},
            ]
        else:
            row["parent_evidence"] = "부모 Texture의 region_treatments 중 Unity 좌하단(35,205,16,16)만 번역. 해당 영역과 겹치는 Sprite는 resources.assets/82 하나다."
    write_json(ledger_path, rows)
    report = {
        "status": "PASS",
        "scope": "G2 처리 분류 및 교체 픽셀 준비만 해결. 실제 후보 패킹·재추출·실행 시각 검수는 아직 NOT_RUN.",
        "utc": datetime.now(timezone.utc).isoformat(),
        "finding": "VRC4-B2-01",
        "classification_resolution": "TRANSLATE",
        "affected_ids": sorted(affected),
        "previous_unresolved_ledger": {"path": str(unresolved_path), "sha256": sha(unresolved_path)},
        "current_ledger": {"path": str(ledger_path), "sha256": sha(ledger_path)},
        "reclassification_evidence": {"path": str(audit / "media_reclassification_icons32.json"), "sha256": sha(audit / "media_reclassification_icons32.json")},
        "prepared_evidence": {"path": str(evidence_path), "sha256": sha(evidence_path)},
        "approved_imagegen_output": {"path": str(approved_path), "sha256": sha(approved_path)},
        "expected_sprite": {"path": str(expected_path), "sha256": sha(expected_path), "rgba_sha256": evidence["expected_rgba_sha256"]},
        "expected_atlas": {"path": str(atlas_path), "sha256": sha(atlas_path)},
        "operation": "기존 imagegen 출력 (8,6)-(24,22)의 픽셀을 16×16 그대로 사용. 재표본화·새 문자 그리기 없음.",
        "actual_image_review": "source_audit도 Icons32_ko_16_v2.png를 functions.view_image(detail=original)로 실제 열어 '글' 표식을 확인했다.",
        "independent_prepared_checks": {
            "source_crop_equals_expected_rgba": "PASS",
            "atlas_cell_equals_expected_rgba": "PASS",
            "changed_pixel_count": len(changed), "outside_changed_pixels": len(outside),
            "status": "PASS",
        },
        "candidate_reextraction": "NOT_RUN",
        "runtime_retest": "NOT_RUN",
        "rc4_visual_failure": "visual_rc4_batch2.json의 FAIL은 보존하며 새 후보 결과로 별도 해결한다.",
        "no_game_asset_mutation_by_this_tool": True,
    }
    write_json(audit / "media_resolution_icons32.json", report)
    print(json.dumps({"status": "PASS", "ledger_sha256": sha(ledger_path), "resolution_sha256": sha(audit / "media_resolution_icons32.json"), "outside_changed_pixels": len(outside)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
