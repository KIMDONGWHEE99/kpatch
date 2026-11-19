"""제작자가 직접 판독한 접촉판·확대 화면의 판정을 위치별 대장으로 고정합니다."""
from __future__ import annotations
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "extracted_private/THE_HORDE_OF_GORAK/steam_26336311"
REVIEW = BASE / "media_review_01"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    media = json.loads((BASE / "nebula_01/media.json").read_text(encoding="utf-8-sig"))
    index = json.loads((REVIEW / "contact_index.json").read_text(encoding="utf-8"))
    baseline = json.loads((BASE / "nebula_03/input.json").read_text(encoding="utf-8"))["sha256"]
    # 아래 판정은 29개 판을 실제 view_image로 모두 읽고, 의심 위치를 확대 판독한 기록입니다.
    observations = [
        "오크·배·성채·배경·사슴 로고 변형·제작사 로고·숫자 0/1을 각 칸에서 판독",
        "숫자·연산기호·물음표·게임 제목 로고, 오크와 UI 빈 바탕을 각 칸에서 판독",
        "오크·거미·전사·배·커서·효과·성채·빈 판넬을 각 칸에서 판독",
        "PLAYTEST 문구와 오크·건물·룬 문양·효과·아이콘을 각 칸에서 판독",
        "MAD OCTOPUS GAMES 로고와 배·오크·건물·배경을 각 칸에서 판독",
        "룬 탑·오크·공격효과·건물·도구 아이콘·일시정지 기호를 각 칸에서 판독",
        "세계지도·배경·포탈·키 그림·도구/물약 아이콘·오크를 각 칸에서 판독",
        "물음표·해골/기술 기호·빈 책·오크·건물·빈 안내판을 각 칸에서 판독",
        "오크·전사·박쥐·효과·건물·희미한 아이콘·선 바탕을 각 칸에서 판독",
        "ORC WARCHIEF 로고·물음표·배경 및 건물의 개별 애니메이션 변형을 각 칸에서 판독",
        "ORC WARCHIEF 축소 로고와 건물·동물·전사·도구·배경을 각 칸에서 판독",
        "물음표와 전사·배·건물·기술 기호·원형 진행 표시를 각 칸에서 판독",
        "원형 진행 표시의 개별 단계와 오크·기병 동작을 각 칸에서 판독",
        "오크·배·빈 책·기술 도식·배경·기병·투사체를 각 칸에서 판독",
        "END·물음표, 배·오크·건물·배경·효과·빈 판넬을 각 칸에서 판독",
        "ORC WARCHIEF 컬러 로고와 비행선·투석기·원형 표시·효과·동물을 각 칸에서 판독",
        "Esc 키·Steam 기호와 아이콘·빈 안내판·불꽃·공성무기·동물을 각 칸에서 판독",
        "DIGITAL DEER STUDIO 로고와 오크·불꽃의 개별 방향/변형을 각 칸에서 판독",
        "불꽃 투사체·병사 무리의 개별 애니메이션을 각 칸에서 판독",
        "불꽃 투사체·연기·성벽·빈 판넬의 개별 변형을 각 칸에서 판독",
        "I 등급·END, 세계 전경·성벽·오크 카드·공성무기를 각 칸에서 판독",
        "I 등급·20/80/150 수량과 열기구·투석기·연기·배경을 각 칸에서 판독",
        "50/100/250/500/1000/5 수량과 비행선·오크·폭발·건물을 각 칸에서 판독",
        "10/+1 수량·II~VI 등급과 오크 카드·배·연기·건물을 각 칸에서 판독",
        "II 등급·A 키와 오크·성벽·공성무기·연기·트로피를 각 칸에서 판독",
        "Shift/Esc/스페이스 기호·WISHLIST ON STEAM!, 전투 삽화·용·성벽·동물을 각 칸에서 판독",
        "DIGITALDEERSTUDIO.PL·사슴/Discord 표식, 전투 삽화·용·동물을 각 칸에서 판독",
        "동물 스프라이트 시트·용·열기구·코인·화살표·파라슈트·빈 판넬을 각 칸에서 판독",
        "전기효과·기병·병사 무리·해골 깃발·건물을 각 칸에서 판독",
    ]
    assert len(index) == len(observations) == 29
    overrides = {}
    def mark(handles, decision, text, reason):
        for handle in handles:
            assert handle not in overrides
            overrides[handle] = (decision, text, reason)
    mark([19,46,49,50,53,54,55,58,60,61,1194], "KEEP", "DIGITAL DEER STUDIO / DIGITAL DEER GAMES STUDIO", "제작사 로고의 고유 브랜드 표기와 로고 디자인을 보존")
    mark([47,48,1896], "KEEP", "사슴 로고 표식", "원문 문장이 없는 제작사 로고 표식이며 브랜드 식별을 보존")
    mark([28], "KEEP", "CREATIVE FORGE", "불꽃과 결합된 제작사·브랜드 로고 고유명사")
    mark([41], "KEEP", "WHITE DEER GAMES STUDIO", "사슴과 결합된 제작사 로고 고유명사")
    mark([283], "KEEP", "MAD OCTOPUS GAMES", "문어와 결합된 제작사 로고 고유명사")
    mark([138], "KEEP", "THE HORDE OF GORAK", "게임의 정식 제목 로고 디자인·브랜드 식별을 보존")
    mark([616,719,1089], "KEEP", "ORC WARCHIEF", "원본에 포함된 다른 게임 제목 로고의 고유명사·브랜드 식별을 보존")
    mark([1893], "KEEP", "DIGITALDEERSTUDIO.PL", "실제 주소를 나타내는 웹사이트 표기이므로 번역하지 않음")
    mark([1162], "KEEP", "Steam 표식", "외부 서비스의 고유 로고 표식")
    mark([1928], "KEEP", "Discord 표식", "외부 서비스의 고유 로고 표식")
    for h,v in {78:"0",79:"1",82:"2",83:"3",94:"4",124:"5",125:"6",126:"7",127:"8",128:"9",129:"-",130:"+",131:".",132:"e"}.items():
        mark([h], "KEEP", v, "숫자·연산자·소수점·지수 표기용 글자 이미지로 수치 표시를 보존")
    mark([85,510,631,789,790,1040], "KEEP", "?", "미확인/도움말을 나타내는 언어 공통 물음표")
    for h,v in {474:"D",1790:"A",1193:"Esc",1836:"Esc",1817:"Shift",1818:"스페이스 기호"}.items():
        mark([h], "KEEP", v, "실제 키보드 입력 키를 가리키는 키캡 표기이므로 키 식별을 보존")
    for h,v in {1463:"I",1537:"I",1730:"VI",1731:"VI",1732:"V",1733:"V",1734:"IV",1735:"IV",1736:"III",1737:"III",1738:"II",1752:"II"}.items():
        mark([h], "KEEP", v, "같은 성채 카드 계열의 로마 숫자 I~VI 등급 표기")
    for h,v in {1538:"20",1539:"20",1540:"80",1541:"80",1542:"150",1543:"150",1630:"50",1637:"50",1638:"250",1639:"250",1641:"500",1642:"500",1643:"100",1644:"100",1660:"500",1661:"500",1662:"1000",1663:"1000",1664:"5",1665:"5",1666:"10",1667:"10",1722:"+1",1723:"+1"}.items():
        mark([h], "KEEP", v, "자원/병력/효과 카드의 아라비아 숫자 수량·증가량을 보존")
    for h,v in {215:"PLAYTEST",980:"END",1512:"END",1820:"WISHLIST ON STEAM!"}.items():
        mark([h], "TRANSLATE", v, "의미 있는 영문 표시 문구를 픽셀에서 직접 확인. 한국어 이미지가 필요")
    zooms = defaultdict(list)
    for item in json.loads((REVIEW / "zooms/index.json").read_text(encoding="utf-8")):
        zooms[item["handle"]].append({"path": "zooms/"+item["sheet"], "sha256": sha(REVIEW / "zooms" / item["sheet"]), "slot": item["slot"]})
    for h in [78,79,82,83,94,124,125,126,127,128,129,130,131,132,1040,474]:
        zooms[h].append({"path":"zooms/zoom_glyphs.png", "sha256":sha(REVIEW/"zooms/zoom_glyphs.png")})
    zooms[1019].append({"path":"zooms/alpha_1019.png", "sha256":sha(REVIEW/"zooms/alpha_1019.png"),"method":"투명 검정 테두리를 밝은 바탕에 합성하여 글자 유무를 직접 확인"})
    direct = {446,1490,1019,1969,1820}
    media_by_handle = {x["handle"]:x for x in media}
    records = []
    seen = set()
    for page, sheet in enumerate(index):
        assert sha(REVIEW / sheet["path"]) == sheet["sha256"]
        for cell in sheet["items"]:
            first = cell["handles"][0]
            decision, text, reason = overrides.get(first, ("NO_TEXT", "", "해당 칸의 원본 그림을 직접 판독했으며 번역할 자연어·숫자·입력 키 표기가 없음"))
            group_images = [media_by_handle[h] for h in cell["handles"]]
            # 데이터 지문뿐 아니라 실제 추출 PNG도 동일한지 확인 후 판독 공유를 허용합니다.
            assert len({x["sha256"] for x in group_images}) == 1
            for handle in cell["handles"]:
                assert handle not in seen
                seen.add(handle)
                m = media_by_handle[handle]
                assert sha(BASE/"nebula_01"/m["path"]) == m["sha256"]
                records.append({"id":f"THOG.dat/0x6666/image:{handle}","handle":handle,"source_dat_sha256":baseline,
                    "source_image_data_sha256":m["source_sha256"],"png_sha256":m["sha256"],"png_path":str((BASE/"nebula_01"/m["path"]).relative_to(ROOT)),
                    "width":m["Width"],"height":m["Height"],"classification":"MEDIA","media_action":decision,
                    "observed_text":text,"reason":reason,"review_status":"PASS","reviewer":"Codex / clickteam_format",
                    "review_date":"2026-10-31","method":"접촉판 각 칸 직접 육안 판독; 필요한 위치는 원본/확대 화면 추가 판독",
                    "sheet":sheet["path"],"sheet_sha256":sheet["sha256"],"slot":cell["slot"],"sheet_observation":observations[page],
                    "shared_review_handles":cell["handles"],"shared_review_basis":"이미지 데이터와 추출 PNG SHA-256 모두 같음",
                    "additional_evidence":zooms.get(first,[]),"original_direct_view":first in direct})
    assert seen == set(media_by_handle)
    with (REVIEW/"media_review.jsonl").open("w",encoding="utf-8",newline="\n") as f:
        for row in sorted(records,key=lambda x:x["handle"]):
            f.write(json.dumps(row,ensure_ascii=False)+"\n")
    candidates=[x for x in records if x["media_action"]=="TRANSLATE"]
    (REVIEW/"textual_image_candidates.json").write_text(json.dumps(candidates,ensure_ascii=False,indent=2),encoding="utf-8")
    counts=dict(Counter(x["media_action"] for x in records))
    summary={"status":"PASS","scope":"추출 이미지 전수 육안 판독·처리 분류; 이미지 수정과 실행 화면 검수는 별도",
        "source_dat_sha256":baseline,"images":len(records),"unique_review_images":sum(len(s['items']) for s in index),
        "sheets_directly_viewed":29,"actions":counts,"unknown":counts.get("UNKNOWN",0),"textual_candidate_handles":[x['handle'] for x in candidates],
        "modified_images":0,"image_rebuild_status":"NOT_RUN","runtime_verification_status":"NOT_RUN",
        "limitations":["그림 속 판타지 룬·해골·도구 표식은 자연어 문장이 아닌 그림 기호로 판독","모든 이미지의 실제 게임 노출 여부는 이 판정의 범위가 아님","음원·영상과 실행 파일 아이콘은 별도 목록 필요"]}
    (REVIEW/"visual_review_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))


if __name__=="__main__":
    main()
