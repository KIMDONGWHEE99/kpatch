"""원본 메뉴·대화상자를 짧거나 긴 문구로 재조립하고 별도 해석기로 대조합니다."""
import copy
import json
import struct
from pathlib import Path

from dat_container import DatFile, sha, utf16z, u32
from extra_chunk_review import parse_player_controls
from resource_builder import MenuResource, PlayerControlsResource, patch_resources

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311/THOG.dat"
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/resource_tests/structure_01"


def independent_menu(data):
    """제작기 객체를 사용하지 않고 Windows 메뉴를 순차 해석합니다."""
    rows = []
    def descend(position, path="menu"):
        index = 0
        while True:
            flags = struct.unpack_from("<H", data, position)[0]
            position += 2
            ident = None
            if not flags & 16:
                ident = struct.unpack_from("<H", data, position)[0]
                position += 2
            key = f"{path}/{index}"
            text, position = utf16z(data, position)
            rows.append((key, flags, ident, text))
            if flags & 16:
                position = descend(position, key)
            if flags & 128:
                return position
            index += 1
    end = descend(u32(data, 4) + 4)
    assert end == u32(data, 4) + u32(data, 8) == u32(data, 12)
    return rows, data[u32(data, 12):]


def logical_controls(parsed):
    result = {}
    for row in parsed["strings"]:
        if row["kind"] == "control_key_name":
            key = f"key:{row['id']}"
        else:
            suffix = row["kind"].removeprefix("dialog_").removeprefix("item_")
            key = f"dialog:{row['dialog_id']}/"
            if "item_index" in row:
                key += f"item:{row['item_index']}/"
            key += suffix
        result[key] = row["source"]
    return result


def geometry(parsed):
    result = copy.deepcopy(parsed["dialogs"])
    for dialog in result:
        for name in ("offset", "size", "title", "font"):
            dialog.pop(name)
        for item in dialog["controls"]:
            for name in ("offset", "title"):
                item.pop(name)
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    checks, candidates = [], []
    def check(name, success):
        assert success, name
        checks.append({"id": name, "status": "PASS"})

    baseline = DatFile.load(SOURCE)
    menu, controls = baseline.one(0x2226), baseline.one(0x225D)
    check("menu_original_exact_roundtrip", MenuResource(menu.decoded).build({}) == menu.decoded)
    check("controls_original_exact_roundtrip", PlayerControlsResource(controls.decoded).build({}) == controls.decoded)
    original_controls = parse_player_controls(controls.decoded)
    original_values = logical_controls(original_controls)
    saved = json.loads((ROOT / "working_private/THE_HORDE_OF_GORAK/investigation_20261031/player_controls_225d.json").read_text(encoding="utf-8"))
    check("baseline_75_fields_match_retained_independent_extraction", logical_controls(saved) == original_values and len(original_values) == 75)
    for case in ("short", "long"):
        text_map = {
            "menu/0": "&파일" if case == "short" else "&파일 및 게임 창 관리 시험",
            "menu/0/0": "&끝\tAlt+F4" if case == "short" else "&게임을 종료하고 바탕 화면으로 돌아가기\tAlt+F4",
            "menu/0/1": "&화면\tAlt+Enter" if case == "short" else "&전체 화면과 창 모드 사이 전환하기\tAlt+Enter",
            "key:100": "연결 없음" if case == "short" else "조이스틱이 연결되어 있지 않거나 필요한 장치 드라이버가 설치되어 있지 않습니다. 장치 연결 상태와 드라이버 설치 상태를 확인해 주세요.",
            "key:101": "%d (숫자 키)" if case == "short" else "%d (키보드 오른쪽의 숫자 키패드)",
            "dialog:110/title": "정보" if case == "short" else "게임 프로그램에 대한 자세한 정보 시험",
            "dialog:113/item:18/title": "키 입력" if case == "short" else "지정할 키를 누르세요. 취소하려면 키보드의 ESC 키를 눌러 이전 화면으로 돌아가세요.",
        }
        text_map.update({f"dialog:{ident}/font": "THOG Noto Sans KR" for ident in (110, 111, 112, 113)})
        plan = []
        for chunk, resource in ((menu, MenuResource(menu.decoded)), (controls, PlayerControlsResource(controls.decoded))):
            for field in resource.fields:
                if field.key in text_map:
                    plan.append({"target": chunk.location, "offset": field.offset, "source": field.value,
                                 "translated": text_map[field.key], "source_container_sha256": sha(chunk.decoded)})
        dat = DatFile(baseline.original)
        manifest = patch_resources(dat, plan)
        output = dat.serialize()
        reread = DatFile(output)
        check(case + "_dat_roundtrip", reread.serialize() == output)
        check(case + "_integrity", reread.integrity_summary()["status"] == "PASS")
        actual_menu, accelerators = independent_menu(reread.one(0x2226).decoded)
        before_menu, before_accelerators = independent_menu(menu.decoded)
        check(case + "_menu_positions_and_commands", [(x[0], x[1], x[2]) for x in before_menu] == [(x[0], x[1], x[2]) for x in actual_menu])
        check(case + "_menu_texts", all(row[3] == text_map[row[0]] for row in actual_menu))
        check(case + "_accelerators_exact", accelerators == before_accelerators)
        parsed = parse_player_controls(reread.one(0x225D).decoded)
        actual_values = logical_controls(parsed)
        expected_values = {key: text_map.get(key, value) for key, value in original_values.items()}
        check(case + "_independent_all_75_fields", actual_values == expected_values)
        check(case + "_dialog_geometry_styles_classes_ids", geometry(parsed) == geometry(original_controls))
        check(case + "_all_dialogs_and_controls_dword_aligned", all(d["offset"] % 4 == 0 and all(i["offset"] % 4 == 0 for i in d["controls"]) for d in parsed["dialogs"]))
        changed_chunks = [a.chunk_id for a, b in zip(baseline.chunks, reread.chunks) if a.raw != b.raw]
        check(case + "_only_menu_controls_and_checksum_changed", set(changed_chunks) == {0x2226, 0x225D, 0x2242})
        check(case + "_all_object_and_font_blocks_unchanged", all(a.raw == b.raw for a, b in zip(baseline.objects + baseline.fonts, reread.objects + reread.fonts)))
        check(case + "_all_four_fonts", all(d["font"]["face"] == "THOG Noto Sans KR" for d in parsed["dialogs"]))
        target = OUT / case / "THOG.dat"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(output)
        (target.parent / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        (target.parent / "field_comparison.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (target.parent / "independent_controls.json").write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
        nebula_path = target.parent / "nebula/package.json"
        if nebula_path.exists():
            identity = json.loads((target.parent / "nebula/input.json").read_text(encoding="utf-8-sig"))
            check(case + "_nebula_candidate_identity", identity["sha256"] == sha(output))
            nebula = json.loads(nebula_path.read_text(encoding="utf-8-sig"))["MenuBar"]
            nebula_items = []
            def visit(items, parent="menu"):
                for index, item in enumerate(items):
                    key = f"{parent}/{index}"
                    nebula_items.append((key, item))
                    visit(item["Items"] or [], key)
            visit(nebula["Items"])
            check(case + "_nebula_all_menu_texts", len(nebula_items) == 3 and all(item["Name"] == text_map[key].replace("&", "") for key, item in nebula_items))
            check(case + "_nebula_all_menu_commands", [(key, item["Flags"]["Value"], item["ID"]) for key, item in nebula_items] == [(x[0], x[1], x[2] or 0) for x in before_menu])
            check(case + "_nebula_accelerators", (nebula["AccelShift"], nebula["AccelKey"], nebula["AccelId"]) == ([17, 145], [13, 115], [1025, 1009]))
        candidates.append({"case": case, "path": str(target), "sha256": sha(output), "bytes": len(output), "changes": len(plan),
                           "menu_bytes": len(reread.one(0x2226).decoded), "controls_bytes": len(reread.one(0x225D).decoded),
                           "changed_chunks": [hex(x) for x in changed_chunks]})
    wrong_plans = {
        "wrong_source": [{"target": menu.location, "offset": 26, "source": "BAD", "translated": "시험"}],
        "unknown_offset": [{"target": menu.location, "offset": 27, "source": "&File", "translated": "시험"}],
        "embedded_nul": [{"target": menu.location, "offset": 26, "source": "&File", "translated": "시\0험"}],
        "wrong_hash": [{"target": menu.location, "offset": 26, "source": "&File", "translated": "시험", "source_container_sha256": "0" * 64}],
        "structural_field": [{"target": controls.location, "offset": 678, "source": "", "translated": "시험"}],
    }
    valid = {"target": menu.location, "offset": 26, "source": "&File", "translated": "&파일"}
    wrong_plans["duplicate_offset"] = [valid, valid]
    wrong_plans["all_changes_atomic"] = [valid, {"target": controls.location, "offset": 192, "source": "BAD", "translated": "시험"}]
    for name, plan in wrong_plans.items():
        dat = DatFile(baseline.original)
        rejected = False
        try:
            patch_resources(dat, plan)
        except ValueError:
            rejected = True
        check("reject_" + name, rejected and dat.serialize() == baseline.original)
    bad = bytearray(controls.decoded)
    struct.pack_into("<I", bad, 20, 1)
    rejected = False
    try:
        PlayerControlsResource(bytes(bad))
    except ValueError:
        rejected = True
    check("reject_corrupt_string_offset", rejected)
    summary = {"status": "PASS", "source_sha256": sha(baseline.original), "checks": checks, "candidates": candidates,
               "independent_reader": "extra_chunk_review.parse_player_controls 및 별도 메뉴 순차 해석기; Nebula 결과 존재 시 후보 해시 확인 후 MenuBar 비교",
               "format_references": ["https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-dlgtemplate", "https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-dlgitemtemplate"],
               "graphics_qa": "NOT_RUN", "font_registration_qa": "NOT_RUN",
               "note": "긴 문구는 구조 시험용이며 UI 폭 확대·실제 한글 글꼴 사용 검수는 별도입니다."}
    (OUT / "test_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": summary["status"], "checks": len(checks), "candidates": candidates}, ensure_ascii=False))


if __name__ == "__main__":
    main()
