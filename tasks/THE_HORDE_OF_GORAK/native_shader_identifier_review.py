"""Direct3D 열거값과 HLSL 문법 이름을 일반 표시 문구와 구분합니다."""
import collections
import json
import re
from pathlib import Path
from dat_container import sha

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/investigation_20261031"
HEADER = Path("C:/Program Files (x86)/Windows Kits/10/Include/10.0.22621.0/shared/d3d9types.h")
KEYWORDS = set("asm asm_fragment BlendState bool break Buffer case cbuffer centroid class column_major compile compile_fragment CompileShader const continue default discard double dword else export extern false float for half if in inline inout int interface line lineadj linear matrix namespace NULL out packoffset pass pixelfragment PixelShader point return register row_major sample sampler shared snorm stateblock stateblock_state static string struct switch tbuffer technique texture true typedef triangle triangleadj uint uniform unorm unsigned vector vertexfragment VertexShader void volatile while".split())
INTRINSICS = set("acos asin atan atan2 ceil clamp clip cosh cross ddx ddy degrees determinant distance exp2 faceforward floor fmod frac frexp fwidth isfinite isinf isnan ldexp length lerp log10 log2 modf normalize pow radians reflect refract round rsqrt saturate sign sincos sinh smoothstep sqrt step tanh transpose trunc tex1D tex1Dbias tex1Dgrad tex1Dlod tex1Dproj tex2D tex2Dbias tex2Dgrad tex2Dlod tex2Dproj tex3D tex3Dbias tex3Dgrad tex3Dlod tex3Dproj texCUBE texCUBEbias texCUBEgrad texCUBElod texCUBEproj D3DCOLORtoUBYTE4".split())
REFERENCES = {
    "keywords": "https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-appendix-keywords",
    "intrinsics": "https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-intrinsic-functions",
    "types": "https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-data-types",
}


def main():
    text = HEADER.read_text(encoding="utf-8-sig", errors="replace")
    enums = {}
    for match in re.finditer(r"\b(D3D[A-Z0-9]*_([A-Z0-9_]+))\b", text):
        name, suffix = match.groups()
        enums.setdefault(suffix, {"identifier": name, "line": text.count("\n", 0, match.start()) + 1})
        enums.setdefault(name, {"identifier": name, "line": text.count("\n", 0, match.start()) + 1})
    path = OUT / "native_string_inventory.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    changed = []
    for row in rows:
        if row["classification"] != "UNKNOWN" or row["kind"] != "section_string" or row["file"] not in ("mmf2d3d8.dll", "mmf2d3d9.dll", "mmf2d3d11.dll"):
            continue
        source, proof = row["source"], None
        if source in enums:
            proof = {"kind": "Direct3D 열거 상수 이름", "header": str(HEADER), "header_sha256": sha(HEADER.read_bytes()), **enums[source]}
        elif source in KEYWORDS:
            proof = {"kind": "HLSL 예약어", "reference": REFERENCES["keywords"]}
        elif source in INTRINSICS:
            proof = {"kind": "HLSL 내장 함수 이름", "reference": REFERENCES["intrinsics"]}
        elif re.fullmatch(r"(?:float|half|int|uint|bool|double)(?:[1-4](?:x[1-4])?)?", source):
            proof = {"kind": "HLSL 스칼라/벡터/행렬 자료형", "reference": REFERENCES["types"]}
        if proof:
            row.update(classification="INTERNAL", candidate_type="SHADER_LANGUAGE_OR_RENDER_STATE_IDENTIFIER",
                       reason=proof["kind"] + ". 컴파일러/렌더링 상태의 기계 식별자로 철자를 유지해야 하며 자연어 UI 번역 대상이 아님",
                       classification_evidence="native_shader_identifier_evidence.json", language_reference=proof)
            changed.append({"file": row["file"], "offset": row["file_offset"], "source_sha256": row["source_bytes_sha256"], "source": source, "proof": proof})
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    (OUT / "native_shader_identifier_evidence.json").write_text(json.dumps({"records": changed, "references": REFERENCES,
        "limits": "컴파일러 진단 문장·임의의 짧은 영문은 이 목록에 없다는 이유로 제외하지 않음"}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"new_internal": len(changed), "by_file": dict(collections.Counter(row["file"] for row in changed))}))


if __name__ == "__main__":
    main()
