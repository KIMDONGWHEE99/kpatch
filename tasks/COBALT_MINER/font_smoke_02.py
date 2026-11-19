"""메뉴 초기화 이벤트가 시험 문구를 덮어쓰는 문제를 별도 후보에서 수정합니다."""
import json
from pathlib import Path

from font_builder import ROOT, DatFile, sha, write_new

BASE = ROOT / 'working_private/COBALT_MINER/font_smoke_01'
OUT = ROOT / 'working_private/COBALT_MINER/font_smoke_02'
TARGET = 'top/031:3333/008:333d'

def main():
    source = BASE / 'COBALT MINER.dat'
    assert sha(source.read_bytes()) == '5babe519485bdc1b05054af440b14c1487e06feaf6c8afb12752978ad0988967'
    dat = DatFile.load(source)
    dat.patch_utf16(TARGET, 3206, 'NEW GAME', '새 게임', slot_bytes=18)
    output = dat.serialize()
    reread = DatFile(output)
    assert reread.serialize() == output and reread.integrity_summary()['status'] == 'PASS'
    write_new(OUT / 'COBALT MINER.dat', output)
    report = {'base_candidate_sha256': sha(source.read_bytes()), 'candidate_sha256': sha(output),
              'builder_sha256': sha(Path(__file__).read_bytes()),
              'change': {'target': TARGET, 'offset': 3206, 'slot_bytes': 18, 'source': 'NEW GAME', 'translation': '새 게임',
                         'semantic_location': 'frame:2/event:16/Actions:0/parameter:0/expression:0',
                         'reason': '첫 메뉴의 언어 초기화 이벤트가 객체 기본 문구를 덮어쓰므로 같은 기대 번역 적용'},
              'scope': 'smoke_01 글꼴·객체 변경과 이 이벤트 한 문구. 창·전체화면 설정은 원본대로 유지.',
              'runtime_qa': 'NOT_RUN', 'integrity': reread.integrity_summary()}
    write_new(OUT / 'build_report.json', (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({'path': str(OUT / 'COBALT MINER.dat'), 'sha256': sha(output)}))

if __name__ == '__main__':
    main()
