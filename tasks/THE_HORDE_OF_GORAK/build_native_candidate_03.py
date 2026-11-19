"""독립 판정 결과를 합치고 추가 표시 리소스가 포함된03을 생성합니다."""
import collections
import json
import re
import build_native_candidate as build
from native_crt_display_review import TRANSLATIONS as CRT
from native_transition_display_review import TRANSLATIONS as TRANSITION
import verify_native_windows_resources as verify

DEBUG = {"Type : Bouncing Ball": "유형 : 공 튀기기", "Speed : %i": "속도 : %i", "Angle : %i degrees": "각도 : %i도",
         "Gravity scale : %i%%": "중력 비율 : %i%%", "Friction : %i": "마찰 : %i", "Elasticity : %i": "탄성 : %i", "Density : %i": "밀도 : %i"}


def main():
    inventory = build.WORK / "native_string_inventory.jsonl"
    rows = [json.loads(line) for line in inventory.read_text(encoding="utf-8").splitlines()]
    patch = json.loads((build.WORK / "bouncing_resource_classification_patch.json").read_text(encoding="utf-8"))
    index = {(row["file"], row["file_offset"]): row for row in rows}
    for edit in patch:
        row = index[edit["file"], edit["file_offset"]]
        assert row["source_bytes_sha256"] == edit["source_bytes_sha256"] and row["file_sha256"] == edit["file_sha256"]
        assert row["source"] == edit["source"]
        row.update(classification=edit["classification"], reason=edit["reason"], classification_evidence=edit["evidence"],
                   consumer=edit["consumer"], classification_confidence=edit.get("confidence", "표시 함수 소비는 확인했으며 게임 접근성은 보수적으로 처리"))
    inventory.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    selected = [row for row in rows if row["classification"] == "VISIBLE_TRANSLATE"]
    (build.WORK / "native_visible_worklist.json").write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    build.OUT = build.ROOT / "working_private/THE_HORDE_OF_GORAK/native_candidate_03"
    build.TRANSLATIONS.update(CRT)
    build.TRANSLATIONS.update(TRANSITION)
    build.TRANSLATIONS.update(DEBUG)
    for row in selected:
        assert re.findall(r"%[dius]|%%", row["source"]) == re.findall(r"%[dius]|%%", build.TRANSLATIONS[row["source"]])
    build.main()
    path = build.OUT / "native_patch_audit.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["limitations"][2] = f"확인된 {len(report['translations'])}개 표시 필드만 포함. 전체 네이티브 문자열 분류 완료를 뜻하지 않음."
    report["limitations"].append("전환 설정과 이동 디버그 창은 표시 필드 소비를 정적으로 확인해 번역했으며 실제 게임에서 창을 열었다고 주장하지 않음.")
    report["additional_evidence"] = ["native_crt_display_evidence.json", "native_transition_display_review.json", "bouncing_resource_review_evidence.json"]
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    verify.BASE = build.OUT
    verify.main()
    print(json.dumps({"inventory_classifications": dict(collections.Counter(row["classification"] for row in rows)),
                      "resource_unknown": sum(row["classification"] == "UNKNOWN" and row["kind"] in ("RT_STRING", "RT_DIALOG") for row in rows)}))


if __name__ == "__main__":
    main()
