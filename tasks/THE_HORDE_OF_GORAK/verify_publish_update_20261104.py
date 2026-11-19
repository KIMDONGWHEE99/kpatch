"""인증 없이 받은 공개 파일과 게시 대상으로 고정한 파일을 대조합니다."""
import concurrent.futures
import hashlib
import json
import subprocess
import urllib.request
from publish_update_20261104 import REPO
from update_20261104 import WORK, sha, save


def main():
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    changed = ['README.md', 'SHA256SUMS.txt', 'downloads/THE_HORDE_OF_GORAK_KOREAN_PATCH_1.0.1_r1.zip', 'releases/v1.0.1.md', 'releases/v1.0.1-verification.json']
    manifest = json.loads((WORK / 'publication_manifest.json').read_text(encoding='utf-8'))
    for r in manifest['files']:
        assert sha(REPO / r['path']) == r['sha256']
    # Git의 텍스트 줄바꿈 정규화가 적용된 실제 커밋 내용과 비교합니다.
    committed = {r['path']: subprocess.check_output(['git', 'show', commit + ':' + r['path']], cwd=REPO) for r in manifest['files']}
    def check(name):
        ref = 'main' if name.endswith('.zip') else commit
        url = f'https://raw.githubusercontent.com/KIMDONGWHEE99/the-horde-of-gorak-korean-patch/{ref}/{name}'
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
            status = response.status
        digest = hashlib.sha256(data).hexdigest()
        assert status == 200 and digest == hashlib.sha256(committed[name]).hexdigest(), name
        return {'path': name, 'bytes': len(data), 'sha256': digest, 'status': 'PASS'}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(check, changed))
    tree_url = f'https://api.github.com/repos/KIMDONGWHEE99/the-horde-of-gorak-korean-patch/git/trees/{commit}?recursive=1'
    with urllib.request.urlopen(tree_url, timeout=60) as response:
        tree = json.load(response)
    assert not tree['truncated']
    blobs = {r['path']: r['sha'] for r in tree['tree'] if r['type'] == 'blob'}
    assert set(blobs) == {r['path'] for r in manifest['files']}
    for path, digest in blobs.items():
        data = committed[path]
        assert hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest() == digest, path
    result = {'status': 'PASS', 'repository': 'https://github.com/KIMDONGWHEE99/the-horde-of-gorak-korean-patch',
              'commit': commit, 'public_files': len(blobs), 'anonymous_downloads': results,
              'manifest_sha256': sha(WORK / 'publication_manifest.json')}
    save(WORK / 'publication_verified.json', result)
    print(json.dumps({'status': result['status'], 'commit': commit, 'public_files': len(blobs), 'anonymous_downloads': len(results)}))


if __name__ == '__main__':
    main()
