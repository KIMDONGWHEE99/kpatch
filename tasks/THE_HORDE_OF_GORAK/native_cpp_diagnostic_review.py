"""C++ 예외 객체와 오류번호 표에 속한 표준 진단 데이터를 식별합니다."""
import ast
import collections
import json
import re
from pathlib import Path
import pefile
from dat_container import sha
from native_inspect import disassemble

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311"
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/investigation_20261031"
VC = Path("C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.43.34808")
SIMPLE = {"Unknown exception", "bad allocation", "bad exception", "bad array new length", "invalid string position",
          "invalid vector<T> subscript", "vector<T> too long", "map/set<T> too long", "invalid map<K, T> key",
          "string too long", "list<T> too long", "deque<T> too long", "invalid deque<T> subscript", "ios_base::failbit set",
          "ios_base::badbit set", "ios_base::eofbit set", "iostream stream error", "invalid hash argument",
          "invalid unordered_map<K, T> key", "invalid argument", "bad cast", "bad typeid"}


def main():
    sources = [VC / "include" / name for name in ("vcruntime_exception.h", "exception", "xstring", "vector", "xtree", "deque", "list", "xhash", "regex", "ios", "xiosbase", "typeinfo")]
    sources += [VC / "crt/src/stl/syserror.cpp"]
    recognized = {}
    literal = r'(?:L|u8|u|U)?"(?:\\.|[^"\\])*"'
    for source in sources:
        if not source.exists():
            continue
        text = source.read_text(encoding="utf-8-sig")
        for match in re.finditer(literal + r'(?:\s*' + literal + r')*', text):
            tokens = re.findall(literal, match.group())
            try:
                value = "".join(ast.literal_eval(re.sub(r'^(?:L|u8|u|U)', '', token)) for token in tokens)
            except Exception:
                continue
            if value not in SIMPLE and not value.startswith("regex_error(") and not (source.name == "syserror.cpp" and "{errc::" in text[text.rfind("\n", 0, match.start()):match.start()]):
                continue
            recognized[value] = {"source": str(source), "source_sha256": sha(source.read_bytes()), "line": text.count("\n", 0, match.start()) + 1,
                                  "role": "std::error_code 번호→진단 이름 표" if source.name == "syserror.cpp" else "std::exception/regex_error 객체의 what() 진단 데이터"}
    path = OUT / "native_string_inventory.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    selected, examples = [], {}
    for row in rows:
        if row["classification"] != "UNKNOWN" or row["kind"] != "section_string" or row["source"] not in recognized:
            continue
        if not row.get("static_references"):
            continue
        proof = recognized[row["source"]]
        row.update(candidate_type="CPP_EXCEPTION_OR_ERROR_CODE_DATA", classification="INTERNAL",
                   reason=proof["role"] + ". C++ 표준 자료구조/오류 처리용 데이터이며 게임의 번역 가능한 UI 필드와 구분함. 실제 MessageBoxW용 CRT 오류 표는 별도로 번역함",
                   classification_evidence="native_cpp_diagnostic_evidence.json", source_reference=proof)
        selected.append({"file": row["file"], "file_sha256": row["file_sha256"], "offset": row["file_offset"],
                         "source_sha256": row["source_bytes_sha256"], "source": row["source"], "references": row["static_references"], "source_reference": proof})
        key = row["file"] + ":" + ("exception" if proof["role"].startswith("std::exception") else "error_code")
        if key in examples:
            continue
        image = pefile.PE(str(BASE / row["file"]))
        for ref in row["static_references"]:
            for location in ref["pointer_offsets"]:
                rva = image.get_rva_from_offset(location)
                section = image.get_section_by_rva(rva)
                if section.Characteristics & 0x20000000:
                    # 주소 피연산자 앞의 명령 시작 후보를 보존합니다. 전체 함수명이라고 단정하지 않습니다.
                    examples[key] = {"pointer_operand_va": hex(image.OPTIONAL_HEADER.ImageBase + rva),
                                     "instruction_window": disassemble(BASE / row["file"], image.OPTIONAL_HEADER.ImageBase + rva - 1, 45)}
                    break
            if key in examples:
                break
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    evidence = {"records": selected, "native_reference_examples": examples,
                "boundary": "표준 C++ 예외 객체의 메시지와 번호표로 식별한 진단 데이터. 독립 UI 메시지/대화상자/게임 텍스트는 이 규칙으로 분류하지 않음",
                "limits": "표준 소스의 정확한 리터럴과 원본 주소참조를 연결한 용도 판정. 임의의 미래 호스트가 what()를 화면에 표시하는 경우까지 부정하지 않으며 이 빌드 외에는 판정을 재사용하지 않음"}
    (OUT / "native_cpp_diagnostic_evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"exact_sources": len(recognized), "new_internal": len(selected), "by_file": dict(collections.Counter(item["file"] for item in selected))}))


if __name__ == "__main__":
    main()
