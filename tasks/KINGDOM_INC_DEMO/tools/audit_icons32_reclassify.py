"""기술 목록의 별도 글상자 아이콘 누락을 재분류하고 원본 위치를 고정합니다."""
import hashlib
import json
from datetime import datetime, timezone

from common import ROOT, DATA, EXTRACT, WORK, load_asset, sha, write_json


def main():
    ledger_path = WORK / "audit/media_classification.json"
    archive_path = WORK / "audit/media_classification_before_icons32.json"
    if not archive_path.exists():
        archive_path.write_bytes(ledger_path.read_bytes())
    old = json.loads(archive_path.read_text(encoding="utf-8"))
    rows = json.loads(ledger_path.read_text(encoding="utf-8"))
    old_by_id = {r["id"]: r for r in old}
    target_ids = {"resources.assets/82", "sharedassets0.assets/11"}
    for key in target_ids:
        assert old_by_id[key]["treatment"] == "KEEP"

    tex_env = load_asset(DATA / "sharedassets0.assets")
    sprite_env = load_asset(DATA / "resources.assets")
    tex_obj = tex_env.file.objects[11]
    sprite_obj = sprite_env.file.objects[82]
    tex_tree = tex_obj.read_typetree()
    sprite_tree = sprite_obj.read_typetree()
    texture = tex_obj.read().image.convert("RGBA")
    sprite = sprite_obj.read().image.convert("RGBA")
    assert texture.size == (256, 256)
    assert sprite.size == (16, 16)
    assert texture.crop((35, 35, 51, 51)).tobytes() == sprite.tobytes()
    assert sprite_tree["m_RD"]["texture"] == {"m_FileID": 3, "m_PathID": 11}
    assert sprite_env.file.externals[2].path == "sharedassets0.assets"
    assert sprite_tree["m_RD"]["settingsRaw"] == 64
    assert sprite_tree["m_SpriteAtlas"] == {"m_FileID": 0, "m_PathID": 0}
    raw_image = bytes(tex_tree["image data"])
    raw_obj = tex_obj.get_raw_data()
    offset = raw_obj.find(raw_image)
    assert offset == 104 and raw_obj.count(raw_image) == 1
    assert tex_tree["m_TextureFormat"] == 4 and tex_tree["m_MipCount"] == 1
    assert len(raw_image) == 262144
    assert tex_tree["m_StreamData"] == {"offset": 0, "size": 0, "path": ""}

    overlaps = []
    for row in old:
        if row.get("type") != "Sprite" or row.get("texture_id") != "sharedassets0.assets/11":
            continue
        rect = row["texture_rect"]
        if max(rect["x"], 35) < min(rect["x"] + rect["width"], 51) and max(rect["y"], 205) < min(rect["y"] + rect["height"], 221):
            overlaps.append(row["id"])
    assert overlaps == ["resources.assets/82"]

    for row in rows:
        if row["id"] not in target_ids:
            continue
        row["treatment"] = "UNKNOWN"
        row["previous_treatment"] = "KEEP"
        row["review_status"] = "FAIL"
        row["expected_treatment_after_resolution"] = "TRANSLATE"
        row["finding"] = "VRC4-B2-01"
        row["reclassification_evidence"] = "rc4 기술 목록 중간 실제 PNG와 원본 Sprite 재추출을 직접 열어 확인. Icons_32는 글상자 기술에 쓰이는 별도 L/잘린 후속 영문 글자 모양이다. 기존 전체 atlas의 '필기 모양 등 의미 기호' 판정으로 이 셀의 영문을 유지할 근거가 부족했다. 이전 IconDecoLabel 32픽셀 교체는 이 셀에 영향을 주지 않는다."
        row["resolution_required"] = "동일 imagegen '글' 생성물을 규격 축소·해당 셀 교체한 후 셀 밖 픽셀/다른 Sprite 불변, 후보 재추출, 실제 화면 재검증."
        if row["type"] == "Texture2D":
            row["affected_region_unity_bottom_left"] = [35, 205, 16, 16]
            row["unaffected_regions"] = "위 16×16 셀 바깥. 새 미확인 문자를 발견했다는 뜻이 아니라 이 셀 때문에 전체 텍스처 처리 상태를 미해결로 전환한다."
    write_json(ledger_path, rows)

    refs = [
        ROOT / "extracted_private/KINGDOM_INC_DEMO/inspection/decompiled/Assets.Source.Player.Tech/T1Mine.cs",
        ROOT / "extracted_private/KINGDOM_INC_DEMO/inspection/decompiled/Assets.Source.Player/TechNode.cs",
        ROOT / "extracted_private/KINGDOM_INC_DEMO/inspection/decompiled/Assets.Behaviour.UI.TechTree/TechTreeListItem.cs",
        ROOT / "extracted_private/KINGDOM_INC_DEMO/inspection/decompiled/SpriteLibrary.cs",
    ]
    report = {
        "status": "FAIL", "resolution_status": "NOT_RUN",
        "utc": datetime.now(timezone.utc).isoformat(),
        "finding": "VRC4-B2-01",
        "candidate": "1.0.0_rc4",
        "reason": "실제 기술 목록에서 별도 atlas 글상자 아이콘의 영문 잔존을 발견했다. 새 후보 rc5 수정·검증 전까지 두 미디어 출처를 UNKNOWN으로 유지한다.",
        "source_files": [
            {"path": str(DATA / "resources.assets"), "sha256": sha(DATA / "resources.assets")},
            {"path": str(DATA / "sharedassets0.assets"), "sha256": sha(DATA / "sharedassets0.assets")},
        ],
        "previous_records": [old_by_id[k] for k in sorted(target_ids)],
        "before_ledger": {"path": str(archive_path), "sha256": sha(archive_path)},
        "current_ledger": {"path": str(ledger_path), "sha256": sha(ledger_path)},
        "unknown_media_ids": sorted(target_ids),
        "source_sprite": {
            "id": "resources.assets/82", "name": "Icons_32",
            "object_sha256": hashlib.sha256(sprite_obj.get_raw_data()).hexdigest(),
            "binding": {"m_FileID": 3, "m_PathID": 11, "external_path": "sharedassets0.assets"},
            "m_Rect": sprite_tree["m_Rect"], "textureRect": sprite_tree["m_RD"]["textureRect"],
            "settingsRaw": 64, "m_SpriteAtlas": sprite_tree["m_SpriteAtlas"],
            "rotation_proof": "UnityPy의 실제 Sprite RGBA 재추출과 Texture RGBA의 좌상단(35,35,51,51) crop가 바이트 단위로 동일하다. 회전·뒤집기 보정 없는 직사각형 영역이다.",
            "image": str(EXTRACT / "media_review/Icons_32_source.png"),
            "image_sha256": sha(EXTRACT / "media_review/Icons_32_source.png"),
            "rgba_sha256": hashlib.sha256(sprite.tobytes()).hexdigest(),
        },
        "texture_patch_boundary": {
            "id": "sharedassets0.assets/11", "name": "Icons",
            "object_sha256": hashlib.sha256(tex_obj.get_raw_data()).hexdigest(),
            "size": [256, 256], "format": "RGBA32", "format_id": 4, "mip_count": 1,
            "storage": "inline image data", "stream": tex_tree["m_StreamData"],
            "image_bytes": 262144,
            "raw_image_sha256": hashlib.sha256(raw_image).hexdigest(),
            "object_file_offset": tex_obj.byte_start,
            "image_relative_offset": offset,
            "image_file_offset": tex_obj.byte_start + offset,
            "unity_bottom_left_rect_xywh": [35, 205, 16, 16],
            "decoded_png_top_left_box": [35, 35, 51, 51],
            "original_file_row_spans": [
                {"offset": tex_obj.byte_start + offset + ((205 + y) * 256 + 35) * 4, "length": 64}
                for y in range(16)
            ],
            "allowed_pixel_count": 256, "allowed_raw_bytes": 1024,
            "overlapping_sprite_ids": overlaps,
            "preserve": "셀 밖 모든 RGBA, Texture 메타데이터와 객체 수, 모든 Sprite 메타데이터·참조. 파일 절대 위치는 원본 좌표이며 후보 재저장 시 객체 이동 가능하므로 객체/필드 기반으로 처리한다.",
        },
        "consumer_chain": "T1Mine.Init deco_label IconName=Icons_32 → TechNode.Icon → SpriteLibrary.Get(사전은 Resources.LoadAll<Sprite>(Icons)) → TechTreeListItem.Update의 _icon.sprite=node.Icon",
        "consumer_evidence": [{"path": str(p), "sha256": sha(p)} for p in refs],
        "visual_evidence": {
            "path": str(WORK / "full_rc4/qa_full_rc4/231829_0396700_scroll.png"),
            "sha256": sha(WORK / "full_rc4/qa_full_rc4/231829_0396700_scroll.png"),
            "viewed_with": "functions.view_image(detail=original)",
            "original_sheet": str(EXTRACT / "media_review/detail_066.png"),
            "original_sheet_sha256": sha(EXTRACT / "media_review/detail_066.png"),
        },
        "proposed_reuse": {
            "path": str(WORK / "media/IconDecoLabel_ko_32.png"),
            "sha256": sha(WORK / "media/IconDecoLabel_ko_32.png"),
            "method": "기존 imagegen 완성물의 동일 '글' 아이콘을 nearest 방식 16×16으로 규격 조정하여 위 셀에 배치. 새 디자인/문자 생성·원본 전체 atlas 재생성 없음.",
            "implementation": "parent가 tooling_audit에게 위임. 본 도구는 미디어·후보를 수정하지 않는다.",
        },
        "invalidated_claims": [
            {"path": str(WORK / "audit/source_summary.json"), "sha256": sha(WORK / "audit/source_summary.json"), "status": "STALE", "reason": "원래 0 UNKNOWN 분류 당시의 기록으로 보존. 이 아이콘을 발견한 현재 분류에는 더 이상 적용하지 않는다."},
            {"path": str(WORK / "audit/source_resolution_final.json"), "sha256": sha(WORK / "audit/source_resolution_final.json"), "status": "STALE", "reason": "rc4 당시 해시·분류 기록으로 보존. 새 ledger 및 rc5 후 source_resolution_rc5.json에서 별도 해결한다."},
        ],
        "not_claimed": ["최종 픽셀 번역 완료", "rc5 정적/실행 통과", "전체 G5 완료", "설치 성공"],
    }
    write_json(WORK / "audit/media_reclassification_icons32.json", report)
    print(json.dumps({"unknown": sorted(target_ids), "ledger_sha256": sha(ledger_path), "report_sha256": sha(WORK / "audit/media_reclassification_icons32.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
