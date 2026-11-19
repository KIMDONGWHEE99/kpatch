"""허용된 REA 연결 설정만 백업 후 갱신한다."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'working_private/REA_GHIDRA_20261031'
CONFIG = Path(r'C:\Users\PC\.codex\config.toml')
OLD_GHIDRA = Path(r'C:\Users\PC\.codex\visualizations\2026\10\31\01a19054-2e7f-7bd0-af04-b341f6f862be\working_private\THE_HORDE_OF_GORAK\toolchain\ghidra_12.1.4_PUBLIC')
REA_ROOT = Path(r'C:\Users\PC\AppData\Local\REA')
GHIDRA = REA_ROOT / 'toolchains/ghidra_12.1.4_PUBLIC'
JAVA = ROOT / 'working_private/SOULASH_2/toolchain/jdk-21.0.12.1+1'
RUNTIME = REA_ROOT / 'runtime'
BACKUP = CONFIG.with_name('config.toml.before-rea-ghidra-20261031.bak')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    before = CONFIG.read_bytes()
    text = before.decode('utf-8-sig')
    assert '[mcp_servers.rea.env]' not in text, '기존 환경 표를 덮어쓰지 않습니다.'
    anchor = '[mcp_servers.rea.tools.binary_session]'
    assert text.count(anchor) == 1 and not BACKUP.exists()
    assert (JAVA / 'bin/java.exe').is_file()
    assert OLD_GHIDRA.is_dir() and not GHIDRA.exists()
    assert OLD_GHIDRA.resolve() == OLD_GHIDRA
    assert OLD_GHIDRA.is_relative_to(Path(r'C:\Users\PC\.codex\visualizations\2026\10\31\01a19054-2e7f-7bd0-af04-b341f6f862be'))
    assert GHIDRA.resolve() == GHIDRA and GHIDRA.is_relative_to(REA_ROOT)
    assert not (OLD_GHIDRA.stat().st_file_attributes & 0x400)
    critical = ['Ghidra/application.properties', 'support/LaunchSupport.jar', 'Ghidra/Framework/Generic/lib/Generic.jar', 'Ghidra/Features/Decompiler/os/win_x86_64/decompile.exe']
    hashes = {name: sha((OLD_GHIDRA / name).read_bytes()) for name in critical}
    # 같은 드라이브 안에서 기존 설치 폴더를 이동해 추가 복사를 만들지 않는다.
    GHIDRA.parent.mkdir(parents=True, exist_ok=True)
    OLD_GHIDRA.rename(GHIDRA)
    assert hashes == {name: sha((GHIDRA / name).read_bytes()) for name in critical}
    RUNTIME.mkdir(parents=True, exist_ok=True)
    env = {'GHIDRA_INSTALL_DIR': str(GHIDRA), 'JAVA_HOME': str(JAVA), 'TEMP': str(RUNTIME), 'TMP': str(RUNTIME)}
    newline = '\r\n' if '\r\n' in text else '\n'
    block = '[mcp_servers.rea.env]' + newline + ''.join(f"{key} = '{value}'{newline}" for key, value in env.items()) + newline
    updated = text.replace(anchor, block + anchor, 1)
    assert updated.replace(block, '', 1) == text
    after = updated.encode('utf-8-sig' if before.startswith(b'\xef\xbb\xbf') else 'utf-8')
    assert CONFIG.read_bytes() == before
    BACKUP.write_bytes(before)
    temp = CONFIG.with_name('config.toml.rea-ghidra-new')
    assert not temp.exists()
    temp.write_bytes(after)
    os.replace(temp, CONFIG)
    assert CONFIG.read_bytes() == after and BACKUP.read_bytes() == before
    result = {'status': 'CONFIGURED_RECONNECT_REQUIRED', 'config': str(CONFIG), 'backup': str(BACKUP),
              'before_sha256': sha(before), 'after_sha256': sha(after), 'environment': env,
              'toolchain_moved_from': str(OLD_GHIDRA), 'toolchain_moved_to': str(GHIDRA),
              'toolchain_hashes': hashes, 'unrelated_configuration_unchanged': True}
    (OUT / 'configuration_change.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
