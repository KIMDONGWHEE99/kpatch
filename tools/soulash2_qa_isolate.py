"""REA 근거로 확인한 다섯 군데만 바꿔 검수 사본의 저장과 외부 연동을 분리한다.

이 실행 파일은 검수 전용이며 배포 후보에 사용하지 않는다.
"""
import hashlib
import json
import struct
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029/Soulash 2.exe"
PROBE = ROOT / "working_private/SOULASH_2/g1_probe_01"
REPORT = ROOT / "working_private/SOULASH_2/qa_isolation"
SOURCE_SHA = "924e1ef316ce5ab4aacf75c2eb83a16932151a0642a2e57af14e7025dac0d430"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    original = BASE.read_bytes()
    assert sha(original) == SOURCE_SHA
    target = PROBE / "Soulash 2.exe"
    previous = target.read_bytes()
    assert previous == original or sha(previous) == "0360865a66f558bc03425f6ad78c353d3e5058717eac37cfb7217cd4694747ae", "검수 원본이 변경되어 있습니다."
    for name in ["tutorial_values.json", "user.settings.json"]:
        assert not (PROBE / "data" / name).exists(), "최초 시작 이전 파일 조건이 다릅니다."
    pe = struct.unpack_from("<I", original, 60)[0]
    assert original[pe:pe+4] == b"PE\0\0"
    assert struct.unpack_from("<H", original, pe+4)[0] == 0x8664
    count = struct.unpack_from("<H", original, pe+6)[0]
    opt_size = struct.unpack_from("<H", original, pe+20)[0]
    image_base = struct.unpack_from("<Q", original, pe+24+24)[0]
    sections = [struct.unpack_from("<8sIIII", original, pe+24+opt_size+40*i) for i in range(count)]

    def offset(address):
        rva = address - image_base
        matches = [s for s in sections if s[2] <= rva < s[2]+s[3]]
        assert len(matches) == 1
        return matches[0][4] + rva - matches[0][2]

    patches = [
        {"role": "pref_path", "offset": 0x9ac316, "before": b"SDL_GetPrefPath\0", "after": b"SDL_GetBasePath\0",
         "evidence": ["xrefs_pref_iat.json", "pseudo_pref_init.json", "pseudo_main_init.json", "pseudo_save_dir.json"]},
        {"role": "steam_init_failure", "va": 0x1403094dd, "before": bytes.fromhex("ff15a5b75800"), "after": bytes.fromhex("b80100000090"),
         "evidence": ["asm_steam_init.json", "pseudo_steam_init.json", "pseudo_steam_setup.json"]},
        {"role": "skip_version_task", "va": 0x140309754, "before": bytes.fromhex("7556"), "after": bytes.fromhex("eb56"),
         "evidence": ["asm_steam_init.json", "pseudo_nonsteam_task.json", "pseudo_nonsteam_request.json"]},
        {"role": "skip_uninitialized_steam_shutdown", "va": 0x140892c04, "before": bytes.fromhex("ff153e200000"), "after": b"\x90" * 6,
         "evidence": ["asm_steam_shutdown.json", "pseudo_steam_shutdown.json", "pseudo_steam_singleton.json"]},
        {"role": "existing_no_crash_reporter_path", "va": 0x1406e50ab, "before": bytes.fromhex("0f858c030000"),
         "after": b"\xe9" + struct.pack("<i", 0x1406e543d-(0x1406e50ab+5)) + b"\x90",
         "evidence": ["asm_crash_init.json", "pseudo_crash_init.json"]},
    ]
    changed = bytearray(original)
    permitted = set()
    for patch in patches:
        start = patch.get("offset") if "offset" in patch else offset(patch["va"])
        patch["offset"] = start
        old, new = patch["before"], patch["after"]
        assert len(old) == len(new)
        assert original[start:start+len(old)] == old, patch["role"]
        changed[start:start+len(old)] = new
        permitted.update(range(start, start+len(old)))
        patch["before"] = old.hex()
        patch["after"] = new.hex()
        patch["evidence"] = [{"path": name, "sha256": sha((ROOT / "working_private/SOULASH_2/rea/responses" / name).read_bytes())} for name in patch["evidence"]]
    differences = [i for i, pair in enumerate(zip(original, changed)) if pair[0] != pair[1]]
    assert differences and set(differences) <= permitted
    target.write_bytes(changed)
    reread = target.read_bytes()
    assert reread == changed and len(reread) == len(original)
    restored = bytearray(reread)
    for patch in patches:
        old = bytes.fromhex(patch["before"])
        restored[patch["offset"]:patch["offset"]+len(old)] = old
    assert bytes(restored) == original
    # 문자열 이름 교체 후에도 Hint와 NUL, 인접 import 이름은 원본 그대로인지 확인한다.
    assert reread[0x9ac314:0x9ac316] == original[0x9ac314:0x9ac316]
    assert reread[0x9ac325:0x9ac345] == original[0x9ac325:0x9ac345]
    assert reread.count(b"SDL_GetPrefPath\0") == 0
    assert reread.count(b"SDL_GetBasePath\0") == original.count(b"SDL_GetBasePath\0") + 1
    report = {"purpose": "QA_ONLY_DO_NOT_DISTRIBUTE", "timestamp": datetime.now(timezone.utc).isoformat(),
              "source_sha256": SOURCE_SHA, "qa_sha256": sha(reread), "target": str(target),
              "tool_sha256": sha(Path(__file__).read_bytes()), "patches": patches,
              "changed_byte_count": len(differences), "changed_byte_offsets": differences,
              "boundary_and_reverse": "PASS", "graphics_qa": "NOT_RUN", "runtime_isolation": "NOT_RUN",
              "launch_requirements": ["cwd=probe", "safe_save_names", "pre_post_user_save_hashes", "actual_process_path_and_hash"],
              "limitations": ["Steam/BugSplat DLL imports remain present", "GetBasePath returns are checked at runtime", "prelaunch migration-file absence must be checked again before any restart"]}
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "g1_isolation_manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"boundary": "PASS", "changed_bytes": len(differences), "qa_sha256": sha(reread)}))


if __name__ == "__main__":
    main()
