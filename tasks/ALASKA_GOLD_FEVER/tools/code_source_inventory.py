"""게임 코드의 문자열과 화면 출력·언어 조회·열거형 변환 단서를 연결합니다."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / 'extracted_private/ALASKA_GOLD_FEVER/25782395/code'
ISIL = CODE / 'isil/IsilDump'
LITERAL = re.compile(r'^\s*(\d+) Move ([^,]+), "(.*?)"\s*$', re.MULTILINE | re.DOTALL)
DISPLAY = re.compile(r'(?:TMP_Text\.(?:set_text|SetText)|Text\.set_text|\.ShowNotification|\.ShowMessage|Dropdown\.(?:AddOptions|set_options)|DebugLogConsole\.AddCommand)')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    paths = []
    for assembly in ISIL.iterdir():
        if assembly.name.startswith('BakedGames.'):
            # 같은 DLL의 외부 대화 엔진은 별도 프레임워크 조사 대상으로 구분합니다.
            paths.extend((assembly / 'BakedGames').rglob('*.txt'))
            paths.extend(assembly.glob('*.txt'))
        elif assembly.name in ('Assembly-CSharp', 'NewAssembly'):
            paths.extend(assembly.rglob('*.txt'))
    rows, methods, files = [], [], []
    for path in sorted(set(paths)):
        raw = path.read_bytes()
        relative = path.relative_to(ISIL).as_posix()
        digest = sha(raw)
        files.append({'path': relative, 'sha256': digest})
        for block in re.split(r'\nMethod: ', raw.decode('utf-8'))[1:]:
            signature, body = block.split('\n', 1)
            if 'ISIL:' not in body:
                continue
            instructions = body.split('ISIL:', 1)[1]
            calls = sorted(set(re.findall(r'\bCall ([^,\n]+)', instructions)))
            flags = {'direct_display_call': bool(DISPLAY.search(instructions)),
                     'enum_to_string': any('Enum.ToString' in call for call in calls),
                     'localized_lookup': any('Localized' in call or 'Localization.' in call or 'Translation' in call for call in calls),
                     'formatting': any('String.Format' in call or 'String.Concat' in call for call in calls),
                     'debug_logging': any(call.startswith('Debug.Log') for call in calls)}
            literals = list(LITERAL.finditer(instructions))
            if literals or any(flags.values()):
                methods.append({'file': relative, 'file_sha256': digest, 'method': signature,
                                'calls': calls, 'flags': flags, 'literal_count': len(literals)})
            for match in literals:
                value = match.group(3)
                rows.append({'id': relative + '|' + signature + '|' + match.group(1),
                             'file': relative, 'file_sha256': digest, 'method': signature,
                             'instruction': int(match.group(1)), 'register': match.group(2), 'text': value,
                             'text_sha256': sha(value.encode('utf-8')), 'classification': 'UNKNOWN',
                             'flags': flags, 'calls': calls})
    output = {'game_id': 'ALASKA_GOLD_FEVER', 'build_id': '25782395', 'status': 'PASS',
              'scope': '게임 자체 네임스페이스의 ISIL 문자열·사용 메서드 조사, 분류 완료 아님',
              'created_utc': datetime.now(timezone.utc).isoformat(),
              'tool_sha256': sha(Path(__file__).read_bytes()), 'isil_report_sha256': sha((CODE / 'isil_analysis.json').read_bytes()),
              'files': files, 'strings': rows, 'methods': methods,
              'counts': {'files': len(files), 'strings': len(rows), 'methods': len(methods),
                         'direct_display_strings': sum(row['flags']['direct_display_call'] for row in rows),
                         'enum_methods': sum(method['flags']['enum_to_string'] for method in methods)}}
    (CODE / 'game_string_inventory.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    display = [row for row in rows if row['flags']['direct_display_call'] and not row['flags']['debug_logging']]
    (CODE / 'display_string_candidates.json').write_text(json.dumps(display, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(output['counts']))
    for row in display[:35]:
        print(json.dumps({key: row[key] for key in ('file', 'method', 'text')}, ensure_ascii=True))


if __name__ == '__main__':
    main()
