"""직접 표시 경계가 확인된 네이티브 문구와 미해결 후보를 구분합니다."""
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/investigation_20261031"


def main():
    source = OUT / "native_string_inventory.jsonl"
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    confirmed = []
    for row in rows:
        file, kind, text = row["file"], row["kind"], row["source"]
        proof = None
        if file == "THOG.exe" and kind == "RT_STRING":
            ident = row["string_id"]
            if 193 <= ident <= 201:
                row.update(classification="VISIBLE_TRANSLATE", reason="실행 오류 번호에 대응하는 문자열. THOG RVA0x58890 함수가 LoadStringW로 읽고 MessageBoxW로 표시")
                proof = "native_resource_output_disasm.json: THOG RVA0x5893f/0x5894b"
            elif ident == 160:
                row.update(classification="INTERNAL", reason="실행 확장 모듈 폴더명 Modules. 실제 원본 하위 폴더와 모듈 경로를 구성하는 식별자")
            elif ident == 192:
                row.update(classification="INTERNAL", reason="GUID 형식의 런타임 식별자. 표시용 자연어가 아니며 원본 문자열 보존")
        elif file == "mmfs2.dll" and kind == "RT_STRING":
            row.update(classification="VISIBLE_TRANSLATE", reason="파일 선택기의 파일 형식 이름·패턴 및 형식 오류 문자열. 구분기호와 %s 자리표시자는 보존해야 함")
            proof = "native_resource_output_disasm.json: MMFS2 RVA0x29300 리소스 문자열 읽기 경계"
        elif file == "mmfs2.dll" and kind == "RT_DIALOG" and row["classification"] == "VISIBLE_TRANSLATE":
            row["reason"] = "MMFS2 대화상자100의 이미지 정보 레이블. Windows 대화상자 문자열 필드로 구조 확인; 실제 게임 접근 경로는 후속 확인"
            proof = "native_pe_resources_evidence.json: MMFS2 RT_DIALOG100"
        elif file in ("AdvDir.mfx", "Layer.mfx") and kind == "RT_STRING":
            row.update(classification="INTERNAL", reason="확장 개발도구의 이름·저작자·조건/액션/표현식 설명 리소스. 이 배포 모듈의 GetActionString/GetConditionString/GetExpressionString/GetObjInfos는 즉시 반환하며 LoadString 가져오기도 없음")
            proof = "native_editor_boundaries_disasm.json; extension_exports_evidence.json"
        elif file == "KcBoxA.mfx" and text.startswith("SystemBox: This object"):
            row.update(classification="INTERNAL", reason="GetActionString/GetExpressionString(공유 RVA0x6010)이 편집 도구의 문자열 출력 버퍼에 복사하는 버전 경고. 게임 화면 출력 경로가 아님")
            proof = "kcbox_editor_message_disasm.json"
        elif file == "Box2DBouncingBall.mvx" and kind == "RT_STRING" and row["string_id"] in (102, 217):
            row.update(classification="VISIBLE_TRANSLATE", reason="운동 객체 초기화 중 물리 엔진이 없을 때 표시하는 MessageBoxW 제목/본문. LoadStringW ID102/217 소비를 직접 확인")
            proof = "native_resource_output_disasm.json: Box2DBouncingBall RVA0x18d3/0x18f0/0x1917"
        elif file == "Steamworks.mfx" and text.startswith("Notice that you should only have"):
            row.update(classification="VISIBLE_TRANSLATE", reason="LoadObject가 중복 Steamworks 객체 수를 %d로 조합해 MessageBoxW에 표시")
            proof = "native_output_literal_disasm.json: Steamworks RVA0x16c6b/0x16c89"
        elif file == "Steamworks.mfx" and text in ("JSON file not found on disk or in MFX resources", " - Error"):
            row.update(classification="VISIBLE_TRANSLATE", reason="EDIF 설명 파일을 로드하지 못할 때 MessageBoxW 본문과 제목에 직접 사용")
            proof = "native_output_literal_disasm.json: Steamworks RVA0x183ff/0x18415/0x1841c"
        elif file == "THOG.exe" and text == "Application Position|*.mfs||":
            row.update(classification="VISIBLE_TRANSLATE", reason="게임 상태 파일 선택용 필터 문자열. THOG RVA0x2fbb0이 UTF16을 복사하고 |를NUL로 분리하여 필터를 구성")
            proof = "native_output_literal_disasm.json: THOG RVA0x2fbd0"
        elif kind == "EDIF_SCHEMA":
            row.update(classification="INTERNAL", reason="Steamworks의 확장 개발도구 설명 스키마: About, 액션·조건·표현식 메뉴, Title, Parameters 및 종속 DLL 정의. 플레이어 문구는 실제 MessageBox 소비 문자열을 별도 기록")
            proof = "steamworks_edif_private.json; native_pe_resources_evidence.json: Steamworks EDIF102"
        elif kind == "RT_DIALOG" and file == "cctrans.dll" and row["classification"] == "VISIBLE_TRANSLATE":
            row.update(classification="UNKNOWN", reason="화면 전환 효과 설정 대화상자. 편집 도구용으로 보이나 실제 호스트 호출 범위를 확인하기 전 제외하지 않음")
        if proof:
            row["classification_evidence"] = proof
        if row["classification"] == "VISIBLE_TRANSLATE":
            confirmed.append(row)
        if row["classification"] == "UNKNOWN":
            if kind == "RT_STRING":
                row["required_evidence"] = f"{file} LoadString 계열 호출에서 리소스 ID{row['string_id']}의 소비 함수와 편집기/런타임 진입 경로 확인"
            elif kind == "RT_DIALOG":
                row["required_evidence"] = f"{file} 리소스 {row['resource_name']}를 host에 전달하는 함수 및 실제 게임이 호출하는지 확인"
            else:
                row["required_evidence"] = f"{file} VA{row.get('preferred_va')}의 코드/주소표 참조를 찾고 MessageBox·대화상자·반환값·로그·컴파일러 내부 처리 중 소비 경로 확인"
    source.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    (OUT / "native_visible_worklist.json").write_text(json.dumps(confirmed, ensure_ascii=False, indent=2), encoding="utf-8")
    unresolved = [row for row in rows if row["classification"] == "UNKNOWN"]
    summary = json.loads((OUT / "native_string_summary.json").read_text(encoding="utf-8"))
    summary.update(classifications=dict(collections.Counter(row["classification"] for row in rows)),
                   confirmed_visible=len(confirmed), unknown_by_kind=dict(collections.Counter(row["kind"] for row in unresolved)),
                   unknown_by_file=dict(collections.Counter(row["file"] for row in unresolved)),
                   actual_runtime_observed=False,
                   limitation="대량 바이트 후보의 UNKNOWN에는 컴파일러·로케일·셰이더·주소표의 오검출도 포함된다. 이는 확정 누락 문구 수가 아니며 전체 네이티브 분류 PASS로 사용할 수 없다. 직접 표시 근거가 있는 문구와 구조상 표시 레이블은 native_visible_worklist.json으로 분리했다.")
    (OUT / "native_string_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"confirmed_visible": len(confirmed), "classifications": summary["classifications"], "unknown_by_kind": summary["unknown_by_kind"]}))


if __name__ == "__main__":
    main()
