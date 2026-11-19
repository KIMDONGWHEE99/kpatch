"""직접 판독한 미디어 기록을 원본과 검수판 해시에 연결한다. 미해결 사항은 유지한다."""
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
REVIEW = ROOT / "working_private/SOULASH_2/media_review/review_v2"
REVIEWED_CATALOG_SHA256 = "ec863be4be3631d0736d45e17c6c3fa9ef44c7d2cfb12927e08d24e85037c19a"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_ogg(path):
    """확장자가 아닌 모든 Ogg 페이지의 스트림 시작 패킷으로 영상 포함 여부를 확인한다."""
    data = path.read_bytes()
    offset, pages, streams, stream_serials = 0, 0, [], set()
    while offset < len(data):
        assert data[offset:offset + 4] == b"OggS" and data[offset + 4] == 0, str(path)
        count = data[offset + 26]
        header_end = offset + 27 + count
        size = sum(data[offset + 27:header_end])
        payload = data[header_end:header_end + size]
        assert len(payload) == size
        serial = int.from_bytes(data[offset + 14:offset + 18], "little")
        stream_serials.add(serial)
        if data[offset + 5] & 2:
            codec = "vorbis" if payload.startswith(b"\x01vorbis") else "theora" if payload.startswith(b"\x80theora") else "UNKNOWN"
            streams.append({"serial": serial, "codec": codec, "first_packet_prefix_hex": payload[:16].hex()})
        offset = header_end + size
        pages += 1
    assert offset == len(data) and stream_serials == {s["serial"] for s in streams}, str(path)
    return {"path": path.relative_to(SOURCE).as_posix(), "sha256": sha(path), "pages": pages, "streams": streams}


def main():
    catalog_path = REVIEW / "catalog.json"
    assert sha(catalog_path) == REVIEWED_CATALOG_SHA256, "직접 판독한 목록이 바뀌었습니다. 새 이미지는 자동 통과시키지 않습니다."
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    earlier = json.loads((REVIEW.parent / "catalog.json").read_text(encoding="utf-8"))
    # 개요판은 앞서 직접 본 파일과 해시가 같아 판독을 재사용한다.
    prior_overviews = {p["page"]: p["sha256"] for p in earlier["overview_pages"]}
    pages, page_map = [], {}
    for group in ("overview_pages", "detail_pages", "gif_pages"):
        for page in catalog[group]:
            assert sha(REVIEW / page["page"]) == page["sha256"]
            if group == "overview_pages":
                assert prior_overviews[page["page"]] == page["sha256"]
            pages.append({**page, "review_status": "PASS", "observation": "모든 칸을 직접 판독함. 자동 글자 인식 결과로 대체하지 않음."})
            for identity in page["items"]:
                page_map.setdefault(identity.split(" ")[0], []).append({"page": page["page"], "sha256": page["sha256"], "region_id": identity})
    html_path = SOURCE / "data/docs/index.html"
    html = html_path.read_text(encoding="utf-8")
    doc_links = {}
    for number, line in enumerate(html.splitlines(), 1):
        for match in re.finditer(r'<img[^>]+src="([^"]+)"', line):
            relative = (Path("data/docs") / match.group(1)).as_posix().replace("/./", "/")
            doc_links.setdefault(relative.casefold(), []).append(number)
    assets_path = SOURCE / "data/mods/core_2/assets.json"
    assets_text = assets_path.read_text(encoding="utf-8")
    asset_lines = list(enumerate(assets_text.splitlines(), 1))
    doc_text_ids = {"I003", "I004", "I008", "I009", "I010", "I011", "I012", "I013", "I014", "I015", "I016", "I017", "I030", "I031"}
    keeps = {
        "I001": "Soulash II 게임 제목 로고. 제품명과 로고 디자인을 보존.",
        "I029": "Soulash 제목 로고. 동봉 모드 제작 설명서의 브랜드 이미지.",
        "I032": "S 모노그램. 예제 모드의 로고로 알파벳 형태 보존.",
        "I033": "예제 모드 지도 화면의 @, %, #, Ω 등은 지형·사물을 표현하는 로그라이크 기호. 자연어 문장 아님.",
        "I053": "책 표지와 장비의 룬 모양·기하 표식을 포함한 사물 그림. 읽을 수 있는 자연어 문장은 없고 장식 기호는 유지.",
        "I060": "무기 세트 I·II 로마 숫자 표시. 숫자 체계와 키 구분 기능 보존.",
        "I065": "파티클의 I·II·III 계열 숫자·음표·기호는 효과 표시이며 자연어 문장 없음. 표시 기호 보존.",
        "I071": "인물 부품 그림. 의복의 장식 룬과 미확인 인물의 ? 기호를 보존. 자연어 문장 없음.",
        "I077": "수면을 뜻하는 Z 기호 애니메이션. 국제적으로 쓰이는 그림 기호로 보존.",
        "I087": "기술 그림 모음의 ?·+ 등 표시 기호를 보존. 자연어 문장 없음.",
        "I102": "미확인 기술의 ? 기호. 번역할 단어가 없는 표시 기호.",
        "I114": "행동 그림 모음의 ?·+ 등 표시 기호를 보존. 자연어 문장 없음.",
        "I190": "PlayStation 조작기의 R·L·R1·R2·L1·L2와 버튼 모양. 실제 장치 표기 보존.",
        "I191": "?·+ 도움말/추가 기호. 자연어 단어가 아닌 조작 기호 보존.",
        "I221": "QWERTY·숫자·F1~F12·ESC 등 키보드 키 그림. 실제 키 표기 보존.",
        "I244": "미확인 자원의 ?와 불꽃 애니메이션. 표시 기호 보존.",
        "I247": "Xbox 조작기의 A·B·X·Y·LT·RT·LB·RB·R·L. 실제 장치 표기 보존.",
        "I248": "완료 체크와 미확인 ? 지도 표시 기호 보존.",
        "I253": "세계 지도 그림의 ? 등 미확인 장소 기호를 보존. 자연어 문장 없음.",
        "I256": "해골과 II 로마 숫자로 이루어진 Soulash 2 모드 아이콘. 제품명 로고 보존."
    }
    translate = {
        "I040": {"text": "! M I S B L O C K / 0 1 2 3 4 5 6 7 8 9", "regions": [[0, 0, 120, 16]], "note": "상단 영문 타일의 조합이 MISS/BLOCK 표시에 쓰이는지 코드 연결 확인 필요. 하단 숫자는 보존. assets.json의 damage_numbers는 10×2 타일."},
        "I081": {"text": "Support Soulash on PATREON", "regions": [[0, 0, 300, 77]], "note": "후원 안내 영문 문구. Soulash·PATREON 브랜드는 유지할 수 있으나 Support…on 안내는 번역 대상. 현재 assets.json 직접 참조는 찾지 못해 실제 사용 여부 UNKNOWN."},
        "I082": {"text": "Tweet", "regions": [[0, 0, 80, 25]], "note": "트윗 작성 동작 버튼. Twitter 새 아이콘을 보존하고 동작 문구를 번역할 대상. assets.json 직접 참조 확인."}
    }
    observations = []
    for item in catalog["unique"]:
        identity = item["id"]
        assert identity in page_map and item["decode_status"] == "PASS"
        for path in item["paths"]:
            assert sha(SOURCE / path) == item["sha256"]
        entry = {**item, "evidence": page_map[identity], "reviewed_region": [0, 0, item["width"], item["height"]],
                 "review_status": "PASS", "treatment": "NO_TEXT", "text_content": [],
                 "observation": "해당 원본 전체를 개요판에서 판독하고, 축소된 게임 그림은 상세 조각을 추가 판독함. 배경·인물·사물·도형으로 구성되며 번역할 자연어 문구를 관찰하지 못함."}
        entry["asset_references"] = []
        entry["documentation_references"] = []
        for path in item["paths"]:
            if path.startswith("data/mods/core_2/"):
                resource = path[len("data/mods/core_2/"):]
                entry["asset_references"].extend({"path": assets_path.relative_to(SOURCE).as_posix(), "sha256": sha(assets_path), "line": n} for n, line in asset_lines if '"' + resource + '"' in line)
            entry["documentation_references"].extend({"path": "data/docs/index.html", "sha256": sha(html_path), "line": n} for n in doc_links.get(path.casefold(), []))
        if any(p.startswith("data/docs/") for p in item["paths"]):
            entry["scope"] = "EXTERNAL_DOCUMENTATION" if entry["documentation_references"] else "DOCUMENTATION_DIRECTORY_UNREFERENCED"
            entry["game_visibility"] = "NOT_ESTABLISHED"
            if identity in doc_text_ids:
                entry["treatment"] = "KEEP" if entry["documentation_references"] else "UNKNOWN"
                entry["text_content"] = ["영문 모드 편집기 또는 메뉴 화면 캡처"]
                entry["observation"] = "동봉 모드 제작 설명서용 화면 캡처. HTML 참조가 있는 항목은 외부 문서 그림으로 유지. 참조가 없는 항목은 표시 범위·처리 UNKNOWN 유지."
        else:
            entry["scope"] = "GAME_OR_MOD_ASSET"
            entry["game_visibility"] = "ASSET_REFERENCE" if entry["asset_references"] else "NOT_ESTABLISHED"
        if identity in keeps:
            entry["treatment"], entry["observation"] = "KEEP", keeps[identity]
        if identity in translate:
            entry["treatment"] = "TRANSLATE"
            entry["text_content"] = [translate[identity]["text"]]
            entry["text_regions"] = translate[identity]["regions"]
            entry["observation"] = translate[identity]["note"]
            entry["implementation_status"] = "NOT_RUN"
        if identity == "I152":
            entry["treatment"] = "UNKNOWN"
            entry["text_content"] = ["첫 패널 표지판에 두 단어의 영문 형태. 둘째 단어는 Gate로 추정되나 정확한 판독 미확정."]
            entry["text_regions"] = [[90, 190, 120, 70], [90, 580, 120, 70]]
            entry["observation"] = "회색/컬러 변형의 동일한 표지판을 8배 확대 판독했으나 첫 단어를 확정하지 못함. 고유명사 또는 안내인지도 UNKNOWN."
            entry["enlargements"] = [{"path": name, "sha256": sha(REVIEW / name)} for name in ("I152_sign_gray.png", "I152_sign_color.png")]
        observations.append(entry)
    ogg_details = [inspect_ogg(SOURCE / x["path"]) for x in catalog["ogg_signatures"]]
    ogg_counts = dict(Counter(stream["codec"] for item in ogg_details for stream in item["streams"]))
    assert "UNKNOWN" not in ogg_counts and "theora" not in ogg_counts
    ogg_path = REVIEW / "ogg_streams.json"
    ogg_path.write_text(json.dumps(ogg_details, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"game_id": "SOULASH_2", "baseline_id": SOURCE.name, "finished": datetime.now(timezone.utc).isoformat(),
              "catalog_sha256": sha(catalog_path), "finalizer_sha256": sha(Path(__file__)),
              "image_files": catalog["file_count"], "unique_images": len(observations), "reviewed_unique_images": len(observations),
              "page_count": len(pages), "reviewed_pages": len(pages), "gif_frames": catalog["gif_frame_count"],
              "review_status": "PASS", "g2_status": "FAIL", "release_ready": False,
              "treatment_counts": dict(Counter(x["treatment"] for x in observations)),
              "unresolved_ids": [x["id"] for x in observations if x["treatment"] == "UNKNOWN"],
              "extraction_error_resolution": catalog["extraction_errors"], "observations": observations, "pages": pages,
              "video_scope": {"video_file_extensions_found": catalog["videos_by_extension"], "ogg_signature_counts": ogg_counts,
                  "ogg_full_stream_inventory": {"path": str(ogg_path), "sha256": sha(ogg_path), "files": len(ogg_details), "pages": sum(x["pages"] for x in ogg_details)},
                  "result": "전체 파일 확장자 목록에 영상 컨테이너 없음. 모든 OGG 페이지를 순회해 모든 스트림의 시작 패킷이 Vorbis임을 확인. 동봉 GIF 5개는 전 프레임 판독 완료. 코드로 생성하는 영상/화면은 별도 런타임 조사 대상."}}
    assert len({x["id"] for x in observations}) == catalog["unique_hash_count"]
    assert set(page_map) == {x["id"] for x in observations}
    (REVIEW / "review_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("image_files", "unique_images", "page_count", "treatment_counts", "unresolved_ids", "video_scope")}, ensure_ascii=True))


if __name__ == "__main__":
    main()
