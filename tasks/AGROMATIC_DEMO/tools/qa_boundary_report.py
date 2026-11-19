"""정식 후보와 실제 검수 사본의 변경 경계를 독립 재열기로 대조합니다."""
import hashlib
import json
import sys
from pathlib import Path
from common import sha, save, read_settings
from pck_tools import read_pack


def verify(production, qa, output):
    production, qa = Path(production).resolve(), Path(qa).resolve()
    original, observed = read_pack(production), read_pack(qa)
    allowed = {'project.binary','scripts/SteamManager.gdc','scripts/GameAnalytics.gdc','scripts/KoreanQaDriver.gdc'}
    changes = []
    errors = []
    for path in sorted(set(original['entries']) | set(observed['entries'])):
        before = original['entries'].get(path)
        after = observed['entries'].get(path)
        if before and after and before['data'] == after['data']:
            continue
        changes.append({'path':path,'before_sha256':hashlib.sha256(before['data']).hexdigest() if before else None,
                        'after_sha256':hashlib.sha256(after['data']).hexdigest() if after else None})
        if path not in allowed or after is None:
            errors.append({'path':path,'reason':'허용하지 않은 변경·삭제'})
    before_settings = read_settings(original['entries']['project.binary']['data'])
    after_settings = read_settings(observed['entries']['project.binary']['data'])
    keys = {key for key in set(before_settings)|set(after_settings) if before_settings.get(key)!=after_settings.get(key)}
    expected_keys = {'application/config/name','application/config/use_custom_user_dir','display/window/size/mode',
                     'display/window/size/window_width_override','display/window/size/window_height_override','autoload/KoreanQaDriver'}
    if not keys.issubset(expected_keys):
        errors.append({'reason':'검수용 프로젝트 필드 경계 초과','keys':sorted(keys-expected_keys)})
    outside = []
    for path in sorted(production.parent.rglob('*')):
        if not path.is_file() or path == production:
            continue
        relative = path.relative_to(production.parent)
        other = qa.parent/relative
        if not other.is_file() or sha(path)!=sha(other):
            errors.append({'path':str(relative),'reason':'EXE 외 게임 파일 변경'})
        outside.append(str(relative))
    if production.read_bytes()[:original['start']] != qa.read_bytes()[:observed['start']]:
        errors.append({'reason':'엔진 실행 코드 부분 변경'})
    report = {'status':'FAIL' if errors else 'PASS','production_sha256':sha(production),'qa_sha256':sha(qa),
              'verifier_sha256':sha(Path(__file__)),'pack_changes':changes,'project_changed_fields':sorted(keys),
              'unchanged_external_file_count':len(outside),'errors':errors,
              'note':'차단 메서드 2개·검수 도우미 새 파일·프로젝트 필드만 별도 검수에 허용. 메서드 본문은 script_build 재복원 자료와 별도 연결'}
    save(output,report)
    print(json.dumps({'status':report['status'],'qa_pack_changes':len(changes),'errors':len(errors)},ensure_ascii=False))
    return report


if __name__=='__main__':
    result=verify(*sys.argv[1:4])
    raise SystemExit(result['status']!='PASS')
