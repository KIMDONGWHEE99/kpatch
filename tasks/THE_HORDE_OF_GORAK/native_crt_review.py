"""로컬 Microsoft CRT 원문의 용도와 정확한 상수 배열을 대조합니다."""
import ast
import collections
import json
import re
import struct
from pathlib import Path
from dat_container import sha

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311"
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/investigation_20261031"
UCRT = Path("C:/Program Files (x86)/Windows Kits/10/Source/10.0.22621.0/ucrt")
VC = Path("C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.43.34808/crt/src")


def main():
    categories = {
        "C++ 기호 해독기의 이름 조립 문자열": [VC / "vcruntime/undname.cxx"],
        "CRT Windows API 동적 로딩 모듈·함수 식별자": [UCRT / "internal/winapi_thunks.cpp", VC / "vcruntime/winapi_downlevel.cpp", VC / "stl/winapisupp.cpp"],
        "CRT 로케일 선택·검색용 이름과 코드 식별자": list((UCRT / "locale").glob("*.cpp")),
        "CRT 기본 달력 표; 이 게임의7249개이벤트표현식에 날짜/요일/월이름 소비 없음": [UCRT / "time/timeset.cpp"],
        "CRT 숫자 변환기의 NaN/무한대/지수 형식 토큰": [UCRT / "convert/cvt.cpp"],
        "CRT 초기화 순서를 정하는 PE 섹션 식별자": [VC / "vcruntime/initializers.cpp", VC / "vcruntime/internal_shared.h"],
        "CRT 정수 파서의 숫자·알파벳 자릿값 표": [VC / "stl/xstoul.cpp", VC / "stl/xstoull.cpp"],
        "CRT 종료 처리 중 CLR 모듈·함수 검색 식별자": [UCRT / "startup/exit.cpp"],
    }
    strings, source_files, arrays = {}, {}, []
    for category, paths in categories.items():
        for path in paths:
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8-sig", errors="replace")
            file_hash = sha(path.read_bytes())
            source_files[str(path)] = file_hash
            for match in re.finditer(r'(?:L|u8|u|U)?("(?:\\.|[^"\\])*?")', content):
                try:
                    value = ast.literal_eval(match.group(1))
                except (ValueError, SyntaxError):
                    continue
                if len(value) >= 4:
                    strings[value] = {"category": category, "source": str(path), "source_sha256": file_hash, "line": content.count("\n", 0, match.start()) + 1}
    big = UCRT / "inc/corecrt_internal_big_integer.h"
    content = big.read_text(encoding="utf-8-sig")
    match = re.search(r"large_power_data\[\]\s*=\s*\{(.*?)\};", content, re.S)
    values = [int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]+)", match.group(1))]
    arrays.append(("large_power_data", struct.pack("<" + "I" * len(values), *values), str(big), sha(big.read_bytes()), "multiply_by_power_of_ten이 읽는 uint32 큰정수 배열"))
    ctype = UCRT / "locale/ctype.cpp"
    content = ctype.read_text(encoding="utf-8-sig")
    macros = {"_UPPER": 1, "_LOWER": 2, "_DIGIT": 4, "_SPACE": 8, "_PUNCT": 16, "_CONTROL": 32, "_BLANK": 64, "_HEX": 128, "_LEADBYTE": 0x8000, "_ALPHA": 0x100, "C1_ALPHA": 0x100}
    for name in ("_wctype", "_ctype", "__newctype", "__newclmap", "__newcumap"):
        match = re.search(re.escape(name) + r"\[\d*\]\s*(?:=\s*)?\{(.*?)\};", content, re.S)
        if not match:
            continue
        body = re.sub(r"//[^\n]*|/\*.*?\*/", "", match.group(1), flags=re.S)
        values = []
        for entry in body.split(","):
            if not entry.strip():
                continue
            value = 0
            for token in re.split(r"[|+]", entry.strip()):
                token = token.strip()
                value |= macros[token] if token in macros else int(token, 0)
            values.append(value)
        width = "B" if name in ("__newclmap", "__newcumap") else "H"
        arrays.append((name, struct.pack("<" + width * len(values), *values), str(ctype), sha(ctype.read_bytes()), "문자 종류 판별·대소문자 변환 함수가 인덱스로 읽는 상수 배열"))
    path = OUT / "native_string_inventory.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    matched_arrays = []
    for file in sorted({row["file"] for row in rows}):
        data = (BASE / file).read_bytes()
        for name, array, source, source_hash, consumer in arrays:
            cursor = 0
            while True:
                index = data.find(array, cursor)
                if index < 0:
                    break
                matched_arrays.append({"file": file, "start": index, "end": index + len(array), "name": name, "array_sha256": sha(array), "source": source, "source_sha256": source_hash, "consumer": consumer})
                cursor = index + len(array)
    for row in rows:
        if row["classification"] != "UNKNOWN" or row["kind"] != "section_string":
            continue
        owner = next((array for array in matched_arrays if array["file"] == row["file"] and array["start"] <= row["file_offset"] and row["file_offset"] + row["bytes"] <= array["end"]), None)
        if owner:
            row.update(classification="INTERNAL", reason="Microsoft CRT 원문의 숫자 배열과 전체 바이트가 일치함: " + owner["consumer"],
                       classification_evidence="native_crt_evidence.json", containing_structure=owner)
        elif row["source"] in strings:
            proof = strings[row["source"]]
            row.update(classification="INTERNAL", reason=proof["category"], classification_evidence="native_crt_evidence.json", source_reference=proof)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    (OUT / "native_crt_evidence.json").write_text(json.dumps({"source_files": source_files, "matched_arrays": matched_arrays, "literal_sources": strings,
        "calendar_evidence": "calendar_expression_review.json", "limitation": "로컬 CRT 소스의버전은게임컴파일러와같다고단정하지않음. 배열은전체바이트일치, 문자열은정확한값과소비문맥을사용함"}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"exact_arrays": len(matched_arrays), "classifications": dict(collections.Counter(row["classification"] for row in rows))}))


if __name__ == "__main__":
    main()
