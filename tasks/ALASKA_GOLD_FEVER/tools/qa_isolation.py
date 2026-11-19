"""검수 사본의 저장·설정·Steam·오류 전송만 격리하며 게임은 실행하지 않습니다."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'source_original/ALASKA_GOLD_FEVER/25782395/game'
CODE = ROOT / 'extracted_private/ALASKA_GOLD_FEVER/25782395/code'
BASELINE = CODE.parent / 'baseline_manifest.json'
QA = ROOT / 'working_private/ALASKA_GOLD_FEVER/risk_runtime/game'
PRODUCT = 'Alaska Gold KQA01'


def long_path(path: Path) -> Path:
    value = os.path.abspath(path)
    return Path(value if value.startswith('\\\\?\\') else '\\\\?\\' + value)


def sha(path: Path) -> str:
    value = hashlib.sha256()
    with long_path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    report_path = QA.parent / 'isolation.json'
    if report_path.exists():
        raise RuntimeError('완성된 검수 격리를 덮어쓰지 않습니다.')
    baseline = json.loads(BASELINE.read_text('utf-8'))
    assert baseline['status'] == 'PASS'
    rows = json.loads((CODE / 'code_map.json').read_text('utf-8'))
    address_owners: dict[int, list[str]] = defaultdict(list)
    for row in rows:
        for method in row['methods']:
            item = next((a['fields'] for a in method['attributes'] if a['type'].endswith('AddressAttribute')), None)
            if item:
                address_owners[int(item['RVA'], 16)].append(method['fullName'])

    def method(type_name: str, name: str) -> dict:
        typ = next(row for row in rows if row['type'] == type_name)
        matches = [item for item in typ['methods'] if item['name'] == name]
        assert len(matches) == 1, (type_name, name, len(matches))
        item = matches[0]
        address = next(a['fields'] for a in item['attributes'] if a['type'].endswith('AddressAttribute'))
        result = {key: int(value, 16) for key, value in address.items()}
        assert len(address_owners[result['RVA']]) == 1, ('공유 메서드 수정 금지', item['fullName'])
        return dict(result, full_name=item['fullName'], assembly=typ['assembly'])

    # 중단된 복사는 지문이 일치하는 파일만 재사용하고 누락은 긴 경로 지원으로 보충합니다.
    QA.mkdir(parents=True, exist_ok=True)
    copied = 0
    for row in baseline['files']:
        src, dst = long_path(SOURCE / row['path']), long_path(QA / row['path'])
        if not dst.is_file() or sha(dst) != row['sha256']:
            assert sha(src) == row['sha256'], row['path']
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
        assert sha(dst) == row['sha256'], row['path']
    print(f'검수 사본 {len(baseline["files"])}파일 지문 확인, {copied}파일 보충', flush=True)

    binary_path = QA / 'GameAssembly.dll'
    original_binary = binary_path.read_bytes()
    binary = bytearray(original_binary)
    changes: list[dict] = []

    def patch(type_name: str, name: str, content: bytes, reason: str) -> None:
        entry = method(type_name, name)
        pos, size = entry['Offset'], entry['Length']
        assert 0 < len(content) <= size
        before = bytes(binary[pos:pos + len(content)])
        assert before == original_binary[pos:pos + len(content)]
        binary[pos:pos + len(content)] = content
        changes.append(dict(entry, before=before.hex(), after=content.hex(), reason=reason,
                            source_method_sha256=hashlib.sha256(original_binary[pos:pos+size]).hexdigest()))

    src = method('UnityEngine.Application', 'get_persistentDataPath')
    dst = method('UnityEngine.Application', 'get_dataPath')
    patch('UnityEngine.Application', 'get_persistentDataPath',
          b'\xe9' + struct.pack('<i', dst['RVA'] - src['RVA'] - 5),
          '저장·설정·로그의 공통 저장 경로를 검수 사본의 Data 디렉터리로 한정')
    patch('BakedGames.Utilities.UtilitiesEditorPreferences', 'DisableSteamInEditor',
          b'\xb8\x01\x00\x00\x00\xc3',
          '게임 자체의 Steam 비활성 분기를 이용해 게임 초기화는 유지')
    patch('SteamManager', 'get_Initialized', b'\x31\xc0\xc3',
          'Steam 통계·업적·순위표 사용부에 미연결 상태 반환')
    patch('Steamworks.SteamAPI', 'Init', b'\x31\xc0\xc3', '별도 초기화 호출도 Steam 연결 금지')
    # RestartAppIfNecessary는 SDK 내부 별칭과 주소를 공유합니다. 직접 수정하지 않고
    # Awake가 위의 Steam 비활성 분기에서 빠져나가 재실행 호출에 도달하지 않게 합니다.
    # 초기화를 막으면 오류 수집기·통계 수집기·네이티브 오류 전송기를 만들지 않습니다.
    patch('Backtrace.Unity.BacktraceClient', 'Refresh', b'\xc6\x41\x30\x00\xc3',
          'Enabled 필드(0x30)를 끄고 오류·통계·네이티브 전송 초기화 생략')
    patch('Backtrace.Unity.BacktraceClient', 'LateUpdate', b'\xc3',
          '초기화하지 않은 오류 수집기의 프레임별 큐 처리 생략')
    patch('Backtrace.Unity.BacktraceDatabase', 'Reload', b'\xc6\x41\x70\x00\xc3',
          'Enable 필드(0x70)를 끄고 오류 보고서 저장·전송 초기화 생략')
    patch('BacktraceManager', 'Awake', b'\xc3', '게임의 오류 수집기 이벤트 등록 생략')
    patch('BacktraceAttributes', 'Initialize', b'\xc3', '오류 수집용 앱 이벤트 등록 생략')
    binary_path.write_bytes(binary)

    settings_path = QA / 'Alaska Gold Fever_Data/globalgamemanagers'
    original_settings = settings_path.read_bytes()
    old_text, new_text = b'Alaska Gold Fever', PRODUCT.encode('utf-8')
    assert len(old_text) == len(new_text)
    old = struct.pack('<I', len(old_text)) + old_text
    new = struct.pack('<I', len(new_text)) + new_text
    assert original_settings.count(old) == 1
    output_settings = original_settings.replace(old, new, 1)
    settings_path.write_bytes(output_settings)
    # 알려지지 않은 꼬리 4바이트를 포함하여 제품명 이외의 원시 객체 바이트를 보존합니다.
    sys.path.insert(0, str(ROOT / 'tools/python_deps'))
    import UnityPy
    before_env, after_env = UnityPy.load(original_settings), UnityPy.load(output_settings)
    before_objects = {(obj.path_id, obj.type.name): obj for obj in before_env.objects}
    after_objects = {(obj.path_id, obj.type.name): obj for obj in after_env.objects}
    assert before_objects.keys() == after_objects.keys()
    for identity, before in before_objects.items():
        after = after_objects[identity]
        expected = before.get_raw_data().replace(old, new, 1) if identity == (1, 'PlayerSettings') else before.get_raw_data()
        assert expected == after.get_raw_data(), identity

    # 게임의 기본값을 사용하고 음량만 검수 사본에서 낮춥니다. 사용자 저장은 복사하지 않습니다.
    options_path = QA / 'Alaska Gold Fever_Data/Options.json'
    write_json(options_path, {'FileName': 'Options', 'MasterVolume': 0.0, 'MusicVolume': 0.0,
                             'SFXVolume': 0.0, 'UIVolume': 0.0, 'AmbienceVolume': 0.0,
                             'DisplayMode': 3, 'ResolutionIndex': -1})

    # 실제 출력에서 각 허용 수정을 되돌리면 기준선과 완전히 같아야 합니다.
    reopened = bytearray(binary_path.read_bytes())
    for item in changes:
        pos = item['Offset']; actual = bytes.fromhex(item['after']); before = bytes.fromhex(item['before'])
        assert reopened[pos:pos+len(actual)] == actual
        reopened[pos:pos+len(before)] = before
    assert reopened == original_binary
    assert settings_path.read_bytes().replace(new, old, 1) == original_settings
    manifest = []
    for row in baseline['files']:
        actual = sha(QA / row['path'])
        if row['path'] not in ('GameAssembly.dll', 'Alaska Gold Fever_Data/globalgamemanagers'):
            assert actual == row['sha256'], row['path']
        manifest.append({'path': row['path'], 'baseline_sha256': row['sha256'], 'qa_sha256': actual})
    report = {'game_id': 'ALASKA_GOLD_FEVER', 'build_id': '25782395', 'status': 'PASS',
              'scope': '정적 검수 격리 준비만 완료; 실제 그래픽 실행은 NOT_RUN',
              'started_utc': started, 'finished_utc': datetime.now(timezone.utc).isoformat(),
              'qa_root': str(QA), 'product_name': PRODUCT,
              'persistent_data_path': str(QA / 'Alaska Gold Fever_Data'),
              'baseline_manifest_sha256': sha(BASELINE), 'code_map_sha256': sha(CODE / 'code_map.json'),
              'tool_sha256': sha(Path(__file__)), 'changes': changes, 'files': manifest,
              'asset_changes': [{'file': 'Alaska Gold Fever_Data/globalgamemanagers',
                                 'path_id': 1, 'field': 'PlayerSettings.productName',
                                 'before': old_text.decode(), 'after': PRODUCT,
                                 'original_objects': len(before_objects), 'unmodified_tail_preserved': True}],
              'added_files': [{'path': str(options_path.relative_to(QA)), 'sha256': sha(options_path)}],
              'launch_arguments': ['-screen-fullscreen', '0', '-screen-width', '1280', '-screen-height', '720',
                                   '-logFile', str(QA.parent / 'run01.log')],
              'remaining': ['실제 경로·GPU·화면 관찰', '런타임 저장 경로 및 사용자 저장 전후 대조',
                            '샘플 번역 번들·카탈로그를 적용했다면 overlay 지문 별도 기록']}
    write_json(report_path, report)
    print(json.dumps({'status': 'PASS', 'methods': len(changes), 'files': len(manifest), 'report': str(report_path)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
