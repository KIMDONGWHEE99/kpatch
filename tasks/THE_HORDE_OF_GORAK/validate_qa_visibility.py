"""독립 Nebula 재추출 전체 트리를 명시한 검수 변경과 대조한다."""
import copy
import json
from pathlib import Path

from dat_container import DatFile, sha
from validate_candidate import differences

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'working_private/THE_HORDE_OF_GORAK'
OUT = WORK / 'qa_fixture_03'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def metadata(expected, dat, frame_index, child_id, child_name):
    frame = [c for c in dat.chunks if c.chunk_id == 0x3333][frame_index]
    expected['Frames'][frame_index]['ChunkSize'] = len(frame.raw)
    expected['Frames'][frame_index][child_name]['ChunkSize'] = len(next(c for c in frame.children if c.chunk_id == child_id).raw)
    expected['Protection']['sha256'] = sha(dat.one(0x2242).decoded)


def main():
    baseline = load(WORK / 'validation_02/nebula_candidate/package.json')
    rows = []
    for name, relative in [('dev', 'THOG.qa-only.dat'), ('pixels', 'pixel_scene19/THOG.qa-only.dat')]:
        actual = load(OUT / f'nebula_{name}/package.json')
        data = (OUT / relative).read_bytes()
        dat = DatFile(data)
        assert dat.integrity_summary()['status'] == 'PASS'
        expected = copy.deepcopy(baseline)
        if name == 'dev':
            expected['FrameItems']['Items']['510']['Properties']['NewObjectFlags']['Value'] = 12
            expected['Frames'][10]['FrameEvents']['Events'][477]['Actions'][0]['Num'] = 6
            expected['Frames'][10]['FrameEvents']['Events'][489]['Actions'][0]['Parameters'][0]['Data']['Value'] = 1
            metadata(expected, dat, 10, 0x333D, 'FrameEvents')
        else:
            for handle in (489, 799):
                expected['FrameItems']['Items'][str(handle)]['Properties']['NewObjectFlags']['Value'] = 8
            instances = expected['Frames'][19]['FrameInstances']['Instances']
            for i, (frame, obj, x, y) in enumerate([(10, 818, 320, 300), (10, 489, 640, 300),
                                                  (10, 799, 960, 300), (9, 222, 543, 500)]):
                matches = [item for item in baseline['Frames'][frame]['FrameInstances']['Instances'] if item['ObjectInfo'] == obj]
                assert len(matches) == 1
                item = copy.deepcopy(matches[0])
                item.update(Handle=100+i, PositionX=x, PositionY=y, Layer=1)
                instances.append(item)
            metadata(expected, dat, 19, 0x3338, 'FrameInstances')
        diff = list(differences(expected, actual))
        assert not diff, diff
        # 재추출 이미지 내용 지문도 원래 후보와 동일해야 한다.
        assert actual['ImageBank'] == baseline['ImageBank']
        rows.append({'name': name, 'dat_sha256': sha(data), 'status': 'PASS',
                     'expected_tree_unexpected_differences': len(diff), 'image_bank_unchanged': True,
                     'package_sha256': sha((OUT / f'nebula_{name}/package.json').read_bytes())})
    report = {'status': 'PASS', 'runtime_status': 'NOT_RUN', 'qa_only': True,
              'baseline_package_sha256': sha((WORK / 'validation_02/nebula_candidate/package.json').read_bytes()),
              'tool_sha256': sha(Path(__file__).read_bytes()), 'results': rows}
    (OUT / 'independent_validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
