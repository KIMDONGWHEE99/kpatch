"""표준 출력으로만 보내는 네이티브 진단 문자열을 호출 근거로 분류합니다."""
import collections
import json
from pathlib import Path
import pefile
from native_inspect import disassemble
from dat_container import sha

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311"
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/investigation_20261031"
LOGGERS = {"Box2DBase.mfx": 0x1001DE30, "mmf2d3d11.dll": 0x100067A0}


def main():
    path = OUT / "native_string_inventory.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    evidence = []
    images = {name: pefile.PE(str(BASE / name)) for name in LOGGERS}
    for row in rows:
        name = row["file"]
        if name not in LOGGERS or row["classification"] != "UNKNOWN" or row["kind"] != "section_string" or row["encoding"] != "ascii":
            continue
        refs = row.get("static_references", [])
        if not refs or any(ref["target_offset"] != row["file_offset"] for ref in refs):
            continue
        proof = []
        valid = True
        image = images[name]
        data = (BASE / name).read_bytes()
        for ref in refs:
            for offset in ref["pointer_offsets"]:
                if data[offset - 1] != 0x68:
                    valid = False
                    break
                start = image.OPTIONAL_HEADER.ImageBase + image.get_rva_from_offset(offset - 1)
                instructions = disassemble(BASE / name, start, 96)
                call = next((item for item in instructions if item["instruction"].startswith("call ")), None)
                if not call or call["instruction"] != "call " + hex(LOGGERS[name]):
                    valid = False
                    break
                proof.append(instructions[:instructions.index(call) + 1])
            if not valid:
                break
        if valid:
            row.update(classification="INTERNAL", reason="이 원문 주소의 모든 PE 재배치 참조는 printf형 표준출력 진단 함수로 직접 전달됨. 표준 스트림 인덱스1을 선택하며 게임 대화상자 문자열 경로가 아님",
                       classification_evidence="native_log_review_evidence.json; native_stdout_diagnostics.json")
            evidence.append({"file": name, "file_sha256": row["file_sha256"], "offset": row["file_offset"], "source_sha256": row["source_bytes_sha256"],
                             "logger": hex(LOGGERS[name]), "references": proof})
    source = Path("C:/Program Files (x86)/Windows Kits/10/Source/10.0.22621.0/ucrt/stdio/_file.cpp")
    result = {"fields": evidence, "stream_source": {"path": str(source), "sha256": sha(source.read_bytes()), "line": 22},
              "source_limit": "게임 컴파일러와 로컬 CRT 소스 버전이 동일하다는 주장이 아님. 스트림선택함수의배열인덱스구조와인수1,문자열주소의직접호출을함께확인함",
              "output_boundary": {"Box2DBase.mfx": "RVA0x1de37 push1 ->0x2a5c8 stream selector, printf formatter0x29ccd",
                                  "mmf2d3d11.dll": "RVA0x67ab push1 ->0x3db51 FILE-array selector (stride0x38), formatter0x40376"}}
    (OUT / "native_log_review_evidence.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"new_internal": len(evidence), "by_file": dict(collections.Counter(item["file"] for item in evidence))}))


if __name__ == "__main__":
    main()
