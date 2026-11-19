"""캡처 BMP를 별도 새 PNG 폴더로 복사 변환하고 원본·출력·픽셀 지문을 연결합니다."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / 'working_private/COBALT_MINER'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def convert(source, output, partial=False):
    source, output = source.resolve(), output.resolve()
    if not source.is_relative_to(PRIVATE) or not output.is_relative_to(PRIVATE) or output == source or output.exists():
        raise ValueError('원본과 분리된 새 Cobalt 비공개 출력 폴더만 허용')
    manifest_path = source / 'cycle_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else None
    if not manifest and not partial:
        raise ValueError('완료 캡처 명세 없음. 진행 중 일부만 보려면 --partial 명시')
    records = {Path(r['output']).name: r for r in manifest['records'] if r.get('api_status') == 'PASS'} if manifest else {}
    files = sorted(source.glob('cycle_[0-9][0-9][0-9][0-9].bmp'))
    if not files or len(files) > 350 or (manifest and set(records) != {p.name for p in files}):
        raise ValueError('캡처 수·명세와 실제 파일 목록 불일치')
    output.mkdir(parents=True)
    converted = []
    for path in files:
        raw = path.read_bytes()
        digest = sha(raw)
        if manifest and digest != records[path.name]['sha256']:
            raise ValueError('JS 캡처 당시 BMP 해시와 현재 파일 불일치')
        target = output / (path.stem + '.png')
        with Image.open(path) as image:
            if image.size != (1920, 1080):
                raise ValueError('예상하지 않은 캡처 크기')
            pixels = image.convert('RGB').tobytes()
            image.convert('RGB').save(target, format='PNG', compress_level=6)
        with Image.open(target) as image:
            if image.convert('RGB').tobytes() != pixels:
                raise ValueError('BMP→PNG 변환의 픽셀 불일치')
        if sha(path.read_bytes()) != digest:
            raise ValueError('변환 중 캡처 원본 변경')
        converted.append(dict(index=int(path.stem.rsplit('_', 1)[1]), original_path=str(path), original_sha256=digest,
                              png_path=str(target), png_sha256=sha(target.read_bytes()), rgb_sha256=sha(pixels),
                              timing=records.get(path.name), graphics_review='NOT_RUN', paragraph_alignment='NOT_RUN'))
    report = dict(status='PASS', partial=partial, source_path=str(source), source_manifest_sha256=sha(manifest_path.read_bytes()) if manifest else None,
                  tool_sha256=sha(Path(__file__).read_bytes()), converted=len(converted), records=converted,
                  originals_preserved=True, graphics_review='NOT_RUN', paragraph_alignment='NOT_RUN',
                  limitation='시간·파일·픽셀 동일성을 검증했습니다. 문단번호는 실제 텍스트 또는 고유한 관심 영역 판독과 별도로 연결해야 합니다.')
    (output / 'archive_manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(status='PASS', converted=len(converted), output=str(output), originals_preserved=True), ensure_ascii=False))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--partial', action='store_true')
    args = parser.parse_args()
    convert(args.source, args.output, args.partial)
