import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

from build import BASE, WORK, CANDIDATE, ROOT, GAME, field_spans


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    source = (BASE / 'VanillaPlus/Config/Localization.csv').read_bytes()
    target = (CANDIDATE / 'VanillaPlus/Config/Localization.csv').read_bytes()
    checks = json.loads((ROOT / 'validation' / GAME / 'ko_0.1.0/static_checks.json').read_text(encoding='utf-8'))
    assert checks['status'] == 'PASS' and checks['candidate_sha256'] == sha(target)
    rows = list(csv.reader(io.StringIO(target.decode('utf-8-sig'))))
    spans = field_spans(source)
    col = rows[0].index('koreana')
    changes = []
    for record, fields in zip(rows[1:], spans[1:]):
        start, end = fields[col]
        changes.append({'offset': start, 'oldBase64': base64.b64encode(source[start:end]).decode('ascii'),
            'newText': '"' + record[col].replace('"', '""') + '"'})
    delta = {'schema': 1, 'modVersion': '1.6.0', 'patchVersion': '0.1.0', 'sourceSha256': sha(source),
        'targetSha256': sha(target), 'sourceSize': len(source), 'targetSize': len(target), 'changes': changes}
    data = json.dumps(delta, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    pack = ROOT / 'release_output' / GAME / 'ko_0.1.0'
    pack.mkdir(parents=True, exist_ok=True)
    (pack / 'korean.delta.json').write_bytes(data)
    script = Path(__file__).with_name('Patch.ps1').read_text(encoding='utf-8').replace('__DELTA_SHA256__', sha(data))
    (pack / 'Patch.ps1').write_text(script, encoding='utf-8-sig')
    for filename, mode in [('적용.cmd', 'Install'), ('제거.cmd', 'Remove')]:
        base_command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0Patch.ps1" -Mode ' + mode
        cmd = '@echo off\r\nchcp 65001 >nul\r\nif "%~1"=="" (\r\n  ' + base_command + '\r\n) else (\r\n  ' + base_command + ' -Path "%~1"\r\n)\r\nset "patchExit=%errorlevel%"\r\npause\r\nexit /b %patchExit%\r\n'
        (pack / filename).write_bytes(cmd.encode('utf-8'))
    readme = '''Vanilla Plus 1.6.0 한국어 번역 0.1.0
작성일: 2026-09-06

이 번역본은 사용자 플레이 테스트용입니다.
번역표 4,235개 항목과 파일 구조를 검사했으며, 실제 게임 실행은 하지 않았습니다.

적용 방법
1. 게임과 전용 서버를 종료합니다.
2. 이 ZIP을 새 폴더에 모두 압축 해제합니다.
3. 적용.cmd를 실행합니다.
4. 설치한 VanillaPlus 모드의 Config 폴더에 있는 Localization.csv를 선택합니다.
   예: Mods/VanillaPlus/Config/Localization.csv
   기본 게임의 Data/Config/Localization.csv를 선택하지 마세요.
5. 적용 완료 메시지를 확인하고 게임 언어를 한국어로 설정하여 실행합니다.

Localization.csv 파일을 적용.cmd 위로 끌어다 놓아도 됩니다.
별도 프로그램이나 Python 설치는 필요하지 않습니다.
모드는 먼저 설치되어 있어야 합니다. 이 ZIP은 전체 모드를 포함하지 않습니다.

제거와 복구
제거.cmd를 실행하고 같은 파일을 선택하면 원래 내용으로 정확히 복구됩니다.
적용 시 옆에 생성되는 Localization.csv.vanillaplus-ko.original은 원본 백업입니다.
제거 도구는 백업이 없어도 이 번역본에서 원문을 복원할 수 있습니다.
작업 중 중단되었다면 같은 도구를 다시 실행하세요. 확인 가능한 임시 파일은 자동 정리합니다.
쓰다 만 임시 파일과 원본 일부만 남은 백업은 .recovered. 이름으로 보관하고 다시 진행합니다.
알 수 없는 버전·수정본·백업은 덮어쓰지 않습니다.

번역 및 변경 범위
- VanillaPlus 1.6.0의 Localization.csv 한국어 칸 4,235개.
- 항목 순서, 내부 키, 영어와 다른 언어, 수치, 색상, 줄바꿈은 보존했습니다.
- XML, 제작법, 능력치 설정, 게임 저장과 설정은 바꾸지 않습니다.
- 기본 게임의 한국어 용어를 참고하고 모드 고유 설명을 추가 번역했습니다.
- SMG5/AK47/M60, R 키, 단위·규격·일부 상표와 로고명은 식별 표기로 유지했습니다.
- 모드 이름 Vanilla + 및 원본 ModInfo 소개는 유지했습니다.
- 원래 게임 이미지에 그려진 간판·로고의 영문은 수정하지 않았습니다.

확인한 검사
빈 번역, 항목 누락·중복·위치 바뀜, 다른 언어 변경, 숫자·부호·태그·줄바꿈 차이 없음.
XML 파일 18개 해석 성공. 명시적 번역 참조 1,231곳에서 누락 없음.
최종 ZIP의 설치·제거 결과는 ZIP 바깥의 제작 보고서에 기록합니다.

미검증
게임 로딩, 글꼴의 실제 한글 출력, 긴 설명 잘림, 다른 모드와의 조합 및 멀티플레이.
실제 플레이 테스트는 사용자가 직접 진행하기로 요청한 범위입니다.

지원 원본 파일 SHA-256
''' + sha(source) + '\n\n적용 결과 파일 SHA-256\n' + sha(target) + '''

원본 모드: unseen / Vanilla Plus
https://www.nexusmods.com/7daystodie/mods/11972
이 패키지는 개인 사용을 위한 한국어 차이 자료와 적용 도구입니다.
원본 모드 전체 파일과 게임 자산은 포함하지 않습니다. 공개 업로드는 수행하지 않았습니다.
'''
    (pack / '사용방법.txt').write_text(readme, encoding='utf-8-sig')
    license_text = '적용 도구 코드(Patch.ps1 및 CMD)에 한해 MIT License를 적용합니다.\n\n' + '''MIT License

Copyright (c) 2026 Korean Patch Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''
    (pack / 'LICENSE.txt').write_text(license_text, encoding='utf-8')
    allowed = ['korean.delta.json', 'Patch.ps1', '적용.cmd', '제거.cmd', '사용방법.txt', 'LICENSE.txt']
    files = [{'path': name, 'size': (pack/name).stat().st_size, 'sha256': sha((pack/name).read_bytes())} for name in allowed]
    (pack / 'package_manifest.json').write_text(json.dumps({'files': files}, ensure_ascii=False, indent=2), encoding='utf-8')
    allowed.append('package_manifest.json')
    assert set(p.name for p in pack.iterdir()) == set(allowed)
    archive = ROOT / 'release_output' / 'VanillaPlus_1.6.0_Korean_0.1.0.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in allowed:
            z.write(pack/name, name)
    (WORK / 'package_info.json').write_text(json.dumps({'path': str(archive), 'sha256': sha(archive.read_bytes()),
        'file_allowlist': allowed, 'delta_sha256': sha(data)}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(archive.name, archive.stat().st_size, sha(archive.read_bytes()))


if __name__ == '__main__':
    main()
