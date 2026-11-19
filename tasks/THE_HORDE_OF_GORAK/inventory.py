"""원시 DAT 위치와 Nebula의 문맥을 연결하는 조사 목록 생성기."""
from __future__ import annotations

import collections
import json
import re
import struct
from pathlib import Path

from dat_container import DatFile, sha, u32, utf16z

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311/THOG.dat"
SEMANTIC = ROOT / "extracted_private/THE_HORDE_OF_GORAK/steam_26336311/nebula_03"
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/investigation_20261031/classification"
EXT_PATH = ROOT / "extracted_private/THE_HORDE_OF_GORAK/steam_26336311/media_review_01/extension_inventory.jsonl"
EXPRESSION_CODES = {15, 22, 23, 27, 28, 45, 46, 52, 53, 54, 59, 62}


def s16(data, offset):
    return struct.unpack_from("<h", data, offset)[0]


def u16(data, offset):
    return struct.unpack_from("<H", data, offset)[0]


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    if name.endswith(".jsonl"):
        path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in data), encoding="utf-8")
    else:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def event_operations(data):
    """296의 원래 이벤트 크기·매개변수 경계를 직접 읽는다."""
    cursor = 0
    events = []
    while cursor < len(data):
        marker = data[cursor:cursor + 4]
        cursor += 4
        if marker in (b"ER>>", b"KR>>"):
            count = u16(data, cursor + 40)
            cursor += 42 + count * 4
        elif marker in (b"ERes", b"ERop"):
            cursor += 4
        elif marker == b"<<ER":
            if cursor != len(data):
                raise ValueError("이벤트 끝의 잔여 자료")
            break
        elif marker == b"ERev":
            end = cursor + 4 + u32(data, cursor)
            cursor += 4
            while cursor < end:
                start = cursor
                size = abs(s16(data, cursor))
                if size < 8:
                    raise ValueError("이벤트 길이 오류")
                counts = data[cursor + 2:cursor + 4]
                event = {"index": len(events), "offset": cursor, "size": size, "flags": u16(data, cursor + 4), "Conditions": [], "Actions": []}
                cursor += 8
                for kind, count in zip(("Conditions", "Actions"), counts):
                    for index in range(count):
                        op_start = cursor
                        op_size = abs(s16(data, cursor))
                        typ, num = struct.unpack_from("<hh", data, cursor + 2)
                        cursor += 6
                        handle = 0
                        if typ == -7 or typ >= 0:
                            handle = u16(data, cursor)
                            cursor += 2
                        flags, param_count = data[cursor:cursor + 2]
                        cursor += 2
                        op = {"kind": kind, "index": index, "offset": op_start, "size": op_size,
                              "type": typ, "num": num, "handle": handle, "flags": flags, "parameters": []}
                        for pindex in range(param_count):
                            pstart = cursor
                            psize = abs(s16(data, cursor))
                            code = s16(data, cursor + 2)
                            if psize < 4 or pstart + psize > op_start + op_size:
                                raise ValueError("매개변수 크기 오류")
                            parameter = {"index": pindex, "offset": pstart, "size": psize, "code": code, "strings": [], "expressions": []}
                            if code in EXPRESSION_CODES:
                                position = pstart + 6
                                while position + 4 <= pstart + psize:
                                    expr_type, expr_num = struct.unpack_from("<hh", data, position)
                                    if expr_type == expr_num == 0:
                                        break
                                    expr_size = u16(data, position + 4)
                                    if expr_size < 6 or position + expr_size > pstart + psize:
                                        raise ValueError("표현식 크기 오류")
                                    expression = {"index": len(parameter["expressions"]), "offset": position, "size": expr_size, "type": expr_type, "num": expr_num}
                                    if expr_type == -1 and expr_num in (0, 3):
                                        if expr_num == 0:
                                            expression["value"] = struct.unpack_from("<i", data, position + 6)[0]
                                        else:
                                            value, last = utf16z(data, position + 6)
                                            if last > position + expr_size:
                                                raise ValueError("표현식 문자열 종료 위치 오류")
                                            expression["value"] = value
                                            parameter["strings"].append({"offset": position + 6, "value": value, "slot_bytes": expr_size - 6, "field": f"expression:{expression['index']}", "expression_index": expression["index"]})
                                    elif expr_type > 1 or expr_type == -7:
                                        expression["handle"] = u16(data, position + 6)
                                    parameter["expressions"].append(expression)
                                    position += expr_size
                            elif code in (40, 41, 63, 64):
                                value, last = utf16z(data, pstart + 4)
                                parameter["strings"].append({"offset": pstart + 4, "value": value, "slot_bytes": psize - 4, "field": "string"})
                            elif code == 38 and psize >= 12:
                                value, last = utf16z(data, pstart + 8)
                                parameter["strings"].append({"offset": pstart + 8, "value": value, "slot_bytes": min(158, psize - 8), "field": "group_name"})
                            op["parameters"].append(parameter)
                            cursor = pstart + psize
                        if cursor > op_start + op_size:
                            raise ValueError("이벤트 명령 경계 초과")
                        op["inline_bytes"] = op_start + op_size - cursor
                        cursor = op_start + op_size
                        event[kind].append(op)
                if cursor > start + size:
                    raise ValueError("이벤트 경계 초과")
                cursor = start + size
                events.append(event)
            if cursor != end:
                raise ValueError("이벤트 목록 크기 불일치")
        else:
            raise ValueError(f"알 수 없는 이벤트 구간: {marker!r}@{cursor - 4}")
    return events


def all_values(value):
    if isinstance(value, dict):
        if value.get("ChunkName") in ("ExpressionString", "ParameterString"):
            yield value.get("Value", "")
        for child in value.values():
            yield from all_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from all_values(child)


def base_record(kind, location, text, data_hash):
    return {"kind": kind, "location": location, "source": text, "source_text_sha256": sha(text.encode("utf-16le")),
            "source_container_sha256": data_hash, "classification": "UNKNOWN", "reason": None}


def apply_native_findings(records, dat, source_digest):
    """독립 REA 조사 결과를 원본·위치·해시가 일치할 때만 연결한다."""
    investigation = OUT.parent
    findings_path = investigation / "native_extra_findings.json"
    controls_path = investigation / "player_controls_225d.json"
    findings = load(findings_path)
    controls = load(controls_path)
    if findings["source_file_sha256"] != source_digest or controls["evidence"]["status"] != "PASS":
        raise ValueError("추가 역분석 근거의 원본 또는 상태 불일치")
    by_location = {row["location"]: row for row in records}
    evidence_paths = set()
    for resolution in findings["unknown_resolutions"]:
        row = by_location[resolution["location"]]
        for key in ("source", "source_text_sha256", "source_container_sha256"):
            if row[key] != resolution[key]:
                raise ValueError(f"추가 분류 근거 불일치: {row['location']}/{key}")
        row.update({key: resolution[key] for key in ("classification", "reason", "native_locations", "evidence")})
        evidence_paths.update(resolution["evidence"])
    for field in controls["strings"]:
        chunk = dat.by_location[field["target"]]
        source, end = utf16z(chunk.decoded, field["offset"])
        if (source != field["source"] or end - field["offset"] != field["slot_bytes"]
                or sha(chunk.decoded) != field["source_container_sha256"]
                or sha(source.encode("utf-16le")) != field["source_text_sha256"]
                or field["source_file_sha256"] != source_digest):
            raise ValueError("키 설정 대화상자 문자열 위치·원본 불일치")
        row = base_record(field["kind"], f"player_controls/{field['kind']}@{field['offset']}", source, sha(chunk.decoded))
        row.update({key: value for key, value in field.items() if key != "kind"})
        row.update(evidence_path=str(controls_path), evidence=controls["evidence"],
                   patch_strategy="순차 UTF16z 및 DWORD 정렬 구조. 원래와 같은 코드 단위 수 또는 구조 전용 재조립 필요")
        if row["classification"] == "INTERNAL":
            row["reason"] = "Windows 대화상자 템플릿의 메뉴·클래스·글꼴 식별자 필드. 표시 제목과 별도 구조"
        elif not source or source == "..." or source.isdecimal():
            row.update(classification="VISIBLE_KEEP", reason="대화상자 표시 필드의 빈 초기값·순수 말줄임 부호·숫자 플레이어 번호. 원문을 보존하고 실행 중 설정값은 별도 추적")
        else:
            row["reason"] = "키 이름 표 또는 Windows 대화상자의 표시 문구. 실행기의 DialogBoxIndirectParamW 소비와 원시 템플릿 구조 확인"
        records.append(row)
    for row in findings["extra_chunks"]:
        chunk = dat.by_location[row["target"]]
        if sha(chunk.decoded) != row["decoded_sha256"] or sha(chunk.raw) != row["raw_sha256"]:
            raise ValueError("추가 청크 분류의 원본 해시 불일치")
        evidence_paths.update(row["evidence"])
    evidence_paths.add("thog_dialog_dispatch_disasm.json")
    save("extra_chunk_classification.json", findings["extra_chunks"])
    return {"findings_path": str(findings_path), "findings_sha256": sha(findings_path.read_bytes()),
            "controls_path": str(controls_path), "controls_sha256": sha(controls_path.read_bytes()),
            "native_evidence": [{"path": str(investigation / name), "sha256": sha((investigation / name).read_bytes())}
                                for name in sorted(evidence_paths)]}


def classify_event(row):
    """확인한 소비 명령만 판정한다. 새 명령은 UNKNOWN을 유지한다."""
    typ, num = row["operation_type"], row["operation_number"]
    index = row["expression_index"]
    expressions = row["expressions"]
    if index is not None and index > 0:
        previous = expressions[index - 1]
        if (previous["type"], previous["num"], previous.get("handle")) in {(35, 82, 54), (35, 82, 215)}:
            row.update(classification="INTERNAL", reason="kcini 숫자 읽기 표현식82의 키 인수. 바로 앞 호출·객체54/215 및 숫자 소비 명령에 연결됨")
            return
    if row["operation_kind"] == "Actions":
        if typ == 35 and num == 86 and row["parameter_index"] == 0:
            row.update(classification="INTERNAL", reason="kcini 파일 선택 명령86의 저장 파일명 인수. 실제 파일 경로이므로 번역하지 않음")
        elif typ == 35 and num in (87, 91) and row["parameter_index"] == 0:
            row.update(classification="INTERNAL", reason=f"kcini 저장 명령{num}의 키 이름 인수. 숫자 쓰기/항목 삭제가 소비하는 저장 형식 식별자")
        elif typ == 37 and num == 102 and row["parameter_index"] == 0:
            row.update(classification="INTERNAL", reason="Steamworks 명령102의 업적 ID 인수. 화면 표시 이름과 별개의 서비스 식별자")
        elif typ == 32 and num == 135 and row["parameter_index"] == 0:
            row.update(classification="VISIBLE_TRANSLATE", reason="KcBoxA 명령135가 화면 버튼의 ON/OFF 문구를 변경함. 버튼54가 아닌 screen/vsync 버튼40/41에 연결")


def image_references(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            here = f"{path}.{key}" if path else key
            if key == "Image" and isinstance(child, int) and (child or value.get("ChunkName") == "ObjectBackdrop"):
                yield here, child
            elif key == "Frames" and isinstance(child, list) and any(owner in path for owner in ("ObjectAnimations", "ObjectCounter")):
                for index, handle in enumerate(child):
                    if isinstance(handle, int):
                        yield f"{here}.{index}", handle
            else:
                yield from image_references(child, here)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from image_references(child, f"{path}.{index}")


def main():
    dat = DatFile.load(SOURCE)
    source_digest = sha(dat.original)
    package = load(SEMANTIC / "package.json")
    objects = package["FrameItems"]["Items"]
    records = []
    frame_use = collections.defaultdict(list)
    for fidx, frame in enumerate(package["Frames"]):
        for inst in frame["FrameInstances"]["Instances"]:
            frame_use[inst["ObjectInfo"]].append({"frame": fidx, "name": frame["FrameName"], "x": inst["PositionX"], "y": inst["PositionY"]})

    for block in dat.objects:
        obj = objects[str(block.index)]
        value = block.decoded
        paragraphs = obj["Properties"].get("ObjectParagraphs", {}).get("Paragraphs", [])
        if paragraphs:
            start = u16(value, 36)
            width, height, count = struct.unpack_from("<iii", value, start + 4)
            if count != len(paragraphs):
                raise ValueError("Nebula와 문단 수 불일치")
            for pidx, paragraph in enumerate(paragraphs):
                offset = start + u32(value, start + 16 + pidx * 4) + 8
                text, end = utf16z(value, offset)
                if text != paragraph["Value"]:
                    raise ValueError("Nebula와 문단 원문 불일치")
                row = base_record("paragraph", f"object:{block.index}/paragraph:{pidx}", text, sha(value))
                row.update({"target": f"object:{block.index}", "offset": offset, "slot_bytes": end - offset,
                            "semantic_path": f"FrameItems.Items.{block.index}.Properties.ObjectParagraphs.Paragraphs.{pidx}.Value",
                            "object_name": obj["Name"], "object_handle": block.index, "font": paragraph["FontHandle"],
                            "width": width, "height": height, "frame_instances": frame_use[block.index],
                            "classification": "VISIBLE_TRANSLATE", "reason": "TEXT/QS 문단 표시 필드이며 실제 프레임 인스턴스·문단 전환이 사용하는 원문"})
                if re.fullmatch(r"[\d\s:/.,%?+\-]+", text) or re.fullmatch(r"v\d+(?:\.\d+)+", text):
                    row.update(classification="VISIBLE_KEEP", reason="숫자·구분기호·숨김 표시 또는 버전 번호만으로 이루어진 표시 필드. 수치와 기호를 보존")
                records.append(row)

    raw_frames = []
    semantic_mismatches = []
    frame_chunks = [c for c in dat.chunks if c.chunk_id == 0x3333]
    for fidx, chunk in enumerate(frame_chunks):
        ev_chunk = next(c for c in chunk.children if c.chunk_id == 0x333D)
        raw_events = event_operations(ev_chunk.decoded)
        raw_frames.append({"frame": fidx, "chunk": ev_chunk.location, "events": raw_events})
        readable = load(SEMANTIC / "frames" / f"{fidx:02d}.json")
        rendered = collections.defaultdict(list)
        for item in readable:
            rendered[(item["ev"], item["kind"])].append(item)
        semantic_events = package["Frames"][fidx]["FrameEvents"]["Events"]
        if len(semantic_events) != len(raw_events):
            raise ValueError("Nebula와 이벤트 개수 불일치")
        for event in raw_events:
            for kind in ("Conditions", "Actions"):
                for op in event[kind]:
                    for parameter in op["parameters"]:
                        for leaf in parameter["strings"]:
                            row = base_record("event_string", f"frame:{fidx}/event:{event['index']}/{kind}:{op['index']}/param:{parameter['index']}/{leaf['field']}", leaf["value"], sha(ev_chunk.decoded))
                            matching = [r for r in rendered[(event["index"], kind)] if r["ObjectType"] == op["type"] and r["ObjectInfo"] == op["handle"] and leaf["value"] in list(all_values(r["parameters"]))]
                            row.update({"frame": fidx, "frame_name": package["Frames"][fidx]["FrameName"], "event": event["index"], "operation_kind": kind,
                                        "operation_type": op["type"], "operation_number": op["num"], "object_handle": op["handle"],
                                        "object_name": objects.get(str(op["handle"]), {}).get("Name") if op["type"] >= 0 else None,
                                        "parameter_code": parameter["code"], "parameter_index": parameter["index"],
                                        "target": ev_chunk.location, "offset": leaf["offset"], "slot_bytes": leaf["slot_bytes"],
                                        "expressions": parameter["expressions"], "expression_index": leaf.get("expression_index"),
                                        "readable_context": [r["display"] for r in matching],
                                        "semantic_operation_indices": [r["index"] for r in matching]})
                            if not matching and leaf["field"] != "group_name":
                                semantic_mismatches.append(row["location"])
                            if leaf["field"] == "group_name":
                                row.update(classification="INTERNAL", reason="이벤트 실행 그룹 식별 필드: ParameterGroup; 296 실행은 숫자 그룹 ID를 사용")
                            else:
                                classify_event(row)
                            records.append(row)

    # ObjectNames는 실행 객체 핸들에 대응하는 메타데이터이며 표시 문단과 분리되어 있다.
    name_chunk = dat.one(0x2254)
    name_offset = 0
    for index, obj in objects.items():
        text, last = utf16z(name_chunk.decoded, name_offset)
        if text != obj["Name"]:
            raise ValueError("객체 이름 순서·원문 불일치")
        row = base_record("object_name", f"object:{index}/name", text, sha(name_chunk.decoded))
        row.update(target=name_chunk.location, offset=name_offset, slot_bytes=last - name_offset,
                   object_handle=int(index), semantic_path=f"FrameItems.Items.{index}.Name",
                   frame_instances=frame_use[int(index)], classification="INTERNAL",
                   reason="ObjectNames 메타데이터. ObjectHeaders.Handle 순서로 연결되며 이벤트는 숫자 핸들로 참조; 별도 TEXT 문단·버튼 표시 필드와 구분")
        records.append(row)
        name_offset = last
    if name_offset != len(name_chunk.decoded):
        raise ValueError("객체 이름 청크 잔여 데이터")

    for fidx, chunk in enumerate(frame_chunks):
        name = next(c for c in chunk.children if c.chunk_id == 0x3335)
        text, end = utf16z(name.decoded)
        row = base_record("frame_name", f"frame:{fidx}/name", text, sha(name.decoded))
        row.update(target=name.location, offset=0, slot_bytes=end, classification="INTERNAL",
                   reason="FrameName 장면 식별 메타데이터. 이동은 숫자 프레임 인덱스·핸들로 수행하며 표시 문단은 별도 객체에 있음")
        records.append(row)
    for block in dat.fonts:
        text, end = utf16z(block.decoded, 40)
        row = base_record("font_name", f"font:{block.handle}/name", text, sha(block.decoded))
        row.update(target=f"font:{block.handle}", offset=40, slot_bytes=64, classification="INTERNAL",
                   reason="LOGFONTW 글꼴 선택 식별자. 번역할 화면 문구가 아니라 한글 글꼴 연결 검사 대상")
        records.append(row)

    ext_path = EXT_PATH
    for ext in (json.loads(line) for line in ext_path.read_text(encoding="utf-8").splitlines()):
        row = base_record(ext["kind"], ext["id"], ext["source"], ext["object_decoded_sha256"])
        row.update(target=f"object:{ext['object_handle']}", offset=ext["object_offset"], slot_bytes=ext["slot_bytes"],
                   object_handle=ext["object_handle"], object_name=ext["object_name"], frame_instances=frame_use[ext["object_handle"]],
                   blob_sha256=ext["blob_sha256"], evidence_path=str(ext_path))
        if ext["kind"] == "button_text":
            row.update(classification="VISIBLE_TRANSLATE", reason="KcBoxA 버튼 문자열 슬롯. 길이 필드208·UTF16z212·후속8바이트 경계 전81개 일치; native 및 실제 표시와 교차 확인 대상")
        elif ext["kind"] == "button_font":
            row.update(classification="INTERNAL", reason="KcBoxA LOGFONTW 글꼴명 32 UTF-16 슬롯. 글꼴 로딩 식별자이며 한글 글꼴 변경 대상으로 추적")
        elif ext["kind"] == "ini_default_path":
            row.update(classification="INTERNAL", reason="kcini 객체의 파일명 초기값. 이벤트 파일명 설정 명령86 및 저장 키 읽기·쓰기와 연결")
        records.append(row)

    for ident, label, category, reason in [
        (0x2224, "app_title", "VISIBLE_KEEP", "원본 게임 고유 제목이며 암호 키 생성 입력. 게임 제목은 유지"),
        (0x222E, "editor_filename", "INTERNAL", "편집 원본 파일 경로 메타데이터이며 실제 암호 키 생성 입력임을 dat_container.Cipher 해제로 확인"),
        (0x222F, "target_filename", "INTERNAL", "빌드 출력 파일명 메타데이터. UI 문단·메뉴 문자열과 별도 형식 필드"),
        (0x223A, "about", "UNKNOWN", "숫자열이지만 About 필드에 저장됨. 화면 표시/내부 식별용 여부 추가 확인 필요"),
    ]:
        chunk = dat.one(ident)
        text, end = utf16z(chunk.decoded)
        row = base_record(label, f"app/{label}", text, sha(chunk.decoded))
        row.update(target=chunk.location, offset=0, slot_bytes=end, classification=category, reason=reason)
        records.append(row)

    menu = dat.one(0x2226)
    menu_start = u32(menu.decoded, 4) + 4
    def read_menu(position, parent=""):
        index = 0
        while True:
            flags = u16(menu.decoded, position)
            position += 2
            command = None
            if not flags & 16:
                command = u16(menu.decoded, position)
                position += 2
            offset = position
            text, position = utf16z(menu.decoded, position)
            path = f"{parent}/{index}"
            row = base_record("menu_text", f"menu{path}", text, sha(menu.decoded))
            row.update(target=menu.location, offset=offset, slot_bytes=position - offset, command_id=command,
                       flags=flags, classification="VISIBLE_TRANSLATE", reason="Windows 메뉴 표시 문자열. 단축키 & 및 탭 뒤 키 조합 보존",
                       patch_strategy="순차 UTF16z 구조이므로 짧은 번역의 NUL 여백 금지. 메뉴 재조립 또는 동일 문자수 유지 필요")
            records.append(row)
            if flags & 16:
                position = read_menu(position, path)
            index += 1
            if flags & 128:
                return position
    menu_end = read_menu(menu_start)
    if menu_end != u32(menu.decoded, 4) + u32(menu.decoded, 8):
        raise ValueError("메뉴 문구 경계 불일치")
    native_evidence = apply_native_findings(records, dat, source_digest)

    resolutions = []
    for frame in raw_frames:
        chunk = dat.by_location[frame["chunk"]]
        for event in frame["events"]:
            for kind in ("Conditions", "Actions"):
                for op in event[kind]:
                    if op["type"] != -1:
                        continue
                    contract = None
                    if (kind, op["num"]) in {("Actions", 0), ("Conditions", -11)} and op["size"] == 8 and not op["parameters"] and not op["inline_bytes"]:
                        contract = "명령 헤더8바이트뿐이며 매개변수·추가 자료가 없다. 원본 표시 문자열 저장 공간이 없음"
                    elif kind == "Conditions" and op["num"] == -10 and op["size"] == 18 and len(op["parameters"]) == 1 and op["parameters"][0]["code"] == 38 and op["parameters"][0]["size"] == 10:
                        contract = "296 그룹 시작의 압축 파라미터38: 헤더4+제어값6바이트. 기존79자 그룹명 슬롯은 존재하지 않음"
                    elif kind == "Actions" and op["num"] in (6, 7) and op["size"] == 10 and not op["parameters"] and op["inline_bytes"] == 2:
                        contract = "그룹 활성/비활성 명령: 헤더8+숫자 그룹ID2바이트. Action.Fix의 GroupParameter296Fix와 연결"
                    if contract:
                        raw = chunk.decoded[op["offset"]:op["offset"] + op["size"]]
                        resolutions.append({"frame": frame["frame"], "event": event["index"], "kind": kind, "index": op["index"],
                                            "type": op["type"], "num": op["num"], "target": frame["chunk"], "offset": op["offset"],
                                            "size": op["size"], "sha256": sha(raw), "raw_hex": raw.hex(), "classification": "INTERNAL",
                                            "reason": contract, "scope": "표시 문자열 추출 누락 여부만 해소; 모든 게임 제어 동작의 역분석 완료를 뜻하지 않음"})
    save("description_error_resolution.jsonl", resolutions)

    image_links = []
    font_links = []
    for handle, obj in objects.items():
        for path, image in image_references(obj["Properties"]):
            image_links.append({"object_handle": int(handle), "object_name": obj["Name"], "field": path,
                                "image_handle": image, "frames": frame_use[int(handle)], "object_sha256": sha(dat.objects[int(handle)].decoded)})
        props = obj["Properties"]
        for index, paragraph in enumerate(props.get("ObjectParagraphs", {}).get("Paragraphs", [])):
            font_links.append({"object_handle": int(handle), "field": f"ObjectParagraphs.Paragraphs.{index}.FontHandle", "font_handle": paragraph["FontHandle"], "frames": frame_use[int(handle)]})
        counter = props.get("ObjectCounter", {})
        if counter.get("DisplayType") == 5:
            font_links.append({"object_handle": int(handle), "field": "ObjectCounter.Font", "font_handle": counter["Font"], "frames": frame_use[int(handle)]})
    save("image_usage.jsonl", image_links)
    save("font_usage.jsonl", font_links)
    language_refs = []
    for path in sorted((SEMANTIC / "frames").glob("*.json")):
        for row in load(path):
            if "Global Value L" in row["display"]:
                language_refs.append({key: row[key] for key in ("frame", "ev", "kind", "index", "display")})
    save("language_analysis.json", {"references": language_refs, "observed_languages": ["English"],
         "default_language_value": 0, "conclusion": "영어 표시 필드만 확인. lang 저장값은 Global Value L에 읽어 두지만 전환·번역 분기 참조는 조사한20프레임에 없음. 영어를 한국어로 직접 치환하고 메뉴 ENGLISH 표시를 한국어로 바꾸는 방식이 적합",
         "limit": "새 언어 전환 기능이 구현되었다고 주장하지 않음", "evidence": "20프레임 모든 명령·618 원시 문자열·770 문단과 source SHA에 연결"})
    save("raw_frames.json", raw_frames)
    for record in records:
        record["source_file_sha256"] = source_digest
    save("inventory.jsonl", records)
    worklist = collections.defaultdict(list)
    for record in records:
        if record["classification"] == "VISIBLE_TRANSLATE":
            worklist[record["source"]].append({key: record[key] for key in ("location", "kind", "target", "offset", "slot_bytes")})
    save("translation_worklist.json", [{"source": source, "occurrences": occurrences, "translation": None,
                                        "note": "동일 원문을 묶은 조사 편의 자료이며 번역 시 각 위치 문맥을 확인"}
                                       for source, occurrences in worklist.items()])
    summary = {"source_sha256": source_digest, "semantic_sha256": sha((SEMANTIC / "package.json").read_bytes()),
               "semantic_directory": str(SEMANTIC), "records": len(records), "by_kind": dict(collections.Counter(r["kind"] for r in records)),
               "classification": dict(collections.Counter(r["classification"] for r in records)), "semantic_mismatches": semantic_mismatches,
               "description_errors_resolved_nontext": len(resolutions), "image_usage_links": len(image_links),
               "native_evidence": native_evidence,
               "tool_sha256": sha(Path(__file__).read_bytes()), "container_tool_sha256": sha((Path(__file__).parent / "dat_container.py").read_bytes())}
    save("summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
