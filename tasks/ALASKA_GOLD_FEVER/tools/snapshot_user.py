"""사용자 저장·Steam 클라우드 관련 파일을 읽기 전용으로 비교합니다."""
from pathlib import Path
import hashlib
import json
import argparse
import datetime
from extract_localization import ROOT, save

WORK = ROOT / 'working_private/ALASKA_GOLD_FEVER/risk_runtime'

def snapshot():
    paths = [Path('C:/Users/PC/AppData/LocalLow/Baked Games/Alaska Gold Fever')]
    steam = Path('D:/steam/userdata')
    if steam.exists():
        paths += list(steam.glob('*/1674200'))
    result = []
    for directory in paths:
        files = []
        for path in sorted(directory.rglob('*')):
            if path.is_file():
                files.append({'path':path.relative_to(directory).as_posix(),'size':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        result.append({'root':str(directory),'exists':directory.exists(),'files':files})
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase',choices=['before','after'])
    args = parser.parse_args()
    value = {'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'roots':snapshot()}
    if args.phase == 'after':
        before = json.loads((WORK / 'user_before.json').read_text('utf-8'))
        value['unchanged'] = before['roots'] == value['roots']
    save(WORK / ('user_' + args.phase + '.json'), value)
    print('사용자 파일',sum(len(r['files']) for r in value['roots']),'개',value.get('unchanged','기준선'))
