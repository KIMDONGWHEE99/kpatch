"""이미지 구조·허용 경계 검사기가 알려진 손상을 실제로 거부하는지 확인합니다."""
import json
import struct
import unittest
from pathlib import Path

from image_builder import DatFile, ImageBank, ROOT, SOURCE, sha, verify_replacement

CANDIDATE = ROOT / 'build_candidate/COBALT_MINER/media_smoke_01/COBALT MINER.dat'
CANDIDATE_12 = ROOT / 'build_candidate/COBALT_MINER/media_smoke_02/COBALT MINER.dat'
MANIFEST_12 = ROOT / 'working_private/COBALT_MINER/media_ko_02/manifest.json'


class ImageBoundaryTests(unittest.TestCase):
    def test_valid_candidate(self):
        self.assertEqual(len(verify_replacement(DatFile.load(SOURCE), DatFile.load(CANDIDATE))), 11)

    def test_valid_candidate_12(self):
        self.assertEqual(len(verify_replacement(DatFile.load(SOURCE), DatFile.load(CANDIDATE_12), MANIFEST_12)), 12)

    def test_shifted_image_offset(self):
        dat = DatFile.load(CANDIDATE)
        bank = ImageBank(dat)
        table = bytearray(dat.one(0x5555).decoded)
        record = bank.records[0]
        struct.pack_into('<I', table, record.handle * 4, record.offset + 261)
        dat.one(0x5555).decoded = bytes(table)
        with self.assertRaisesRegex(ValueError, '위치표'):
            ImageBank(dat)

    def test_non_target_record_change(self):
        dat = DatFile.load(CANDIDATE)
        bank = ImageBank(dat)
        record = bank.by_handle[1123]
        body = bytearray(record.body)
        body[32] ^= 1
        record.replacement = bytes(body)
        bank.apply()
        with self.assertRaisesRegex(ValueError, '비대상'):
            verify_replacement(DatFile.load(SOURCE), DatFile(dat.serialize()))

    def test_wrong_target_pixel(self):
        dat = DatFile.load(CANDIDATE)
        bank = ImageBank(dat)
        record = bank.by_handle[1374]
        body = bytearray(record.body)
        body[32] ^= 1
        record.replacement = bytes(body)
        bank.apply()
        with self.assertRaisesRegex(ValueError, '픽셀 불일치'):
            verify_replacement(DatFile.load(SOURCE), DatFile(dat.serialize()))

    def test_missing_replacement(self):
        with self.assertRaisesRegex(ValueError, '변경 이미지 집합'):
            verify_replacement(DatFile.load(SOURCE), DatFile.load(SOURCE))


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ImageBoundaryTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'status': 'PASS' if result.wasSuccessful() else 'FAIL', 'tests_run': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors), 'test_sha256': sha(Path(__file__).read_bytes()),
              'builder_sha256': sha((ROOT / 'tasks/COBALT_MINER/image_builder.py').read_bytes()),
              'candidate_sha256': sha(CANDIDATE.read_bytes()),
              'cases': ['정상 후보', '위치표 1바이트 이동', '비대상 이미지 변조', '교체 대상 잘못된 픽셀', '교체 누락']}
    report.update({'candidate_12_sha256': sha(CANDIDATE_12.read_bytes()), 'manifest_12_sha256': sha(MANIFEST_12.read_bytes())})
    report['cases'].append('정상 12장 후보')
    (CANDIDATE_12.parent / 'image_boundary_test_results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
