"""고정 원본에서 텍스트·글꼴·네이티브 후보를 새 비공개 폴더에 만듭니다."""
from __future__ import annotations
import argparse
import importlib.util
import json
import re
import shutil
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/python_deps'))
sys.path.insert(0, str(ROOT / 'tasks/THE_HORDE_OF_GORAK'))
from dat_container import DatFile, sha, u32, utf16z
from resource_builder import patch_resources

def local_module(name):
    spec = importlib.util.spec_from_file_location('cobalt_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

validator = local_module('validate_candidate')
font_builder = local_module('font_builder')
WORK = validator.WORK
SOURCE = validator.SOURCE

def resize_button(dat, row):
    """확장 문자열의 길이 필드 세 곳과 마지막 8바이트를 보존합니다."""
    handle = row['object_handle']
    block = dat.objects[handle]
    before = block.decoded
    current = before if block.replacement is None else block.replacement
    extension = struct.unpack_from('<H', current, 12)[0]
    blob = extension + 20
    start, size = blob + 212, u32(current, blob + 208)
    if row['kind'] != 'button_text' or row['extension'] != 'KcBoxA.mfx' or row['offset'] != start:
        raise ValueError('KcBoxA 표시 위치와 다름')
    if u32(current) != len(current) or u32(current, extension) != len(current) - extension or start + size + 8 != len(current):
        raise ValueError('KcBoxA 길이 또는 후미 경계 오류')
    if utf16z(current, start) != (row['source'], start + size):
        raise ValueError('KcBoxA 원문 또는 종료 위치 불일치')
    # 객체의 모든 내부 위치는 문자열 앞을 가리켜야 후미 확장이 안전합니다.
    for offset in (4, 6, 12, 14, 36, 38, 40, 62):
        if struct.unpack_from('<H', current, offset)[0] >= start:
            raise ValueError('문자열 뒤를 참조하는 객체 오프셋')
    for offset in (54, 58):
        if u32(current, offset) >= start:
            raise ValueError('문자열 뒤를 참조하는 객체 오프셋')
    encoded = row['translated'].encode('utf-16le') + b'\0\0'
    result = bytearray(current[:start] + encoded + current[-8:])
    struct.pack_into('<I', result, 0, len(result))
    struct.pack_into('<I', result, extension, len(result) - extension)
    struct.pack_into('<I', result, blob + 208, len(encoded))
    block.replacement = bytes(result)
    return dict(location=row['location'], object_handle=handle, text_offset=start, old_bytes=size,
                new_bytes=len(encoded), original_object_sha256=sha(before), output_object_sha256=sha(result))

def build(candidate_id, translation_path, native_source=validator.NATIVE, native_expected=validator.NATIVE_EXPECTED, native_inventory=None, media_manifest=None):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{2,90}', candidate_id):
        raise ValueError('후보 ID에는 소문자·숫자·밑줄·하이픈만 허용')
    destination = ROOT / 'build_candidate/COBALT_MINER' / candidate_id
    evidence = WORK / 'candidate_builds' / candidate_id
    if destination.exists() or evidence.exists():
        raise ValueError('기존 후보 ID 덮어쓰기 금지')
    native_source, native_expected = Path(native_source), Path(native_expected)
    tracked_inputs = [Path(translation_path), validator.CLASSIFICATION / 'inventory.jsonl',
                      validator.NATIVE / 'native_patch_audit.json', native_expected, validator.BASELINE]
    if native_inventory:
        tracked_inputs.append(Path(native_inventory))
    if media_manifest:
        tracked_inputs.append(Path(media_manifest))
    if (native_source / 'native_json_audit.json').exists():
        tracked_inputs.extend([native_source / 'native_json_audit.json', native_source / 'independent_validation.json'])
    title_path = native_source / 'native_title_audit.json'
    title_audit = validator.load(title_path) if title_path.exists() else None
    json_source = native_source
    if title_audit:
        json_source = (ROOT / title_audit['parent_candidate']).resolve()
        if not json_source.is_relative_to(WORK):
            raise ValueError('제목 보완의 부모 후보 경계 오류')
        tracked_inputs.extend([title_path, native_source / 'independent_validation.json', json_source / 'native_json_audit.json', json_source / 'independent_validation.json'])
    input_hashes = {str(p.resolve()): sha(p.read_bytes()) for p in tracked_inputs}
    inventory = validator.read_inventory()
    plan = validator.load_plan(translation_path, inventory)
    original = DatFile.load(SOURCE / 'COBALT MINER.dat')
    if sha(original.original) != validator.SOURCE_HASH or original.serialize() != original.original:
        raise ValueError('원본 해시 또는 무변경 재저장 불일치')
    # 글꼴 시험 DAT를 누적 수정하지 않고 항상 게임 원본에서 다시 시작합니다.
    dat = DatFile.load(SOURCE / 'COBALT MINER.dat')
    for row in plan.values():
        _, raw = dat.get_target(row['target'])
        if sha(raw) != row['source_container_sha256'] or utf16z(raw, row['offset'])[0] != row['source']:
            raise ValueError(f"원본 위치·컨테이너 연결 불일치: {row['location']}")
    fonts = {weight: (validator.FONT_DIR / f'CobaltNotoSansKR-{weight}.ttf').read_bytes() for weight in (400, 700)}
    if any(sha(raw) != validator.FONT_HASHES[weight] for weight, raw in fonts.items()):
        raise ValueError('소규모 시험과 다른 글꼴')
    embedded, mappings, buttons = font_builder.apply_fonts(dat, fonts)
    resources, resized, fixed = [], [], []
    for row in plan.values():
        if row['kind'] in validator.RESOURCE_KINDS:
            resources.append(row)
        elif row['kind'] == 'button_text':
            resized.append(resize_button(dat, row))
        elif row['kind'] in {'paragraph', 'event_string'}:
            dat.patch_utf16(row['target'], row['offset'], row['source'], row['translated'], row['slot_bytes'])
            fixed.append(dict(location=row['location'], target=row['target'], offset=row['offset'], slot_bytes=row['slot_bytes']))
        else:
            raise ValueError(f"구현되지 않은 표시 종류: {row['kind']}")
    resource_report = patch_resources(dat, resources)
    image_changes = []
    if media_manifest:
        image_builder = local_module('image_builder')
        image_changes = image_builder.apply_images(dat, media_manifest)
    output = dat.serialize()
    candidate = DatFile(output)
    if candidate.serialize() != output:
        raise ValueError('후보 재읽기 왕복 불일치')
    # 파일 쓰기 전에 독립 검증기를 통과해야 합니다.
    dat_report, positions = validator.validate_dat(original, candidate, inventory, plan, media_manifest)
    source_files = {p.relative_to(SOURCE).as_posix(): sha(p.read_bytes()) for p in SOURCE.rglob('*') if p.is_file()}
    if source_files != {r['path']: r['sha256'] for r in validator.load(validator.BASELINE)['files']}:
        raise ValueError('고정 원본 기준과 사본의 파일·해시 차이')
    native_audit = validator.load(validator.NATIVE / 'native_patch_audit.json')
    json_audit = validator.load(json_source / 'native_json_audit.json') if (json_source / 'native_json_audit.json').exists() else None
    for entry in native_audit['files']:
        digest = json_audit['candidate_sha256'] if json_audit and entry['file'] == json_audit['file'] else entry['candidate_sha256']
        if title_audit:
            title_file = next(r for r in title_audit['files'] if r['file'] == entry['file'])
            if title_file['parent_sha256'] != digest:
                raise ValueError('제목 보완의 부모 지문 불일치')
            digest = title_file['candidate_sha256']
        if source_files.get(entry['file']) != entry['source_sha256'] or sha((native_source / entry['file']).read_bytes()) != digest:
            raise ValueError('네이티브 후보의 입력 또는 출력 해시 불일치')
    destination.mkdir(parents=True)
    evidence.mkdir(parents=True)
    try:
        for name in source_files:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if name == 'COBALT MINER.dat':
                target.write_bytes(output)
            else:
                source = native_source / name if any(e['file'] == name for e in native_audit['files']) else SOURCE / name
                shutil.copyfile(source, target)
        report, positions, native_positions = validator.validate(destination, translation_path, native_source, native_expected, native_inventory, media_manifest)
        if {p.relative_to(SOURCE).as_posix(): sha(p.read_bytes()) for p in SOURCE.rglob('*') if p.is_file()} != source_files:
            raise ValueError('제작 전후 원본 무결성 변경')
        if any(sha(Path(path).read_bytes()) != digest for path, digest in input_hashes.items()):
            raise ValueError('제작 도중 입력 변경: 결과 STALE')
        inputs = {
            'translations': dict(path=str(Path(translation_path).resolve()), sha256=sha(Path(translation_path).read_bytes())),
            'inventory': dict(path=str(validator.CLASSIFICATION / 'inventory.jsonl'), sha256=sha((validator.CLASSIFICATION / 'inventory.jsonl').read_bytes())),
            'native_audit': dict(path=str(validator.NATIVE / 'native_patch_audit.json'), sha256=sha((validator.NATIVE / 'native_patch_audit.json').read_bytes())),
            'native_source': str(native_source), 'media_manifest': str(media_manifest) if media_manifest else None,
            'font_files': {str(weight): dict(sha256=sha(raw), path=str(validator.FONT_DIR / f'CobaltNotoSansKR-{weight}.ttf')) for weight, raw in fonts.items()},
            'tools': {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in [Path(__file__), Path(validator.__file__), Path(font_builder.__file__),
                       ROOT / 'tasks/THE_HORDE_OF_GORAK/dat_container.py', ROOT / 'tasks/THE_HORDE_OF_GORAK/resource_builder.py',
                       ROOT / 'tasks/THE_HORDE_OF_GORAK/inventory.py', ROOT / 'tasks/THE_HORDE_OF_GORAK/extra_chunk_review.py',
                       Path(__file__).with_name('validate_native_candidate.py')]}, 'tracked_inputs': input_hashes}
        if media_manifest:
            inputs['tools']['tasks/COBALT_MINER/image_builder.py'] = sha(Path(image_builder.__file__).read_bytes())
        build_report = dict(status='PASS', candidate_id=candidate_id, created_utc=datetime.now(timezone.utc).isoformat(),
                            candidate_path=str(destination), source_files=source_files, candidate_files=report['files'], inputs=inputs,
                            fixed_slots=fixed, resized_buttons=resized, resource_fields=resource_report,
                            image_changes=image_changes,
                            fonts=dict(embedded=embedded, mappings=mappings, buttons=buttons),
                            scope='텍스트·글꼴·지정 네이티브·지정 미디어 통합 후보. 최종 배포본 아님',
                            media=report['media'], graphics_qa='NOT_RUN', release='NOT_RUN')
        for name, value in [('build_report.json', build_report), ('validation.json', report), ('positions.json', positions), ('native_positions.json', native_positions)]:
            (evidence / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        for name, digest in inputs['tools'].items():
            source = ROOT / name
            if sha(source.read_bytes()) != digest:
                raise ValueError('도구 파일이 제작 중 변경됨')
            target = evidence / 'tool_snapshot' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    except Exception as error:
        # 부분 후보를 성공으로 오인하지 않도록 실패를 비공개 증거 폴더에 남깁니다.
        (evidence / 'FAILED.json').write_text(json.dumps(dict(status='FAIL', error=str(error), candidate_id=candidate_id), ensure_ascii=False, indent=2), encoding='utf-8')
        raise
    return dict(status='PASS', candidate_id=candidate_id, candidate_path=str(destination), evidence=str(evidence),
                dat_sha256=sha(output), dat_positions=len(plan), native_positions=report['native']['checked_fields'], media=report['media'], graphics_qa='NOT_RUN')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-id', default='ko_text_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S'))
    parser.add_argument('--translations', type=Path, default=validator.TRANSLATIONS)
    parser.add_argument('--native-source', type=Path, default=validator.NATIVE)
    parser.add_argument('--native-expected', type=Path, default=validator.NATIVE_EXPECTED)
    parser.add_argument('--native-inventory', type=Path)
    parser.add_argument('--media-manifest', type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.candidate_id, args.translations, args.native_source, args.native_expected, args.native_inventory, args.media_manifest), ensure_ascii=False))

if __name__ == '__main__':
    main()
