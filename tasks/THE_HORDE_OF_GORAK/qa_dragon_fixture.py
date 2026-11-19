"""도감 용 본문을 표시하기 위한 검수 전용 방향 값 두 곳만 바꾼다."""
import copy
import json
import shutil
import struct
import sys
from pathlib import Path

from dat_container import DatFile, sha
from qa_visibility_fixture import verify
from validate_candidate import differences
from validate_qa_visibility import metadata

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'working_private/THE_HORDE_OF_GORAK'
SOURCE = WORK / 'qa_fixture_03'
OUT = WORK / 'qa_fixture_04'
TARGET = 'top/037:3333/008:333d'


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def build():
    assert not OUT.exists()
    before = (SOURCE / 'THOG.qa-only.dat').read_bytes()
    assert sha(before) == 'e6ceb3944576995f074bd03382167380de4a812241986ebcd323ed09d2168ee8'
    dat = DatFile(before)
    changes = [{'target': TARGET, 'offset': offset, 'source': 256, 'expected': 1, 'format': '<I',
                'field': f'frame10.event{event}.action0.object874.directionMask',
                'reason': '검수용 도감 용 아이콘을 잠금 방향8 대신 방향0으로 두어 기존 툴팁302 조건을 만족'}
               for event, offset in [(178, 56978), (179, 57046)]]
    for change in changes:
        dat.patch(TARGET, change['offset'], struct.pack('<I', 256), struct.pack('<I', 1))
    after = dat.serialize()
    chunks = verify(DatFile(before), after, changes)
    OUT.mkdir()
    (OUT / 'THOG.qa-only.dat').write_bytes(after)
    shutil.copytree(SOURCE / 'profiles', OUT / 'profiles')
    profiles = []
    for path in sorted((SOURCE / 'profiles').rglob('*')):
        if path.is_file():
            relative = path.relative_to(SOURCE)
            assert path.read_bytes() == (OUT / relative).read_bytes()
            profiles.append({'path': str(relative), 'sha256': sha(path.read_bytes())})
    save(OUT / 'fixture_report.json', {'qa_only': True, 'status': 'PASS', 'runtime_status': 'NOT_RUN',
         'source_fixture': str(SOURCE), 'source_sha256': sha(before), 'qa_dat_sha256': sha(after),
         'changes': changes, 'changed_decoded_chunks': chunks, 'unchanged_profiles': profiles,
         'tool_sha256': sha(Path(__file__).read_bytes())})
    (OUT / 'QA_ROUTE.md').write_text('# 도감 용 본문 검수 전용 사본04\n\n배포하지 않습니다. fixture03에서 방향 마스크 두 곳만 256→1로 바꿨습니다. 원본의 성 번호 조건·도감 이름·본문·글꼴은 그대로입니다. 전체 건물 저장을 새 격리 profile에 복사하고 이어하기로 진입한 뒤 ESC→도감 탭→용 아이콘을 가리킵니다. 기존 fixture03의 DEV 전체 표시와9개 저장 프로필을 유지합니다. 픽셀 검수 사본은 별도의 fixture03/pixel_scene19를 사용합니다.\n\n이 사본은 원본 도감 잠금 논리를 통과하기 위한 검수 보조이며 정상 게임에서 용 도감에 접근 가능하다는 근거로 보고하지 않습니다. 제작기는 게임을 실행하거나 기존 QA 폴더를 수정하지 않았습니다.\n', encoding='utf-8')
    assert (SOURCE / 'THOG.qa-only.dat').read_bytes() == before
    print(json.dumps({'status': 'PASS', 'qa_dat_sha256': sha(after)}))


def validate():
    expected = json.loads((SOURCE / 'nebula_dev/package.json').read_text(encoding='utf-8'))
    actual = json.loads((OUT / 'nebula/package.json').read_text(encoding='utf-8'))
    for event in (178, 179):
        expected['Frames'][10]['FrameEvents']['Events'][event]['Actions'][0]['Parameters'][0]['Data']['Value'] = 1
    data = (OUT / 'THOG.qa-only.dat').read_bytes()
    metadata(expected, DatFile(data), 10, 0x333D, 'FrameEvents')
    diff = list(differences(expected, actual))
    assert not diff, diff
    report = {'status': 'PASS', 'runtime_status': 'NOT_RUN', 'qa_only': True,
              'qa_dat_sha256': sha(data), 'semantic_unexpected_changes': 0,
              'source_package_sha256': sha((SOURCE / 'nebula_dev/package.json').read_bytes()),
              'candidate_package_sha256': sha((OUT / 'nebula/package.json').read_bytes()),
              'tool_sha256': sha(Path(__file__).read_bytes())}
    save(OUT / 'independent_validation.json', report)
    print(json.dumps(report))


if __name__ == '__main__':
    validate() if '--validate' in sys.argv else build()
