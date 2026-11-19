"""검수판 육안 판독과 원본 텍스처 참조로 모든 미디어 위치를 분류합니다."""
from common import *
from collections import Counter

AUDIT = WORK / "audit"
REVIEW = EXTRACT / "media_review"
BRANDS = {"globalgamemanagers.assets/30", "sharedassets0.assets/31", "sharedassets1.assets/59"}
FONT_ATLASES = {"globalgamemanagers.assets/11", "resources.assets/17", "resources.assets/18",
               "sharedassets0.assets/6", "sharedassets0.assets/7",
               "sharedassets0.assets/15", "sharedassets0.assets/18"}
LETTER_SYMBOLS = {"resources.assets/14", "sharedassets0.assets/11"}
TRANSLATE = {"sharedassets1.assets/27"}
EMPTY = {"resources.assets/9", "resources.assets/15", "sharedassets0.assets/10"}


def main():
    assert sha(EXTRACT/"media.json") == "804fed6653711b3774c818924ea8e07948af5b84e674d9f3ed0fe9f12a140d39", "새 미디어 목록은 육안 검토 전 자동 판정하지 않습니다."
    assert sha(REVIEW/"texture_index.json") == "fd7b9eeb81b722aada319f779b6f0d123814cdec67f1fdce383cb9143e36bd6b", "검토한 이미지 목록과 다릅니다."
    media = json.loads((EXTRACT / "media.json").read_text(encoding="utf-8"))
    textures = json.loads((REVIEW / "texture_index.json").read_text(encoding="utf-8"))
    texture_index = {r["id"]: r for r in textures}
    resolutions = {r["id"]: r for r in json.loads((EXTRACT / "error_resolutions.json").read_text(encoding="utf-8"))}
    results = {}
    for r in textures:
        rid = r["id"]
        treatment = "UNKNOWN"
        evidence = "미디어 판독 미완료."
        if rid in EMPTY and resolutions[rid]["status"] == "PASS":
            treatment = "NO_TEXT"
            evidence = resolutions[rid]["resolution"]
        elif r.get("image"):
            assert sha(r["image"]) == r["image_sha256"], "검토 이미지가 변경되었습니다."
            if rid in TRANSLATE:
                treatment = "TRANSLATE"
                evidence = "4배 확대한 detail_110.png에서 글상자 꾸미기 아이콘의 영문 'Lab...'를 확인. '글' 표식으로 교체 대상."
            elif rid in BRANDS:
                treatment = "KEEP"
                evidence = "검수판 육안 판독: Kingdom Inc. 또는 Leaping Turtle 고유 브랜드 로고. 원형 유지."
            elif rid in FONT_ATLASES:
                treatment = "KEEP"
                evidence = "검수판 육안 판독: FontAsset/디버그 글꼴의 개별 글리프 아틀라스이며 표시 문장 아님. 한국어 지원은 글꼴 의존 관계 검사로 별도 검증."
            elif rid in LETTER_SYMBOLS:
                treatment = "KEEP"
                evidence = "검수판 및 4배 확대 판독: 표정·물품 아이콘에 물음표/느낌표/정보 i/필기 모양 등 의미 기호. 번역할 단어·문장 없음."
            else:
                treatment = "NO_TEXT"
                evidence = "검수판 sheet_00~09 육안 판독: 배경·버튼 테두리·광원 노이즈·시설·장비·캐릭터 그림으로 식별 가능한 언어 문구 없음. 작은 아이콘 묶음은 확대 확인."
        record = {**r, "treatment": treatment, "evidence": evidence,
                  "review_method": "제작자 육안 판독 및 원본 픽셀 SHA-256 연결"}
        if r.get("sheet") is not None:
            record["review_sheet"] = str(REVIEW / f'sheet_{r["sheet"]:02}.jpg')
            record["review_sheet_sha256"] = sha(record["review_sheet"])
        results[rid] = record
    for path in asset_files():
        rows = [r for r in media if r["file"] == path.name and r["type"] == "Sprite"]
        if not rows:
            continue
        env = load_asset(path)
        for r in rows:
            tree = env.file.objects[r["path_id"]].read_typetree()
            pointer = tree["m_RD"]["texture"]
            source_file = path.name if pointer["m_FileID"] == 0 else Path(env.file.externals[pointer["m_FileID"]-1].path).name
            texture_id = f'{source_file}/{pointer["m_PathID"]}'
            parent = results.get(texture_id)
            results[r["id"]] = {**r, "texture_id": texture_id,
                                "texture_rect": tree["m_RD"]["textureRect"],
                                "treatment": parent["treatment"] if parent else "UNKNOWN",
                                "evidence": "원본 Sprite.m_RD.texture 참조와 textureRect로 검수한 부모 텍스처의 동일 픽셀 영역을 연결.",
                                "parent_image_sha256": parent.get("image_sha256") if parent else None,
                                "parent_evidence": parent.get("evidence") if parent else None}
    output = [results[r["id"]] for r in media]
    write_json(AUDIT / "media_classification.json", output)
    summary = {"game_id": GAME_ID, "build_id": BUILD, "media_input_sha256": sha(EXTRACT/"media.json"),
               "tool_sha256": sha(__file__), "texture_count": len(textures),
               "type_counts": dict(Counter(r["type"] for r in output)),
               "treatment_counts": dict(Counter(r["treatment"] for r in output)),
               "translation_locations": [r["id"] for r in output if r["treatment"] == "TRANSLATE"],
               "status": "PASS" if all(r["treatment"] != "UNKNOWN" for r in output) else "FAIL",
               "scope": "미디어 분류 완료 여부. 번역 후보 적용·그래픽 검증 완료를 의미하지 않음."}
    write_json(AUDIT / "media_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
