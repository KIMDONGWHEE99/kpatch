"""게임 확장 로더와 편집기 전용 리소스 소비 함수를 대조합니다."""
import collections
import json
import struct
from pathlib import Path
import pefile
from dat_container import sha

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311"
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/investigation_20261031"


def main():
    binary = (BASE / "Box2DBase.mfx").read_bytes()
    image = pefile.PE(data=binary)
    names = {entry.name.decode(): entry.address for entry in image.DIRECTORY_ENTRY_EXPORT.symbols if entry.name}
    loadstring = next(item.address for module in image.DIRECTORY_ENTRY_IMPORT for item in module.imports if item.name == b"LoadStringW")
    refs = []
    for section in image.sections:
        if not section.Characteristics & 0x20000000:
            continue
        start, raw = section.VirtualAddress, section.get_data()
        cursor = 0
        while True:
            cursor = raw.find(struct.pack("<I", loadstring), cursor)
            if cursor < 0:
                break
            rva = start + cursor
            assert 0x4620 <= rva < 0x4EB0
            owner = max(((address, name) for name, address in names.items() if address <= rva), default=None)
            refs.append({"rva": hex(rva), "enclosing_export": owner[1], "export_start": hex(owner[0])})
            cursor += 4
    assert len(refs) == 10
    evidence = {"file": "Box2DBase.mfx", "sha256": sha(binary), "LoadStringW_calls": refs,
                "host_proof": ["runtime_extension_import_tables.json", "runtime_extension_imports_disasm.json"],
                "consumer_proof": "native_editor_resource_consumers.json",
                "conclusion": "LoadStringW 주소참조10개는 편집기 GetActionString/GetActionTitle/GetConditionString/GetDebugItem/GetExpressionParam/GetExpressionString/GetExpressionTitle/GetObjInfos 영역에만 있고, 실제 THOG 확장 로더의 호출 이름표는 이 함수들을 불러오지 않는다. GetProperties는 즉시 반환한다.",
                "limitations": "다른파일의가상함수호출을같은근거로일괄제외하지않음"}
    (OUT / "native_editor_review_evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    path = OUT / "native_string_inventory.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    for row in rows:
        if row["classification"] != "UNKNOWN" or row["kind"] != "RT_STRING":
            continue
        if row["file"] == "Box2DBase.mfx":
            row.update(classification="INTERNAL", reason="편집기 전용 문자열/속성 리소스: 모든 LoadStringW 주소참조10개가 게임 로더에서 불러오지 않는 편집기 함수 경계 안에 있음",
                       classification_evidence="native_editor_review_evidence.json")
        elif row["file"] == "KcBoxA.mfx":
            row.update(classification="INTERNAL", reason="확장 제작 도구의 모듈명·설명. 유일한 LoadStringW 소비는 GetObjInfos(RVA0x60c0)이며 게임 확장 로더가 요청하지 않는 함수",
                       classification_evidence="native_editor_boundaries_disasm.json; runtime_extension_import_tables.json")
        elif row["file"] == "kcini.mfx":
            row.update(classification="INTERNAL", reason="INI 확장 모듈 이름 리소스2. LoadString API를 가져오지 않으며 런타임 파일경로는 별도의 기본 경로·설정 필드로 구성됨",
                       classification_evidence="native_pe_resources_evidence.json; native_extra_findings.json")
        elif row["file"] == "Steamworks.mfx" and row["source"] == "MF2":
            row.update(classification="INTERNAL", reason="확장 모듈 SDK 형식 식별자 MF2. 같은 리소스1은 Box2DBase/KcBoxA에서도 사용하며 표시 오류 본문·제목은 별도 UTF16 리터럴로 확인됨",
                       classification_evidence="native_pe_resources_evidence.json; native_output_literal_disasm.json")
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"classifications": dict(collections.Counter(row["classification"] for row in rows))}))


if __name__ == "__main__":
    main()
