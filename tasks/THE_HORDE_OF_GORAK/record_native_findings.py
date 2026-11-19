"""네이티브 확인 결과를 원본 해시와 소규모 근거 파일에 연결합니다."""
from pathlib import Path
import json
import struct
from dat_container import DatFile, sha, utf16z

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/investigation_20261031"
SOURCE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311"


def checksum(data):
    result = 0
    aligned = len(data) // 4 * 4
    for offset in range(0, aligned, 4):
        value = struct.unpack_from("<I", data, offset)[0]
        result = (((result << 1) | (result >> 31)) + value) & 0xffffffff
    for value in data[aligned:]:
        result = (((result << 1) | (result >> 31)) + value) & 0xffffffff
    return result


def main():
    dat = DatFile.load(SOURCE / "THOG.dat")
    start = 48 + dat.one(0x222f).offset
    end = 48 + dat.one(0x2242).offset
    calculated = checksum(dat.original[start:end])
    stored = struct.unpack("<I", dat.one(0x2242).decoded)[0]
    assert calculated == stored ^ 0x0d
    result = {
        "game_id": "THE_HORDE_OF_GORAK", "build_id": "steam_26336311",
        "source_file_sha256": sha(dat.original),
        "native_source_sha256": {n: sha((SOURCE / n).read_bytes()) for n in ["THOG.exe", "Modules/mmfs2.dll", "Modules/KcBoxA.mfx", "Modules/Layer.mfx", "Modules/AdvDir.mfx"]},
        "authority": "원본 PE와 DAT의 정적 판독 및 독립 계산. REA 내보내기 Evidence와 Capstone 판독을 구분함",
        "checksum_2242": {
            "status": "PASS", "start_inclusive": start, "end_exclusive": end,
            "range_sha256": sha(dat.original[start:end]), "calculated": hex(calculated), "stored": hex(stored),
            "algorithm": "초깃값0. 222F 헤더부터 2242 헤더 전까지 LE32 단위로 ROL32(sum,1)+value mod2^32, 마지막1~3바이트는 각 byte로 같은 연산. 기록값=sum XOR 0x0d",
            "native_locations": ["THOG RVA0x241a:222F에서 시작위치 저장", "RVA0x25c8:2242 처리", "RVA0x26b7:dword 누적", "RVA0x26e1:잔여byte 누적", "RVA0x2740:비교", "RVA0x2752:불일치 시 창생성 생략"],
            "evidence": "thog_target_checksum_disasm.json",
            "scope": "무결성 필드의 정상 재계산이며 검증 분기나 권한 확인을 제거하지 않음"},
        "window_creation": {
            "status": "PASS", "crash": "THOG RVA0x5a259는 global(base+0x9e5b8)+0x6a의 너비를 읽음. NULL이면0x6a 접근 예외",
            "call": "THOG RVA0x3824 -> MMFS2 ordinal1080 RVA0x18d70(context,createParams), stdcall ret8",
            "return_contract": {"0": "할당 실패", "1": "context NULL", "2": "CreateWindowEx 실패", ">32": "성공 객체 포인터"},
            "params": {"0x00": "size=0x4c", "0x08": "HINSTANCE", "0x0c": "menu", "0x10": "parent HWND", "0x14": "height", "0x18": "width", "0x1c": "y", "0x20": "x", "0x24": "style", "0x28": "title UTF16", "0x2c": "class UTF16", "0x30": "exStyle", "0x44": "type=2", "0x48": "flags=0 또는0x200"},
            "skip_condition": "THOG RVA0x3614: local[ebp-0x274]은 진입 시 stack 인수에서 받은 부모 앱 포인터. 비NULL 또는 byte[ebp-0x275] 비0이면 생성 생략",
            "evidence": ["thog_surface_params_disasm.json", "mmfs_surface_create_disasm.json", "mmfs_surface_impl_disasm.json", "thog_create_skip_disasm.json", "thog_crash_5a259_disasm.json"],
            "limitation": "실제 실행의 원인 확정은 부모의 별도 REA 관측 및 합계수정 후보 실행 결과에 연결해야 함"},
        "unknown_resolutions": [], "extra_chunks": []}
    inventory = [json.loads(line) for line in (OUT / "classification/inventory.jsonl").read_text(encoding="utf-8").splitlines()]
    for row in inventory:
        if row["location"] not in {"object:40/extension/utf16_candidate@0", "object:41/extension/utf16_candidate@0", "object:71/extension/utf16_candidate@4", "object:480/extension/utf16_candidate@4", "app/about"}:
            continue
        info = {k: row[k] for k in ("location", "source", "source_file_sha256", "source_container_sha256", "source_text_sha256")}
        if row["location"] == "app/about":
            info.update(classification="VISIBLE_KEEP", reason="원문72자리 숫자열. 3자리씩 바이트로 읽으면 PACKED 이진 표식이나, 엔진은223A를 app+0x90에 저장하고 About control105에 그대로 표시하므로 내부문구로 제외하지 않음",
                        native_locations=["THOG RVA0x224e", "THOG RVA0x5b24d~0x5b25b SetDlgItemTextW"], evidence=["thog_about_dialog_disasm.json", "thog_chunk_handlers_disasm.json"])
        elif row["object_handle"] in (40, 41):
            info.update(classification="INTERNAL", reason="UTF16 후보 '@ '의 실제4바이트는 int16 너비64·높이32. CreateRunObject가 editData+0x14/+0x16을 runtime+0x60/+0x64에 숫자로 복사하고 GetObjectRect가 RECT.right/bottom 산술에 사용함",
                        native_locations=["KcBoxA RVA0x2590~0x259b", "KcBoxA RVA0x5f29~0x5f3e"], evidence=["extension_create_disasm.json", "extension_rect_disasm.json", "extension_exports_evidence.json"])
        else:
            plugin = "Layer" if row["object_handle"] == 71 else "AdvDir"
            info.update(classification="INTERNAL", reason=f"{plugin}의 편집 구조 내 int16쌍32·32이며 표시문자열 소비 없음. Layer CreateRunObject는 editData 인수를 읽지 않고 runtime 필드만 복사하며, AdvDir는 editData+0x1c의 별도 ASCII숫자360부터 읽음. 해당4바이트는 읽지 않음. 두 모듈 DisplayRunObject/GetObjectRect도 즉시 반환하는 함수",
                        native_locations=["Layer RVA0x6200~0x6217", "Layer RVA0x6150/0x6180", "AdvDir RVA0x1e50~0x1eb9", "AdvDir RVA0x1f00/0x1de0"], evidence=["extension_create_disasm.json", "extension_rect_disasm.json", "extension_exports_evidence.json"])
        result["unknown_resolutions"].append(info)
    chunk_info = {
        0x2251: ("INTERNAL", "4바이트 언어 ID=0. THOG RVA0x2089에서 app+0x3e8에4바이트읽고 GetLocaleInfoW에숫자ID로전달"),
        0x225c: ("INTERNAL", "16바이트 모두0. THOG RVA0x1fb6은 청크 존재 플래그만1로설정하고내용을건너뜀"),
        0x224d: ("INTERNAL", "8바이트 정수[0,3]. THOG RVA0x305c가 app+0x3d8/+0x3dc에각4바이트를읽음. 텍스트필드없음"),
        0x223e: ("INTERNAL", "운동 확장 모듈 목록1개 Box2DBouncingBall.mvx. 원본 Modules에 같은 파일존재, 런타임 모듈 로딩 이름이며 번역대상이아님"),
        0x225d: ("VISIBLE_TRANSLATE", "문자열표22개와Windows대화상자4개·컨트롤38개. 실제DialogBoxIndirectParamW 소비를확인. player_controls_225d.json의75개문자열필드로세부분류")}
    for ident, (classification, reason) in chunk_info.items():
        chunk = dat.one(ident)
        result["extra_chunks"].append({"id": hex(ident), "target": chunk.location, "decoded_size": len(chunk.decoded), "decoded_sha256": sha(chunk.decoded), "raw_sha256": sha(chunk.raw), "classification": classification, "reason": reason, "evidence": ["thog_chunk_handlers_disasm.json", "thog_chunk_switch_disasm.json"]})
    (OUT / "native_extra_findings.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"checksum_original": "PASS", "unknown_resolutions": len(result["unknown_resolutions"]), "extra_chunks": len(result["extra_chunks"])}))


if __name__ == "__main__":
    main()
