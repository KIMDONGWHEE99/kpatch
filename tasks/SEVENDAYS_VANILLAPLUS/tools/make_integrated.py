import csv
import datetime
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[3]
GAME = 'SEVENDAYS_VANILLAPLUS'
BUILD = 'integrated_0.1.0_28a6c1cb'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_once(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == data, str(path)
    else:
        path.write_bytes(data)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    source = ROOT / 'source_original' / GAME / '1.6.0/VanillaPlus_1.6.0.zip'
    translated = ROOT / 'build_candidate' / GAME / 'ko_0.1.0_final_28a6c1cb/VanillaPlus/Config/Localization.csv'
    previous = ROOT / 'validation' / GAME / 'ko_0.1.0'
    static_bytes = (previous / 'static_checks.json').read_bytes()
    static = json.loads(static_bytes)
    frozen_manifest = json.loads((previous / 'final_manifest.json').read_text(encoding='utf-8'))
    source_bytes, translated_bytes = source.read_bytes(), translated.read_bytes()
    assert sha(source_bytes) == '0ecd9323c633fe75648c0a0dd606951b3860af4c80a15b2330172a38a2fe91bd'
    assert sha(translated_bytes) == static['candidate_sha256'] == '28a6c1cb311e0cccd116c157b10e5e097bedb9632c132d177c4303a396a0b233'
    assert static['status'] == 'PASS' and sha(static_bytes) == frozen_manifest['static_checks_sha256']
    folder = ROOT / 'build_candidate' / GAME / BUILD
    archive = folder / 'VanillaPlus_1.6.0_Korean_Integrated.zip'
    key = 'VanillaPlus/Config/Localization.csv'
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source_bytes)) as original, zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        assert original.testzip() is None
        source_names = original.namelist()
        assert len(source_names) == len(set(source_names)) == 19
        originals = {name: original.read(name) for name in source_names}
        for entry in original.infolist():
            content = translated_bytes if entry.filename == key else originals[entry.filename]
            output.writestr(entry, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    write_once(archive, buffer.getvalue())
    # 최종 ZIP을 다시 열고 모든 포함 파일을 원본 또는 고정 번역표와 대조한다.
    expected = {**originals, key: translated_bytes}
    manifest = []
    with zipfile.ZipFile(archive) as final:
        assert final.testzip() is None and final.namelist() == source_names
        for name in source_names:
            data = final.read(name)
            assert data == expected[name], name
            manifest.append({'path': name, 'size': len(data), 'sha256': sha(data), 'changed': data != originals[name]})
        rows = list(csv.DictReader(io.StringIO(final.read(key).decode('utf-8-sig')), strict=True))
        assert len(rows) == 4235 and all(row['koreana'].strip() for row in rows)
        assert 'VanillaPlus/ModInfo.xml' in final.namelist()
        # 새 설치와 기존 원본 모드에 덮어쓰기를 각각 작업 공간 사본으로 확인한다.
        work = ROOT / 'working_private' / GAME / BUILD / datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        for mode in ('clean_install', 'replace_original'):
            install_root = (work / mode / 'Mods').resolve()
            if mode == 'replace_original':
                for name, data in originals.items():
                    target = (install_root / name).resolve()
                    assert target.is_relative_to(install_root)
                    write_once(target, data)
            for name in final.namelist():
                target = (install_root / name).resolve()
                assert target.is_relative_to(install_root)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(final.read(name))
            installed = {str(p.relative_to(install_root)).replace('\\', '/'): p.read_bytes() for p in install_root.rglob('*') if p.is_file()}
            assert installed == expected, mode
    assert sum(row['changed'] for row in manifest) == 1
    assert sha(source.read_bytes()) == sha(source_bytes)
    instructions = '''Vanilla Plus 1.6.0 한국어 통합본 (번역 0.1.0)

이 ZIP은 원본 모드 전체에 한국어 번역표를 미리 반영한 통합본입니다.
별도 한글패치 적용기나 기존 영문 모드의 선행 설치가 필요하지 않습니다.

1. 게임을 종료합니다.
2. ZIP을 풀어 나온 VanillaPlus 폴더를 평소 사용하는 Mods 폴더에 넣습니다.
   폴더 구조: Mods/VanillaPlus/ModInfo.xml
3. 기존 VanillaPlus가 있으면 같은 폴더에 덮어씁니다. 이름을 바꿔 중복 설치하지 마세요.
4. 게임 언어를 한국어로 설정하고 실행합니다.

복구하려면 처음 받은 영문 VanillaPlus 1.6.0 ZIP의 폴더로 덮어쓰면 됩니다.

원본 파일 19개 중 Config/Localization.csv의 한국어 칸만 변경했습니다.
다른 18개 파일은 원본과 같습니다. 한국어 칸은 4,235개이며 무기 모델명 등 일부 식별 표기는 유지합니다.
기존 패치의 정적 검사를 통과한 번역표를 그대로 사용했고 통합 ZIP의 내용과 폴더 구조를 다시 검사했습니다.
요청대로 실제 플레이 테스트는 하지 않았습니다. 기본 게임 이미지의 간판·로고는 그대로입니다.
사용자 제공 모드의 개인 사용을 위한 통합본이며 공개 업로드는 하지 않았습니다.
'''
    write_once(folder / '설치방법.txt', instructions.encode('utf-8-sig'))
    report = {'game_id': GAME, 'build_id': BUILD, 'status': 'PASS', 'archive_sha256': sha(archive.read_bytes()),
        'archive_size': archive.stat().st_size, 'source_zip_sha256': sha(source_bytes), 'translation_sha256': sha(translated_bytes),
        'reused_static_checks_sha256': sha(static_bytes), 'tool_sha256': sha(Path(__file__).read_bytes()),
        'files': manifest, 'file_count': len(manifest), 'unchanged_files': 18, 'changed_files': [key],
        'korean_rows': len(rows), 'checks': {'archive_crc': 'PASS', 'root_folder': 'PASS', 'all_content_hashes': 'PASS',
        'csv_reopen': 'PASS', 'clean_install_copy': 'PASS', 'overwrite_original_copy': 'PASS', 'source_preserved': 'PASS'},
        'runtime_qa': 'NOT_RUN', 'scope': '사용자 요청에 따른 로컬 모드 통합본. 실제 게임 설치·공개 업로드 없음.',
        'completed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    evidence = ROOT / 'validation' / GAME / BUILD
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'integrated_checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (evidence / 'RESULT_REPORT.md').write_text(f'''# Vanilla Plus 한국어 통합본

원본 모드 전체에 검증된 한국어 번역표를 미리 반영했습니다. 현재 사용자의 요청으로 별도 적용기가 없는 통합본을 제작했습니다. 개인용 결과물이며 공개 업로드와 실제 게임 설치는 하지 않았습니다.

- 파일: `{str(archive.relative_to(ROOT)).replace(chr(92), '/')}`
- ZIP 크기: {archive.stat().st_size:,}바이트
- ZIP SHA-256: `{report['archive_sha256']}`
- 구성: 원본과 같은 경로의 파일 19개. Config/Localization.csv 하나만 변경, 나머지 18개는 바이트 단위로 원본과 동일.
- 한국어: 4,235개 칸. 번역표 해시 `{sha(translated_bytes)}`로 이전 정적 검사와 동일한 입력임을 확인.
- 최종 ZIP 재열기·CRC·파일 전체 해시·CSV 구조·깨끗한 설치 사본·기존 원본 덮어쓰기 사본 검사 PASS.
- 사용자 제공 원본 ZIP 및 기존 차이 패치 ZIP은 보존.
- 실제 플레이·글꼴·레이아웃 검수는 사용자가 직접 수행하는 기존 요청을 유지하며 NOT_RUN.
- 포함 파일이 실제 모드 원본과 번역표인 이번 통합본에는 이전 차이 패키지의 공개 배포 허용 목록을 적용하지 않음. 명시적인 사용자 요청에 따른 비공개 통합 산출물로 build_candidate에 보관.

ZIP을 풀어 나온 VanillaPlus 폴더를 Mods에 넣고 게임 언어를 한국어로 사용합니다. 기존 VanillaPlus가 있으면 동일 폴더를 교체하며 중복 폴더를 만들지 않습니다. 모드 자체 제거는 VanillaPlus 폴더 제거이고, 한글만 원상복구하려면 영문 원본 ZIP으로 교체합니다.

[상세 검사](integrated_checks.json). 실제 실행 결과나 전체 게임 한글화 완료로 확대하지 않습니다.
''', encoding='utf-8')
    print(json.dumps({'archive': str(archive), 'sha256': report['archive_sha256'], 'size': archive.stat().st_size,
        'file_count': len(manifest), 'unchanged': 18, 'changed': key, 'korean_rows': len(rows), 'status': 'PASS'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
