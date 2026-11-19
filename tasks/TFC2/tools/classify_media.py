from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


TRANSLATE = {
    ("sharedassets4.assets", 13),
    ("sharedassets4.assets", 49),
}

KEEP_NAMES = {
    "MPS_logo_splash_4K_4",
    "MPS_logo_splash_4K_4_0",
    "TFC_Logo",
    "TFC2 logo",
    "TFC2 logo_0",
    "W-LOGO-RGB",
    "W-LOGO-RGB_0",
    "Credits_Logo_KoU",
    "Credits_Logo_wield",
    "SQ-small-digital-small-digital-landscape-cmyk-gov white text",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="TFC2 그래픽·미디어 전수 분류표 생성")
    parser.add_argument("--structure", type=Path, required=True)
    parser.add_argument("--review-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    structure = json.loads(args.structure.read_text(encoding="utf-8"))
    review = json.loads(args.review_index.read_text(encoding="utf-8"))
    if review.get("errors"):
        raise RuntimeError(f"미디어 추출 오류가 있습니다: {review['errors']}")

    records: list[dict[str, object]] = []
    for file_row in structure["files"]:
        file_name = str(file_row["relative_path"])
        for media in file_row.get("media", []):
            path_id = int(media["path_id"])
            name = str(media.get("name", ""))
            key = (file_name, path_id)
            if key in TRANSLATE:
                action = "TRANSLATE"
                reason = "픽셀에 포함된 하투사 연도 표제를 한국어 이미지로 교체"
            elif name in KEEP_NAMES:
                action = "VISIBLE_KEEP"
                reason = "게임·개발사·배급사·지원 기관의 고유 로고"
            elif file_name == "Resources/unity default resources" and (
                "Watermark" in name or name == "EscToExit_Text"
            ):
                action = "INTERNAL"
                reason = "Unity 편집기·평가판·개발 빌드용 기본 자원이며 정식 게임 표시물이 아님"
            else:
                action = "NO_TEXT"
                reason = "18장 접촉 시트 육안 검토에서 번역할 픽셀 문구가 없는 그래픽·글꼴·재질"
            records.append(
                {
                    "file": file_name,
                    "path_id": path_id,
                    "object_type": str(media["object_type"]),
                    "name": name,
                    "classification": "MEDIA",
                    "action": action,
                    "reason": reason,
                }
            )

    actions = Counter(str(row["action"]) for row in records)
    unknown = [row for row in records if row["action"] == "UNKNOWN"]
    report = {
        "schema_version": 1,
        "structure": str(args.structure.resolve()),
        "review_index": str(args.review_index.resolve()),
        "reviewed_unique_images": int(review["unique_images"]),
        "reviewed_contact_sheets": int(review["sheet_count"]),
        "record_count": len(records),
        "classification_counts": {"MEDIA": len(records)},
        "action_counts": dict(sorted(actions.items())),
        "unknown_count": len(unknown),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: value for key, value in report.items() if key != "records"}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if unknown else 0)


if __name__ == "__main__":
    main()
