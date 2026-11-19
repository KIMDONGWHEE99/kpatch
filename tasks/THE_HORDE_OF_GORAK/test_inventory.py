"""미분류 기본값과 손상된 표현식 경계의 거부를 확인한다."""
import copy
import json
import struct

from dat_container import DatFile
from inventory import SOURCE, OUT, base_record, classify_event, event_operations, save


def main():
    checks = []

    def check(name, result):
        assert result, name
        checks.append({"id": name, "status": "PASS"})

    unknown = base_record("event_string", "synthetic/new", "New visible text", "synthetic")
    unknown.update(operation_type=99, operation_number=135, expression_index=None, expressions=[], operation_kind="Actions", parameter_index=0)
    classify_event(unknown)
    check("new_opcode_remains_unknown", unknown["classification"] == "UNKNOWN")
    visible = copy.deepcopy(unknown)
    visible["operation_type"] = 32
    classify_event(visible)
    check("known_button_display_classified", visible["classification"] == "VISIBLE_TRANSLATE")
    nonmatching = copy.deepcopy(unknown)
    nonmatching.update(expression_index=1, expressions=[{"type": 35, "num": 82, "handle": 999}, {"type": -1, "num": 3}])
    classify_event(nonmatching)
    check("unidentified_ini_object_remains_unknown", nonmatching["classification"] == "UNKNOWN")
    known = copy.deepcopy(nonmatching)
    known["expressions"][0]["handle"] = 54
    classify_event(known)
    check("known_ini_numeric_key_classified", known["classification"] == "INTERNAL")

    dat = DatFile.load(SOURCE)
    frame = [c for c in dat.chunks if c.chunk_id == 0x3333][2]
    chunk = next(c for c in frame.children if c.chunk_id == 0x333D)
    events = event_operations(chunk.decoded)
    first = next(expression for event in events for kind in ("Conditions", "Actions") for op in event[kind] for parameter in op["parameters"] for expression in parameter["expressions"])
    bad = bytearray(chunk.decoded)
    struct.pack_into("<H", bad, first["offset"] + 4, 0)
    refused = False
    try:
        event_operations(bytes(bad))
    except ValueError:
        refused = True
    check("corrupt_expression_size_rejected", refused)
    check("normal_event_stream_still_accepted", len(events) > 0)
    save("inventory_test_report.json", {"checks": checks, "scope": "분류 기본값·명시적 규칙·표현식 경계만 검증"})
    print(json.dumps({"checks": len(checks), "status": "PASS"}))


if __name__ == "__main__":
    main()
